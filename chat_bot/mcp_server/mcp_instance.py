"""MCP instance for task_pilot MCP Server."""

import json
import logging
import sys
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

# Configure tool logging EARLY - use stderr to avoid uvicorn stdout capture
_tool_logger = logging.getLogger("mcp.tools")
_tool_logger.setLevel(logging.INFO)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(
    logging.Formatter("\033[96m[MCP]\033[0m %(message)s")
)
_tool_logger.addHandler(_stderr_handler)
_tool_logger.propagate = False


class ToolCallLoggingMiddleware(Middleware):
    """Middleware that logs all MCP tool calls with their arguments."""

    async def on_call_tool(
        self,
        context: MiddlewareContext,
        call_next: Any,
    ) -> Any:
        """Log tool calls with name and arguments.

        Args:
            context: Middleware context containing request info.
            call_next: Function to call the next middleware/handler.

        Returns:
            Any: Result from the tool call.
        """
        # context.message is CallToolRequestParams (not a wrapper with .params)
        params = context.message
        tool_name = getattr(params, "name", "unknown")
        arguments = getattr(params, "arguments", {}) or {}

        args_str = json.dumps(arguments, ensure_ascii=False, default=str)
        _tool_logger.info("🔧 Tool called: %s | Args: %s", tool_name, args_str)

        result = await call_next(context)

        _tool_logger.info("✅ Tool completed: %s", tool_name)

        return result


mcp = FastMCP("task_pilot MCP Server")
mcp.add_middleware(ToolCallLoggingMiddleware())
