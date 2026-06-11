#!/usr/bin/env python3
"""Entry point for running MCP server from Cursor or command line."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from chat_bot.mcp_server.server import main  # noqa: E402

if __name__ == "__main__":
    main()
