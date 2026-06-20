"""Tests for MessageRouter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_bot.handlers.router import MessageRouter
from chat_bot.models import InteractionType, RouteResult


class TestMessageRouter:
    """Test suite for MessageRouter."""

    @pytest.fixture
    def router(self, mock_repository: MagicMock) -> MessageRouter:
        """Create a router without constructing the real assistant."""
        return MessageRouter(
            bot_username="kaitenbot",
            repository=mock_repository,
            assistant=None,
        )

    @staticmethod
    def make_message(text: str, chat_type: str = "group") -> MagicMock:
        """Create a minimal Telegram message mock."""
        message = MagicMock()
        message.text = text
        message.message_id = 10
        message.reply_to_message = None
        message.chat = MagicMock(id=123, type=chat_type)
        message.from_user = MagicMock(id=456, username="user")
        return message

    def test_private_chat_text_is_for_bot(self, router: MessageRouter) -> None:
        """Any regular private-chat text should be routed to the bot."""
        message = self.make_message("покажи мои задачи", chat_type="private")

        info = router.get_interaction_info(message)

        assert info.interaction_type == InteractionType.NEW_CONVERSATION
        assert router.is_bot_mentioned(message) is True

    def test_group_text_without_mention_is_not_for_bot(
        self, router: MessageRouter
    ) -> None:
        """Group-chat text still requires an explicit mention or reply."""
        message = self.make_message("покажи мои задачи", chat_type="group")

        info = router.get_interaction_info(message)

        assert info.interaction_type == InteractionType.NOT_FOR_BOT
        assert router.is_bot_mentioned(message) is False

    @pytest.mark.asyncio
    async def test_route_private_chat_text_to_mcp_handler(
        self,
        router: MessageRouter,
    ) -> None:
        """Private-chat text should invoke the natural-language handler."""
        message = self.make_message("покажи мои задачи", chat_type="private")
        update = MagicMock(message=message, channel_post=None)
        context = MagicMock()
        router.mcp_handler = MagicMock()
        router.mcp_handler.handle = AsyncMock(return_value="Готово")

        result = await router.route(update, context)

        assert result == "Готово"
        router.mcp_handler.handle.assert_awaited_once_with(
            text="покажи мои задачи",
            chat_id=123,
            user_id=456,
            username="user",
            current_message_id=10,
            is_reply=False,
            reply_to_message_id=None,
            repository=router.repository,
        )

    @pytest.mark.asyncio
    async def test_route_report_request_to_workload_report(
        self,
        router: MessageRouter,
    ) -> None:
        """Report requests should produce a document result without invoking MCP."""
        message = self.make_message("дай отчет по загруженности", chat_type="private")
        update = MagicMock(message=message, channel_post=None)
        context = MagicMock()
        router.mcp_handler = MagicMock()
        router.mcp_handler.handle = AsyncMock(return_value="MCP")
        router.workload_report_service.generate = AsyncMock(
            return_value=RouteResult(text="Готово")
        )

        result = await router.route(update, context)

        assert isinstance(result, RouteResult)
        assert result.text == "Готово"
        router.workload_report_service.generate.assert_awaited_once()
        router.mcp_handler.handle.assert_not_awaited()
