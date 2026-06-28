"""Tool routing for narrowing MCP tool access before agent execution."""

from __future__ import annotations

import logging
import time
import re
from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Iterable, List, Optional

from pydantic import BaseModel, Field

from .logging_config import sanitize_for_logging
from .metrics import record_ai_request

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolRoute:
    """Static route definition with a domain-specific tool whitelist."""

    route: str
    description: str
    tool_names: tuple[str, ...]


@dataclass(frozen=True)
class WorkerProfile:
    """Worker definition used by the orchestrator."""

    worker: str
    description: str
    routes: tuple[str, ...]


ROUTES: tuple[ToolRoute, ...] = (
    ToolRoute(
        route="reporting",
        description=("Сводки, статусы и отчёты по доскам, задачам и команде."),
        tool_names=(
            "manage_boards",
            "manage_cards",
            "manage_comments",
            "manage_users",
            "manage_members",
        ),
    ),
    ToolRoute(
        route="workspace_setup",
        description=(
            "Пространства, доски, колонки и первичная настройка структуры работы."
        ),
        tool_names=(
            "manage_spaces",
            "manage_boards",
            "manage_columns",
            "manage_tags",
        ),
    ),
    ToolRoute(
        route="card_operations",
        description=(
            "Карточки, комментарии, перемещение, назначение ответственных, теги, "
            "тайм-логи и массовые действия по задачам."
        ),
        tool_names=(
            "manage_columns",
            "manage_cards",
            "manage_comments",
            "move_card",
            "manage_members",
            "manage_tags",
            "manage_time_logs",
            "mass_update",
            "break_into_tasks",
        ),
    ),
    ToolRoute(
        route="people_and_access",
        description=(
            "Пользователи, участники карточек и пространства, роли и состав команды."
        ),
        tool_names=(
            "manage_users",
            "manage_members",
        ),
    ),
    ToolRoute(
        route="general_assistant",
        description=(
            "Объяснение, консультация, вопросы без обязательных действий в Kaiten."
        ),
        tool_names=(),
    ),
)

ROUTES_BY_NAME: dict[str, ToolRoute] = {route.route: route for route in ROUTES}
WORKERS: tuple[WorkerProfile, ...] = (
    WorkerProfile(
        worker="reporting_worker",
        description="Готовит сводки, статусы и аналитические ответы по Kaiten.",
        routes=("reporting",),
    ),
    WorkerProfile(
        worker="workspace_worker",
        description="Настраивает пространства, доски, колонки и структуру работы.",
        routes=("workspace_setup",),
    ),
    WorkerProfile(
        worker="card_worker",
        description="Работает с карточками, комментариями, перемещением и массовыми операциями.",
        routes=("card_operations",),
    ),
    WorkerProfile(
        worker="people_worker",
        description="Работает с пользователями, участниками и доступами.",
        routes=("people_and_access",),
    ),
    WorkerProfile(
        worker="general_worker",
        description="Отвечает без вызова инструментов, когда действий в Kaiten не нужно.",
        routes=("general_assistant",),
    ),
)
WORKERS_BY_NAME: dict[str, WorkerProfile] = {
    worker.worker: worker for worker in WORKERS
}
DEFAULT_WORKER_BY_ROUTE: dict[str, str] = {
    route.route: next(
        (worker.worker for worker in WORKERS if route.route in worker.routes),
        "general_worker",
    )
    for route in ROUTES
}


class RouteDecision(BaseModel):
    """Structured output from the input router."""

    route: str = Field(description="One of the known route names.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for route choice."
    )
    needs_clarification: bool = Field(
        default=False,
        description="Set true when user request is too ambiguous to execute safely.",
    )
    clarification_question: str | None = Field(
        default=None,
        description="A short Russian clarification question when needed.",
    )


class OrchestratorPlan(BaseModel):
    """History-aware orchestration result for the main agent."""

    route: str = Field(description="One of the known route names.")
    worker: str = Field(description="Worker profile that should execute the task.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for the orchestration plan."
    )
    needs_clarification: bool = Field(
        default=False,
        description="Whether the user must clarify missing data before execution.",
    )
    clarification_question: str | None = Field(
        default=None,
        description="A short Russian clarification question when needed.",
    )
    user_goal: str = Field(
        default="general_question",
        description="Normalized user intent such as summary, create, update or explain.",
    )
    entity_type: str | None = Field(
        default=None,
        description="Entity type like board, sprint, card, space, user.",
    )
    entity_name: str | None = Field(
        default=None,
        description="Concrete entity name if resolved from the dialog.",
    )
    time_period: str | None = Field(
        default=None,
        description="Requested time period if present.",
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Still missing slots required for safe execution.",
    )
    task_brief: str = Field(
        default="",
        description="Normalized task brief for the selected worker.",
    )


class ToolRouter:
    """LLM-first router with deterministic fallback for tool selection."""

    def __init__(self, llm: Any) -> None:
        self.llm = llm

    async def route(self, message: str, tools: List[Any]) -> RouteDecision:
        """Return the best route for the given message and available tools."""
        available_tool_names = self._tool_names(tools)
        available_routes = self._available_routes(available_tool_names)

        if not available_routes:
            return RouteDecision(
                route="general_assistant",
                confidence=1.0,
            )

        try:
            model = self.llm.with_structured_output(RouteDecision)
            prompt = self._build_prompt(
                message=message,
                available_routes=available_routes,
                available_tool_names=available_tool_names,
            )
            ai_started_at = time.perf_counter()
            try:
                decision: RouteDecision = await model.ainvoke(prompt)  # type: ignore[assignment]
                record_ai_request(
                    operation="tool_route",
                    model=getattr(self.llm, "model_name", None)
                    or getattr(self.llm, "model", None),
                    status="success",
                    started_at=ai_started_at,
                    response=decision,
                )
            except Exception:
                record_ai_request(
                    operation="tool_route",
                    model=getattr(self.llm, "model_name", None)
                    or getattr(self.llm, "model", None),
                    status="error",
                    started_at=ai_started_at,
                )
                raise
            normalized = self._normalize_decision(decision, available_routes)
            logger.info(
                "Tool routing via LLM: route=%s confidence=%.2f",
                normalized.route,
                normalized.confidence,
            )
            return normalized
        except Exception as exc:
            logger.warning("Tool routing fallback engaged: %s", exc)
            return self._heuristic_route(
                message=message, available_routes=available_routes
            )

    async def orchestrate(
        self,
        message: str,
        history: str,
        tools: List[Any],
    ) -> OrchestratorPlan:
        """Resolve dialog state and choose a worker for execution."""
        available_tool_names = self._tool_names(tools)
        available_routes = self._available_routes(available_tool_names)
        logger.info(
            "Orchestrator started",
            extra={
                "event_type": "orchestrator_started",
                "user_message": sanitize_for_logging(message, max_length=500),
                "dialog_history": sanitize_for_logging(history, max_length=1500),
                "available_routes": [route.route for route in available_routes],
                "available_tool_names": available_tool_names,
            },
        )

        if not available_routes:
            plan = OrchestratorPlan(
                route="general_assistant",
                worker="general_worker",
                confidence=1.0,
                task_brief=message.strip(),
            )
            self._log_orchestrator_plan(plan, source="no_routes")
            return plan

        try:
            model = self.llm.with_structured_output(OrchestratorPlan)
            prompt = self._build_orchestrator_prompt(
                history=history,
                message=message,
                available_routes=available_routes,
                available_tool_names=available_tool_names,
            )
            ai_started_at = time.perf_counter()
            try:
                plan: OrchestratorPlan = await model.ainvoke(prompt)  # type: ignore[assignment]
                record_ai_request(
                    operation="tool_orchestrate",
                    model=getattr(self.llm, "model_name", None)
                    or getattr(self.llm, "model", None),
                    status="success",
                    started_at=ai_started_at,
                    response=plan,
                )
            except Exception:
                record_ai_request(
                    operation="tool_orchestrate",
                    model=getattr(self.llm, "model_name", None)
                    or getattr(self.llm, "model", None),
                    status="error",
                    started_at=ai_started_at,
                )
                raise
            normalized = self._normalize_orchestrator_plan(
                plan, available_routes, message
            )
            self._log_orchestrator_plan(normalized, source="llm")
            return normalized
        except Exception as exc:
            logger.warning(
                "Orchestrator fallback engaged: %s",
                exc,
                extra={
                    "event_type": "orchestrator_fallback",
                    "error_message": sanitize_for_logging(str(exc), max_length=500),
                },
            )
            return self._heuristic_orchestrate(
                message=message,
                history=history,
                available_routes=available_routes,
            )

    def select_tools(self, route: str, tools: List[Any]) -> List[Any]:
        """Filter tools by route whitelist."""
        route_config = ROUTES_BY_NAME.get(route)
        if route_config is None:
            return tools

        allowed = set(route_config.tool_names)
        if not allowed:
            return []
        return [tool for tool in tools if getattr(tool, "name", None) in allowed]

    def build_executor_context(self, route: str) -> str:
        """Provide route-specific execution guardrails."""
        route_config = ROUTES_BY_NAME.get(route)
        if route_config is None:
            return ""

        if route == "general_assistant":
            return (
                "\n\n## Активный маршрут\n"
                "general_assistant: отвечай без вызова инструментов, если только "
                "позже не потребуется явное уточнение от пользователя."
            )

        return (
            "\n\n## Активный маршрут\n"
            f"{route_config.route}: {route_config.description}\n"
            "Ты видишь только разрешённые инструменты этого маршрута. "
            "Не компенсируй отсутствие инструмента выдуманными действиями. "
            "Если запрос двусмысленный или данных не хватает, сначала задай "
            "короткий уточняющий вопрос. "
            "Если в текущем маршруте доступен нужный инструмент, выполняй действие, "
            "а не утверждай, что такой возможности нет."
        )

    def build_worker_context(
        self,
        worker: str,
        user_goal: str,
        entity_type: Optional[str],
        entity_name: Optional[str],
        time_period: Optional[str],
        task_brief: str,
        missing_fields: List[str],
    ) -> str:
        """Provide worker-specific execution context."""
        worker_profile = WORKERS_BY_NAME.get(worker)
        worker_description = (
            worker_profile.description
            if worker_profile
            else "Исполняет нормализованную задачу."
        )
        entity_line = entity_type or "не указан"
        if entity_name:
            entity_line += f" ({entity_name})"

        missing_text = ", ".join(missing_fields) if missing_fields else "нет"
        return (
            "\n\n## Оркестратор\n"
            f"- Worker: {worker}\n"
            f"- Роль: {worker_description}\n"
            f"- Цель пользователя: {user_goal}\n"
            f"- Сущность: {entity_line}\n"
            f"- Период: {time_period or 'не указан'}\n"
            f"- Отсутствующие поля: {missing_text}\n"
            f"- Нормализованная задача: {task_brief}\n"
            "- Не задавай повторно вопросы по уже заполненным полям. "
            "Если поля заполнены, выполняй задачу или отвечай по существу.\n"
        )

    def _normalize_decision(
        self,
        decision: RouteDecision,
        available_routes: Iterable[ToolRoute],
    ) -> RouteDecision:
        available_names = {route.route for route in available_routes}
        route = (
            decision.route if decision.route in available_names else "general_assistant"
        )
        if route == "general_assistant":
            return RouteDecision(
                route=route,
                confidence=decision.confidence,
                needs_clarification=decision.needs_clarification,
                clarification_question=decision.clarification_question,
            )
        return RouteDecision(
            route=route,
            confidence=decision.confidence,
            needs_clarification=decision.needs_clarification,
            clarification_question=decision.clarification_question,
        )

    def _normalize_orchestrator_plan(
        self,
        plan: OrchestratorPlan,
        available_routes: Iterable[ToolRoute],
        message: str,
    ) -> OrchestratorPlan:
        available_names = {route.route for route in available_routes}
        route = plan.route if plan.route in available_names else "general_assistant"
        worker = DEFAULT_WORKER_BY_ROUTE.get(route, "general_worker")
        if (
            plan.worker in WORKERS_BY_NAME
            and route in WORKERS_BY_NAME[plan.worker].routes
        ):
            worker = plan.worker

        needs_clarification = plan.needs_clarification or bool(plan.missing_fields)
        clarification_question = plan.clarification_question
        if needs_clarification and not clarification_question:
            clarification_question = self._default_clarification_question(
                user_goal=plan.user_goal,
                entity_type=plan.entity_type,
                missing_fields=plan.missing_fields,
            )

        task_brief = plan.task_brief.strip() or message.strip()

        return OrchestratorPlan(
            route=route,
            worker=worker,
            confidence=plan.confidence,
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            user_goal=plan.user_goal,
            entity_type=plan.entity_type,
            entity_name=plan.entity_name,
            time_period=plan.time_period,
            missing_fields=plan.missing_fields,
            task_brief=task_brief,
        )

    def _available_routes(self, available_tool_names: List[str]) -> List[ToolRoute]:
        available = set(available_tool_names)
        routes: List[ToolRoute] = []
        for route in ROUTES:
            if route.route == "general_assistant":
                routes.append(route)
                continue
            if available.intersection(route.tool_names):
                routes.append(route)
        return routes

    def _build_prompt(
        self,
        message: str,
        available_routes: List[ToolRoute],
        available_tool_names: List[str],
    ) -> str:
        routes_text = "\n".join(
            f"- {route.route}: {route.description}" for route in available_routes
        )
        tools_text = ", ".join(available_tool_names) if available_tool_names else "нет"
        return dedent(f"""
            Ты маршрутизатор запросов для task_pilot.
            Твоя задача: выбрать ОДИН маршрут, определить нужен ли вызов инструмента
            и стоит ли сначала запросить уточнение.

            Доступные маршруты:
            {routes_text}

            Доступные инструменты:
            {tools_text}

            Правила:
            - Если запрос информационный, консультационный или можно ответить без действий,
              выбирай general_assistant.
            - Если пользователь хочет изменить данные в Kaiten или получить фактические данные
              из Kaiten, выбирай профильный маршрут.
            - Формулировки вроде "обнови", "синхронизируй", "внеси изменения",
              "примени по диалогу/обсуждению/переписке" означают, что нужны реальные
              действия в Kaiten, а не текстовый совет.
            - Если формулировка недостаточно точная для безопасного действия, ставь
              needs_clarification=true и дай короткий вопрос на русском.
            - Не выбирай route, которого нет в списке доступных маршрутов.

            Запрос пользователя:
            {message}
            """).strip()

    def _build_orchestrator_prompt(
        self,
        history: str,
        message: str,
        available_routes: List[ToolRoute],
        available_tool_names: List[str],
    ) -> str:
        routes_text = "\n".join(
            f"- {route.route}: {route.description}" for route in available_routes
        )
        tools_text = ", ".join(available_tool_names) if available_tool_names else "нет"
        workers_text = "\n".join(
            f"- {worker.worker}: {worker.description}" for worker in WORKERS
        )
        return dedent(f"""
            Ты главный агент-оркестратор task_pilot.
            Твоя задача:
            1. Понять намерение пользователя из текущего сообщения И истории диалога.
            2. Восстановить уже выяснённые факты, чтобы не задавать повторные вопросы.
            3. Выбрать один маршрут и одного worker-исполнителя.
            4. Сформировать краткую нормализованную задачу для worker-а.

            Важно:
            - Учитывай ссылки на контекст: "по ней", "по этой доске", "сделай это".
            - Если в истории уже выяснили тип сущности или её имя, не спрашивай это снова.
            - Спрашивай только реально отсутствующие поля.
            - Если данных уже достаточно, needs_clarification=false.
            - Для информационных и отчётных запросов по Kaiten обычно нужен reporting worker, а не general_assistant.
            - Если пользователь просит обновить Kaiten по диалогу, обсуждению или переписке,
              используй историю как источник изменений и выбирай mutating-route, а не general_assistant.
            Доступные маршруты:
            {routes_text}

            Доступные worker-исполнители:
            {workers_text}

            Доступные инструменты:
            {tools_text}

            История диалога:
            {history or "история отсутствует"}

            Текущее сообщение пользователя:
            {message}
            """).strip()

    def _heuristic_route(
        self,
        message: str,
        available_routes: List[ToolRoute],
    ) -> RouteDecision:
        text = message.lower()
        available_names = {route.route for route in available_routes}

        if "workspace_setup" in available_names and any(
            keyword in text
            for keyword in ("создай доску", "сделай доску", "настрой доску")
        ):
            return RouteDecision(
                route="workspace_setup",
                confidence=0.7,
            )

        if (
            "workspace_setup" in available_names
            and any(keyword in text for keyword in ("доск", "колонк", "board", "space"))
            and not any(
                keyword in text
                for keyword in (
                    "карточ",
                    "задач",
                    "перемест",
                    "передвин",
                    "move",
                    "назнач",
                )
            )
        ):
            return RouteDecision(
                route="workspace_setup",
                confidence=0.66,
            )

        card_operations_keywords = (
            "карточ",
            "задач",
            "comment",
            "комментар",
            "обнови зада",
            "обнови карточ",
            "синхронизируй задач",
            "синхронизируй карточ",
            "перенес",
            "перемест",
            "двин",
            "move",
            "tag",
            "тег",
            "тайм",
            "колонк",
            "column",
            "done",
            "todo",
            "to do",
            "in progress",
            "backlog",
            "подзада",
            "разбей",
            "декомпоз",
            "эпик",
        )

        keyword_map = (
            (
                "card_operations",
                card_operations_keywords,
            ),
            (
                "reporting",
                ("сводк", "summary", "отч", "статус", "status"),
            ),
            (
                "workspace_setup",
                ("пространств", "пространство", "доск", "колонк", "board", "space"),
            ),
            (
                "people_and_access",
                ("пользоват", "участник", "ответствен", "роль", "команд"),
            ),
        )

        for route_name, keywords in keyword_map:
            if route_name in available_names and any(
                keyword in text for keyword in keywords
            ):
                return RouteDecision(
                    route=route_name,
                    confidence=0.62,
                )

        if "workspace_setup" in available_names and any(
            keyword in text
            for keyword in (
                "обнови доск",
                "обнови колонк",
                "синхронизируй доск",
                "синхронизируй колонк",
                "пространств",
            )
        ):
            return RouteDecision(
                route="workspace_setup",
                confidence=0.64,
            )

        return RouteDecision(
            route="general_assistant",
            confidence=0.4,
        )

    def _heuristic_orchestrate(
        self,
        message: str,
        history: str,
        available_routes: List[ToolRoute],
    ) -> OrchestratorPlan:
        combined = f"{history}\n{message}".strip()
        user_history = self._extract_user_history(history)
        combined_user = f"{user_history}\n{message}".strip()
        text = combined.lower()
        user_text = combined_user.lower()
        route_decision = self._heuristic_route(
            message=combined, available_routes=available_routes
        )
        user_goal = self._infer_goal(user_text)
        message_entity_type = self._infer_entity_type(message.lower())
        history_entity_type = self._infer_entity_type(user_history.lower())
        entity_type = message_entity_type or history_entity_type
        if entity_type is None and self._has_context_reference(message.lower()):
            entity_type = history_entity_type

        entity_name = self._infer_entity_name(message, entity_type)
        if entity_name is None and entity_type is not None:
            entity_name = self._infer_entity_name(user_history, entity_type)
        time_period = self._infer_time_period(user_text)

        missing_fields: List[str] = []
        needs_clarification = False
        clarification_question: Optional[str] = None

        if user_goal == "summary" and entity_type is None:
            missing_fields.append("entity_type")
            needs_clarification = True
            clarification_question = "Какую доску или карточку вы хотите сводку?"
        elif (
            user_goal == "summary"
            and entity_name is None
            and entity_type
            in {
                "board",
                "card",
                "space",
            }
        ):
            missing_fields.append("entity_name")
            needs_clarification = True
            clarification_question = self._default_clarification_question(
                user_goal=user_goal,
                entity_type=entity_type,
                missing_fields=missing_fields,
            )

        route = route_decision.route
        if user_goal == "summary" and "reporting" in {
            r.route for r in available_routes
        }:
            route = "reporting"
        elif user_goal in {"create_or_update", "update"} and route in {
            "general_assistant",
            "reporting",
            "people_and_access",
            "workspace_setup",
        }:
            available_route_names = {r.route for r in available_routes}
            text_lower = message.lower()
            has_card_operation_hint = any(
                keyword in text_lower
                for keyword in (
                    "карточ",
                    "задач",
                    "перемест",
                    "передвин",
                    "move",
                    "назнач",
                )
            )
            if (
                entity_type in {"board", "space"}
                and "workspace_setup" in available_route_names
                and not has_card_operation_hint
            ):
                route = "workspace_setup"
            elif (
                entity_type in {"card", "user"}
                and "card_operations" in available_route_names
            ):
                route = "card_operations"

        worker = DEFAULT_WORKER_BY_ROUTE.get(route, "general_worker")
        task_brief = self._build_task_brief(
            user_goal=user_goal,
            entity_type=entity_type,
            entity_name=entity_name,
            time_period=time_period,
            fallback=message,
        )

        plan = OrchestratorPlan(
            route=route,
            worker=worker,
            confidence=max(route_decision.confidence, 0.55),
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            user_goal=user_goal,
            entity_type=entity_type,
            entity_name=entity_name,
            time_period=time_period,
            missing_fields=missing_fields,
            task_brief=task_brief,
        )
        self._log_orchestrator_plan(
            plan,
            source="heuristic",
            user_history=user_history,
            combined_user=combined_user,
        )
        return plan

    def _default_clarification_question(
        self,
        user_goal: str,
        entity_type: Optional[str],
        missing_fields: List[str],
    ) -> str:
        if "entity_name" in missing_fields and entity_type == "board":
            return "Как называется доска, по которой нужна сводка?"
        if "entity_name" in missing_fields and entity_type == "card":
            return "По какой карточке нужна сводка?"
        if user_goal == "summary":
            return (
                "Какую доску, карточку или пространство нужно использовать для сводки?"
            )
        return "Что именно нужно уточнить, чтобы безопасно выполнить ваш запрос?"

    def _infer_goal(self, text: str) -> str:
        if any(
            keyword in text
            for keyword in ("сводк", "summary", "отч", "статус", "status")
        ):
            return "summary"
        if any(
            keyword in text for keyword in ("разбей", "декомпоз", "подзада", "эпик")
        ):
            return "breakdown"
        if any(
            keyword in text
            for keyword in (
                "созд",
                "добав",
                "настрой",
                "сделай",
                "синхрониз",
                "внеси",
                "примени",
            )
        ):
            return "create_or_update"
        if any(
            keyword in text
            for keyword in (
                "перенес",
                "перемест",
                "двин",
                "move",
                "назнач",
                "обнов",
                "актуализ",
            )
        ):
            return "update"
        return "general_question"

    def _infer_entity_type(self, text: str) -> str | None:
        lowered = text.lower()
        if "доск" in lowered or re.search(r"\bboard\b", lowered):
            return "board"
        if any(keyword in lowered for keyword in ("карточ", "задач")) or re.search(
            r"\bcard\b", lowered
        ):
            return "card"
        if "пространств" in lowered or re.search(r"\bspace\b", lowered):
            return "space"
        if any(keyword in lowered for keyword in ("пользоват", "участник", "команд")):
            return "user"
        return None

    def _infer_entity_name(self, text: str, entity_type: str | None) -> str | None:
        if entity_type == "board":
            return self._extract_name_after_keyword(
                text, ("доске", "доску", "доска", "board")
            )
        if entity_type == "card":
            return self._extract_name_after_keyword(
                text, ("карточке", "карточку", "карточка", "задаче", "задачу", "задача")
            )
        if entity_type == "space":
            return self._extract_name_after_keyword(
                text, ("пространстве", "пространство", "space")
            )
        return None

    def _infer_time_period(self, text: str) -> str | None:
        if "за неделю" in text:
            return "week"
        if "за месяц" in text:
            return "month"
        if "за день" in text or "сегодня" in text:
            return "day"
        return None

    def _build_task_brief(
        self,
        user_goal: str,
        entity_type: str | None,
        entity_name: str | None,
        time_period: str | None,
        fallback: str,
    ) -> str:
        brief_parts = [f"goal={user_goal}"]
        if entity_type:
            brief_parts.append(f"entity_type={entity_type}")
        if entity_name:
            brief_parts.append(f"entity_name={entity_name}")
        if time_period:
            brief_parts.append(f"time_period={time_period}")
        if len(brief_parts) == 1:
            return fallback.strip()
        return ", ".join(brief_parts)

    def _extract_name_after_keyword(
        self,
        text: str,
        keywords: tuple[str, ...],
    ) -> str | None:
        lowered = text.lower()
        for keyword in keywords:
            marker = f"{keyword} "
            index = lowered.rfind(marker)
            if index == -1:
                continue
            candidate = text[index + len(marker) :].strip()
            if not candidate:
                continue
            candidate = candidate.splitlines()[0].strip(" \"'.,:;!?")
            candidate = candidate.split(" и ")[0].split(" или ")[0].strip()
            if len(candidate.split()) > 6:
                continue
            if candidate.lower().startswith(
                (
                    "вы ",
                    "нужна ",
                    "нужно ",
                    "хочу ",
                    "хотим ",
                    "получить ",
                    "сделать ",
                )
            ):
                continue
            if candidate:
                return candidate
        return None

    def _extract_user_history(self, history: str) -> str:
        """Keep only user turns from the orchestrator transcript."""
        lines = []
        for raw_line in history.splitlines():
            line = raw_line.strip()
            if line.startswith("Пользователь:"):
                lines.append(line.removeprefix("Пользователь:").strip())
        return "\n".join(lines)

    def _has_context_reference(self, text: str) -> bool:
        """Detect references like 'по ней' or 'эта доска' that rely on prior context."""
        markers = (
            "по ней",
            "по нему",
            "по ней сводку",
            "по нему сводку",
            "по этой",
            "по этому",
            "эта доска",
            "эта карточка",
            "та доска",
            "она",
            "он",
            "ней",
            "нему",
            "по диалогу",
            "согласно диалогу",
            "по обсуждению",
            "по переписке",
            "из диалога",
            "из обсуждения",
        )
        return any(marker in text for marker in markers)

    def _log_orchestrator_plan(
        self,
        plan: OrchestratorPlan,
        source: str,
        user_history: str | None = None,
        combined_user: str | None = None,
    ) -> None:
        """Emit structured logs for the final orchestration decision."""
        logger.info(
            "Orchestrator plan resolved",
            extra={
                "event_type": "orchestrator_plan",
                "orchestrator_source": source,
                "route": plan.route,
                "worker": plan.worker,
                "confidence": plan.confidence,
                "needs_clarification": plan.needs_clarification,
                "clarification_question": sanitize_for_logging(
                    plan.clarification_question, max_length=300
                ),
                "user_goal": plan.user_goal,
                "entity_type": plan.entity_type,
                "entity_name": plan.entity_name,
                "time_period": plan.time_period,
                "missing_fields": plan.missing_fields,
                "task_brief": sanitize_for_logging(plan.task_brief, max_length=500),
                "user_history": sanitize_for_logging(user_history, max_length=800),
                "combined_user": sanitize_for_logging(combined_user, max_length=1000),
            },
        )

    @staticmethod
    def _tool_names(tools: List[Any]) -> List[str]:
        return [str(getattr(tool, "name", tool)) for tool in tools]
