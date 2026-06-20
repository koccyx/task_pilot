"""Tests for structured logging instrumentation."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_bot.logging_config import SimpleJSONFormatter
from chat_bot.mcp_server.client.mcp_client import KaitenMCPClient, MCPClientConfig


class TestStructuredLogging:
    """Tests for generic structured logging fields."""

    def test_simple_json_formatter_keeps_extra_fields(self) -> None:
        """Formatter should preserve arbitrary extra fields in JSON logs."""
        formatter = SimpleJSONFormatter()
        record = logging.LogRecord(
            name="chat_bot.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="Tool request started",
            args=(),
            exc_info=None,
        )
        record.event_type = "tool_request_started"  # type: ignore[attr-defined]
        record.tool_name = "manage_cards"  # type: ignore[attr-defined]
        record.tool_args = {"action": "list"}  # type: ignore[attr-defined]

        payload = json.loads(formatter.format(record))

        assert payload["event_type"] == "tool_request_started"
        assert payload["tool_name"] == "manage_cards"
        assert payload["tool_args"] == {"action": "list"}


class TestMCPClientLogging:
    """Tests for MCP client tool-call logging."""

    def test_extract_text_from_serialized_mcp_payload(self) -> None:
        """Serialized MCP-style dict payloads should expose only content text."""
        fake_result = MagicMock()
        fake_result.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": "Found 1 cards:\n• Test card (ID: 1)",
                            }
                        ],
                        "structured_content": [
                            {
                                "id": 1,
                                "owner": {
                                    "avatar_initials_url": "data:image/png;base64,AAAA"
                                },
                            }
                        ],
                        "meta": {"operation": "list"},
                    },
                    ensure_ascii=False,
                )
            )
        ]

        result = KaitenMCPClient._extract_text_from_result(fake_result)

        assert result == "Found 1 cards:\n• Test card (ID: 1)"
        assert "structured_content" not in result
        assert "base64" not in result

    @pytest.mark.asyncio
    async def test_tool_function_logs_start_and_completion(self) -> None:
        """LangChain tool wrapper should log start and completion events."""
        client = KaitenMCPClient(
            MCPClientConfig(server_url="http://localhost:8000/mcp")
        )

        fake_result = MagicMock()
        fake_result.isError = False
        fake_result.content = [MagicMock(text="Success")]

        transport_client = MagicMock()
        transport_client.__aenter__ = AsyncMock(return_value=transport_client)
        transport_client.__aexit__ = AsyncMock(return_value=None)
        transport_client.call_tool = AsyncMock(return_value=fake_result)

        client._create_client = MagicMock(return_value=transport_client)  # type: ignore[method-assign]
        tool_func = client._create_tool_function("manage_cards")

        with patch("chat_bot.mcp_server.client.mcp_client.logger") as mock_logger:
            result = await tool_func(action="list")

        assert result == "Success"
        assert mock_logger.info.call_count >= 2

        started_call = mock_logger.info.call_args_list[0]
        completed_call = mock_logger.info.call_args_list[-1]

        assert started_call.args[0] == "Tool request started"
        assert started_call.kwargs["extra"]["tool_name"] == "manage_cards"
        assert started_call.kwargs["extra"]["tool_args"] == {"action": "list"}

        assert completed_call.args[0] == "Tool request completed"
        assert completed_call.kwargs["extra"]["tool_status"] == "success"
        assert completed_call.kwargs["extra"]["tool_result"] == "Success"

    @pytest.mark.asyncio
    async def test_tool_function_returns_only_content_text_from_serialized_payload(
        self,
    ) -> None:
        """LangChain tool wrapper should not return structured_content JSON."""
        client = KaitenMCPClient(
            MCPClientConfig(server_url="http://localhost:8000/mcp")
        )

        fake_result = MagicMock()
        fake_result.isError = False
        fake_result.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": "Found 1 cards:\n• Test card (ID: 1)",
                            }
                        ],
                        "structured_content": [
                            {
                                "id": 1,
                                "owner": {
                                    "avatar_initials_url": "data:image/png;base64,AAAA"
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        ]

        transport_client = MagicMock()
        transport_client.__aenter__ = AsyncMock(return_value=transport_client)
        transport_client.__aexit__ = AsyncMock(return_value=None)
        transport_client.call_tool = AsyncMock(return_value=fake_result)

        client._create_client = MagicMock(return_value=transport_client)  # type: ignore[method-assign]
        tool_func = client._create_tool_function("manage_cards")

        result = await tool_func(action="list")

        assert result == "Found 1 cards:\n• Test card (ID: 1)"
        assert "structured_content" not in result
        assert "base64" not in result

    @pytest.mark.asyncio
    async def test_tool_function_drops_none_arguments_before_call(self) -> None:
        """Optional arguments with None should not be forwarded to MCP."""
        client = KaitenMCPClient(
            MCPClientConfig(server_url="http://localhost:8000/mcp")
        )

        fake_result = MagicMock()
        fake_result.isError = False
        fake_result.content = [MagicMock(text="Success")]

        transport_client = MagicMock()
        transport_client.__aenter__ = AsyncMock(return_value=transport_client)
        transport_client.__aexit__ = AsyncMock(return_value=None)
        transport_client.call_tool = AsyncMock(return_value=fake_result)

        client._create_client = MagicMock(return_value=transport_client)  # type: ignore[method-assign]
        tool_func = client._create_tool_function("manage_cards")

        await tool_func(action="list", asap=None, limit=5, skip=0)

        transport_client.call_tool.assert_awaited_once_with(
            "manage_cards",
            {"action": "list", "limit": 5, "skip": 0},
        )
