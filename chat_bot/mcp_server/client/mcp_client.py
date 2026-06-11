"""MCP Client for connecting to task_pilot MCP Server via FastMCP.

This module provides a client that communicates with the MCP server
using FastMCP's official Client class with streamable-http transport.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from fastmcp import Client
from fastmcp.client.logging import LogMessage
from fastmcp.client.transports import StreamableHttpTransport
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from chat_bot.logging_config import get_logger, sanitize_for_logging

logger = get_logger(__name__)

# Logging level mapping for MCP to Python
LOGGING_LEVEL_MAP = logging.getLevelNamesMapping()


class MCPClientConfig(BaseModel):
    """Configuration for MCP Client."""

    server_url: str = Field(
        default="http://localhost:8000/mcp",
        description="HTTP URL of MCP server endpoint",
    )
    timeout: float = Field(
        default=60.0,
        description="Timeout for requests in seconds",
    )


async def default_log_handler(message: LogMessage) -> None:
    """Default handler for MCP server logs.

    Forwards server logs to Python's logging system at appropriate levels.

    Args:
        message: Log message from MCP server.
    """
    msg = message.data.get("msg", str(message.data))
    extra = message.data.get("extra")

    # Convert MCP log level to Python log level
    level = LOGGING_LEVEL_MAP.get(message.level.upper(), logging.INFO)

    # Handle 'notice' level (MCP specific)
    if message.level.lower() == "notice":
        level = logging.INFO
    elif message.level.lower() in ("alert", "emergency"):
        level = logging.CRITICAL

    logger.log(
        level,
        f"[MCP Server] {msg}",
        extra={
            "event_type": "mcp_server_log",
            "mcp_log_level": message.level,
            "mcp_log_extra": sanitize_for_logging(extra),
        },
    )


async def default_progress_handler(
    progress: float,
    total: Optional[float],
    message: Optional[str],
) -> None:
    """Default handler for MCP progress notifications.

    Logs progress updates for long-running operations.

    Args:
        progress: Current progress value.
        total: Expected total value (may be None or zero).
        message: Optional status message.
    """
    if total is not None and total > 0:
        percentage = (progress / total) * 100
        logger.info(
            f"[MCP Progress] {percentage:.1f}% - {message or ''}",
            extra={
                "event_type": "mcp_progress",
                "progress": progress,
                "total": total,
                "percentage": round(percentage, 2),
                "progress_message": message,
            },
        )
    else:
        logger.info(
            f"[MCP Progress] {progress} - {message or ''}",
            extra={
                "event_type": "mcp_progress",
                "progress": progress,
                "total": total,
                "progress_message": message,
            },
        )


class KaitenMCPClient:
    """Client for task_pilot MCP Server via FastMCP.

    Connects to a separately running MCP server using FastMCP's official
    Client class and provides LangChain-compatible tools for function calling.
    """

    def __init__(
        self,
        config: Optional[MCPClientConfig] = None,
        log_handler: Optional[Callable[[LogMessage], Any]] = None,
        progress_handler: Optional[
            Callable[[float, Optional[float], Optional[str]], Any]
        ] = None,
    ) -> None:
        """Initialize the MCP client.

        Args:
            config: Client configuration (uses defaults if not provided).
            log_handler: Custom handler for server logs.
            progress_handler: Custom handler for progress notifications.
        """
        self.config = config or MCPClientConfig()
        self._log_handler = log_handler or default_log_handler
        self._progress_handler = progress_handler or default_progress_handler
        self._client: Optional[Client] = None
        self._tools: List[Any] = []
        self._initialized = False

        logger.info(f"Initialized MCP client: url={self.config.server_url}")

    def _create_client(self) -> Client:
        """Create FastMCP Client instance.

        Creates a new Client for each call. For streamable HTTP transport,
        each request is stateless so connection "caching" isn't beneficial.
        The underlying httpx library handles connection pooling automatically.

        Returns:
            Configured FastMCP Client.
        """
        transport = StreamableHttpTransport(url=self.config.server_url)

        return Client(
            transport=transport,
            log_handler=self._log_handler,
            progress_handler=self._progress_handler,
            timeout=self.config.timeout,
        )

    async def initialize(self) -> None:
        """Initialize the MCP client and connect to the server.

        Raises:
            ConnectionError: If connection to the server fails.
        """
        if self._initialized:
            logger.debug("MCP client already initialized")
            return

        try:
            logger.info(
                f"Connecting to MCP server via FastMCP: {self.config.server_url}"
            )

            # Create client
            self._client = self._create_client()

            # Connect and get tools
            logger.info("Connecting to MCP server and fetching tools...")
            async with self._client:
                # Test connection
                await self._client.ping()
                logger.debug("MCP server ping successful")

                # Get available tools
                raw_tools = await self._client.list_tools()
                self._tools = self._convert_to_langchain_tools(raw_tools)

            logger.info(
                f"✅ Successfully connected to MCP server. "
                f"Available tools: {len(self._tools)}"
            )

            # Log tool names
            tool_names = [tool.name for tool in self._tools]
            logger.info(f"MCP Tools: {', '.join(tool_names)}")

            self._initialized = True

        except Exception as e:
            logger.error(
                f"Failed to connect to MCP server at {self.config.server_url}: {e}"
            )
            raise ConnectionError(
                f"Cannot connect to MCP server at {self.config.server_url}. "
                "Make sure the server is running: python -m chat_bot.mcp_server.server"
            ) from e

    def _convert_to_langchain_tools(self, mcp_tools: List[Any]) -> List[StructuredTool]:
        """Convert MCP tools to LangChain StructuredTool format.

        Args:
            mcp_tools: List of MCP tool definitions.

        Returns:
            List of LangChain StructuredTool objects.
        """
        tools = []

        for tool_info in mcp_tools:
            tool_name = tool_info.name
            tool_description = tool_info.description or "No description"

            # Parse parameters from input schema
            input_schema = tool_info.inputSchema or {}
            parameters = self._parse_input_schema(input_schema)

            # Create input model dynamically
            InputModel = create_model(
                f"{tool_name}_input",
                **parameters,
            )

            # Create async tool function that calls MCP server
            tool_func = self._create_tool_function(tool_name)

            # Create LangChain tool
            # Note: func=None because tool_func is async; only coroutine is set
            tool = StructuredTool.from_function(
                name=tool_name,
                description=tool_description,
                func=None,
                coroutine=tool_func,
                args_schema=InputModel,
            )
            tools.append(tool)

        return tools

    def _create_tool_function(self, tool_name: str) -> Any:
        """Create async function for calling MCP tool.

        Args:
            tool_name: Name of the tool.

        Returns:
            Async function that calls the MCP tool.
        """

        async def tool_func(**kwargs: Any) -> str:
            """Execute tool via MCP protocol."""
            started_at = time.time()
            sanitized_kwargs = self._sanitize_tool_arguments(kwargs)
            logger.info(
                "Tool request started",
                extra={
                    "event_type": "tool_request_started",
                    "tool_name": tool_name,
                    "tool_args": sanitize_for_logging(sanitized_kwargs),
                },
            )
            try:
                # Create fresh client for each call - HTTP is stateless
                # and FastMCP Client context manager manages connection lifecycle
                client = self._create_client()
                async with client:
                    result = await client.call_tool(tool_name, sanitized_kwargs)

                    # Check for tool-level error
                    is_error = getattr(result, "isError", False)

                    # Extract text from result
                    text_content = self._extract_text_from_result(result)
                    duration_ms = round((time.time() - started_at) * 1000, 2)

                    # If tool returned error, prefix with error marker
                    if is_error:
                        logger.warning(
                            "Tool request completed with tool error",
                            extra={
                                "event_type": "tool_request_completed",
                                "tool_name": tool_name,
                                "tool_args": sanitize_for_logging(sanitized_kwargs),
                                "tool_status": "tool_error",
                                "tool_result": sanitize_for_logging(
                                    text_content, max_length=2000
                                ),
                                "duration_ms": duration_ms,
                            },
                        )
                        return f"❌ ОШИБКА: {text_content}"

                    logger.info(
                        "Tool request completed",
                        extra={
                            "event_type": "tool_request_completed",
                            "tool_name": tool_name,
                            "tool_args": sanitize_for_logging(sanitized_kwargs),
                            "tool_status": "success",
                            "tool_result": sanitize_for_logging(
                                text_content, max_length=2000
                            ),
                            "duration_ms": duration_ms,
                        },
                    )
                    return text_content

            except Exception as e:
                logger.error(
                    f"Error calling tool {tool_name}: {e}",
                    extra={
                        "event_type": "tool_request_failed",
                        "tool_name": tool_name,
                        "tool_args": sanitize_for_logging(sanitized_kwargs),
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "duration_ms": round((time.time() - started_at) * 1000, 2),
                    },
                    exc_info=True,
                )
                return f"❌ Error: {str(e)}"

        return tool_func

    def _resolve_json_type(self, prop_schema: Dict[str, Any]) -> type:
        """Resolve JSON schema type to Python type.

        Handles simple types, anyOf/oneOf unions, and nullable types.

        Args:
            prop_schema: JSON schema property definition.

        Returns:
            Python type corresponding to the JSON schema type.
        """
        # Handle anyOf/oneOf (commonly used for nullable types)
        if "anyOf" in prop_schema or "oneOf" in prop_schema:
            type_options = prop_schema.get("anyOf") or prop_schema.get("oneOf", [])
            for option in type_options:
                option_type = option.get("type")
                if option_type and option_type != "null":
                    return self._map_json_type_to_python(option_type)
            return str

        # Handle type as array (e.g., ["integer", "null"])
        prop_type = prop_schema.get("type", "string")
        if isinstance(prop_type, list):
            for t in prop_type:
                if t != "null":
                    return self._map_json_type_to_python(t)
            return str

        return self._map_json_type_to_python(prop_type)

    def _map_json_type_to_python(self, json_type: str) -> type:
        """Map a single JSON schema type to Python type.

        Args:
            json_type: JSON schema type string.

        Returns:
            Corresponding Python type.
        """
        type_mapping: Dict[str, type] = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return type_mapping.get(json_type, str)

    def _parse_input_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON schema to Pydantic field definitions.

        Args:
            schema: JSON schema object.

        Returns:
            Dictionary mapping field names to (type, Field()) tuples.
        """
        parameters: Dict[str, Any] = {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for prop_name, prop_schema in properties.items():
            description = prop_schema.get("description", "")

            # Resolve type from JSON schema
            py_type = self._resolve_json_type(prop_schema)

            # Make optional if not required
            if prop_name not in required:
                py_type = Optional[py_type]  # type: ignore
                default = Field(default=None, description=description)
            else:
                default = Field(..., description=description)

            parameters[prop_name] = (py_type, default)

        return parameters

    @staticmethod
    def _sanitize_tool_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Drop `None` arguments before forwarding them to MCP tools.

        LangChain may include optional fields with explicit `None` values even when
        the underlying tool schema defines a non-null default. Sending those values
        through FastMCP triggers avoidable validation errors.
        """
        return {key: value for key, value in arguments.items() if value is not None}

    @staticmethod
    def _extract_text_from_result(result: Any) -> str:
        """Extract text content from MCP tool result.

        Args:
            result: MCP tool result.

        Returns:
            Extracted text content as string.
        """
        # Result from FastMCP Client is a CallToolResult object
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if hasattr(item, "text"):
                        text_parts.append(item.text)
                    elif isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                return "\n".join(text_parts)

        return str(result)

    async def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Call an MCP tool by name.

        This is the public API for calling tools directly without
        going through LangChain.

        Args:
            name: Name of the tool to call.
            arguments: Optional tool arguments.

        Returns:
            Tool result.

        Raises:
            RuntimeError: If client is not initialized.
            Exception: If tool call fails.
        """
        started_at = time.time()
        call_arguments = self._sanitize_tool_arguments(arguments or {})
        logger.info(
            "Direct tool request started",
            extra={
                "event_type": "tool_request_started",
                "tool_name": name,
                "tool_args": sanitize_for_logging(call_arguments),
                "request_mode": "direct",
            },
        )

        try:
            client = self._create_client()
            async with client:
                result = await client.call_tool(name, call_arguments)

            logger.info(
                "Direct tool request completed",
                extra={
                    "event_type": "tool_request_completed",
                    "tool_name": name,
                    "tool_args": sanitize_for_logging(call_arguments),
                    "tool_status": (
                        "tool_error" if getattr(result, "isError", False) else "success"
                    ),
                    "tool_result": sanitize_for_logging(
                        self._extract_text_from_result(result),
                        max_length=2000,
                    ),
                    "duration_ms": round((time.time() - started_at) * 1000, 2),
                    "request_mode": "direct",
                },
            )
            return result
        except Exception as e:
            logger.error(
                f"Direct tool request failed for {name}: {e}",
                extra={
                    "event_type": "tool_request_failed",
                    "tool_name": name,
                    "tool_args": sanitize_for_logging(call_arguments),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "duration_ms": round((time.time() - started_at) * 1000, 2),
                    "request_mode": "direct",
                },
                exc_info=True,
            )
            raise

    async def get_tools(self) -> List[Any]:
        """Get LangChain-compatible tools from the MCP server.

        Returns:
            List of LangChain tool objects.

        Raises:
            RuntimeError: If client is not initialized.
        """
        if not self._initialized:
            await self.initialize()

        return self._tools

    async def close(self) -> None:
        """Close the MCP client and cleanup resources."""
        self._client = None
        self._tools = []
        self._initialized = False
        logger.info("MCP client closed")

    async def __aenter__(self) -> "KaitenMCPClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
