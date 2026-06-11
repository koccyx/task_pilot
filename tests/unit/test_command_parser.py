"""
Tests for CommandParser.
"""

import pytest

from chat_bot.commands.parser import CommandParser
from chat_bot.models import CommandType


class TestCommandParser:
    """Test suite for CommandParser."""

    def test_is_command_with_slash(self) -> None:
        """Test that text starting with / is recognized as command."""
        assert CommandParser.is_command("/create_task") is True
        assert CommandParser.is_command("/help") is True
        assert CommandParser.is_command("  /create_task  ") is True

    def test_is_command_without_slash(self) -> None:
        """Test that text without / is not recognized as command."""
        assert CommandParser.is_command("create_task") is False
        assert CommandParser.is_command("help") is False
        assert CommandParser.is_command("") is False

    def test_parse_simple_command(self) -> None:
        """Test parsing a simple command without arguments."""
        result = CommandParser.parse("/help", chat_id=123, user_id=456)
        assert result.command_type == CommandType.HELP
        assert result.arguments == {}
        assert result.chat_id == 123
        assert result.user_id == 456

    def test_parse_command_with_single_argument(self) -> None:
        """Test parsing command with single argument."""
        result = CommandParser.parse(
            '/create_task title="Test Task"', chat_id=123, user_id=456
        )
        assert result.command_type == CommandType.CREATE_TASK
        assert result.arguments == {"title": "Test Task"}
        assert result.raw_text == '/create_task title="Test Task"'

    def test_parse_command_with_multiple_arguments(self) -> None:
        """Test parsing command with multiple arguments."""
        result = CommandParser.parse(
            '/create_task title="Test" assignee=John due=2025-12-31',
            chat_id=123,
            user_id=456,
        )
        assert result.command_type == CommandType.CREATE_TASK
        assert result.arguments == {
            "title": "Test",
            "assignee": "John",
            "due": "2025-12-31",
        }

    def test_parse_command_with_quoted_values(self) -> None:
        """Test parsing command with quoted values."""
        result = CommandParser.parse(
            '/create_task title="Test Task" description="Long description"',
            chat_id=123,
            user_id=456,
        )
        assert result.arguments == {
            "title": "Test Task",
            "description": "Long description",
        }

    def test_parse_command_with_single_quotes(self) -> None:
        """Test parsing command with single-quoted values."""
        result = CommandParser.parse(
            "/create_task title='Test Task'", chat_id=123, user_id=456
        )
        assert result.arguments == {"title": "Test Task"}

    def test_parse_command_with_integer_values(self) -> None:
        """Test parsing command with integer values."""
        result = CommandParser.parse(
            "/list_tasks board_id=123 limit=50", chat_id=123, user_id=456
        )
        assert result.arguments == {"board_id": 123, "limit": 50}
        assert isinstance(result.arguments["board_id"], int)
        assert isinstance(result.arguments["limit"], int)

    def test_parse_command_with_float_values(self) -> None:
        """Test parsing command with float values."""
        result = CommandParser.parse(
            "/some_command value=3.14", chat_id=123, user_id=456
        )
        assert result.arguments == {"value": 3.14}
        assert isinstance(result.arguments["value"], float)

    def test_parse_command_with_boolean_values(self) -> None:
        """Test parsing command with boolean values."""
        result = CommandParser.parse(
            "/some_command enabled=true disabled=false", chat_id=123, user_id=456
        )
        assert result.arguments == {"enabled": True, "disabled": False}

    def test_parse_unknown_command(self) -> None:
        """Test parsing unknown command."""
        result = CommandParser.parse("/unknown_command", chat_id=123, user_id=456)
        assert result.command_type == CommandType.UNKNOWN
        assert result.arguments == {}

    def test_parse_command_with_bot_mention(self) -> None:
        """Test parsing command with @botname mention."""
        result = CommandParser.parse(
            "/create_task@mybot title=Test", chat_id=123, user_id=456
        )
        assert result.command_type == CommandType.CREATE_TASK
        assert result.arguments == {"title": "Test"}

    def test_parse_command_with_username(self) -> None:
        """Test parsing command with username."""
        result = CommandParser.parse(
            "/help", chat_id=123, user_id=456, username="test_user"
        )
        assert result.username == "test_user"

    def test_parse_empty_command(self) -> None:
        """Test parsing empty command."""
        result = CommandParser.parse("/", chat_id=123, user_id=456)
        assert result.command_type == CommandType.UNKNOWN
        assert result.arguments == {}

    def test_parse_command_with_spaces_in_quoted_value(self) -> None:
        """Test parsing command with spaces in quoted value."""
        result = CommandParser.parse(
            '/create_task title="Test Task With Spaces"', chat_id=123, user_id=456
        )
        assert result.arguments == {"title": "Test Task With Spaces"}

    def test_parse_command_with_special_characters(self) -> None:
        """Test parsing command with special characters in values."""
        result = CommandParser.parse(
            '/create_task title="Test: Task (v1.0)"', chat_id=123, user_id=456
        )
        assert result.arguments == {"title": "Test: Task (v1.0)"}

    def test_parse_command_case_insensitive(self) -> None:
        """Test that command names are case-insensitive."""
        result = CommandParser.parse("/CREATE_TASK title=Test", chat_id=123, user_id=456)
        assert result.command_type == CommandType.CREATE_TASK

    def test_parse_command_with_no_arguments(self) -> None:
        """Test parsing command with no arguments after command name."""
        result = CommandParser.parse("/list_tasks", chat_id=123, user_id=456)
        assert result.command_type == CommandType.LIST_TASKS
        assert result.arguments == {}

    def test_parse_command_with_mixed_argument_types(self) -> None:
        """Test parsing command with mixed argument types."""
        result = CommandParser.parse(
            '/create_task title="Test" board_id=123 limit=50 enabled=true',
            chat_id=123,
            user_id=456,
        )
        assert result.arguments == {
            "title": "Test",
            "board_id": 123,
            "limit": 50,
            "enabled": True,
        }
        assert isinstance(result.arguments["title"], str)
        assert isinstance(result.arguments["board_id"], int)
        assert isinstance(result.arguments["limit"], int)
        assert isinstance(result.arguments["enabled"], bool)
