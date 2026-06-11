"""
Pytest configuration and shared fixtures.
"""

import asyncio
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_bot.models import CommandRequest, CommandType, Message, MessagesData
from chat_bot.repository_base import BaseChatRepository


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create a mock repository for testing."""
    repo = MagicMock(spec=BaseChatRepository)
    repo.read_chat_messages = AsyncMock(return_value=MessagesData(messages=[]))
    repo.save_message = AsyncMock()
    repo.read_recent_messages = AsyncMock(return_value=MessagesData(messages=[]))
    repo.get_conversation_chain = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def sample_message() -> Message:
    """Create a sample message for testing."""
    return Message(
        message_id=1,
        timestamp="2025-01-15T10:00:00Z",
        sender_name="test_user",
        text="Test message",
    )


@pytest.fixture
def sample_messages_data(sample_message: Message) -> MessagesData:
    """Create sample messages data for testing."""
    return MessagesData(messages=[sample_message])


@pytest.fixture
def sample_command_request() -> CommandRequest:
    """Create a sample command request for testing."""
    return CommandRequest(
        command_type=CommandType.CREATE_TASK,
        raw_text="/create_task title=Test",
        arguments={"title": "Test"},
        chat_id=12345,
        user_id=67890,
        username="test_user",
    )
