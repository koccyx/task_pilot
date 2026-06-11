"""
Handler for slash commands.

All commands are routed to the MCP server for execution.
"""

import logging
import os
from typing import Any, Dict, Optional

from ..commands import CommandParser, CommandRegistry
from ..mcp_server.client.mcp_client import KaitenMCPClient, MCPClientConfig
from ..models import CommandType, UserProfile
from ..repository_base import BaseChatRepository

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handles slash commands and routes to MCP tools.
    """

    def __init__(
        self,
        repository: BaseChatRepository,
    ) -> None:
        """
        Initialize the command handler.

        Args:
            repository: Message repository for chat context.
        """
        self.repository = repository

        # Initialize MCP client (lazy initialization)
        self.mcp_client: Optional[KaitenMCPClient] = None
        self._mcp_initialized = False

        # Initialize command registry
        CommandRegistry.initialize()

    async def handle(
        self,
        text: str,
        chat_id: int,
        user_id: int,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> str:
        """
        Handle a slash command.

        Args:
            text: Command text
            chat_id: Chat ID
            user_id: User ID
            username: Username
            display_name: Telegram display name

        Returns:
            Response message
        """
        # Parse the command
        command = CommandParser.parse(
            text=text,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
        )

        logger.info("Processing command: %s", command.command_type)

        # Route to appropriate handler
        if command.command_type == CommandType.CREATE_TASK:
            return await self._handle_create_task(command.arguments)
        elif command.command_type == CommandType.ASSIGN_TASK:
            return await self._handle_assign_task(command.arguments)
        elif command.command_type == CommandType.LIST_TASKS:
            return await self._handle_list_tasks(command.arguments)
        elif command.command_type == CommandType.LIST_CARDS:
            return await self._handle_list_cards(command.arguments)
        elif command.command_type == CommandType.MOVE_CARD:
            return await self._handle_move_card(command.arguments)
        elif command.command_type == CommandType.LIST_USERS:
            return await self._handle_list_users(command.arguments)
        elif command.command_type == CommandType.SPACE_MEMBERS:
            return await self._handle_space_members(command.arguments)
        elif command.command_type == CommandType.SET_RESPONSIBLE:
            return await self._handle_set_responsible(command.arguments)
        elif command.command_type == CommandType.ADD_MEMBER:
            return await self._handle_add_member(command.arguments)
        elif command.command_type == CommandType.REMOVE_MEMBER:
            return await self._handle_remove_member(command.arguments)
        elif command.command_type == CommandType.CARD_MEMBERS:
            return await self._handle_card_members(command.arguments)
        elif command.command_type == CommandType.ADD_COMMENT:
            return await self._handle_add_comment(command.arguments)
        elif command.command_type == CommandType.SHOW_COMMENTS:
            return await self._handle_show_comments(command.arguments)
        elif command.command_type == CommandType.UPDATE_COMMENT:
            return await self._handle_update_comment(command.arguments)
        elif command.command_type == CommandType.DELETE_COMMENT:
            return await self._handle_delete_comment(command.arguments)
        elif command.command_type == CommandType.MASS_UPDATE:
            return await self._handle_mass_update(command.arguments)
        elif command.command_type == CommandType.BREAK_INTO_TASKS:
            return await self._handle_break_into_tasks(command.arguments)
        elif command.command_type == CommandType.BOARD_STATUS:
            return await self._handle_board_status(command.arguments)
        elif command.command_type == CommandType.TASKS_FROM_CHAT:
            return await self._handle_tasks_from_chat(chat_id, command.arguments)
        elif command.command_type == CommandType.GET_SPACES:
            return await self._handle_get_spaces(command.arguments)
        elif command.command_type == CommandType.GET_BOARDS:
            return await self._handle_get_boards(command.arguments)
        elif command.command_type == CommandType.GET_COLUMNS:
            return await self._handle_get_columns(command.arguments)
        elif command.command_type == CommandType.CREATE_SPACE:
            return await self._handle_create_space(command.arguments)
        elif command.command_type == CommandType.CREATE_BOARD:
            return await self._handle_create_board(command.arguments)
        elif command.command_type == CommandType.GET_TAGS:
            return await self._handle_get_tags(command.arguments)
        elif command.command_type == CommandType.CREATE_TAG:
            return await self._handle_create_tag(command.arguments)
        elif command.command_type == CommandType.GET_TIME_LOGS:
            return await self._handle_get_time_logs(command.arguments)
        elif command.command_type == CommandType.LOG_TIME:
            return await self._handle_log_time(command.arguments)
        elif command.command_type == CommandType.SEARCH_CARDS:
            return await self._handle_search_cards(command.arguments)
        elif command.command_type == CommandType.REMOVE_COLUMN:
            return await self._handle_remove_column(command.arguments)
        elif command.command_type == CommandType.INTRODUCE:
            return await self._handle_introduce(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                display_name=display_name,
                args=command.arguments,
            )
        elif command.command_type == CommandType.HELP:
            return CommandRegistry.format_help_message()
        elif command.command_type == CommandType.UNKNOWN:
            return (
                "❓ Неизвестная команда. "
                "Используйте /help для списка доступных команд."
            )

        # For summary and tasks, return None to let existing handlers work
        return ""

    async def _handle_introduce(
        self,
        chat_id: int,
        user_id: int,
        username: Optional[str],
        display_name: Optional[str],
        args: Dict[str, Any],
    ) -> str:
        """Persist the user's introduction profile."""
        introduced_name = args.get("name")
        if not introduced_name:
            return (
                '❌ Укажите имя: /introduce name="Имя Фамилия" '
                'kaiten="Имя в Kaiten"'
            )

        profile = UserProfile(
            chat_id=chat_id,
            telegram_user_id=user_id,
            telegram_username=username,
            telegram_display_name=display_name or username or f"user_{user_id}",
            introduced_name=str(introduced_name),
            kaiten_user_name=(
                str(args["kaiten"]) if "kaiten" in args else None
            ),
        )
        saved = await self.repository.upsert_user_profile(profile)

        kaiten_hint = (
            f"\nKaiten: {saved.kaiten_user_name}"
            if saved.kaiten_user_name
            else ""
        )
        return (
            "✅ Профиль сохранён.\n"
            f"Буду помнить вас как: {saved.introduced_name}{kaiten_hint}"
        )

    async def _handle_create_task(self, args: Dict[str, Any]) -> str:
        """Handle create_task command via MCP create_card tool."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        title = args.get("title")
        if not title:
            return '❌ Укажите название задачи: /create_task title="Название"'

        try:
            tool_args: Dict[str, Any] = {"action": "create", "title": str(title)}
            if "board" in args:
                tool_args["board"] = str(args["board"])
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "due" in args:
                tool_args["due_date"] = str(args["due"])
            if "description" in args:
                tool_args["description"] = str(args["description"])

            return await self._call_mcp_tool("manage_cards", tool_args)
        except Exception as e:
            logger.error(f"Error calling create_card tool: {e}", exc_info=True)
            return f"❌ Ошибка при создании задачи: {str(e)}"

    async def _handle_assign_task(self, args: Dict[str, Any]) -> str:
        """Handle assign_task command via MCP set_responsible tool."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        task_id = args.get("id")
        assignee = args.get("assignee")

        if not task_id or not assignee:
            return (
                "❌ Укажите ID задачи и исполнителя: /assign_task id=123 assignee=Имя"
            )

        try:
            tool_args: Dict[str, Any] = {
                "action": "set_responsible",
                "card_id": int(task_id),
                "owner_name": str(assignee),
            }
            return await self._call_mcp_tool("manage_members", tool_args)
        except Exception as e:
            logger.error(f"Error calling set_responsible tool: {e}", exc_info=True)
            return f"❌ Ошибка при назначении задачи: {str(e)}"

    async def _handle_list_tasks(self, args: Dict[str, Any]) -> str:
        """Handle list_tasks command via MCP list_cards tool."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: Dict[str, Any] = {"action": "list"}
            if "board" in args:
                tool_args["board"] = str(args["board"])
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "assignee" in args:
                tool_args["owner_name"] = str(args["assignee"])
            if "limit" in args:
                tool_args["limit"] = int(args["limit"])

            return await self._call_mcp_tool("manage_cards", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_cards tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка задач: {str(e)}"

    async def _handle_board_status(self, args: Dict[str, Any]) -> str:
        """Handle board_status command via MCP list_cards tool."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        board = args.get("board")
        if not board:
            return "❌ Укажите название доски: /board_status board=Название"

        try:
            tool_args: Dict[str, Any] = {"action": "list", "board": str(board)}
            return await self._call_mcp_tool("manage_cards", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_cards tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении статуса доски: {str(e)}"

    async def _handle_tasks_from_chat(self, chat_id: int, args: dict) -> str:
        """Handle tasks_from_chat command."""
        days = int(args.get("days", 1))
        limit = int(args.get("limit", 50))

        # Load messages using read_recent_messages to respect days parameter
        messages_data = await self.repository.read_recent_messages(
            chat_id, limit=limit, days=days
        )

        if not messages_data.messages:
            return "📭 Сообщений для анализа не найдено"

        return (
            f"📜 Найдено {len(messages_data.messages)} сообщений за {days} дн.\n"
            "Для извлечения задач используйте /tasks или упомяните бота "
            'с запросом "создай задачи из обсуждения".'
        )

    async def _ensure_mcp_client(self) -> bool:
        """Ensure MCP client is initialized.

        Returns:
            True if MCP client is available, False otherwise.
        """
        if self._mcp_initialized:
            return self.mcp_client is not None

        try:
            server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
            # Ensure URL has /mcp endpoint (strip trailing slashes first)
            server_url = server_url.rstrip("/")
            if not server_url.endswith("/mcp"):
                server_url = server_url + "/mcp"

            config = MCPClientConfig(server_url=server_url)
            self.mcp_client = KaitenMCPClient(config)
            await self.mcp_client.initialize()
            self._mcp_initialized = True
            logger.info("MCP client initialized for command handler")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize MCP client: {e}")
            self._mcp_initialized = True
            return False

    async def _call_mcp_tool(self, tool_name: str, tool_args: dict) -> str:
        """Call an MCP tool and extract text from result.

        Args:
            tool_name: Name of the MCP tool to call.
            tool_args: Arguments to pass to the tool.

        Returns:
            Extracted text from tool result.

        Raises:
            Exception: If tool call fails.
        """
        if not self.mcp_client:
            raise RuntimeError("MCP client not initialized")

        result = await self.mcp_client.call_tool(tool_name, tool_args)
        return KaitenMCPClient._extract_text_from_result(result)

    async def _handle_list_cards(self, args: dict) -> str:
        """Handle list_cards command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            # Build tool arguments from command arguments
            tool_args: dict = {"action": "list"}
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "board" in args:
                tool_args["board"] = str(args["board"])
            if "space_id" in args:
                tool_args["space_id"] = int(args["space_id"])
            if "column_id" in args:
                tool_args["column_id"] = int(args["column_id"])
            if "condition" in args:
                tool_args["condition"] = int(args["condition"])
            if "query" in args:
                tool_args["query"] = str(args["query"])
            if "due_date_after" in args:
                tool_args["due_date_after"] = str(args["due_date_after"])
            if "due_date_before" in args:
                tool_args["due_date_before"] = str(args["due_date_before"])
            if "owner_id" in args:
                tool_args["owner_id"] = int(args["owner_id"])
            if "tag_ids" in args:
                tool_args["tag_ids"] = str(args["tag_ids"])
            if "limit" in args:
                tool_args["limit"] = int(args["limit"])
            if "skip" in args:
                tool_args["skip"] = int(args["skip"])

            return await self._call_mcp_tool("manage_cards", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_cards tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка карточек: {str(e)}"

    async def _handle_move_card(self, args: dict) -> str:
        """Handle move_card command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /move_card card_id=12345"

        try:
            # Build tool arguments from command arguments
            tool_args: dict = {"card_id": int(card_id)}
            if "column_id" in args:
                tool_args["column_id"] = int(args["column_id"])
            if "column" in args:
                tool_args["column"] = str(args["column"])
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "board" in args:
                tool_args["board"] = str(args["board"])
            if "lane_id" in args:
                tool_args["lane_id"] = int(args["lane_id"])
            if "sort_order" in args:
                tool_args["sort_order"] = int(args["sort_order"])
            if "position" in args:
                tool_args["position"] = int(args["position"])

            return await self._call_mcp_tool("move_card", tool_args)
        except Exception as e:
            logger.error(f"Error calling move_card tool: {e}", exc_info=True)
            return f"❌ Ошибка при перемещении карточки: {str(e)}"

    async def _handle_list_users(self, args: dict) -> str:
        """Handle list_users command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {"action": "list"}
            if "offset" in args:
                tool_args["offset"] = int(args["offset"])
            if "limit" in args:
                tool_args["limit"] = int(args["limit"])

            return await self._call_mcp_tool("manage_users", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_users tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка пользователей: {str(e)}"

    async def _handle_space_members(self, args: dict) -> str:
        """Handle space_members command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {"action": "space_members"}
            if "space_id" in args:
                tool_args["space_id"] = int(args["space_id"])
            if "space" in args:
                tool_args["space"] = str(args["space"])

            return await self._call_mcp_tool("manage_users", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_users tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении участников пространства: {str(e)}"

    async def _handle_set_responsible(self, args: dict) -> str:
        """Handle set_responsible command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /set_responsible card_id=12345"

        try:
            tool_args: dict = {"action": "set_responsible", "card_id": int(card_id)}
            if "owner_id" in args:
                tool_args["owner_id"] = int(args["owner_id"])
            if "owner_name" in args:
                tool_args["owner_name"] = str(args["owner_name"])

            return await self._call_mcp_tool("manage_members", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_members tool: {e}", exc_info=True)
            return f"❌ Ошибка при назначении ответственного: {str(e)}"

    async def _handle_add_member(self, args: dict) -> str:
        """Handle add_member command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /add_member card_id=12345"

        try:
            tool_args: dict = {"action": "add", "card_id": int(card_id)}
            if "user_id" in args:
                tool_args["user_id"] = int(args["user_id"])
            if "user_name" in args:
                tool_args["user_name"] = str(args["user_name"])

            return await self._call_mcp_tool("manage_members", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_members tool: {e}", exc_info=True)
            return f"❌ Ошибка при добавлении участника: {str(e)}"

    async def _handle_remove_member(self, args: dict) -> str:
        """Handle remove_member command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /remove_member card_id=12345"

        try:
            tool_args: dict = {"action": "remove", "card_id": int(card_id)}
            if "user_id" in args:
                tool_args["user_id"] = int(args["user_id"])
            if "user_name" in args:
                tool_args["user_name"] = str(args["user_name"])

            return await self._call_mcp_tool("manage_members", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_members tool: {e}", exc_info=True)
            return f"❌ Ошибка при удалении участника: {str(e)}"

    async def _handle_card_members(self, args: dict) -> str:
        """Handle card_members command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /card_members card_id=12345"

        try:
            tool_args: dict = {"action": "list", "card_id": int(card_id)}

            return await self._call_mcp_tool("manage_members", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_members tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении участников карточки: {str(e)}"

    async def _handle_add_comment(self, args: dict) -> str:
        """Handle add_comment command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        text = args.get("text")
        if not card_id or not text:
            return (
                "❌ Укажите ID карточки и текст комментария: "
                '/add_comment card_id=12345 text="Текст комментария"'
            )

        try:
            tool_args: dict = {
                "action": "add",
                "card_id": int(card_id),
                "text": str(text),
            }
            if "attachments" in args:
                tool_args["attachments"] = args["attachments"]

            return await self._call_mcp_tool("manage_comments", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_comments tool: {e}", exc_info=True)
            return f"❌ Ошибка при добавлении комментария: {str(e)}"

    async def _handle_show_comments(self, args: dict) -> str:
        """Handle show_comments command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /show_comments card_id=12345"

        try:
            tool_args: dict = {"action": "show", "card_id": int(card_id)}

            return await self._call_mcp_tool("manage_comments", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_comments tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении комментариев: {str(e)}"

    async def _handle_update_comment(self, args: dict) -> str:
        """Handle update_comment command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        comment_id = args.get("comment_id")
        text = args.get("text")
        if not card_id or not comment_id or not text:
            return (
                "❌ Укажите ID карточки, ID комментария и новый текст: "
                '/update_comment card_id=12345 comment_id=789 text="Новый текст"'
            )

        try:
            tool_args: dict = {
                "action": "update",
                "card_id": int(card_id),
                "comment_id": int(comment_id),
                "text": str(text),
            }

            return await self._call_mcp_tool("manage_comments", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_comments tool: {e}", exc_info=True)
            return f"❌ Ошибка при обновлении комментария: {str(e)}"

    async def _handle_delete_comment(self, args: dict) -> str:
        """Handle delete_comment command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        comment_id = args.get("comment_id")
        if not card_id or not comment_id:
            return (
                "❌ Укажите ID карточки и ID комментария: "
                "/delete_comment card_id=12345 comment_id=789"
            )

        try:
            tool_args: dict = {
                "action": "delete",
                "card_id": int(card_id),
                "comment_id": int(comment_id),
            }

            return await self._call_mcp_tool("manage_comments", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_comments tool: {e}", exc_info=True)
            return f"❌ Ошибка при удалении комментария: {str(e)}"

    async def _handle_mass_update(self, args: dict) -> str:
        """Handle mass_update command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {}
            if "target_board_id" in args:
                tool_args["target_board_id"] = int(args["target_board_id"])
            if "target_board" in args:
                tool_args["target_board"] = str(args["target_board"])
            if "target_column_id" in args:
                tool_args["target_column_id"] = int(args["target_column_id"])
            if "target_column" in args:
                tool_args["target_column"] = str(args["target_column"])
            if "filter_tag" in args:
                tool_args["filter_tag"] = str(args["filter_tag"])
            if "filter_owner_id" in args:
                tool_args["filter_owner_id"] = int(args["filter_owner_id"])
            if "filter_column_id" in args:
                tool_args["filter_column_id"] = int(args["filter_column_id"])
            if "confirm" in args:
                tool_args["confirm"] = bool(args["confirm"])

            return await self._call_mcp_tool("mass_update", tool_args)
        except Exception as e:
            logger.error(f"Error calling mass_update tool: {e}", exc_info=True)
            return f"❌ Ошибка при массовом обновлении: {str(e)}"

    async def _handle_break_into_tasks(self, args: dict) -> str:
        """Handle break_into_tasks command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки-эпика: /break_into_tasks card_id=12345"

        try:
            tool_args: dict = {"card_id": int(card_id)}
            if "target_board_id" in args:
                tool_args["target_board_id"] = int(args["target_board_id"])
            if "target_board" in args:
                tool_args["target_board"] = str(args["target_board"])
            if "target_column_id" in args:
                tool_args["target_column_id"] = int(args["target_column_id"])
            if "inherit_owner" in args:
                tool_args["inherit_owner"] = bool(args["inherit_owner"])
            if "auto_confirm" in args:
                tool_args["auto_confirm"] = bool(args["auto_confirm"])

            return await self._call_mcp_tool("break_into_tasks", tool_args)
        except Exception as e:
            logger.error(f"Error calling break_into_tasks tool: {e}", exc_info=True)
            return f"❌ Ошибка при разбиении эпика на подзадачи: {str(e)}"

    async def _handle_get_spaces(self, args: dict) -> str:
        """Handle get_spaces command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            return await self._call_mcp_tool("manage_spaces", {"action": "list"})
        except Exception as e:
            logger.error(f"Error calling manage_spaces tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка пространств: {str(e)}"

    async def _handle_get_boards(self, args: dict) -> str:
        """Handle get_boards command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {"action": "list"}
            if "space_id" in args:
                tool_args["space_id"] = int(args["space_id"])
            if "space" in args:
                tool_args["space"] = str(args["space"])

            return await self._call_mcp_tool("manage_boards", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_boards tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка досок: {str(e)}"

    async def _handle_get_columns(self, args: dict) -> str:
        """Handle get_columns command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {"action": "list"}
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "board" in args:
                tool_args["board"] = str(args["board"])

            return await self._call_mcp_tool("manage_columns", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_columns tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка колонок: {str(e)}"

    async def _handle_create_space(self, args: dict) -> str:
        """Handle create_space command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        title = args.get("title")
        if not title:
            return '❌ Укажите название пространства: /create_space title="Название"'

        try:
            tool_args: dict = {"action": "create", "title": str(title)}
            return await self._call_mcp_tool("manage_spaces", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_spaces tool: {e}", exc_info=True)
            return f"❌ Ошибка при создании пространства: {str(e)}"

    async def _handle_create_board(self, args: dict) -> str:
        """Handle create_board command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        title = args.get("title")
        if not title:
            return '❌ Укажите название доски: /create_board title="Название"'

        try:
            tool_args: dict = {"action": "create", "title": str(title)}
            if "space_id" in args:
                tool_args["space_id"] = int(args["space_id"])
            if "space" in args:
                tool_args["space"] = str(args["space"])
            if "description" in args:
                tool_args["description"] = str(args["description"])

            return await self._call_mcp_tool("manage_boards", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_boards tool: {e}", exc_info=True)
            return f"❌ Ошибка при создании доски: {str(e)}"

    async def _handle_get_tags(self, args: dict) -> str:
        """Handle get_tags command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {"action": "list"}
            if "card_id" in args:
                tool_args["card_id"] = int(args["card_id"])

            return await self._call_mcp_tool("manage_tags", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_tags tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении списка тегов: {str(e)}"

    async def _handle_create_tag(self, args: dict) -> str:
        """Handle create_tag command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        name = args.get("name")
        if not name:
            return '❌ Укажите название тега: /create_tag name="название"'

        try:
            tool_args: dict = {"action": "create", "name": str(name)}
            if "card_id" in args:
                tool_args["card_id"] = int(args["card_id"])

            return await self._call_mcp_tool("manage_tags", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_tags tool: {e}", exc_info=True)
            return f"❌ Ошибка при создании тега: {str(e)}"

    async def _handle_get_time_logs(self, args: dict) -> str:
        """Handle get_time_logs command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        if not card_id:
            return "❌ Укажите ID карточки: /get_time_logs card_id=12345"

        try:
            tool_args: dict = {"action": "list", "card_id": int(card_id)}
            if "for_date" in args:
                tool_args["for_date"] = str(args["for_date"])
            if "personal" in args:
                tool_args["personal"] = bool(args["personal"])

            return await self._call_mcp_tool("manage_time_logs", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_time_logs tool: {e}", exc_info=True)
            return f"❌ Ошибка при получении логов времени: {str(e)}"

    async def _handle_log_time(self, args: dict) -> str:
        """Handle log_time command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        card_id = args.get("card_id")
        time_spent = args.get("time_spent")
        for_date = args.get("for_date")
        role_id = args.get("role_id")

        if not all([card_id, time_spent, for_date, role_id]):
            return (
                "❌ Укажите обязательные параметры: "
                "/log_time card_id=12345 time_spent=60 for_date=2025-12-08 role_id=1"
            )

        try:
            tool_args: dict = {
                "action": "log",
                "card_id": int(card_id),
                "time_spent": int(time_spent),
                "for_date": str(for_date),
                "role_id": int(role_id),
            }
            if "comment" in args:
                tool_args["comment"] = str(args["comment"])

            return await self._call_mcp_tool("manage_time_logs", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_time_logs tool: {e}", exc_info=True)
            return f"❌ Ошибка при логировании времени: {str(e)}"

    async def _handle_search_cards(self, args: dict) -> str:
        """Handle search_cards command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        query = args.get("query")
        if not query:
            return '❌ Укажите поисковый запрос: /search_cards query="текст"'

        try:
            tool_args: dict = {"action": "search", "query": str(query)}
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "board" in args:
                tool_args["board"] = str(args["board"])
            if "space_id" in args:
                tool_args["space_id"] = int(args["space_id"])
            if "limit" in args:
                tool_args["limit"] = int(args["limit"])

            return await self._call_mcp_tool("manage_cards", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_cards tool: {e}", exc_info=True)
            return f"❌ Ошибка при поиске карточек: {str(e)}"

    async def _handle_remove_column(self, args: dict) -> str:
        """Handle remove_column command."""
        if not await self._ensure_mcp_client():
            return (
                "❌ MCP сервер недоступен. "
                "Убедитесь, что MCP_TRANSPORT=http и MCP_SERVER_URL настроены."
            )

        try:
            tool_args: dict = {"action": "remove"}
            if "board_id" in args:
                tool_args["board_id"] = int(args["board_id"])
            if "board" in args:
                tool_args["board"] = str(args["board"])
            if "column_id" in args:
                tool_args["column_id"] = int(args["column_id"])
            if "column" in args:
                tool_args["column"] = str(args["column"])
            if "force" in args:
                tool_args["force"] = bool(args["force"])

            return await self._call_mcp_tool("manage_columns", tool_args)
        except Exception as e:
            logger.error(f"Error calling manage_columns tool: {e}", exc_info=True)
            return f"❌ Ошибка при удалении колонки: {str(e)}"
