"""Tests for MCP chat context loading."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_bot.handlers.mcp_handler import MCPHandler
from chat_bot.models import Message, UserProfile


def make_message(
    message_id: int,
    timestamp: str,
    text: str,
    reply_to_message_id: int | None = None,
) -> Message:
    """Create a minimal message fixture."""
    return Message(
        message_id=message_id,
        timestamp=timestamp,
        sender_name="user",
        text=text,
        reply_to_message_id=reply_to_message_id,
    )


class TestMCPHandlerContext:
    """Tests for merged chat context."""

    @pytest.mark.asyncio
    async def test_load_chat_context_returns_last_ten_messages(self) -> None:
        assistant = MagicMock()
        handler = MCPHandler(assistant=assistant)
        repository = MagicMock()

        recent_messages = [
            make_message(
                index,
                f"2025-01-01T10:{index:02d}:00",
                f"message {index}",
            )
            for index in range(1, 13)
        ]
        repository.read_recent_messages = AsyncMock(
            return_value=MagicMock(messages=recent_messages)
        )

        context = await handler._load_chat_context(
            repository=repository,
            chat_id=123,
            current_message_id=12,
            is_reply=True,
            reply_to_message_id=11,
        )

        assert context is not None
        assert [msg.message_id for msg in context] == list(range(2, 12))
        repository.read_recent_messages.assert_awaited_once_with(chat_id=123, limit=10)
        repository.get_conversation_chain.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_chat_context_returns_none_on_repository_error(self) -> None:
        assistant = MagicMock()
        handler = MCPHandler(assistant=assistant)
        repository = MagicMock()
        repository.read_recent_messages = AsyncMock(side_effect=RuntimeError("db down"))

        context = await handler._load_chat_context(
            repository=repository,
            chat_id=123,
            current_message_id=5,
            is_reply=False,
            reply_to_message_id=None,
        )

        assert context is None

    def test_deduplicate_messages_preserves_order_and_excludes_current(self) -> None:
        """Deduplication should keep chronological order and drop current message."""
        messages = [
            make_message(2, "2025-01-01T10:02:00", "second"),
            make_message(1, "2025-01-01T10:01:00", "first"),
            make_message(2, "2025-01-01T10:02:00", "second updated"),
            make_message(3, "2025-01-01T10:03:00", "current"),
        ]

        result = MCPHandler._deduplicate_messages(messages, current_message_id=3)

        assert [msg.message_id for msg in result] == [1, 2]
        assert result[1].text == "second updated"

    @pytest.mark.asyncio
    async def test_handle_uses_simple_task_agent_and_ten_message_context(self) -> None:
        assistant = MagicMock()
        handler = MCPHandler(assistant=assistant)
        handler._initialized = True
        handler._tools = [MagicMock(name="manage_cards")]
        handler._tools_cached_at = time.time()
        handler.task_agent.run = AsyncMock(return_value="Готово")
        repository = MagicMock()
        current_user = UserProfile(
            chat_id=123,
            telegram_user_id=456,
            telegram_username="stepan",
            telegram_display_name="Степан",
            introduced_name="Степан",
            kaiten_user_name="Stepan1922",
            kaiten_user_id=1056226,
        )
        repository.get_user_profile = AsyncMock(return_value=current_user)
        repository.list_user_profiles = AsyncMock(return_value=[current_user])
        repository.read_recent_messages = AsyncMock(return_value=MagicMock(messages=[]))

        result = await handler.handle(
            text="создай задачи по диалогу",
            chat_id=123,
            user_id=456,
            repository=repository,
        )

        assert result == "Готово"
        handler.task_agent.run.assert_awaited_once()
        assert handler.task_agent.run.await_args.kwargs["current_user"] == current_user
        repository.read_recent_messages.assert_awaited_once_with(
            chat_id=123,
            limit=10,
        )

    def test_select_task_agent_uses_light_agent_for_simple_request(self) -> None:
        assistant = MagicMock()
        assistant.config.light_model = "qwen3:8b"
        assistant.light_llm = MagicMock()
        assistant.routing_llm = assistant.light_llm
        assistant.llm = MagicMock()
        handler = MCPHandler(assistant=assistant)

        selected = handler._select_task_agent(
            text="покажи мои задачи",
            history=[],
        )

        assert handler.light_task_agent is not None
        assert selected is handler.light_task_agent

    def test_select_task_agent_keeps_main_agent_for_complex_request(self) -> None:
        assistant = MagicMock()
        assistant.config.light_model = "qwen3:8b"
        assistant.light_llm = MagicMock()
        assistant.routing_llm = assistant.light_llm
        assistant.llm = MagicMock()
        handler = MCPHandler(assistant=assistant)

        selected = handler._select_task_agent(
            text="создай задачи по диалогу и назначь ответственных",
            history=[],
        )

        assert selected is handler.task_agent
