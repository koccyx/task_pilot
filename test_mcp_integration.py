#!/usr/bin/env python3
"""Test script for MCP tools integration with Assistant."""

import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_mcp_tools():
    """Test MCP tools integration."""
    from chat_bot.assistant import Assistant
    from chat_bot.mcp_server.tools.langchain_adapter import MCPToolsAdapter

    logger.info("Initializing Assistant...")
    assistant = Assistant()

    logger.info("Initializing MCP tools adapter...")
    try:
        adapter = MCPToolsAdapter()
        tools = adapter.get_langchain_tools()
        logger.info(f"Loaded {len(tools)} MCP tools:")
        for tool in tools:
            logger.info(f"  - {tool.name}: {tool.description}")
    except Exception as e:
        logger.error(f"Failed to initialize MCP tools: {e}")
        logger.info("This is expected if KAITEN_API_URL/TOKEN are not configured")
        return

    # Test simple message without tool call
    logger.info("\n=== Test 1: Simple message ===")
    try:
        response = await assistant.chat_with_tools(
            message="Привет! Как дела?",
            tools=tools,
        )
        logger.info(f"Response: {response}")
    except Exception as e:
        logger.error(f"Test 1 failed: {e}")

    # Test message that should trigger tool call
    logger.info("\n=== Test 2: Create card request ===")
    try:
        response = await assistant.chat_with_tools(
            message="Создай карточку с названием 'Тестовая задача' на доске 123",
            tools=tools,
        )
        logger.info(f"Response: {response}")
    except Exception as e:
        logger.error(f"Test 2 failed: {e}")

    logger.info("\n=== Tests completed ===")


if __name__ == "__main__":
    asyncio.run(test_mcp_tools())


