"""Tests for the minimal task-only agent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from chat_bot.models import Message, UserProfile
from chat_bot.rag.agent_context import RagContext
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
        assert graph.ainvoke.await_args.args[0]["input_message_count"] == 11

    @pytest.mark.asyncio
    async def test_run_adds_rag_context_to_system_prompt_when_needed(self) -> None:
        rag_builder = MagicMock()
        rag_builder.build_context = AsyncMock(
            return_value=RagContext(
                used=True,
                query="регламент отпусков",
                results=[],
                context_block="\n\n## Контекст из внутренней базы знаний\nРегламент",
                reason="docs request",
            )
        )
        agent = SimpleTaskAgent(llm=MagicMock(), rag_context_builder=rag_builder)
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Ответ по регламенту.")],
                "final_response": "Ответ по регламенту.",
            }
        )
        tools = [SimpleNamespace(name="manage_cards")]

        with patch.object(agent, "_build_graph", return_value=graph) as build_graph:
            result = await agent.run(
                "что написано в регламенте по отпускам?",
                tools,
                history=[],
            )

        assert result == "Ответ по регламенту."
        rag_builder.build_context.assert_awaited_once()
        system_prompt = build_graph.call_args.kwargs["system_prompt"]
        assert "Контекст из внутренней базы знаний" in system_prompt
        assert "Регламент" in system_prompt

    @pytest.mark.asyncio
    async def test_run_does_not_add_rag_context_when_gate_skips_it(self) -> None:
        rag_builder = MagicMock()
        rag_builder.build_context = AsyncMock(
            return_value=RagContext(
                used=False,
                query="",
                results=[],
                context_block="",
                reason="no docs markers",
            )
        )
        agent = SimpleTaskAgent(llm=MagicMock(), rag_context_builder=rag_builder)
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [AIMessage(content="Создана карточка.")],
                "final_response": "Создана карточка.",
            }
        )
        tools = [SimpleNamespace(name="manage_cards")]

        with patch.object(agent, "_build_graph", return_value=graph) as build_graph:
            result = await agent.run("создай карточку", tools, history=[])

        assert result == "Создана карточка."
        system_prompt = build_graph.call_args.kwargs["system_prompt"]
        assert "no docs markers" not in system_prompt
        assert "Регламент" not in system_prompt

    @pytest.mark.asyncio
    async def test_run_does_not_return_bot_message_from_history(self) -> None:
        agent = SimpleTaskAgent(llm=MagicMock())
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    HumanMessage(content="какие задачки есть на доске Основная доска?"),
                    AIMessage(
                        content="[1141] @dialog_manager_bot: Да, я здесь! Чем могу помочь?"
                    ),
                    HumanMessage(
                        content=(
                            "Текущий запрос: какие задачки есть на доске "
                            "Основная доска?"
                        )
                    ),
                    AIMessage(content=""),
                ],
                "final_response": "",
            }
        )
        history = [
            Message(
                message_id=1141,
                timestamp="2026-06-19T20:07:12",
                sender_name="@dialog_manager_bot",
                text="Да, я здесь! Чем могу помочь?",
                is_bot_message=True,
            )
        ]
        tools = [SimpleNamespace(name="manage_cards")]

        with patch.object(agent, "_build_graph", return_value=graph):
            result = await agent.run(
                "какие задачки есть на доске Основная доска?",
                tools,
                history,
            )

        assert result == "Не удалось получить результат."

    @pytest.mark.asyncio
    async def test_run_falls_back_to_tool_result_when_model_response_is_empty(
        self,
    ) -> None:
        agent = SimpleTaskAgent(llm=MagicMock())
        graph = MagicMock()
        graph.ainvoke = AsyncMock(
            return_value={
                "messages": [
                    HumanMessage(content="Текущий запрос: какие задачки есть на мне?"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "manage_cards", "args": {}, "id": "call_1"}
                        ],
                    ),
                    ToolMessage(
                        content=(
                            "Found 2 cards:\n"
                            "• Познакомьтесь с Kaiten на практике (ID: 66036670)\n"
                            "• Kaiten: с чего начать (ID: 66036672)"
                        ),
                        tool_call_id="call_1",
                    ),
                    AIMessage(content=""),
                ],
                "final_response": "",
            }
        )
        tools = [SimpleNamespace(name="manage_cards")]

        with patch.object(agent, "_build_graph", return_value=graph):
            result = await agent.run("какие задачки есть на мне?", tools)

        assert "Found 2 cards" in result
        assert "66036670" in result

    def test_system_prompt_requires_only_title_and_board(self) -> None:
        prompt = SimpleTaskAgent._system_prompt([])

        assert "ответов по внутренней базе знаний" in prompt
        assert "Контекст из внутренней базы знаний" in prompt
        assert "можешь отвечать на вопросы пользователя" in prompt
        assert "обязательны только название и доска" in prompt
        assert "Описания формируй самостоятельно" not in prompt
        assert "Описание формируй самостоятельно" in prompt
        assert "Основная доска" in prompt
        assert "jmlc" in prompt
        assert "Не спрашивай доску для новых задач" in prompt
        assert "Если пользователь явно указал другую доску" in prompt

    def test_system_prompt_explains_how_to_list_tasks_by_assignee(self) -> None:
        current_user = UserProfile(
            chat_id=123,
            telegram_user_id=456,
            telegram_username="stepan",
            telegram_display_name="Степан",
            introduced_name="Степан",
            kaiten_user_name="Stepan1922",
            kaiten_user_id=1056226,
        )

        prompt = SimpleTaskAgent._system_prompt([current_user], current_user)

        assert 'manage_cards с action="list"' in prompt
        assert "owner_id" in prompt
        assert "Для просмотра по исполнителю доска не обязательна" in prompt
        assert "Запрос просмотра не должен создавать" in prompt
        assert "Kaiten: Stepan1922" in prompt
        assert "Kaiten ID: 1056226" in prompt

    def test_system_prompt_explains_how_to_assign_responsible(self) -> None:
        current_user = UserProfile(
            chat_id=123,
            telegram_user_id=456,
            telegram_username="stepan",
            telegram_display_name="Степан",
            introduced_name="Степан",
            kaiten_user_name="Stepan1922",
            kaiten_user_id=1056226,
        )

        prompt = SimpleTaskAgent._system_prompt([current_user], current_user)

        assert 'manage_members с action="set_responsible"' in prompt
        assert 'manage_cards с action="search"' in prompt
        assert 'Для "назначь меня" используй текущего пользователя' in prompt
        assert "Назначай только если" in prompt
        assert "доска не обязательна" in prompt
        assert "не должен создавать новую карточку" in prompt
