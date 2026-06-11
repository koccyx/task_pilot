"""
Tests for CommandHandler.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_bot.handlers.command_handler import CommandHandler
from chat_bot.models import CommandType


class TestCommandHandler:
    """Test suite for CommandHandler."""

    @pytest.fixture
    def handler(self, mock_repository: MagicMock) -> CommandHandler:
        """Create a CommandHandler instance for testing."""
        return CommandHandler(repository=mock_repository)

    @pytest.mark.asyncio
    async def test_handle_help_command(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling help command."""
        result = await handler.handle(
            text="/help", chat_id=123, user_id=456, username="test_user"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_handle_unknown_command(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling unknown command."""
        result = await handler.handle(
            text="/unknown_command", chat_id=123, user_id=456, username="test_user"
        )
        assert "Неизвестная команда" in result or "unknown" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_create_task_without_mcp(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling create_task when MCP is not available."""
        with patch.object(
            handler, "_ensure_mcp_client", AsyncMock(return_value=False)
        ):
            result = await handler.handle(
                text='/create_task title="Test"',
                chat_id=123,
                user_id=456,
                username="test_user",
            )
            assert "MCP сервер недоступен" in result or "недоступен" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_list_tasks_without_mcp(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling list_tasks when MCP is not available."""
        with patch.object(
            handler, "_ensure_mcp_client", AsyncMock(return_value=False)
        ):
            result = await handler.handle(
                text="/list_tasks", chat_id=123, user_id=456, username="test_user"
            )
            assert "MCP сервер недоступен" in result or "недоступен" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_tasks_from_chat(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling tasks_from_chat command."""
        mock_repository.read_recent_messages = AsyncMock(
            return_value=MagicMock(messages=[])
        )

        result = await handler.handle(
            text="/tasks_from_chat days=1", chat_id=123, user_id=456
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_handle_tasks_from_chat_with_messages(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling tasks_from_chat with messages."""
        from chat_bot.models import Message, MessagesData

        # Create a valid message
        message = Message(
            message_id=1,
            timestamp="2025-01-15T10:00:00Z",
            sender_name="test_user",
            text="Test message",
        )

        mock_repository.read_recent_messages = AsyncMock(
            return_value=MessagesData(messages=[message])
        )

        result = await handler.handle(
            text="/tasks_from_chat days=1", chat_id=123, user_id=456
        )
        assert isinstance(result, str)
        assert "сообщений" in result.lower() or "messages" in result.lower()

    @pytest.mark.asyncio
    async def test_ensure_mcp_client_success(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test MCP client initialization success."""
        with patch.dict(
            os.environ, {"MCP_SERVER_URL": "http://localhost:8000"}, clear=False
        ):
            with patch(
                "chat_bot.handlers.command_handler.KaitenMCPClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.initialize = AsyncMock()
                mock_client_class.return_value = mock_client

                result = await handler._ensure_mcp_client()
                assert result is True
                assert handler.mcp_client is not None

    @pytest.mark.asyncio
    async def test_ensure_mcp_client_failure(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test MCP client initialization failure."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "chat_bot.handlers.command_handler.KaitenMCPClient"
            ) as mock_client_class:
                mock_client_class.side_effect = Exception("Connection failed")

                result = await handler._ensure_mcp_client()
                assert result is False

    @pytest.mark.asyncio
    async def test_call_mcp_tool_success(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test calling MCP tool successfully."""
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.content = [MagicMock(type="text", text="Success")]
        mock_client.call_tool = AsyncMock(return_value=mock_result)

        handler.mcp_client = mock_client
        handler._mcp_initialized = True

        result = await handler._call_mcp_tool("test_tool", {"arg": "value"})
        assert result == "Success"
        mock_client.call_tool.assert_called_once_with("test_tool", {"arg": "value"})

    @pytest.mark.asyncio
    async def test_call_mcp_tool_no_client(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test calling MCP tool when client is not initialized."""
        handler.mcp_client = None

        with pytest.raises(RuntimeError, match="MCP client not initialized"):
            await handler._call_mcp_tool("test_tool", {})

    @pytest.mark.asyncio
    async def test_handle_list_users_without_mcp(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling list_users when MCP is not available."""
        with patch.object(
            handler, "_ensure_mcp_client", AsyncMock(return_value=False)
        ):
            result = await handler.handle(
                text="/list_users", chat_id=123, user_id=456, username="test_user"
            )
            assert "MCP сервер недоступен" in result or "недоступен" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_move_card_missing_card_id(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling move_card without card_id."""
        # Mock MCP client to be available
        with patch.dict(
            os.environ, {"MCP_SERVER_URL": "http://localhost:8000"}, clear=False
        ):
            with patch(
                "chat_bot.handlers.command_handler.KaitenMCPClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.initialize = AsyncMock()
                mock_client_class.return_value = mock_client
                handler.mcp_client = mock_client
                handler._mcp_initialized = True

                result = await handler.handle(
                    text="/move_card", chat_id=123, user_id=456, username="test_user"
                )
                assert "card_id" in result.lower() or "карточки" in result.lower()

    @pytest.mark.asyncio
    async def test_handle_add_comment_missing_params(
        self, handler: CommandHandler, mock_repository: MagicMock
    ) -> None:
        """Test handling add_comment with missing parameters."""
        # Mock MCP client to be available
        with patch.dict(
            os.environ, {"MCP_SERVER_URL": "http://localhost:8000"}, clear=False
        ):
            with patch(
                "chat_bot.handlers.command_handler.KaitenMCPClient"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.initialize = AsyncMock()
                mock_client_class.return_value = mock_client
                handler.mcp_client = mock_client
                handler._mcp_initialized = True

                result = await handler.handle(
                    text="/add_comment", chat_id=123, user_id=456, username="test_user"
                )
                assert "card_id" in result.lower() or "комментария" in result.lower()
