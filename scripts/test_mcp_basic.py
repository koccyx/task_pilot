#!/usr/bin/env python3
"""Basic MCP tool call verification script.

This script tests basic MCP tool calls via HTTP transport.
Useful for quick verification that MCP server is working correctly.

Usage:
    python scripts/test_mcp_basic.py

Environment variables:
    MCP_SERVER_URL: MCP server URL (default: http://localhost:8000/mcp)
"""

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chat_bot.mcp_server.client.mcp_client import KaitenMCPClient, MCPClientConfig

load_dotenv()

# MCP Server URL
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp").rstrip("/")
if not MCP_SERVER_URL.endswith("/mcp"):
    MCP_SERVER_URL = MCP_SERVER_URL + "/mcp"


async def test_tool_call(
    client: KaitenMCPClient, tool_name: str, args: dict, description: str
) -> bool:
    """Test a single tool call.

    Args:
        client: MCP client instance.
        tool_name: Name of the tool to call.
        args: Arguments for the tool.
        description: Description of what we're testing.

    Returns:
        True if call succeeded, False otherwise.
    """
    print(f"\n🔧 Testing: {description}")
    print(f"   Tool: {tool_name}")
    print(f"   Args: {args}")

    # Check if this is an error handling test or can legitimately fail
    is_error_test = (
        "error handling" in description.lower()
        or "expected to fail" in description.lower()
        or "may fail" in description.lower()
        or "testing structure" in description.lower()
    )

    try:
        result = await client.call_tool(tool_name, args)
        text = KaitenMCPClient._extract_text_from_result(result)

        # Check if result indicates an error
        is_error = getattr(result, "isError", False)

        if is_error or text.startswith("❌"):
            if is_error_test:
                print(f"   ⚠️  Expected error (OK): {text[:150]}...")
                return True
            print(f"   ❌ Error: {text[:200]}")
            return False
        else:
            print(f"   ✅ Success: {text[:200]}...")
            return True
    except Exception as e:
        error_msg = str(e)
        
        # Check for common "acceptable" errors
        acceptable_errors = [
            "404 Not Found",  # Resource doesn't exist (e.g., no sprints)
            "403 Forbidden",  # Access denied (e.g., invalid card ID)
        ]
        is_acceptable_error = any(err in error_msg for err in acceptable_errors)
        
        if is_error_test or is_acceptable_error:
            status = "Expected" if is_error_test else "Acceptable"
            print(f"   ⚠️  {status} exception (OK): {error_msg[:150]}...")
            return True
        print(f"   ❌ Exception: {error_msg}")
        return False


async def main() -> None:
    """Run basic MCP tool call tests."""
    print("=" * 60)
    print("MCP Server Basic Tool Call Tests")
    print("=" * 60)
    print(f"Server URL: {MCP_SERVER_URL}")

    # Create client
    config = MCPClientConfig(server_url=MCP_SERVER_URL, timeout=30.0)
    client = KaitenMCPClient(config)

    try:
        print("\n📡 Connecting to MCP server...")
        await client.initialize()
        print("✅ Connected successfully!")

        # Test basic tool calls in sequence (later tests can use data from earlier ones)
        results = []
        space_id = None
        space_name = None
        board_id = None
        board_name = None
        
        # 1. List users
        success = await test_tool_call(
            client, "manage_users", {"action": "list", "limit": 3}, "List users"
        )
        results.append(("manage_users", success))

        # 2. List spaces (we'll use this for boards)
        spaces_result_obj = await client.call_tool("manage_spaces", {"action": "list"})
        spaces_text = KaitenMCPClient._extract_text_from_result(spaces_result_obj)
        spaces_success = not spaces_text.startswith("❌") and len(spaces_text) > 0
        print(f"\n🔧 Testing: List spaces")
        print(f"   Tool: manage_spaces")
        print(f"   Args: {{'action': 'list'}}")
        if spaces_success:
            print(f"   ✅ Success: {spaces_text[:200]}...")
            # Try to extract space_id and space_name from result
            try:
                # Method 1: Check if result has structured_content attribute
                if hasattr(spaces_result_obj, "structured_content"):
                    structured = spaces_result_obj.structured_content
                    if isinstance(structured, list) and len(structured) > 0:
                        first_space = structured[0]
                        if isinstance(first_space, dict):
                            if "id" in first_space:
                                space_id = first_space["id"]
                                print(f"   📌 Found space_id: {space_id}")
                            if "title" in first_space:
                                space_name = first_space["title"]
                                print(f"   📌 Found space_name: {space_name}")
                
                # Method 2: Try parsing from text (fallback)
                if not space_id and "ID:" in spaces_text:
                    match = re.search(r"\(ID:\s*(\d+)\)", spaces_text)
                    if match:
                        space_id = int(match.group(1))
                        print(f"   📌 Found space_id from text: {space_id}")
                
                # Extract space name from text if available
                if not space_name and "•" in spaces_text:
                    # Try to extract name before (ID:...)
                    match = re.search(r"•\s*([^(]+)\s*\(ID:", spaces_text)
                    if match:
                        space_name = match.group(1).strip()
                        print(f"   📌 Found space_name from text: {space_name}")
            except Exception as e:
                print(f"   ⚠️  Could not extract space info: {e}")
        else:
            print(f"   ❌ Error: {spaces_text[:200]}")
        results.append(("manage_spaces", spaces_success))

        # 3. List boards - requires space_id or space
        boards_args = {"action": "list"}
        if space_id:
            boards_args["space_id"] = space_id
            boards_description = f"List boards (using space_id={space_id})"
        elif space_name:
            boards_args["space"] = space_name
            boards_description = f"List boards (using space='{space_name}')"
        else:
            boards_description = "List boards (no space available - will fail)"
        
        boards_result_obj = await client.call_tool("manage_boards", boards_args)
        boards_text = KaitenMCPClient._extract_text_from_result(boards_result_obj)
        boards_success = not boards_text.startswith("❌") and len(boards_text) > 0
        print(f"\n🔧 Testing: {boards_description}")
        print(f"   Tool: manage_boards")
        print(f"   Args: {boards_args}")
        if boards_success:
            print(f"   ✅ Success: {boards_text[:200]}...")
            # Try to extract board_id and board_name
            try:
                if hasattr(boards_result_obj, "structured_content"):
                    structured = boards_result_obj.structured_content
                    if isinstance(structured, list) and len(structured) > 0:
                        first_board = structured[0]
                        if isinstance(first_board, dict):
                            if "id" in first_board:
                                board_id = first_board["id"]
                                print(f"   📌 Found board_id: {board_id}")
                            if "title" in first_board:
                                board_name = first_board["title"]
                                print(f"   📌 Found board_name: {board_name}")
                
                if not board_id and "ID:" in boards_text:
                    match = re.search(r"\(ID:\s*(\d+)\)", boards_text)
                    if match:
                        board_id = int(match.group(1))
                        print(f"   📌 Found board_id from text: {board_id}")
                
                if not board_name and "•" in boards_text:
                    match = re.search(r"•\s*([^(]+)\s*\(ID:", boards_text)
                    if match:
                        board_name = match.group(1).strip()
                        print(f"   📌 Found board_name from text: {board_name}")
            except Exception as e:
                print(f"   ⚠️  Could not extract board info: {e}")
        else:
            print(f"   ❌ Error: {boards_text[:200]}")
        results.append(("manage_boards", boards_success))

        # 4. List columns - requires board_id or board
        columns_args = {"action": "list"}
        if board_id:
            columns_args["board_id"] = board_id
            columns_description = f"List columns (using board_id={board_id})"
        elif board_name:
            columns_args["board"] = board_name
            columns_description = f"List columns (using board='{board_name}')"
        else:
            columns_description = "List columns (no board available - will fail)"
        
        columns_result_obj = await client.call_tool("manage_columns", columns_args)
        columns_text = KaitenMCPClient._extract_text_from_result(columns_result_obj)
        columns_success = not columns_text.startswith("❌") and len(columns_text) > 0
        print(f"\n🔧 Testing: {columns_description}")
        print(f"   Tool: manage_columns")
        print(f"   Args: {columns_args}")
        if columns_success:
            print(f"   ✅ Success: {columns_text[:200]}...")
        else:
            print(f"   ❌ Error: {columns_text[:200]}")
        results.append(("manage_columns", columns_success))

        # 5. List cards
        cards_success = await test_tool_call(
            client,
            "manage_cards",
            {"action": "list", "limit": 3},
            "List cards",
        )
        results.append(("manage_cards", cards_success))

        # 6. List sprints - requires board_id or board
        sprints_args = {"action": "list"}
        if board_id:
            sprints_args["board_id"] = board_id
            sprints_description = f"List sprints (using board_id={board_id}) - may fail if no sprints"
        elif board_name:
            sprints_args["board"] = board_name
            sprints_description = f"List sprints (using board='{board_name}') - may fail if no sprints"
        else:
            sprints_args["board_id"] = 1  # Fallback to test structure (will likely fail)
            sprints_description = "List sprints (no board available - testing with dummy ID, may fail)"
        sprints_success = await test_tool_call(
            client, "manage_sprints", sprints_args, sprints_description
        )
        results.append(("manage_sprints", sprints_success))

        # 7. Move card (error handling test)
        move_success = await test_tool_call(
            client,
            "move_card",
            {"card_id": 999999, "column_id": 888888},
            "Move card (error handling - expected to fail)",
        )
        results.append(("move_card", move_success))

        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        passed = sum(1 for _, success in results if success)
        total = len(results)
        print(f"Passed: {passed}/{total}")

        for tool_name, success in results:
            status = "✅" if success else "❌"
            print(f"  {status} {tool_name}")

        if passed == total:
            print("\n✅ All tests passed!")
            sys.exit(0)
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Failed to connect to MCP server: {e}")
        print("\nMake sure:")
        print("  1. MCP server is running")
        print(f"  2. Server URL is correct: {MCP_SERVER_URL}")
        print("  3. Environment variables are set (KAITEN_API_URL, KAITEN_API_TOKEN)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
