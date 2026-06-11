"""
Slash command parser for extracting commands and arguments.
"""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from ..models import CommandRequest, CommandType

logger = logging.getLogger(__name__)


class CommandParser:
    """
    Parser for slash commands with key=value syntax.

    Supports commands like:
    - /create_task title="Design landing page" assignee=Maria due=2025-12-08
    - /list_tasks board=Marketing status=InProgress
    - /assign_task id=143 assignee=Ivan
    """

    # Mapping of command strings to CommandType enum
    COMMAND_MAP: Dict[str, CommandType] = {
        # Task management
        "create_task": CommandType.CREATE_TASK,
        "assign_task": CommandType.ASSIGN_TASK,
        "list_tasks": CommandType.LIST_TASKS,
        "tasks": CommandType.TASKS,
        "summary": CommandType.SUMMARY,
        "tasks_from_chat": CommandType.TASKS_FROM_CHAT,
        # Cards and comments
        "list_cards": CommandType.LIST_CARDS,
        "move_card": CommandType.MOVE_CARD,
        "add_comment": CommandType.ADD_COMMENT,
        "show_comments": CommandType.SHOW_COMMENTS,
        "update_comment": CommandType.UPDATE_COMMENT,
        "delete_comment": CommandType.DELETE_COMMENT,
        "card_members": CommandType.CARD_MEMBERS,
        # Members and responsibility
        "list_users": CommandType.LIST_USERS,
        "space_members": CommandType.SPACE_MEMBERS,
        "set_responsible": CommandType.SET_RESPONSIBLE,
        "add_member": CommandType.ADD_MEMBER,
        "remove_member": CommandType.REMOVE_MEMBER,
        # Automation and analytics
        "mass_update": CommandType.MASS_UPDATE,
        "break_into_tasks": CommandType.BREAK_INTO_TASKS,
        # Board status
        "board_status": CommandType.BOARD_STATUS,
        "introduce": CommandType.INTRODUCE,
        # Help
        "help": CommandType.HELP,
    }

    # Pattern to match key=value or key="value with spaces"
    ARGUMENT_PATTERN = re.compile(r'(\w+)=(?:"([^"]+)"|\'([^\']+)\'|(\S+))')

    @classmethod
    def is_command(cls, text: str) -> bool:
        """
        Check if text starts with a slash command.

        Args:
            text: Message text to check

        Returns:
            True if text is a slash command
        """
        return text.strip().startswith("/")

    @classmethod
    def parse(
        cls,
        text: str,
        chat_id: int,
        user_id: int,
        username: Optional[str] = None,
    ) -> CommandRequest:
        """
        Parse a slash command into a CommandRequest.

        Args:
            text: Command text to parse
            chat_id: Chat ID where command was issued
            user_id: User ID who issued the command
            username: Optional username of the issuer

        Returns:
            CommandRequest with parsed command and arguments
        """
        text = text.strip()
        command_type, arguments = cls._parse_command(text)

        return CommandRequest(
            command_type=command_type,
            raw_text=text,
            arguments=arguments,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
        )

    @classmethod
    def _parse_command(cls, text: str) -> Tuple[CommandType, Dict[str, Any]]:
        """
        Parse command text into command type and arguments.

        Args:
            text: Raw command text

        Returns:
            Tuple of (CommandType, arguments dict)
        """
        # Remove leading slash
        if text.startswith("/"):
            text = text[1:]

        # Split into command and rest
        parts = text.split(maxsplit=1)
        if not parts:
            return CommandType.UNKNOWN, {}

        # Extract command name (handle @botname suffix)
        command_name = parts[0].split("@")[0].lower()

        # Get command type
        command_type = cls.COMMAND_MAP.get(command_name, CommandType.UNKNOWN)

        # Parse arguments if present
        arguments: Dict[str, Any] = {}
        if len(parts) > 1:
            arguments = cls._parse_arguments(parts[1])

        logger.debug("Parsed command: %s with arguments: %s", command_type, arguments)
        return command_type, arguments

    @classmethod
    def _parse_arguments(cls, args_text: str) -> Dict[str, Any]:
        """
        Parse key=value arguments from text.

        Args:
            args_text: Text containing key=value pairs

        Returns:
            Dictionary of parsed arguments
        """
        arguments: Dict[str, Any] = {}

        for match in cls.ARGUMENT_PATTERN.finditer(args_text):
            key = match.group(1)
            # Value is in group 2 (double-quoted), 3 (single-quoted), or 4 (unquoted)
            value = match.group(2) or match.group(3) or match.group(4)

            # Try to convert to appropriate type
            arguments[key] = cls._convert_value(value)

        return arguments

    @classmethod
    def _convert_value(cls, value: str) -> Any:
        """
        Convert string value to appropriate type.

        Args:
            value: String value to convert

        Returns:
            Converted value (int, float, bool, or str)
        """
        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Try boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Return as string
        return value
