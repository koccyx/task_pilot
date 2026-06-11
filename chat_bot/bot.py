"""
Telegram Chat Logger Bot

A bot that logs all messages from Telegram chats and channels to local JSON files.
Each day gets its own JSON file in DDMMYYYY.json format.
Supports hybrid interaction (natural language + slash commands) for Kaiten integration.
"""

import logging
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message as TelegramMessage,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Import Assistant for AI-powered summarization
from .assistant import Assistant
from .commands.registry import CommandRegistry
from .formatter import MessageFormatter
from .handlers import MessageRouter
from .healthcheck import HealthCheckServer
from .models import BotConfig, Message, MessagesData, PostgresConfig, UserProfile
from .repository_postgres import ChatRepository as PostgresChatRepository
from .repository_base import BaseChatRepository
from .telegram_formatter import TelegramMarkdownFormatter

# Load environment variables
load_dotenv()

# Setup structured logging
from chat_bot.logging_config import setup_structured_logging

import os

log_level = os.getenv("LOG_LEVEL", "INFO")
use_json = os.getenv("LOG_JSON", "true").lower() == "true"
setup_structured_logging(level=log_level, use_json=use_json)

# Get logger
from chat_bot.logging_config import get_logger

logger = get_logger(__name__)


class ChatLoggerBot:
    def __init__(
        self,
        token: str,
        postgres_config: PostgresConfig,
        health_check_port: int = int(os.getenv("HEALTHCHECK_PORT", "8080")),
    ):
        """
        Initialize the bot with token and storage configuration.

        Args:
            token: Telegram bot token
            postgres_config: PostgreSQL configuration for chat storage.
        """
        # Validate configuration using Pydantic model
        self.config = BotConfig(
            token=token,
            postgres_config=postgres_config,
        )

        # Initialize repository for data access
        self.repository = PostgresChatRepository(postgres_config)

        # Initialize AI Assistant for summarization
        try:
            self.assistant = Assistant()
            logger.info("AI Assistant initialized successfully")
        except Exception as e:
            raise Exception(f"Error initializing AI Assistant: {e}")

        # Initialize the application
        self.application = Application.builder().token(self.config.token).build()

        # Get bot username for mention detection
        self.bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "kaitenbot")

        # Initialize message router for hybrid mode
        self.message_router = MessageRouter(
            bot_username=self.bot_username,
            repository=self.repository,
            assistant=self.assistant,
        )

        # Add command handlers first (higher priority)
        # Important: menu and help must be registered before other commands
        self.application.add_handler(
            CommandHandler("start", self.handle_start_command)
        )
        self.application.add_handler(
            CommandHandler("menu", self.handle_menu_command)
        )
        self.application.add_handler(
            CommandHandler("help", self.handle_help_command)
        )
        self.application.add_handler(
            CommandHandler("summary", self.handle_summary_command)
        )
        self.application.add_handler(CommandHandler("tasks", self.handle_tasks_command))

        # Register all supported slash commands for Kaiten/MCP tools
        supported_commands = {
            info.name for info in CommandRegistry.get_all_commands()
        } - {"summary", "tasks", "menu", "help"}
        if supported_commands:
            self.application.add_handler(
                CommandHandler(list(supported_commands), self.handle_kaiten_command)
            )

        # Add callback query handler for confirmation buttons
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))

        # Add message handler for non-command messages (must be last, lowest priority)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        # Initialize standalone health check server for container orchestration
        self.healthcheck_server = HealthCheckServer(port=health_check_port)

    async def get_user_profile(
        self, chat_id: int, telegram_user_id: int
    ) -> Optional[UserProfile]:
        """Fetch persistent profile for a chat/user pair."""
        return await self.repository.get_user_profile(chat_id, telegram_user_id)

    async def ensure_user_introduced(
        self, message: TelegramMessage
    ) -> Optional[UserProfile]:
        """Return the user profile, or ask the user to introduce themselves."""
        user = message.from_user
        if user is None or message.chat is None:
            return None

        profile = await self.get_user_profile(message.chat.id, user.id)
        if profile is not None:
            return profile

        await message.reply_text(
            "Чтобы пользоваться ботом, сначала представьтесь.\n"
            'Отправьте команду: /introduce name="Имя Фамилия" kaiten="Имя в Kaiten"\n'
            'Параметр `kaiten` необязателен, если имя в Kaiten совпадает.'
        )
        return None

    def get_sender_name(self, update: Update) -> str:
        """Extract sender name from message or channel post updates.

        Args:
            update: Telegram update containing a message or channel post.

        Returns:
            str: Resolved sender name or a safe fallback.
        """
        message = update.message or update.channel_post
        if message and message.from_user:
            user = message.from_user
            if user.first_name and user.last_name:
                return f"{user.first_name} {user.last_name}"
            if user.first_name:
                return user.first_name
            if user.username:
                return f"@{user.username}"
            return f"User{user.id}"

        if message and message.sender_chat and message.sender_chat.title:
            return message.sender_chat.title

        if message and message.chat and message.chat.title:
            return message.chat.title

        return "Unknown"

    @staticmethod
    def get_sender_username(update: Update) -> Optional[str]:
        """Extract Telegram username from an update."""
        message = update.message or update.channel_post
        if message and message.from_user and message.from_user.username:
            return message.from_user.username
        return None

    def truncate_message(self, text: str, max_length: int = 4000) -> str:
        """Truncate message to fit Telegram limits.

        Args:
            text: The message text to truncate.
            max_length: Maximum length (default 4000, leaves room for suffix).

        Returns:
            Truncated message with indication if truncated.
        """
        if len(text) <= max_length:
            return text

        truncate_suffix = f"\n\n... (сообщение обрезано, всего {len(text)} символов)"
        available_length = max_length - len(truncate_suffix)
        return text[:available_length] + truncate_suffix

    async def send_formatted_message(
        self, message: TelegramMessage, text: str
    ) -> Optional[TelegramMessage]:
        """Send a message with proper Telegram Markdown formatting.

        Converts standard Markdown (including tables) to Telegram MarkdownV2,
        with fallbacks if formatting fails.

        Args:
            message: Telegram message to reply to.
            text: Standard Markdown text to send.

        Returns:
            The sent Telegram message, or None if sending failed.
        """
        # Truncate first (before formatting to avoid cutting escape sequences)
        truncated = self.truncate_message(text)

        # Try MarkdownV2 with telegramify-markdown conversion
        try:
            formatted = TelegramMarkdownFormatter.format_for_telegram(truncated)
            parse_mode = TelegramMarkdownFormatter.get_parse_mode()
            return await message.reply_text(formatted, parse_mode=parse_mode)
        except Exception as e:
            logger.debug("MarkdownV2 failed: %s, trying Markdown", e)

        # Fallback to basic Markdown
        try:
            return await message.reply_text(truncated, parse_mode="Markdown")
        except Exception as e:
            logger.debug("Markdown failed: %s, sending plain text", e)

        # Final fallback: plain text
        return await message.reply_text(truncated)

    async def get_today_messages(self, chat_id: int) -> MessagesData:
        """Get today's messages for a specific chat."""
        return await self.repository.read_chat_messages(chat_id)

    async def save_message(self, message_data: Message, chat_id: int) -> None:
        """Save message data to today's JSON file in chat-specific directory."""
        await self.repository.save_message(message_data, chat_id)

    async def _save_bot_response(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_to_message_id: int,
    ) -> None:
        """Save bot response message to storage.

        Args:
            chat_id: Chat ID where the message was sent.
            message_id: ID of the sent bot message.
            text: Text content of the bot response.
            reply_to_message_id: ID of the user message being replied to.
        """
        bot_message = Message(
            timestamp=datetime.now().isoformat(),
            message_id=message_id,
            sender_name=f"@{self.bot_username}",
            telegram_username=self.bot_username,
            text=text,
            reply_to_message_id=reply_to_message_id,
            is_bot_message=True,
        )
        await self.save_message(bot_message, chat_id)
        logger.debug("Saved bot response message_id=%d", message_id)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle incoming messages and save them to JSON."""
        try:
            # Extract message content
            if update.message:
                message = update.message
                message_type = "message"
            elif update.channel_post:
                message = update.channel_post
                message_type = "channel_post"
            else:
                return

            # Skip commands - they are handled by CommandHandler
            if message.text and message.text.startswith("/"):
                return

            # Get chat_id from the message
            if not message.chat:
                return
            chat_id = message.chat.id
            user = message.from_user
            user_id = user.id if user else None
            username = user.username if user else None

            profile: Optional[UserProfile] = None
            if user_id is not None:
                profile = await self.get_user_profile(chat_id, user_id)

            # Extract reply_to_message_id if this is a reply
            reply_to_message_id: Optional[int] = None
            if message.reply_to_message:
                reply_to_message_id = message.reply_to_message.message_id

            # Prepare optimized message data (only essential fields)
            message_data = Message(
                timestamp=datetime.now().isoformat(),
                message_id=message.message_id,
                sender_name=(
                    profile.introduced_name if profile else self.get_sender_name(update)
                ),
                telegram_user_id=user_id,
                telegram_username=username,
                text=message.text if message.text else None,
                reply_to_message_id=reply_to_message_id,
                is_bot_message=False,
            )

            # Save the message
            await self.save_message(message_data, chat_id)

            logger.info(f"Processed {message_type} from {message_data.sender_name}")

            # Check for bot mention and route to hybrid handler
            # Only reply to regular messages, not channel posts
            if update.message:
                if user_id is not None and profile is None:
                    profile = await self.ensure_user_introduced(update.message)
                    if profile is None:
                        return

                response = await self.message_router.route(update, context)
                if response:
                    sent_message = await self.send_formatted_message(
                        update.message, response
                    )
                    # Save bot response with is_bot_message=True
                    if sent_message:
                        await self._save_bot_response(
                            chat_id=chat_id,
                            message_id=sent_message.message_id,
                            text=response,
                            reply_to_message_id=message.message_id,
                        )

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def handle_kaiten_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle Kaiten-related slash commands."""
        try:
            message = update.message
            if not message or not message.text:
                return

            command_name = message.text.strip().split(maxsplit=1)[0].split("@")[0]
            if command_name != "/introduce":
                profile = await self.ensure_user_introduced(message)
                if profile is None:
                    return

            response = await self.message_router.route(update, context)
            if response:
                await self.send_formatted_message(message, response)

        except Exception as e:
            logger.error(f"Error handling Kaiten command: {e}")
            if update.message:
                await update.message.reply_text(
                    "❌ Произошла ошибка при обработке команды."
                )

    async def handle_help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command - show available commands."""
        try:
            from .commands import CommandRegistry

            CommandRegistry.initialize()
            help_text = CommandRegistry.format_help_message()

            if update.message:
                await update.message.reply_text(help_text)

        except Exception as e:
            logger.error(f"Error handling help command: {e}")
            if update.message:
                await update.message.reply_text(
                    "❌ Произошла ошибка при получении справки."
                )

    async def handle_start_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /start command with onboarding instructions."""
        if update.message:
            await update.message.reply_text(
                "Привет. Перед началом работы представьтесь командой:\n"
                '/introduce name="Имя Фамилия" kaiten="Имя в Kaiten"\n'
                "Параметр kaiten можно пропустить, если имя совпадает."
            )

    async def handle_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle callback queries from inline keyboards."""
        try:
            query = update.callback_query
            if not query or not query.data:
                return

            await query.answer()

            if query.data.startswith("menu_"):
                await self._handle_menu_callback(query, context)
            else:
                logger.debug("Ignoring unsupported callback query: %s", query.data)

        except Exception as e:
            logger.error(f"Error handling callback query: {e}")

    async def _handle_menu_callback(
        self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle menu button callbacks."""
        try:
            if not query.message or not isinstance(query.message, TelegramMessage):
                return

            # Map button callbacks to agent requests
            menu_requests = {
                "menu_users": "покажи список пользователей",
                "menu_spaces": "покажи список пространств",
                "menu_cards": "покажи список карточек",
                "menu_boards": "покажи список досок",
                "menu_help": None,  # Special case - show help directly
            }

            request_text = menu_requests.get(query.data)
            if request_text is None:
                # Handle help button
                if query.data == "menu_help":
                    help_text = (
                        "🤖 **Что может бот?**\n\n"
                        "Я помогаю работать с Kaiten через естественный язык. "
                        "Просто опишите, что нужно сделать, и я выполню действие.\n\n"
                        "**Основные возможности:**\n"
                        "• 👥 Управление пользователями и участниками\n"
                        "• 🏢 Работа с пространствами\n"
                        "• 📋 Создание и управление карточками\n"
                        "• 📊 Просмотр и управление досками\n"
                        "• 💬 Комментарии и обсуждения\n"
                        "• 🏷️ Работа с тегами\n"
                        "• ⏱️ Учет времени\n\n"
                        "**Примеры запросов:**\n"
                        "• \"Покажи все карточки на доске Marketing\"\n"
                        "• \"Создай карточку 'Новая задача' на доске Marketing\"\n"
                        "• \"Назначь Ивана ответственным за карточку #123\"\n"
                        "• \"Покажи список пользователей\"\n"
                        "• \"Какие доски есть в пространстве Development?\"\n\n"
                        "💡 **Совет:** Используйте меню (/menu) для быстрого доступа к основным функциям!"
                    )
                    await self.send_formatted_message(query.message, help_text)
                return

            # Send "typing..." indicator
            await context.bot.send_chat_action(
                chat_id=query.message.chat.id, action="typing"
            )

            # Route request through MCP handler
            chat_id = query.message.chat.id
            user = query.from_user
            user_id = user.id if user else 0
            username = user.username if user else None

            if self.message_router.mcp_handler:
                # Ensure MCP handler is initialized
                if not self.message_router.mcp_handler._initialized:
                    try:
                        await self.message_router.mcp_handler.initialize()
                    except Exception as e:
                        logger.error(f"Failed to initialize MCP handler: {e}")
                        await query.message.reply_text(
                            "❌ Не удалось подключиться к MCP серверу. "
                            "Проверьте конфигурацию и логи."
                        )
                        return

                response = await self.message_router.mcp_handler.handle(
                    text=request_text,
                    chat_id=chat_id,
                    user_id=user_id,
                    username=username,
                )
                await self.send_formatted_message(query.message, response)
            else:
                await query.message.reply_text(
                    "❌ Обработчик не настроен. Проверьте конфигурацию AI."
                )

        except Exception as e:
            logger.error(f"Error handling menu callback: {e}")
            if query.message and isinstance(query.message, TelegramMessage):
                await query.message.reply_text(
                    "❌ Произошла ошибка при обработке запроса."
                )

    async def handle_menu_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /menu command - show main menu with buttons."""
        try:
            if not update.message:
                logger.warning("handle_menu_command: no message in update")
                return

            profile = await self.ensure_user_introduced(update.message)
            if profile is None:
                return

            logger.info("Handling /menu command")

            # Create inline keyboard with buttons
            keyboard = [
                [
                    InlineKeyboardButton("👥 Пользователи", callback_data="menu_users"),
                    InlineKeyboardButton("🏢 Пространства", callback_data="menu_spaces"),
                ],
                [
                    InlineKeyboardButton("📋 Карточки", callback_data="menu_cards"),
                    InlineKeyboardButton("📊 Доски", callback_data="menu_boards"),
                ],
                [
                    InlineKeyboardButton("❓ Помощь", callback_data="menu_help"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            menu_text = (
                "📱 Главное меню\n\n"
                "Выберите действие:\n"
                "• 👥 Пользователи - список пользователей\n"
                "• 🏢 Пространства - список пространств\n"
                "• 📋 Карточки - список карточек\n"
                "• 📊 Доски - список досок\n"
                "• ❓ Помощь - справка по командам"
            )

            logger.debug(f"Sending menu with {len(keyboard)} rows of buttons")
            await update.message.reply_text(
                menu_text, reply_markup=reply_markup
            )
            logger.info("Menu sent successfully")

        except Exception as e:
            logger.error(f"Error handling menu command: {e}", exc_info=True)
            if update.message:
                await update.message.reply_text(
                    "❌ Произошла ошибка при отображении меню."
                )

    async def handle_summary_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /summary command - show today's messages."""
        try:
            if not update.effective_chat:
                return
            if update.message:
                profile = await self.ensure_user_introduced(update.message)
                if profile is None:
                    return
            chat_id = update.effective_chat.id
            today_data = await self.get_today_messages(chat_id)

            if not today_data.messages:
                # No messages today - respond in Russian
                response = "Сегодня сообщений нет. 📭"
            else:
                # Use AI Assistant for intelligent summarization
                try:
                    logger.info("Generating AI-powered summary...")
                    summary_response = await self.assistant.summarize(today_data)
                    if summary_response.success:
                        response = summary_response.summary
                        logger.info("AI summary generated successfully")
                    else:
                        logger.error(
                            f"AI summarization failed: {summary_response.error_message}"
                        )
                        # Fallback to manual summary
                        messages = today_data.messages
                        response = (
                            f"📊 **Сводка за сегодня** ({len(messages)} сообщений):\n\n"
                        )
                        formatted_messages = (
                            MessageFormatter.format_messages_for_display(
                                today_data, max_length=100
                            )
                        )
                        response += formatted_messages
                except Exception as e:
                    logger.error(f"AI summarization failed: {e}")
                    # Fallback to manual summary
                    messages = today_data.messages
                    response = (
                        f"📊 **Сводка за сегодня** ({len(messages)} сообщений):\n\n"
                    )
                    formatted_messages = MessageFormatter.format_messages_for_display(
                        today_data, max_length=100
                    )
                    response += formatted_messages

            if update.message:
                await self.send_formatted_message(update.message, response)
            logger.info(f"Summary sent for chat {chat_id}")

        except Exception as e:
            logger.error(f"Error handling summary command: {e}")
            if update.message:
                await update.message.reply_text(
                    "Произошла ошибка при получении сводки. 😔"
                )

    async def handle_tasks_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /tasks command - extract tasks from today's messages."""
        try:
            if not update.effective_chat:
                return
            if update.message:
                profile = await self.ensure_user_introduced(update.message)
                if profile is None:
                    return
            chat_id = update.effective_chat.id
            today_data = await self.get_today_messages(chat_id)

            if not today_data.messages:
                # No messages today - respond in Russian
                response = "Сегодня сообщений нет. 📭"
            else:
                # Use AI Assistant for task extraction
                try:
                    logger.info("Extracting tasks from messages...")
                    tasks_response = await self.assistant.extract_tasks(today_data)
                    if tasks_response.success:
                        if tasks_response.tasks:
                            response = "📋 **Извлеченные задачи:**\n\n"
                            for i, task in enumerate(tasks_response.tasks, 1):
                                deadline_str = ""
                                if task.deadline:
                                    fmt = task.deadline.strftime("%d.%m.%Y %H:%M")
                                    deadline_str = f" (до {fmt})"
                                title = f"{task.assignee}: {task.title}"
                                response += f"{i}. **{title}**{deadline_str}\n"
                        else:
                            response = "🔍 Задачи в сообщениях не найдены."
                        count = len(tasks_response.tasks)
                        logger.info("Task extraction completed: %d tasks", count)
                    else:
                        logger.error(
                            f"Task extraction failed: {tasks_response.error_message}"
                        )
                        err = tasks_response.error_message
                        response = f"❌ Ошибка при извлечении задач: {err}"
                except Exception as e:
                    logger.error(f"Task extraction failed: {e}")
                    response = "❌ Произошла ошибка при извлечении задач."

            if update.message:
                await self.send_formatted_message(update.message, response)
            logger.info(f"Tasks sent for chat {chat_id}")

        except Exception as e:
            logger.error(f"Error handling tasks command: {e}")
            if update.message:
                await update.message.reply_text(
                    "Произошла ошибка при извлечении задач. 😔"
                )

    async def start(self) -> None:
        """Start the bot."""
        logger.info("Starting Telegram Chat Logger Bot...")

        try:
            # Start the bot
            await self.application.initialize()
            await self.application.start()
            if self.application.updater:
                await self.application.updater.start_polling()

            # Start the health check server
            await self.healthcheck_server.start()

            logger.info("Bot is running. Press Ctrl+C to stop.")

            # Keep the bot running using a simple infinite loop with sleep
            # This is the most reliable way to keep the bot running
            import asyncio

            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Stopping bot...")
        except Exception as e:
            logger.error(f"Error running bot: {e}")
        finally:
            try:
                # Stop the health check server
                await self.healthcheck_server.stop()

                close_repository = getattr(self.repository, "close", None)
                if callable(close_repository):
                    await close_repository()

                # Stop the bot properly
                if self.application.updater:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Bot stopped successfully.")
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")


def main() -> None:
    """Main function to run the bot."""
    # Get bot token from environment
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set!")
        logger.error("Please create a .env file with your bot token:")
        logger.error("TELEGRAM_BOT_TOKEN=your_bot_token_here")
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise Exception("DATABASE_URL is required")
    postgres_config = PostgresConfig(database_url=database_url)
    logger.info("PostgreSQL configuration detected, using database storage")

    # Create and start the bot
    bot = ChatLoggerBot(
        token,
        postgres_config=postgres_config,
    )

    import asyncio

    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
