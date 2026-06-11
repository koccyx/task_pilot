"""Handler for natural language requests using MCP protocol.

This handler uses the Model Context Protocol to communicate with
the task_pilot MCP Server via FastMCP's official Client class, enabling
proper tool execution with context, progress reporting, logging, and tracing.

Uses streamable-http transport to connect to a separately running MCP server.
Implements TTL-based tool caching to avoid unnecessary re-fetching.
"""

import logging
import os
import time
from typing import Any, List, Optional

from ..assistant import Assistant
from ..mcp_server.client.mcp_client import KaitenMCPClient, MCPClientConfig
from ..models import Message, UserProfile
from ..repository_base import BaseChatRepository

logger = logging.getLogger(__name__)

# Tool cache TTL in seconds (5 minutes)
_TOOLS_CACHE_TTL: float = 300.0


class MCPHandler:
    """Handles natural language requests using MCP protocol.

    This handler:
    1. Connects to the MCP server via FastMCP streamable-http transport
    2. Gets tools dynamically from the server
    3. Uses LangChain function calling with MCP tools
    4. Receives server logs via MCP log protocol
    5. Monitors progress via MCP progress notifications
    """

    def __init__(
        self,
        assistant: Assistant,
        mcp_config: Optional[MCPClientConfig] = None,
    ) -> None:
        """Initialize the MCP handler.

        Args:
            assistant: Assistant instance for AI processing.
            mcp_config: MCP client configuration (uses defaults if not provided).
        """
        self.assistant = assistant

        # Read configuration from environment if not provided
        if mcp_config is None:
            server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8000")
            # Ensure URL has /mcp endpoint (strip trailing slashes first)
            server_url = server_url.rstrip("/")
            if not server_url.endswith("/mcp"):
                server_url = server_url + "/mcp"

            mcp_config = MCPClientConfig(server_url=server_url)

            logger.info(f"MCP configuration from environment: url={server_url}")

        self.mcp_client = KaitenMCPClient(mcp_config)
        self._tools: List[Any] = []
        self._initialized = False
        self._tools_cached_at: Optional[float] = None

        logger.info("MCP handler created (not yet connected)")

    async def initialize(self) -> None:
        """Initialize the MCP client and fetch tools.

        Raises:
            Exception: If MCP client initialization fails.
        """
        if self._initialized:
            logger.debug("MCP handler already initialized")
            return

        try:
            logger.info("Initializing MCP handler...")

            # Connect to MCP server and get tools
            await self.mcp_client.initialize()
            self._tools = await self.mcp_client.get_tools()
            self._tools_cached_at = time.time()

            self._initialized = True
            logger.info(f"✅ MCP handler initialized with {len(self._tools)} tools")

        except ImportError as e:
            logger.error(
                "Failed to initialize MCP client: langchain-mcp-adapters not installed"
            )
            raise ImportError(
                "Please install langchain-mcp-adapters: "
                "pip install langchain-mcp-adapters"
            ) from e

        except Exception as e:
            logger.error(f"Failed to initialize MCP handler: {e}", exc_info=True)
            raise

    async def _refresh_tools_if_needed(self) -> None:
        """Refresh tools if cache has expired.

        Uses TTL-based caching to avoid unnecessary network roundtrips
        to the MCP server for tool discovery.
        """
        now = time.time()

        # Check if cache expired
        if self._tools_cached_at is None or now - self._tools_cached_at > _TOOLS_CACHE_TTL:
            logger.info(
                "Tool cache expired (TTL=%.0fs), refreshing...",
                _TOOLS_CACHE_TTL,
            )
            try:
                self._tools = await self.mcp_client.get_tools()
                self._tools_cached_at = now
                logger.info(f"Tool cache refreshed: {len(self._tools)} tools")
            except Exception as e:
                logger.warning(
                    f"Failed to refresh tool cache: {e}. Using stale cache."
                )
                # Keep using stale cache rather than failing

    async def handle(
        self,
        text: str,
        chat_id: int,
        user_id: int,
        username: Optional[str] = None,
        current_message_id: Optional[int] = None,
        is_reply: bool = False,
        reply_to_message_id: Optional[int] = None,
        repository: Optional[BaseChatRepository] = None,
    ) -> str:
        """Handle a natural language request using MCP tools.

        Args:
            text: User message text.
            chat_id: Chat ID.
            user_id: User ID.
            username: Username.
            current_message_id: Current Telegram message ID.
            is_reply: Whether this is a reply to a bot message.
            reply_to_message_id: ID of the message being replied to.
            repository: Repository for fetching conversation history.

        Returns:
            Response message.
        """
        # Ensure initialized
        if not self._initialized:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize MCP handler: {e}")
                return (
                    "❌ Не удалось подключиться к MCP серверу. "
                    "Проверьте конфигурацию и логи."
                )

        # Refresh tools if cache expired (TTL-based)
        await self._refresh_tools_if_needed()

        if not self._tools:
            logger.error("No MCP tools available")
            return (
                "❌ MCP инструменты не доступны. "
                "Проверьте конфигурацию KAITEN_API_URL и KAITEN_API_TOKEN."
            )

        # Get conversation history if this is a reply
        history: Optional[List[Message]] = None
        user_profile: Optional[UserProfile] = None
        if repository:
            try:
                user_profile = await repository.get_user_profile(chat_id, user_id)
            except Exception as e:
                logger.warning(f"Failed to load user profile: {e}")

        if repository:
            history = await self._load_chat_context(
                repository=repository,
                chat_id=chat_id,
                current_message_id=current_message_id,
                is_reply=is_reply,
                reply_to_message_id=reply_to_message_id,
            )

        logger.info(
            "Processing MCP request from user %s in chat %d: %s",
            username,
            chat_id,
            text[:50],
        )

        try:
            # Use Assistant's chat_with_tools with MCP tools
            response = await self.assistant.chat_with_tools(
                message=text,
                tools=self._tools,
                history=history,
                user_profile=user_profile,
            )
            return response

        except Exception as e:
            logger.error(f"Error processing MCP request: {e}", exc_info=True)
            return f"❌ Ошибка при обработке запроса: {str(e)}"

    async def _load_chat_context(
        self,
        repository: BaseChatRepository,
        chat_id: int,
        current_message_id: Optional[int],
        is_reply: bool,
        reply_to_message_id: Optional[int],
    ) -> Optional[List[Message]]:
        """Load recent chat context and merge it with reply-chain history."""
        context_limit = int(os.getenv("CHAT_CONTEXT_MESSAGE_LIMIT", "12"))
        recent_messages: List[Message] = []
        reply_chain: List[Message] = []

        try:
            recent_batch = await repository.read_recent_messages(
                chat_id=chat_id,
                limit=context_limit,
            )
            recent_messages = recent_batch.messages
            logger.info(
                "Loaded recent chat context: %d messages",
                len(recent_messages),
            )
        except Exception as e:
            logger.warning(f"Failed to load recent chat context: {e}")

        if is_reply and reply_to_message_id:
            try:
                reply_chain = await repository.get_conversation_chain(
                    chat_id=chat_id,
                    message_id=reply_to_message_id,
                )
                logger.info(
                    "Loaded reply conversation chain: %d messages",
                    len(reply_chain),
                )
            except Exception as e:
                logger.warning(f"Failed to load conversation history: {e}")

        deduplicated_recent = self._deduplicate_messages(
            recent_messages,
            current_message_id=current_message_id,
        )
        deduplicated_chain = self._deduplicate_messages(
            reply_chain,
            current_message_id=current_message_id,
        )

        if deduplicated_chain:
            chain_ids = {msg.message_id for msg in deduplicated_chain}
            remaining_slots = max(0, context_limit - len(deduplicated_chain))
            extra_recent = [
                msg for msg in deduplicated_recent if msg.message_id not in chain_ids
            ]
            if remaining_slots:
                extra_recent = extra_recent[-remaining_slots:]
            else:
                extra_recent = []

            final_context = self._deduplicate_messages(
                deduplicated_chain + extra_recent,
                current_message_id=current_message_id,
            )
            logger.info(
                "Prepared reply-aware chat context: chain=%d extra_recent=%d total=%d",
                len(deduplicated_chain),
                len(extra_recent),
                len(final_context),
            )
            return final_context or None

        final_context = deduplicated_recent[-context_limit:] if context_limit > 0 else []

        logger.info(
            "Prepared recent chat context: %d messages",
            len(final_context),
        )
        return final_context or None

    @staticmethod
    def _deduplicate_messages(
        messages: List[Message],
        current_message_id: Optional[int] = None,
    ) -> List[Message]:
        """Deduplicate messages by message_id preserving chronological order."""
        unique_by_id: dict[int, Message] = {}

        for msg in messages:
            if current_message_id is not None and msg.message_id == current_message_id:
                continue
            unique_by_id[msg.message_id] = msg

        return sorted(
            unique_by_id.values(),
            key=lambda msg: (msg.timestamp, msg.message_id),
        )

    async def close(self) -> None:
        """Close the MCP client and cleanup resources."""
        if self.mcp_client:
            await self.mcp_client.close()
            self._tools = []
            self._initialized = False
            self._tools_cached_at = None
            logger.info("MCP handler closed")

    async def __aenter__(self) -> "MCPHandler":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        """Async context manager exit."""
        await self.close()
