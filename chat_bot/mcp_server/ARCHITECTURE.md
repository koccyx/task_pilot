# MCP Server Architecture

## Overview

This document describes the clean architecture of the MCP server, where business logic is centralized and adapters are thin wrappers.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  KaitenClient (Pure HTTP)                   │
│              Infrastructure Layer Only                      │
│                                                             │
│  • get(endpoint) - HTTP GET                                │
│  • post(endpoint, data) - HTTP POST                        │
│  • put(endpoint, data) - HTTP PUT                          │
│  • delete(endpoint) - HTTP DELETE                          │
│  • close() - Cleanup                                       │
│                                                             │
│  NO business logic - just HTTP transport!                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│           Business Logic Helpers (tools/)                   │
│                                                             │
│  • find_board_by_name(client, board_name)                  │
│    → Fetches spaces, iterates boards, finds by name       │
│                                                             │
│  Pure functions that use HTTP client                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────────┐
│                   MCP Tools (Core Logic)                    │
│              Single Source of Truth                         │
│                                                             │
│  @mcp.tool()                                               │
│  • create_card(title, board, asap, due_date, description)  │
│  • get_card(card_id)                                       │
│  • update_card(card_id, title, board, description)        │
│  • delete_card(card_id)                                    │
│                                                             │
│  All business logic orchestration:                         │
│  - Calls business logic helpers                            │
│  - Data validation (Pydantic models)                       │
│  - Error handling                                          │
│  - Progress reporting (MCP Context)                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ↓                           ↓
┌──────────────────┐         ┌──────────────────────┐
│   MCP Protocol   │         │   KaitenMCPClient    │
│   (stdio/HTTP)   │         │   (HTTP Transport)   │
│                  │         │                      │
│  Used by:        │         │  • Connects to MCP   │
│  • Cursor        │         │    server via HTTP   │
│  • Claude Desktop│         │  • Provides public   │
│  • MCP Clients   │         │    call_tool() API   │
│                  │         │  • Generates tools   │
│  Returns: dict   │         │    for LangChain     │
└──────────────────┘         └──────────┬───────────┘
                                        │
                                        ↓
                              ┌──────────────────┐
                              │  Telegram Bot    │
                              │  (MCPHandler)    │
                              │                  │
                              │  Uses LangChain  │
                              │  tools for       │
                              │  function calling│
                              └──────────────────┘
```

## Key Principles

### 1. Pure Layered Architecture

**KaitenClient** - Pure HTTP transport:
- Only HTTP methods (get, post, put, delete)
- No business logic at all
- Just infrastructure

**Business Logic Helpers** (`helpers.py`):
- Reusable business logic functions
- Take HTTP client as parameter
- Example: `find_board_by_name(client, name)`

**MCP Tools** (`create_card.py`, `update_card.py`, etc.):
- Orchestrate business logic
- Call helpers when needed
- Data validation
- Error handling
- Progress reporting

### 2. KaitenMCPClient

**KaitenMCPClient** provides HTTP transport to MCP server:
- Connects to MCP server via HTTP
- Provides `call_tool()` public API for direct tool calls
- Generates LangChain-compatible tools dynamically
- Static `extract_text_from_result()` for text extraction

### 3. No Duplication

```python
# ❌ BAD (duplicating logic in client)
class KaitenClient:
    async def create_card(self, ...):
        # Duplicate all logic from MCP tool
        board_id = await self.find_board_by_name(board)
        card_data = Card(...)
        response = await self.post(...)
        # ... 50 lines of duplicated code

# ✅ GOOD (single source of truth in MCP tools)
# Tool logic lives in tools/create_card.py
# Client just calls it via MCP protocol
result = await mcp_client.call_tool("create_card", {"title": "Task"})
text = KaitenMCPClient.extract_text_from_result(result)
```

## Benefits

1. **Maintainability** - Change logic in one place (MCP tools)
2. **Consistency** - Same behavior for MCP and LangChain
3. **Testability** - Test core logic once, adapters are trivial
4. **Clarity** - Clear separation of concerns

## File Structure

```
chat_bot/mcp_server/
├── client/
│   ├── kaiten_client.py       # Pure HTTP client (NO business logic)
│   └── mcp_client.py          # MCP client for HTTP transport + LangChain tools
├── tools/
│   ├── helpers.py             # Business logic helpers
│   ├── create_card.py         # MCP tool (orchestrates)
│   ├── update_card.py         # MCP tool (orchestrates)
│   ├── get_card.py            # MCP tool (orchestrates)
│   ├── delete_card.py         # MCP tool (orchestrates)
│   └── ...                    # 30+ additional tools for cards, sprints, users
├── models/
│   └── card.py                # Pydantic models
└── config/
    └── settings.py            # Configuration
```

## Usage Examples

### Direct MCP Tool Usage

```python
from chat_bot.mcp_server.tools import create_card

# Use directly (returns dict)
result = await create_card(
    title="Task",
    board="Marketing",  # Resolves name to ID automatically
    asap=True,
    ctx=None
)
print(result["meta"]["card_id"])
```

### Via KaitenMCPClient (LangChain Tools)

```python
from chat_bot.mcp_server.client.mcp_client import KaitenMCPClient, MCPClientConfig

# Initialize client (connects to MCP server via HTTP)
config = MCPClientConfig(transport="http", server_url="http://localhost:8000")
async with KaitenMCPClient(config) as client:
    # Get LangChain-compatible tools
    tools = await client.get_tools()
    
    # Call tool directly via public API
    result = await client.call_tool("create_card", {
        "title": "Task",
        "board_id": 123,
    })
    
    # Extract text from result
    text = KaitenMCPClient.extract_text_from_result(result)
    print(text)  # "Card created successfully with ID: 456"
```

## Board Name Resolution

The system uses Kaiten's hierarchy to resolve board names:

1. **Fetch Spaces**: `client.get("spaces")`
2. **Fetch Boards**: For each space, `client.get(f"spaces/{id}/boards")`
3. **Find Board**: Search by name (case-insensitive)
4. **Return ID**: Use in API calls

This business logic lives in `tools/helpers.py` as a pure function:
```python
async def find_board_by_name(client: KaitenClient, board_name: str) -> Optional[int]
```

MCP tools call this helper when they need to resolve board names. The HTTP client is just transport - it knows nothing about boards or spaces.

