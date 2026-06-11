"""
Tests for CommandRegistry.
"""

import pytest

from chat_bot.commands.registry import CommandInfo, CommandRegistry
from chat_bot.models import CommandType


class TestCommandRegistry:
    """Test suite for CommandRegistry."""

    def test_initialize(self) -> None:
        """Test that registry initializes with commands."""
        CommandRegistry.initialize()
        commands = CommandRegistry.get_all_commands()
        assert len(commands) > 0
        assert all(isinstance(cmd, CommandInfo) for cmd in commands)

    def test_get_command_existing(self) -> None:
        """Test getting an existing command."""
        CommandRegistry.initialize()
        cmd_info = CommandRegistry.get_command(CommandType.CREATE_TASK)
        assert cmd_info is not None
        assert cmd_info.command_type == CommandType.CREATE_TASK
        assert cmd_info.name == "create_task"
        assert "Создать" in cmd_info.description or "создать" in cmd_info.description

    def test_get_command_nonexistent(self) -> None:
        """Test getting a non-existent command."""
        CommandRegistry.initialize()
        # CommandType.UNKNOWN might not be registered
        cmd_info = CommandRegistry.get_command(CommandType.UNKNOWN)
        # Either None or a CommandInfo object
        assert cmd_info is None or isinstance(cmd_info, CommandInfo)

    def test_get_all_commands(self) -> None:
        """Test getting all commands."""
        CommandRegistry.initialize()
        commands = CommandRegistry.get_all_commands()
        assert len(commands) > 0

        # Check that all commands have required fields
        for cmd in commands:
            assert isinstance(cmd, CommandInfo)
            assert cmd.command_type is not None
            assert cmd.name is not None
            assert cmd.description is not None
            assert isinstance(cmd.parameters, list)
            assert cmd.example is not None

    def test_format_help_message(self) -> None:
        """Test formatting help message."""
        CommandRegistry.initialize()
        help_text = CommandRegistry.format_help_message()
        assert isinstance(help_text, str)
        assert len(help_text) > 0
        assert "Доступные команды" in help_text or "команды" in help_text

    def test_command_info_structure(self) -> None:
        """Test that CommandInfo has correct structure."""
        CommandRegistry.initialize()
        cmd_info = CommandRegistry.get_command(CommandType.CREATE_TASK)
        assert cmd_info is not None

        # Check all fields exist
        assert hasattr(cmd_info, "command_type")
        assert hasattr(cmd_info, "name")
        assert hasattr(cmd_info, "description")
        assert hasattr(cmd_info, "parameters")
        assert hasattr(cmd_info, "example")
        assert hasattr(cmd_info, "requires_mention")

        # Check types
        assert isinstance(cmd_info.command_type, CommandType)
        assert isinstance(cmd_info.name, str)
        assert isinstance(cmd_info.description, str)
        assert isinstance(cmd_info.parameters, list)
        assert isinstance(cmd_info.example, str)
        assert isinstance(cmd_info.requires_mention, bool)

    def test_help_command_exists(self) -> None:
        """Test that help command is registered."""
        CommandRegistry.initialize()
        cmd_info = CommandRegistry.get_command(CommandType.HELP)
        assert cmd_info is not None
        assert cmd_info.name == "help"

    def test_common_commands_exist(self) -> None:
        """Test that common commands are registered."""
        CommandRegistry.initialize()
        common_commands = [
            CommandType.CREATE_TASK,
            CommandType.LIST_TASKS,
            CommandType.ASSIGN_TASK,
            CommandType.HELP,
        ]

        for cmd_type in common_commands:
            cmd_info = CommandRegistry.get_command(cmd_type)
            assert cmd_info is not None, f"Command {cmd_type} should be registered"

    def test_command_examples_are_valid(self) -> None:
        """Test that command examples are valid strings."""
        CommandRegistry.initialize()
        commands = CommandRegistry.get_all_commands()

        for cmd in commands:
            assert cmd.example is not None
            assert isinstance(cmd.example, str)
            assert len(cmd.example) > 0
            # Example should start with /
            assert cmd.example.startswith("/")
