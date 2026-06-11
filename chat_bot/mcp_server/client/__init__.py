"""Client module for task_pilot MCP Server.

Note: KaitenMCPClient and MCPClientConfig are imported lazily to avoid
loading langchain dependencies when only KaitenClient is needed.
"""

from chat_bot.mcp_server.client.kaiten_client import KaitenClient

__all__ = ["KaitenClient"]
