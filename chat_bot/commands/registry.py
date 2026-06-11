"""
Command registry for managing available commands.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from ..models import CommandType


@dataclass
class CommandInfo:
    """Information about a registered command."""

    command_type: CommandType
    name: str
    description: str
    parameters: List[str]
    example: str
    requires_mention: bool = False


class CommandRegistry:
    """
    Registry of available slash commands.

    Provides command metadata for help messages and validation.
    """

    _commands: Dict[CommandType, CommandInfo] = {}

    @classmethod
    def initialize(cls) -> None:
        """Initialize the registry with default commands."""
        cls._commands = {
            CommandType.CREATE_TASK: CommandInfo(
                command_type=CommandType.CREATE_TASK,
                name="create_task",
                description="Создать новую задачу в Kaiten",
                parameters=["title", "assignee", "due", "board"],
                example='/create_task title="Отчет" assignee=Alex due=2025-12-09',
            ),
            CommandType.ASSIGN_TASK: CommandInfo(
                command_type=CommandType.ASSIGN_TASK,
                name="assign_task",
                description="Назначить задачу на пользователя",
                parameters=["id", "assignee"],
                example="/assign_task id=143 assignee=Иван",
            ),
            CommandType.LIST_TASKS: CommandInfo(
                command_type=CommandType.LIST_TASKS,
                name="list_tasks",
                description="Показать список задач",
                parameters=["board", "status", "assignee"],
                example="/list_tasks board=Marketing status=InProgress",
            ),
            CommandType.INTRODUCE: CommandInfo(
                command_type=CommandType.INTRODUCE,
                name="introduce",
                description="Представиться боту и сохранить свой профиль",
                parameters=["name", "kaiten"],
                example='/introduce name="Иван Петров" kaiten="Иван Петров"',
            ),
            CommandType.LIST_CARDS: CommandInfo(
                command_type=CommandType.LIST_CARDS,
                name="list_cards",
                description="Показать список карточек с фильтрацией",
                parameters=[
                    "board_id",
                    "board",
                    "space_id",
                    "column_id",
                    "condition",
                    "query",
                    "due_date_after",
                    "due_date_before",
                    "owner_id",
                    "tag_ids",
                    "limit",
                    "skip",
                ],
                example="/list_cards board=Marketing condition=1 limit=20",
            ),
            CommandType.MOVE_CARD: CommandInfo(
                command_type=CommandType.MOVE_CARD,
                name="move_card",
                description="Переместить карточку между колонками/досками",
                parameters=[
                    "card_id",
                    "column_id",
                    "column",
                    "board_id",
                    "board",
                    "lane_id",
                    "sort_order",
                    "position",
                ],
                example="/move_card card_id=12345 column='В работе'",
            ),
            CommandType.LIST_USERS: CommandInfo(
                command_type=CommandType.LIST_USERS,
                name="list_users",
                description="Показать список всех пользователей компании",
                parameters=["offset", "limit"],
                example="/list_users limit=20",
            ),
            CommandType.SPACE_MEMBERS: CommandInfo(
                command_type=CommandType.SPACE_MEMBERS,
                name="space_members",
                description="Показать участников пространства",
                parameters=["space_id", "space"],
                example="/space_members space=Marketing",
            ),
            CommandType.SET_RESPONSIBLE: CommandInfo(
                command_type=CommandType.SET_RESPONSIBLE,
                name="set_responsible",
                description="Назначить ответственного на карточку",
                parameters=["card_id", "owner_id", "owner_name"],
                example="/set_responsible card_id=12345 owner_name='Вера'",
            ),
            CommandType.ADD_MEMBER: CommandInfo(
                command_type=CommandType.ADD_MEMBER,
                name="add_member",
                description="Добавить участника к карточке",
                parameters=["card_id", "user_id", "user_name"],
                example="/add_member card_id=12345 user_name='Вера'",
            ),
            CommandType.REMOVE_MEMBER: CommandInfo(
                command_type=CommandType.REMOVE_MEMBER,
                name="remove_member",
                description="Удалить участника из карточки",
                parameters=["card_id", "user_id", "user_name"],
                example="/remove_member card_id=12345 user_name='Вера'",
            ),
            CommandType.CARD_MEMBERS: CommandInfo(
                command_type=CommandType.CARD_MEMBERS,
                name="card_members",
                description="Показать участников карточки",
                parameters=["card_id"],
                example="/card_members card_id=12345",
            ),
            CommandType.ADD_COMMENT: CommandInfo(
                command_type=CommandType.ADD_COMMENT,
                name="add_comment",
                description="Добавить комментарий к карточке",
                parameters=["card_id", "text", "attachments"],
                example='/add_comment card_id=12345 text="Нужно обсудить архитектуру"',
            ),
            CommandType.SHOW_COMMENTS: CommandInfo(
                command_type=CommandType.SHOW_COMMENTS,
                name="show_comments",
                description="Показать все комментарии карточки",
                parameters=["card_id"],
                example="/show_comments card_id=12345",
            ),
            CommandType.UPDATE_COMMENT: CommandInfo(
                command_type=CommandType.UPDATE_COMMENT,
                name="update_comment",
                description="Редактировать комментарий",
                parameters=["card_id", "comment_id", "text"],
                example='/update_comment card_id=12345 comment_id=789 text="Архитектура согласована"',
            ),
            CommandType.DELETE_COMMENT: CommandInfo(
                command_type=CommandType.DELETE_COMMENT,
                name="delete_comment",
                description="Удалить комментарий",
                parameters=["card_id", "comment_id"],
                example="/delete_comment card_id=12345 comment_id=789",
            ),
            CommandType.MASS_UPDATE: CommandInfo(
                command_type=CommandType.MASS_UPDATE,
                name="mass_update",
                description="Массовое обновление карточек по фильтру",
                parameters=[
                    "target_board_id",
                    "target_board",
                    "target_column_id",
                    "target_column",
                    "filter_tag",
                    "filter_owner_id",
                    "filter_column_id",
                    "confirm",
                ],
                example="/mass_update filter_tag=urgent target_board=Hotfix target_column='To Do'",
            ),
            CommandType.BREAK_INTO_TASKS: CommandInfo(
                command_type=CommandType.BREAK_INTO_TASKS,
                name="break_into_tasks",
                description="Разбить эпик на подзадачи",
                parameters=[
                    "card_id",
                    "target_board_id",
                    "target_board",
                    "target_column_id",
                    "inherit_owner",
                    "auto_confirm",
                ],
                example="/break_into_tasks card_id=12345",
            ),
            CommandType.BOARD_STATUS: CommandInfo(
                command_type=CommandType.BOARD_STATUS,
                name="board_status",
                description="Показать статус доски",
                parameters=["board"],
                example="/board_status board=Marketing",
            ),
            CommandType.TASKS_FROM_CHAT: CommandInfo(
                command_type=CommandType.TASKS_FROM_CHAT,
                name="tasks_from_chat",
                description="Создать задачи из обсуждения в чате",
                parameters=["days", "limit"],
                example="/tasks_from_chat days=2",
            ),
            CommandType.SUMMARY: CommandInfo(
                command_type=CommandType.SUMMARY,
                name="summary",
                description="Показать сводку сообщений за сегодня",
                parameters=[],
                example="/summary",
            ),
            CommandType.TASKS: CommandInfo(
                command_type=CommandType.TASKS,
                name="tasks",
                description="Извлечь задачи из сообщений за сегодня",
                parameters=[],
                example="/tasks",
            ),
            CommandType.GET_SPACES: CommandInfo(
                command_type=CommandType.GET_SPACES,
                name="get_spaces",
                description="Показать список всех пространств (spaces)",
                parameters=[],
                example="/get_spaces",
            ),
            CommandType.GET_BOARDS: CommandInfo(
                command_type=CommandType.GET_BOARDS,
                name="get_boards",
                description="Показать список досок в пространстве",
                parameters=["space_id", "space"],
                example="/get_boards space=Marketing",
            ),
            CommandType.GET_COLUMNS: CommandInfo(
                command_type=CommandType.GET_COLUMNS,
                name="get_columns",
                description="Показать список колонок на доске",
                parameters=["board_id", "board"],
                example="/get_columns board=Backend",
            ),
            CommandType.CREATE_SPACE: CommandInfo(
                command_type=CommandType.CREATE_SPACE,
                name="create_space",
                description="Создать новое пространство",
                parameters=["title"],
                example='/create_space title="Новый проект"',
            ),
            CommandType.CREATE_BOARD: CommandInfo(
                command_type=CommandType.CREATE_BOARD,
                name="create_board",
                description="Создать новую доску в пространстве",
                parameters=["title", "space_id", "space", "description"],
                example='/create_board title="Backend Tasks" space=Development',
            ),
            CommandType.GET_TAGS: CommandInfo(
                command_type=CommandType.GET_TAGS,
                name="get_tags",
                description="Показать список тегов",
                parameters=["card_id"],
                example="/get_tags card_id=12345",
            ),
            CommandType.CREATE_TAG: CommandInfo(
                command_type=CommandType.CREATE_TAG,
                name="create_tag",
                description="Создать тег и опционально прикрепить к карточке",
                parameters=["name", "card_id"],
                example='/create_tag name="urgent" card_id=12345',
            ),
            CommandType.GET_TIME_LOGS: CommandInfo(
                command_type=CommandType.GET_TIME_LOGS,
                name="get_time_logs",
                description="Показать логи времени по карточке",
                parameters=["card_id", "for_date", "personal"],
                example="/get_time_logs card_id=12345",
            ),
            CommandType.LOG_TIME: CommandInfo(
                command_type=CommandType.LOG_TIME,
                name="log_time",
                description="Залогировать время на карточку",
                parameters=["card_id", "time_spent", "for_date", "role_id", "comment"],
                example="/log_time card_id=12345 time_spent=60 for_date=2025-12-08 role_id=1",
            ),
            CommandType.SEARCH_CARDS: CommandInfo(
                command_type=CommandType.SEARCH_CARDS,
                name="search_cards",
                description="Поиск карточек по тексту",
                parameters=["query", "board_id", "board", "space_id", "limit"],
                example='/search_cards query="баг авторизации"',
            ),
            CommandType.REMOVE_COLUMN: CommandInfo(
                command_type=CommandType.REMOVE_COLUMN,
                name="remove_column",
                description="Удалить колонку с доски",
                parameters=["board_id", "board", "column_id", "column", "force"],
                example="/remove_column board=Backend column='Архив' force=true",
            ),
            CommandType.HELP: CommandInfo(
                command_type=CommandType.HELP,
                name="help",
                description="Показать справку по командам",
                parameters=[],
                example="/help",
            ),
        }

    @classmethod
    def get_command(cls, command_type: CommandType) -> Optional[CommandInfo]:
        """
        Get command info by type.

        Args:
            command_type: Type of command to look up

        Returns:
            CommandInfo if found, None otherwise
        """
        if not cls._commands:
            cls.initialize()
        return cls._commands.get(command_type)

    @classmethod
    def get_all_commands(cls) -> List[CommandInfo]:
        """
        Get all registered commands.

        Returns:
            List of all CommandInfo objects
        """
        if not cls._commands:
            cls.initialize()
        return list(cls._commands.values())

    @classmethod
    def format_help_message(cls) -> str:
        """
        Format help message with all available commands.

        Returns:
            Formatted help message string (plain text to avoid markdown issues)
        """
        if not cls._commands:
            cls.initialize()

        lines = ["📋 Доступные команды:\n"]

        for info in cls._commands.values():
            params = ", ".join(info.parameters) if info.parameters else "нет"
            lines.append(f"/{info.name} - {info.description}")
            lines.append(f"  Параметры: {params}")
            lines.append(f"  Пример: {info.example}\n")

        lines.append("\n💡 Естественный язык:")
        lines.append("Упомяните бота и опишите что нужно сделать:")
        lines.append("• создай задачу Подготовить отчет для Алексея")
        lines.append("• какие задачи на этой неделе?")
        lines.append("• создай задачи из нашего обсуждения")

        return "\n".join(lines)
