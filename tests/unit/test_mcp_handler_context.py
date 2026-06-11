"""Tests for MCP chat context loading."""

import os
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch

import pytest

from chat_bot.handlers.mcp_handler import MCPHandler
from chat_bot.models import Message


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
    async def test_load_chat_context_keeps_chain_and_fills_from_recent(self) -> None:
        """Reply chain should be kept in full and filled with the latest recent messages."""
        assistant = MagicMock()
        handler = MCPHandler(assistant=assistant)
        repository = MagicMock()

        recent_messages = [
            make_message(1, "2025-01-01T10:00:00", "first"),
            make_message(2, "2025-01-01T10:01:00", "second"),
            make_message(3, "2025-01-01T10:02:00", "third"),
            make_message(4, "2025-01-01T10:03:00", "fourth"),
            make_message(5, "2025-01-01T10:04:00", "current"),
        ]
        reply_chain = [
            make_message(1, "2025-01-01T10:00:00", "first"),
            make_message(10, "2025-01-01T09:58:00", "reply root"),
            make_message(11, "2025-01-01T09:59:00", "reply child"),
        ]

        repository.read_recent_messages = AsyncMock(
            return_value=MagicMock(messages=recent_messages)
        )
        repository.get_conversation_chain = AsyncMock(return_value=reply_chain)

        with patch.dict(os.environ, {"CHAT_CONTEXT_MESSAGE_LIMIT": "4"}):
            context = await handler._load_chat_context(
                repository=repository,
                chat_id=123,
                current_message_id=5,
                is_reply=True,
                reply_to_message_id=11,
            )

        assert context is not None
        assert [msg.message_id for msg in context] == [10, 11, 1, 4]

    @pytest.mark.asyncio
    async def test_load_chat_context_without_reply_returns_last_recent_messages(self) -> None:
        """Without a reply, context should be the last N recent messages only."""
        assistant = MagicMock()
        handler = MCPHandler(assistant=assistant)
        repository = MagicMock()

        recent_messages = [
            make_message(1, "2025-01-01T10:00:00", "first"),
            make_message(2, "2025-01-01T10:01:00", "second"),
            make_message(3, "2025-01-01T10:02:00", "third"),
            make_message(4, "2025-01-01T10:03:00", "fourth"),
            make_message(5, "2025-01-01T10:04:00", "current"),
        ]

        repository.read_recent_messages = AsyncMock(
            return_value=MagicMock(messages=recent_messages)
        )
        repository.get_conversation_chain = AsyncMock(return_value=[])

        with patch.dict(os.environ, {"CHAT_CONTEXT_MESSAGE_LIMIT": "3"}):
            context = await handler._load_chat_context(
                repository=repository,
                chat_id=123,
                current_message_id=5,
                is_reply=False,
                reply_to_message_id=None,
            )

        assert context is not None
        assert [msg.message_id for msg in context] == [2, 3, 4]

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
