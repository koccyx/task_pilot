"""Main MCP server for Kaiten API."""

import os

from dotenv import load_dotenv

from chat_bot.logging_config import setup_structured_logging

load_dotenv()

# Setup structured logging
log_level = os.getenv("LOG_LEVEL", "INFO")
use_json = os.getenv("LOG_JSON", "true").lower() == "true"
setup_structured_logging(level=log_level, use_json=use_json)

# ============================================================
# SPECIALIZED TOOLS
# ============================================================
import chat_bot.mcp_server.tools.break_into_tasks  # noqa: F401, E402

# ============================================================
# NEW CONSOLIDATED TOOLS
# ============================================================
import chat_bot.mcp_server.tools.manage_boards  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_cards  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_columns  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_comments  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_members  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_spaces  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_tags  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_time_logs  # noqa: F401, E402
import chat_bot.mcp_server.tools.manage_users  # noqa: F401, E402
import chat_bot.mcp_server.tools.mass_update  # noqa: F401, E402
import chat_bot.mcp_server.tools.move_card  # noqa: F401, E402

# Import mcp - it configures tool logging
from chat_bot.mcp_server.mcp_instance import mcp  # noqa: E402


def main() -> None:
    """Initialize and run the MCP server with HTTP transport."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
