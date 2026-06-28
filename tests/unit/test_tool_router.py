"""Tests for tool routing and tool-gating in Assistant."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from chat_bot.assistant import Assistant
from chat_bot.models import Message
from chat_bot.tool_router import OrchestratorPlan, RouteDecision, ToolRouter


class TestToolRouter:
    """Test suite for tool routing."""

    def test_select_tools_filters_by_route(self) -> None:
        """Card route should expose only card-related tools."""
        router = ToolRouter(llm=MagicMock())
        tools = [
            SimpleNamespace(name="manage_cards"),
            SimpleNamespace(name="manage_boards"),
            SimpleNamespace(name="manage_members"),
        ]

        selected = router.select_tools("card_operations", tools)

        assert [tool.name for tool in selected] == [
            "manage_cards",
            "manage_members",
        ]

    def test_select_tools_for_workspace_setup_excludes_non_workspace_tools(
        self,
    ) -> None:
        """Workspace setup route should expose only board/space setup tools."""
        router = ToolRouter(llm=MagicMock())
        tools = [
            SimpleNamespace(name="manage_spaces"),
            SimpleNamespace(name="manage_boards"),
            SimpleNamespace(name="manage_columns"),
            SimpleNamespace(name="move_card"),
        ]

        selected = router.select_tools("workspace_setup", tools)

        assert [tool.name for tool in selected] == [
            "manage_spaces",
            "manage_boards",
            "manage_columns",
        ]

    @pytest.mark.asyncio
    async def test_heuristic_route_fallback_for_board_setup(self) -> None:
        """Fallback should classify board setup requests into workspace route."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_boards"),
            SimpleNamespace(name="manage_columns"),
        ]

        decision = await router.route(
            message="создай доску продаж и добавь колонки",
            tools=tools,
        )

        assert decision.route == "workspace_setup"

    @pytest.mark.asyncio
    async def test_heuristic_route_fallback_for_card_operations(self) -> None:
        """Fallback should treat columns, movement and decomposition as card operations."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_columns"),
            SimpleNamespace(name="move_card"),
            SimpleNamespace(name="break_into_tasks"),
        ]

        decision = await router.route(
            message="создай колонку done и потом разбей эту задачу на подзадачи",
            tools=tools,
        )

        assert decision.route == "card_operations"

    @pytest.mark.asyncio
    async def test_heuristic_orchestrate_recovers_board_summary_from_history(
        self,
    ) -> None:
        """Orchestrator fallback should reuse resolved board from prior clarification."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_boards"),
            SimpleNamespace(name="manage_cards"),
        ]

        plan = await router.orchestrate(
            history=(
                "Ассистент: Какую доску вы хотите получить сводку?\n"
                "Пользователь: по доске storyboard"
            ),
            message="получить по ней сводку",
            tools=tools,
        )

        assert plan.route == "reporting"
        assert plan.worker == "reporting_worker"
        assert plan.user_goal == "summary"
        assert plan.entity_type == "board"
        assert plan.entity_name == "storyboard"
        assert plan.needs_clarification is False

    @pytest.mark.asyncio
    async def test_heuristic_orchestrate_ignores_assistant_question_as_entity_name(
        self,
    ) -> None:
        """Assistant clarification text must not be mistaken for a board name."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_boards"),
        ]

        plan = await router.orchestrate(
            history="Ассистент: Какую доску вы хотите получить сводку?",
            message="сделай сводку",
            tools=tools,
        )

        assert plan.entity_name is None
        assert plan.needs_clarification is True

    @pytest.mark.asyncio
    async def test_heuristic_orchestrate_recovers_board_from_demonstrative_reference(
        self,
    ) -> None:
        """Fallback should resolve 'эта доска' to the last user-provided board."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_boards"),
            SimpleNamespace(name="manage_cards"),
        ]

        plan = await router.orchestrate(
            history=(
                "Ассистент: Какую доску использовать?\n"
                "Пользователь: доска storyboard"
            ),
            message="покажи статус по этой доске",
            tools=tools,
        )

        assert plan.route == "reporting"
        assert plan.entity_type == "board"
        assert plan.entity_name == "storyboard"
        assert plan.needs_clarification is False

    @pytest.mark.asyncio
    async def test_heuristic_orchestrate_prefers_card_operations_for_column_move_requests(
        self,
    ) -> None:
        """Create/move requests around columns must not be routed into reporting."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_columns"),
            SimpleNamespace(name="move_card"),
            SimpleNamespace(name="manage_cards"),
        ]

        plan = await router.orchestrate(
            history="Пользователь: доска storyboard",
            message="создай новую колонку in progress на доске storyboard и передвинь туда карточку 1",
            tools=tools,
        )

        assert plan.route == "card_operations"
        assert plan.worker == "card_worker"
        assert plan.user_goal in {"create_or_update", "update"}

    @pytest.mark.asyncio
    async def test_heuristic_orchestrate_routes_board_sync_from_dialog_to_workspace(
        self,
    ) -> None:
        """Dialog-driven board updates should stay in a mutating route."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_boards"),
            SimpleNamespace(name="manage_columns"),
        ]

        plan = await router.orchestrate(
            history=(
                "Пользователь: доска roadmap\n"
                "Пользователь: нужно обновить описание и добавить колонку blocked"
            ),
            message="обнови ее согласно диалогу",
            tools=tools,
        )

        assert plan.route == "workspace_setup"
        assert plan.worker == "workspace_worker"
        assert plan.user_goal in {"create_or_update", "update"}
        assert plan.entity_type == "board"
        assert plan.entity_name == "roadmap"
        assert plan.needs_clarification is False

    @pytest.mark.asyncio
    async def test_heuristic_orchestrate_routes_card_sync_from_dialog_to_card_operations(
        self,
    ) -> None:
        """Dialog-driven card updates should not fall back to general assistant."""
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        router = ToolRouter(llm=llm)
        tools = [
            SimpleNamespace(name="manage_cards"),
            SimpleNamespace(name="manage_members"),
            SimpleNamespace(name="move_card"),
        ]

        plan = await router.orchestrate(
            history=(
                "Пользователь: задача onboarding\n"
                "Пользователь: нужно сменить ответственного на Алексея и обновить описание"
            ),
            message="синхронизируй ее по обсуждению",
            tools=tools,
        )

        assert plan.route == "card_operations"
        assert plan.worker == "card_worker"
        assert plan.user_goal in {"create_or_update", "update"}
        assert plan.entity_type == "card"
        assert plan.entity_name == "onboarding"
        assert plan.needs_clarification is False

    def test_select_tools_for_card_operations_includes_columns_for_mixed_request(
        self,
    ) -> None:
        """Card operations route must allow mixed column + card execution."""
        router = ToolRouter(llm=MagicMock())
        tools = [
            SimpleNamespace(name="manage_columns"),
            SimpleNamespace(name="manage_cards"),
            SimpleNamespace(name="move_card"),
            SimpleNamespace(name="manage_members"),
        ]

        selected = router.select_tools("card_operations", tools)

        assert [tool.name for tool in selected] == [
            "manage_columns",
            "manage_cards",
            "move_card",
            "manage_members",
        ]


class TestAssistantToolGating:
    """Test suite for Assistant router integration."""

    @staticmethod
    def _dummy_tool(name: str):
        async def _tool() -> str:
            """Dummy tool for LangGraph tests."""
            return "ok"

        _tool.__name__ = name
        return _tool

    def _make_assistant(self) -> Assistant:
        assistant = Assistant.__new__(Assistant)
        assistant.llm = MagicMock()
        assistant.tool_router = MagicMock()
        assistant.chat_with_tools_prompt_template = "System time: {current_datetime}"
        assistant._log_agent_trace = MagicMock()
        return assistant

    @pytest.mark.asyncio
    async def test_chat_with_tools_runs_langgraph_and_returns_final_response(
        self,
    ) -> None:
        """chat_with_tools should invoke compiled graph and return final output."""
        assistant = self._make_assistant()
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Готово")],
                "final_response": "Готово",
            }
        )

        with patch.object(
            assistant, "_build_chat_graph", return_value=fake_graph
        ) as build_graph:
            result = await assistant.chat_with_tools(
                message="создай задачу и назначь ответственного",
                tools=[SimpleNamespace(name="manage_cards")],
            )

        assert result == "Готово"
        build_graph.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_tools_appends_only_relevant_scenarios(self) -> None:
        """Matched scenarios should be appended only for matching requests."""
        assistant = self._make_assistant()
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Готово")],
                "final_response": "Готово",
            }
        )

        with (
            patch.object(
                assistant, "_build_chat_graph", return_value=fake_graph
            ) as build_graph,
            patch(
                "chat_bot.assistant.load_relevant_scenarios",
                return_value="\n\n## 📋 Релевантные сценарии\nscenario",
            ) as load_relevant,
        ):
            await assistant.chat_with_tools(
                message="создай доску продаж и добавь колонки",
                tools=[SimpleNamespace(name="manage_boards")],
            )

        load_relevant.assert_called_once_with(
            message="создай доску продаж и добавь колонки"
        )
        assert "Релевантные сценарии" in build_graph.call_args.kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_chat_with_tools_trims_history_before_agent_run(self) -> None:
        """History passed to the graph should be capped to the configured size."""
        assistant = self._make_assistant()
        fake_graph = MagicMock()
        fake_graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Готово")],
                "final_response": "Готово",
            }
        )

        history = [
            Message(
                message_id=index,
                timestamp=f"2025-01-01T10:{index:02d}:00",
                sender_name="user",
                text=f"msg {index}",
                is_bot_message=bool(index % 2),
            )
            for index in range(1, 6)
        ]

        with (
            patch.object(assistant, "_build_chat_graph", return_value=fake_graph),
            patch.dict(os.environ, {"AGENT_HISTORY_MESSAGE_LIMIT": "2"}),
        ):
            await assistant.chat_with_tools(
                message="покажи задачи",
                tools=[SimpleNamespace(name="manage_cards")],
                history=history,
            )

        graph_input = fake_graph.ainvoke.await_args.args[0]
        assert len(graph_input["messages"]) == 3
        assert graph_input["messages"][0].content == "msg 4"
        assert graph_input["messages"][1].content == "msg 5"
        assert graph_input["messages"][2].content == "покажи задачи"

    def test_select_history_for_agent_keeps_only_referenced_bot_messages(self) -> None:
        """Unrelated stale bot replies should not be injected into the next run."""
        history = [
            Message(
                message_id=1,
                timestamp="2025-01-01T10:00:00",
                sender_name="bot",
                text="старый ответ",
                is_bot_message=True,
            ),
            Message(
                message_id=2,
                timestamp="2025-01-01T10:01:00",
                sender_name="user",
                text="старый вопрос",
            ),
            Message(
                message_id=3,
                timestamp="2025-01-01T10:02:00",
                sender_name="bot",
                text="актуальный ответ",
                is_bot_message=True,
            ),
            Message(
                message_id=4,
                timestamp="2025-01-01T10:03:00",
                sender_name="user",
                text="уточнение по ответу",
                reply_to_message_id=3,
            ),
        ]

        filtered = Assistant._select_history_for_agent(history)

        assert [msg.message_id for msg in filtered] == [2, 3, 4]

    @pytest.mark.asyncio
    async def test_build_chat_graph_routes_to_direct_answer_without_tools(self) -> None:
        """Informational route should answer directly without tool execution."""
        assistant = self._make_assistant()
        assistant.tool_router.orchestrate = AsyncMock(
            return_value=OrchestratorPlan(
                route="general_assistant",
                worker="general_worker",
                confidence=0.87,
                user_goal="general_question",
                task_brief="объясни разницу между доской и пространством",
            )
        )
        assistant.tool_router.select_tools = MagicMock(return_value=[])
        assistant.tool_router.build_executor_context = MagicMock(return_value="")
        assistant.tool_router.build_worker_context = MagicMock(return_value="")
        assistant.direct_answer_llm = MagicMock()
        assistant.direct_answer_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="Ответ без тулов")
        )
        assistant.llm.ainvoke = AsyncMock()

        graph = assistant._build_chat_graph(
            tools=[self._dummy_tool("manage_boards")],
            system_prompt="System",
        )
        result = await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(content="объясни разницу между доской и пространством")
                ],
                "route": "",
                "requires_tool": False,
                "route_confidence": 0.0,
                "worker": "",
                "user_goal": "",
                "entity_type": "",
                "entity_name": "",
                "time_period": "",
                "missing_fields": [],
                "task_brief": "",
                "selected_tool_names": [],
                "tool_validation_failed": False,
                "final_response": "",
            }
        )

        assert result["final_response"] == "Ответ без тулов"
        assistant.direct_answer_llm.ainvoke.assert_awaited_once()
        assistant.llm.ainvoke.assert_not_awaited()
