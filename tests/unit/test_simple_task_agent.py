"""Tests for the minimal task-only agent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from chat_bot.models import Message
from chat_bot.simple_task_agent import SimpleTaskAgent


class TestSimpleTaskAgent:
    @pytest.mark.asyncio
    async def test_run_uses_only_task_tools_and_last_ten_messages(self) -> None:
        agent = SimpleTaskAgent(llm=MagicMock())
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Созданы две карточки.")],
                "final_response": "Созданы две карточки.",
            }
        )
        history = [
            Message(
                message_id=index,
                timestamp=f"2026-06-15T10:{index:02d}:00",
                sender_name="user",
                text=f"message {index}",
            )
            for index in range(1, 13)
        ]
        tools = [
            SimpleNamespace(name="manage_cards"),
            SimpleNamespace(name="move_card"),
            SimpleNamespace(name="manage_boards"),
        ]

        with patch.object(agent, "_build_graph", return_value=graph) as build_graph:
            result = await agent.run("создай задачи по диалогу", tools, history)

        assert result == "Созданы две карточки."
        selected = build_graph.call_args.kwargs["tools"]
        assert [tool.name for tool in selected] == ["manage_cards", "move_card"]
        input_messages = graph.ainvoke.await_args.args[0]["messages"]
        assert len(input_messages) == 11
        assert input_messages[0].content.startswith("[3]")
        assert input_messages[-1].content == "Текущий запрос: создай задачи по диалогу"

    def test_system_prompt_requires_only_title_and_board(self) -> None:
        prompt = SimpleTaskAgent._system_prompt([])

        assert "обязательны только название и доска" in prompt
        assert "Описания формируй самостоятельно" not in prompt
        assert "Описание формируй самостоятельно" in prompt
        assert "спроси только доску" in prompt
