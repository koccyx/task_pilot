"""A small single-agent flow for creating and updating Kaiten tasks."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Annotated, Any, List, Optional, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .logging_config import get_logger, sanitize_for_logging
from .models import Message, UserProfile
from .rag.agent_context import AgentRagContextBuilder

logger = get_logger(__name__)

TASK_TOOL_NAMES = {
    "manage_cards",
    "manage_members",
    "move_card",
    "manage_comments",
}

DEFAULT_TASK_SPACE_NAME = "jmlc"
DEFAULT_TASK_BOARD_NAME = "Основная доска"


class TaskAgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add_messages]
    final_response: str
    input_message_count: int


class SimpleTaskAgent:
    """One ReAct agent with only task-related Kaiten tools."""

    def __init__(
        self,
        llm: Any,
        rag_context_builder: Optional[AgentRagContextBuilder] = None,
        allowed_tool_names: Optional[set[str]] = TASK_TOOL_NAMES,
    ) -> None:
        self.llm = llm
        self.rag_context_builder = rag_context_builder
        self.allowed_tool_names = allowed_tool_names

    async def run(
        self,
        message: str,
        tools: List[Any],
        history: Optional[List[Message]] = None,
        user_profiles: Optional[List[UserProfile]] = None,
        current_user: Optional[UserProfile] = None,
    ) -> str:
        """Use the last ten messages to view, create, or update Kaiten tasks."""
        run_id = uuid4().hex
        started_at = time.perf_counter()
        history = (history or [])[-10:]
        user_profiles = user_profiles or []
        selected_tools = (
            list(tools)
            if self.allowed_tool_names is None
            else [
                tool
                for tool in tools
                if getattr(tool, "name", None) in self.allowed_tool_names
            ]
        )
        logger.info(
            "Simple task agent started",
            extra={
                "event_type": "simple_task_agent_started",
                "agent_run_id": run_id,
                "history_message_count": len(history),
                "tool_names": [
                    getattr(tool, "name", str(tool)) for tool in selected_tools
                ],
                "user_message": sanitize_for_logging(message, max_length=1000),
            },
        )

        if not selected_tools:
            return "Инструменты для работы с задачами не настроены."

        system_prompt = self._system_prompt(user_profiles, current_user)
        rag_context = await self._build_rag_context(message=message, history=history)
        if rag_context:
            system_prompt += rag_context

        graph = self._build_graph(
            tools=selected_tools,
            system_prompt=system_prompt,
            run_id=run_id,
        )
        input_messages = self._history_messages(history)
        input_messages.append(HumanMessage(content=f"Текущий запрос: {message}"))
        try:
            result = await graph.ainvoke(
                {
                    "messages": input_messages,
                    "final_response": "",
                    "input_message_count": len(input_messages),
                },
                config={
                    "recursion_limit": int(
                        os.getenv("SIMPLE_TASK_AGENT_RECURSION_LIMIT", "30")
                    )
                },
            )
            generated_messages = result.get("messages", [])[len(input_messages) :]
            response = (
                result.get("final_response", "")
                or self._last_ai_content(generated_messages)
                or self._last_tool_content(generated_messages)
            )
            logger.info(
                "Simple task agent completed",
                extra={
                    "event_type": "simple_task_agent_completed",
                    "agent_run_id": run_id,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "final_response": sanitize_for_logging(response, max_length=2000),
                },
            )
            return response or "Не удалось получить результат."
        except Exception as exc:
            logger.error(
                "Simple task agent failed: %s",
                exc,
                exc_info=True,
                extra={
                    "event_type": "simple_task_agent_failed",
                    "agent_run_id": run_id,
                    "error_type": type(exc).__name__,
                    "error_message": sanitize_for_logging(str(exc), max_length=1000),
                },
            )
            return f"Ошибка при работе с задачами: {exc}"

    async def _build_rag_context(self, message: str, history: List[Message]) -> str:
        if os.getenv("RAG_AGENT_ENABLED", "true").lower() != "true":
            return ""

        builder = self.rag_context_builder
        if builder is None:
            builder = AgentRagContextBuilder(llm=self.llm)
            self.rag_context_builder = builder

        context = await builder.build_context(message=message, history=history)
        return context.context_block if context.used else ""

    def _build_graph(self, tools: List[Any], system_prompt: str, run_id: str) -> Any:
        graph = StateGraph(TaskAgentState)
        tool_node = ToolNode(tools=tools, handle_tool_errors=True)

        async def agent_step(state: TaskAgentState) -> TaskAgentState:
            response = await self.llm.bind_tools(tools).ainvoke(
                [SystemMessage(content=system_prompt)] + state["messages"]
            )
            logger.info(
                "Simple task agent step",
                extra={
                    "event_type": "simple_task_agent_step",
                    "agent_run_id": run_id,
                    "tool_calls": sanitize_for_logging(
                        getattr(response, "tool_calls", []) or [], max_length=3000
                    ),
                    "content": sanitize_for_logging(
                        getattr(response, "content", ""), max_length=2000
                    ),
                },
            )
            return {"messages": [response]}

        def after_agent(state: TaskAgentState) -> str:
            last = state["messages"][-1]
            if isinstance(last, AIMessage) and getattr(last, "tool_calls", []):
                return "tools"
            return "finalize"

        def finalize(state: TaskAgentState) -> TaskAgentState:
            generated_messages = state["messages"][
                state.get("input_message_count", 0) :
            ]
            response = self._last_ai_content(
                generated_messages
            ) or self._last_tool_content(generated_messages)
            return {"final_response": response}

        graph.add_node("agent", agent_step)
        graph.add_node("tools", tool_node)
        graph.add_node("finalize", finalize)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent", after_agent, {"tools": "tools", "finalize": "finalize"}
        )
        graph.add_edge("tools", "agent")
        graph.add_edge("finalize", END)
        return graph.compile()

    @staticmethod
    def _history_messages(history: List[Message]) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        for item in history:
            if not item.text:
                continue
            content = f"[{item.message_id}] {item.sender_name}: {item.text}"
            if item.is_bot_message:
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))
        return messages

    @staticmethod
    def _last_ai_content(messages: List[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                content = getattr(message, "content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""

    @staticmethod
    def _last_tool_content(messages: List[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, ToolMessage):
                content = getattr(message, "content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""

    @staticmethod
    def _system_prompt(
        user_profiles: List[UserProfile],
        current_user: Optional[UserProfile] = None,
    ) -> str:
        users = []
        for profile in user_profiles:
            users.append(
                f"- Telegram: {profile.telegram_username or profile.introduced_name}; "
                f"Kaiten: {profile.kaiten_user_name or profile.introduced_name}; "
                f"Kaiten ID: {profile.kaiten_user_id or 'не указан'}"
            )
        user_directory = "\n".join(users) or "- соответствия пользователей отсутствуют"
        if current_user is None:
            current_user_identity = "- текущий пользователь не определён"
        else:
            current_user_identity = (
                f"- Telegram: "
                f"{current_user.telegram_username or current_user.introduced_name}; "
                f"Kaiten: "
                f"{current_user.kaiten_user_name or current_user.introduced_name}; "
                f"Kaiten ID: {current_user.kaiten_user_id or 'не указан'}"
            )
        return f"""
Ты агент для работы с задачами Kaiten и ответов по внутренней базе знаний.

Тебе передаются последние 10 сообщений диалога и текущий запрос.
Используй их как единый контекст и выполняй запрос до конца.

Правила:
- Если в системном сообщении есть раздел "Контекст из внутренней базы знаний",
  можешь отвечать на вопросы пользователя по этому разделу без вызова инструментов.
- Для вопросов по внутренним документам используй только предоставленный RAG-контекст.
  Если в нём нет ответа, прямо скажи, что в загруженных документах не нашлось
  достаточно информации.
- Не отвечай на вопрос по документам фразой, что ты можешь работать только с Kaiten:
  RAG-контекст является разрешённым источником для информационного ответа.
- Запросы "что на мне", "мои задачи", "покажи мои карточки" и аналогичные означают:
  вызови manage_cards с action="list" и фильтром текущего пользователя.
- Запросы о задачах другого человека означают: найди человека в каталоге пользователей
  и вызови manage_cards с action="list" и его фильтром.
- Для фильтра по исполнителю используй owner_id, если Kaiten ID известен, иначе owner_name
  с именем пользователя в Kaiten. Для просмотра по исполнителю доска не обязательна.
- Запрос просмотра не должен создавать, изменять, перемещать или удалять карточки.
- Если указанного человека нельзя однозначно найти в каталоге, уточни только человека.
- В ответе на просмотр кратко перечисли найденные карточки и их существенные поля.
- Запросы "назначь меня ответственным", "назначь Степана на задачу" и аналогичные
  означают назначение ответственного через manage_members с action="set_responsible".
- Для "назначь меня" используй текущего пользователя. Для другого человека найди
  его в каталоге пользователей. Передавай owner_id, если Kaiten ID известен,
  иначе owner_name с именем пользователя в Kaiten.
- Для назначения на существующую карточку нужен card_id. Если ID неизвестен, найди
  карточку через manage_cards с action="search" по её названию. Назначай только если
  найдена ровно одна подходящая карточка; иначе уточни карточку.
- Для назначения ответственного на существующую карточку доска не обязательна.
- Запрос назначения не должен создавать новую карточку, если пользователь явно
  не попросил одновременно создать её.
- Создавай и обновляй карточки, пиши им содержательные описания из контекста диалога.
- Запросы вроде "поставь задачки по диалогу" означают: найди в сообщениях намерения,
  договорённости и поручения, затем создай отдельную карточку для каждого пункта.
- Фразы "я хочу ..." являются задачами; автор сообщения является исполнителем.
- Для создания карточки обязательны только название и доска.
- Если пользователь просит поставить, дать или создать задачу и не указал доску
  явно, создавай карточку на доске "{DEFAULT_TASK_BOARD_NAME}" в пространстве
  "{DEFAULT_TASK_SPACE_NAME}".
- Если пользователь явно указал другую доску или пространство, используй именно
  то, что указал пользователь.
- Описание формируй самостоятельно из сообщения и связанного контекста.
- Колонка, срок и исполнитель необязательны. Не спрашивай их, если пользователь
  явно не потребовал конкретное значение.
- Не спрашивай доску для новых задач, когда применим дефолт
  "{DEFAULT_TASK_SPACE_NAME}" / "{DEFAULT_TASK_BOARD_NAME}".
- При создании в колонке сначала создай карточку, затем перемести её через move_card.
- При создании карточки с ответственным сначала создай карточку, затем используй
  manage_members с action="set_responsible" и ID созданной карточки.
- Не выдумывай доску, пользователя, срок или результат инструмента.
- В финальном ответе дай только обычный краткий итог без внутренних статусов.
- Если человек пишет "Я сделал" то перемещай задачку в колонку сделано или другую конечную колонку на доске означающую завершение задачи.
- Если человек пишет "Я начал делать" значит перемести задачку на колонку В процессе или другую с таким же смыслом.

Каталог пользователей:
{user_directory}

Текущий пользователь:
{current_user_identity}

Текущая дата: {datetime.now().date().isoformat()}
""".strip()
