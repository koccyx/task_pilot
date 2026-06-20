"""
Message router for handling Telegram messages.
"""

import logging
import os
from typing import Optional, Union

from telegram import Message, Update
from telegram.ext import ContextTypes

from ..assistant import Assistant
from ..commands import CommandParser
from ..models import InteractionInfo, InteractionType, RouteResult
from ..reports import WorkloadReportService
from ..repository_base import BaseChatRepository
from .command_handler import CommandHandler
from .mcp_handler import MCPHandler

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    Routes incoming Telegram messages to appropriate handlers.

    Detects:
    - Slash commands → CommandHandler
    - Bot mentions/replies → MCPHandler (natural language via MCP tools)
    - Regular messages → passthrough to logging
    """

    def __init__(
        self,
        bot_username: str,
        repository: BaseChatRepository,
        assistant: Optional[Assistant] = None,
    ) -> None:
        """
        Initialize the message router.

        Args:
            bot_username: Bot's username for mention detection
            repository: Repository for message storage
            assistant: Assistant for AI processing with function calling
        """
        self.bot_username = bot_username.lower().lstrip("@")
        self.repository = repository

        # Initialize command handler
        self.command_handler = CommandHandler(repository=self.repository)
        self.workload_report_service = WorkloadReportService()

        # Initialize MCP handler for natural language processing
        if assistant is not None:
            logger.info("MCP handler initialized for natural language processing")
            self.mcp_handler: Optional[MCPHandler] = MCPHandler(assistant=assistant)
        else:
            logger.warning("No assistant provided, MCP handler not available")
            self.mcp_handler = None

        # Check if hybrid mode is enabled
        self.hybrid_enabled = os.getenv("HYBRID_MODE_ENABLED", "true").lower() == "true"

    def get_interaction_info(self, message: Message) -> InteractionInfo:
        """
        Determine the type of interaction with the bot.

        Args:
            message: Telegram message

        Returns:
            InteractionInfo with type and reply_to_message_id if applicable
        """
        if not message.text:
            return InteractionInfo(interaction_type=InteractionType.NOT_FOR_BOT)

        # Check if message is a reply to bot (takes priority - continues conversation)
        if message.reply_to_message:
            reply_from = message.reply_to_message.from_user
            if reply_from and reply_from.username:
                if reply_from.username.lower() == self.bot_username:
                    return InteractionInfo(
                        interaction_type=InteractionType.REPLY_TO_BOT,
                        reply_to_message_id=message.reply_to_message.message_id,
                    )

        # In private chats every text message is addressed to the bot.
        if message.chat and message.chat.type == "private":
            return InteractionInfo(interaction_type=InteractionType.NEW_CONVERSATION)

        # Check for @mention (new conversation)
        text_lower = message.text.lower()
        if f"@{self.bot_username}" in text_lower:
            return InteractionInfo(interaction_type=InteractionType.NEW_CONVERSATION)

        return InteractionInfo(interaction_type=InteractionType.NOT_FOR_BOT)

    def is_bot_mentioned(self, message: Message) -> bool:
        """
        Check if the bot is mentioned or replied to.

        Args:
            message: Telegram message

        Returns:
            True if bot should respond
        """
        info = self.get_interaction_info(message)
        return info.interaction_type != InteractionType.NOT_FOR_BOT

    def is_command(self, message: Message) -> bool:
        """
        Check if message is a slash command.

        Args:
            message: Telegram message

        Returns:
            True if message is a command
        """
        if not message.text:
            return False
        # Exclude menu and help commands - they are handled separately
        text = message.text.strip()
        if (
            text in ("/menu", "/help")
            or text.startswith("/menu ")
            or text.startswith("/help ")
        ):
            return False
        return CommandParser.is_command(message.text)

    async def route(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> Optional[Union[str, RouteResult]]:
        """
        Route incoming message to appropriate handler.

        Args:
            update: Telegram update
            context: Bot context

        Returns:
            Response message or None if no response needed
        """
        message = update.message or update.channel_post
        if not message or not message.text:
            return None

        if not self.hybrid_enabled:
            logger.debug("Hybrid mode disabled, skipping routing")
            return None

        # Route based on message type
        if self.is_command(message):
            return await self._handle_command(update, context)

        # Check interaction type
        interaction_info = self.get_interaction_info(message)
        if interaction_info.interaction_type != InteractionType.NOT_FOR_BOT:
            return await self._handle_mention(update, context, interaction_info)

        # Not a command or mention - let normal logging proceed
        return None

    async def _handle_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> Optional[Union[str, RouteResult]]:
        """Handle slash command."""
        message = update.message or update.channel_post
        if not message or not message.text:
            return None

        chat_id = message.chat.id if message.chat else 0
        user = message.from_user
        user_id = user.id if user else 0
        username = user.username if user else None
        display_name = None
        if user:
            if user.first_name and user.last_name:
                display_name = f"{user.first_name} {user.last_name}"
            elif user.first_name:
                display_name = user.first_name
            elif username:
                display_name = f"@{username}"

        logger.info("Handling command from user %s in chat %d", username, chat_id)

        return await self.command_handler.handle(
            text=message.text,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
        )

    async def _handle_mention(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        interaction_info: InteractionInfo,
    ) -> Optional[Union[str, RouteResult]]:
        """Handle bot mention for natural language processing."""
        message = update.message or update.channel_post
        if not message or not message.text:
            return None

        chat_id = message.chat.id if message.chat else 0
        user = message.from_user
        user_id = user.id if user else 0
        username = user.username if user else None

        # Remove bot mention from text
        clean_text = message.text.replace(f"@{self.bot_username}", "").strip()

        is_reply = interaction_info.interaction_type == InteractionType.REPLY_TO_BOT

        logger.info(
            "Handling %s from user %s in chat %d: %s",
            "reply" if is_reply else "mention",
            username,
            chat_id,
            clean_text[:50],
        )

        if WorkloadReportService.is_workload_report_request(clean_text):
            logger.info("Generating workload report for chat %d", chat_id)
            try:
                return await self.workload_report_service.generate()
            except Exception as exc:
                logger.error(
                    "Failed to generate workload report: %s",
                    exc,
                    exc_info=True,
                )
                return f"❌ Не удалось сформировать отчет по загруженности: {exc}"

        # Use MCP handler for natural language processing
        if self.mcp_handler:
            return await self.mcp_handler.handle(
                text=clean_text,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                current_message_id=message.message_id,
                is_reply=is_reply,
                reply_to_message_id=interaction_info.reply_to_message_id,
                repository=self.repository,
            )
        else:
            logger.error("MCP handler not available")
            return "❌ Обработчик не настроен. Проверьте конфигурацию AI."
