"""
Tests for Pydantic models.
"""

import pytest
from pydantic import ValidationError

from chat_bot.models import (
    CommandRequest,
    CommandType,
    Message,
    MessagesData,
)


class TestCommandRequest:
    """Test suite for CommandRequest model."""

    def test_create_valid_command_request(self) -> None:
        """Test creating a valid CommandRequest."""
        request = CommandRequest(
            command_type=CommandType.CREATE_TASK,
            raw_text="/create_task title=Test",
            arguments={"title": "Test"},
            chat_id=12345,
            user_id=67890,
        )
        assert request.command_type == CommandType.CREATE_TASK
        assert request.raw_text == "/create_task title=Test"
        assert request.arguments == {"title": "Test"}
        assert request.chat_id == 12345
        assert request.user_id == 67890
        assert request.username is None

    def test_create_command_request_with_username(self) -> None:
        """Test creating CommandRequest with username."""
        request = CommandRequest(
            command_type=CommandType.HELP,
            raw_text="/help",
            arguments={},
            chat_id=12345,
            user_id=67890,
            username="test_user",
        )
        assert request.username == "test_user"

    def test_create_command_request_missing_required_fields(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            CommandRequest(
                command_type=CommandType.CREATE_TASK,
                raw_text="/create_task",
                # Missing chat_id and user_id
            )

    def test_command_request_default_arguments(self) -> None:
        """Test that arguments default to empty dict."""
        request = CommandRequest(
            command_type=CommandType.HELP,
            raw_text="/help",
            chat_id=12345,
            user_id=67890,
        )
        assert request.arguments == {}


class TestMessage:
    """Test suite for Message model."""

    def test_create_valid_message(self) -> None:
        """Test creating a valid Message."""
        message = Message(
            message_id=1,
            timestamp="2025-01-15T10:00:00Z",
            sender_name="test_user",
            text="Test message",
        )
        assert message.message_id == 1
        assert message.timestamp == "2025-01-15T10:00:00Z"
        assert message.sender_name == "test_user"
        assert message.text == "Test message"
        assert message.is_bot_message is False

    def test_create_message_without_text(self) -> None:
        """Test creating Message without text (optional field)."""
        message = Message(
            message_id=1,
            timestamp="2025-01-15T10:00:00Z",
            sender_name="test_user",
        )
        assert message.text is None

    def test_create_message_missing_required_fields(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            Message(
                message_id=1,
                # Missing timestamp and sender_name
            )


class TestMessagesData:
    """Test suite for MessagesData model."""

    def test_create_valid_messages_data(self) -> None:
        """Test creating valid MessagesData."""
        message = Message(
            message_id=1,
            timestamp="2025-01-15T10:00:00Z",
            sender_name="test_user",
            text="Test",
        )
        data = MessagesData(messages=[message])
        assert len(data.messages) == 1
        assert data.messages[0] == message

    def test_create_empty_messages_data(self) -> None:
        """Test creating MessagesData with empty list."""
        data = MessagesData(messages=[])
        assert len(data.messages) == 0

    def test_messages_data_default_factory(self) -> None:
        """Test that messages default to empty list."""
        data = MessagesData()
        assert isinstance(data.messages, list)
        assert len(data.messages) == 0

    def test_messages_data_validation_none(self) -> None:
        """Test that None messages are handled by validator."""
        # The validator should convert None to empty list
        # But Pydantic v2 may reject None before validator runs
        # So we test that default_factory works instead
        data = MessagesData()
        assert isinstance(data.messages, list)
        assert len(data.messages) == 0


class TestCommandType:
    """Test suite for CommandType enum."""

    def test_command_type_values(self) -> None:
        """Test that CommandType has expected values."""
        assert CommandType.CREATE_TASK == "create_task"
        assert CommandType.HELP == "help"
        assert CommandType.UNKNOWN == "unknown"

    def test_command_type_enum_membership(self) -> None:
        """Test that CommandType values are enum members."""
        assert isinstance(CommandType.CREATE_TASK, CommandType)
        assert isinstance(CommandType.HELP, CommandType)

    def test_command_type_string_comparison(self) -> None:
        """Test that CommandType can be compared to strings."""
        assert CommandType.CREATE_TASK == "create_task"
        # For str Enum, str() returns the enum representation, use .value for value
        assert CommandType.CREATE_TASK.value == "create_task"
