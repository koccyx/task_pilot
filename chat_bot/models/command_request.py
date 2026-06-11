"""
Command request model for parsed slash commands.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    """Supported slash command types."""

    CREATE_TASK = "create_task"
    ASSIGN_TASK = "assign_task"
    LIST_TASKS = "list_tasks"
    LIST_CARDS = "list_cards"
    MOVE_CARD = "move_card"
    LIST_USERS = "list_users"
    SPACE_MEMBERS = "space_members"
    SET_RESPONSIBLE = "set_responsible"
    ADD_MEMBER = "add_member"
    REMOVE_MEMBER = "remove_member"
    CARD_MEMBERS = "card_members"
    ADD_COMMENT = "add_comment"
    SHOW_COMMENTS = "show_comments"
    UPDATE_COMMENT = "update_comment"
    DELETE_COMMENT = "delete_comment"
    MASS_UPDATE = "mass_update"
    BREAK_INTO_TASKS = "break_into_tasks"
    BOARD_STATUS = "board_status"
    TASKS_FROM_CHAT = "tasks_from_chat"
    # New navigation and utility commands
    GET_SPACES = "get_spaces"
    GET_BOARDS = "get_boards"
    GET_COLUMNS = "get_columns"
    CREATE_SPACE = "create_space"
    CREATE_BOARD = "create_board"
    GET_TAGS = "get_tags"
    CREATE_TAG = "create_tag"
    GET_TIME_LOGS = "get_time_logs"
    LOG_TIME = "log_time"
    SEARCH_CARDS = "search_cards"
    REMOVE_COLUMN = "remove_column"
    INTRODUCE = "introduce"
    SUMMARY = "summary"
    TASKS = "tasks"
    HELP = "help"
    UNKNOWN = "unknown"


class CommandRequest(BaseModel):
    """
    Represents a parsed slash command request.

    Attributes:
        command_type: Type of the command
        raw_text: Original command text
        arguments: Parsed key-value arguments
        chat_id: Chat ID where command was issued
        user_id: User ID who issued the command
        username: Username of the command issuer
    """

    command_type: CommandType = Field(..., description="Type of command")
    raw_text: str = Field(..., description="Original command text")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Parsed arguments"
    )
    chat_id: int = Field(..., description="Chat ID")
    user_id: int = Field(..., description="User ID")
    username: Optional[str] = Field(None, description="Username")
