"""RAG routing and context building for the task agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Sequence

from pydantic import BaseModel, Field

from chat_bot.logging_config import get_logger, sanitize_for_logging
from chat_bot.models import Message

from .service import RagService
from .settings import RagSettings
from .vector_store import VectorSearchResult

logger = get_logger(__name__)


class RagRouteDecision(BaseModel):
    """Decision whether the current dialog needs internal knowledge search."""

    use_rag: bool = Field(description="Whether to search the internal knowledge base.")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for the decision.",
    )
    reason: str = Field(default="", description="Short reason for logging.")
    query_hint: str = Field(
        default="",
        description="Optional search hint extracted from the user messages.",
    )


class RagRephrasedQuery(BaseModel):
    """Standalone RAG search query derived from recent dialog."""

    query: str = Field(description="Standalone query for internal knowledge search.")


@dataclass(frozen=True)
class RagContext:
    """Context block produced by RAG for the main agent prompt."""

    used: bool
    query: str
    results: list[VectorSearchResult]
    context_block: str
    reason: str = ""


class AgentRagContextBuilder:
    """Decide whether RAG is needed and format its results for the agent."""

    def __init__(
        self,
        llm: Any,
        rag_service: RagService | None = None,
        result_limit: int | None = None,
    ) -> None:
        self.llm = llm
        self._rag_service = rag_service
        self.result_limit = result_limit or int(
            os.getenv("RAG_AGENT_RESULT_LIMIT", "4")
        )

    async def build_context(
        self, message: str, history: Sequence[Message]
    ) -> RagContext:
        """Return a RAG context block when recent user messages need it."""
        user_messages = self._last_user_messages(
            message=message, history=history, limit=3
        )
        decision = await self._route(user_messages)
        logger.info(
            "RAG gate decision",
            extra={
                "event_type": "rag_gate_decision",
                "use_rag": decision.use_rag,
                "confidence": decision.confidence,
                "reason": sanitize_for_logging(decision.reason, max_length=500),
                "query_hint": sanitize_for_logging(decision.query_hint, max_length=500),
            },
        )
        if not decision.use_rag:
            return RagContext(
                used=False,
                query="",
                results=[],
                context_block="",
                reason=decision.reason,
            )

        query = await self._rephrase(
            messages=self._last_dialog_messages(
                message=message, history=history, limit=4
            ),
            query_hint=decision.query_hint,
        )
        if not query.strip():
            query = decision.query_hint.strip() or message.strip()

        try:
            results = await self._service.search(query, limit=self.result_limit)
        except Exception as exc:
            logger.warning(
                "RAG search failed: %s",
                exc,
                extra={
                    "event_type": "rag_search_failed",
                    "query": sanitize_for_logging(query, max_length=500),
                    "error_type": type(exc).__name__,
                    "error_message": sanitize_for_logging(str(exc), max_length=1000),
                },
            )
            return RagContext(
                used=True,
                query=query,
                results=[],
                context_block=(
                    "\n\n## Контекст из внутренней базы знаний\n"
                    "Поиск во внутренней базе знаний временно недоступен. "
                    "Не утверждай, что проверил документы."
                ),
                reason=decision.reason,
            )

        logger.info(
            "RAG search completed",
            extra={
                "event_type": "rag_search_completed",
                "query": sanitize_for_logging(query, max_length=500),
                "result_count": len(results),
                "filenames": [result.filename for result in results],
            },
        )
        return RagContext(
            used=True,
            query=query,
            results=results,
            context_block=self._format_context_block(query=query, results=results),
            reason=decision.reason,
        )

    @property
    def _service(self) -> RagService:
        if self._rag_service is None:
            self._rag_service = RagService(RagSettings.from_env())
        return self._rag_service

    async def _route(self, user_messages: Sequence[str]) -> RagRouteDecision:
        joined = "\n".join(
            f"- {message}" for message in user_messages if message.strip()
        )
        if not joined.strip():
            return RagRouteDecision(use_rag=False, confidence=1.0, reason="empty input")

        try:
            model = self.llm.with_structured_output(RagRouteDecision)
            decision: RagRouteDecision = await model.ainvoke(
                self._route_prompt(joined)
            )  # type: ignore[assignment]
            return decision
        except Exception as exc:
            logger.warning("RAG gate fallback engaged: %s", exc)
            return self._heuristic_route(user_messages)

    async def _rephrase(
        self,
        messages: Sequence[str],
        query_hint: str,
    ) -> str:
        joined = "\n".join(messages)
        try:
            model = self.llm.with_structured_output(RagRephrasedQuery)
            result: RagRephrasedQuery = await model.ainvoke(
                self._rephrase_prompt(joined, query_hint)
            )  # type: ignore[assignment]
            return result.query.strip()
        except Exception as exc:
            logger.warning("RAG rephrase fallback engaged: %s", exc)
            return query_hint.strip() or self._latest_user_text(messages)

    @staticmethod
    def _last_user_messages(
        message: str,
        history: Sequence[Message],
        limit: int,
    ) -> list[str]:
        user_messages = [
            item.text.strip()
            for item in history
            if not item.is_bot_message and item.text and item.text.strip()
        ]
        if message.strip():
            user_messages.append(message.strip())
        return user_messages[-limit:]

    @staticmethod
    def _last_dialog_messages(
        message: str,
        history: Sequence[Message],
        limit: int,
    ) -> list[str]:
        dialog_messages = []
        for item in history:
            if not item.text or not item.text.strip():
                continue
            role = "assistant" if item.is_bot_message else "user"
            dialog_messages.append(f"{role}: {item.text.strip()}")
        if message.strip():
            dialog_messages.append(f"user: {message.strip()}")
        return dialog_messages[-limit:]

    @staticmethod
    def _latest_user_text(messages: Sequence[str]) -> str:
        for message in reversed(messages):
            if message.startswith("user:"):
                return message.removeprefix("user:").strip()
        return messages[-1].strip() if messages else ""

    @staticmethod
    def _route_prompt(user_messages: str) -> str:
        return dedent(
            f"""
            Ты решаешь, нужен ли поиск во внутренней базе знаний RAG.
            Учитывай только последние сообщения пользователя.

            Последние сообщения пользователя:
            {user_messages}

            Верни use_rag=true, если пользователь спрашивает про внутренние документы,
            регламенты, инструкции, базу знаний, загруженные файлы, правила компании
            или просит выполнить действие по правилам из документов.

            Верни use_rag=false для обычных действий в Kaiten, отчетов, списков задач,
            приветствий и общих вопросов, если нет зависимости от внутренних документов.
            """
        ).strip()

    @staticmethod
    def _rephrase_prompt(messages: str, query_hint: str) -> str:
        return dedent(
            f"""
            Переформулируй диалог в самостоятельный поисковый запрос для внутренней
            базы знаний. Убери местоимения вроде "это", "там", "по нему", если их
            можно раскрыть из контекста. Не добавляй фактов, которых нет в диалоге.

            Подсказка маршрутизатора: {query_hint or "нет"}

            Последние сообщения диалога:
            {messages}
            """
        ).strip()

    @staticmethod
    def _heuristic_route(user_messages: Sequence[str]) -> RagRouteDecision:
        text = "\n".join(user_messages).lower()
        if text.strip().startswith("/"):
            return RagRouteDecision(
                use_rag=False,
                confidence=0.8,
                reason="slash command",
            )

        rag_keywords = (
            "документ",
            "документац",
            "регламент",
            "инструкц",
            "база знаний",
            "загруженн",
            "внутренн",
            "по правилам",
            "согласно",
            "как у нас принято",
            "что у нас написано",
        )
        if any(keyword in text for keyword in rag_keywords):
            return RagRouteDecision(
                use_rag=True,
                confidence=0.72,
                reason="matched internal knowledge keyword",
                query_hint=user_messages[-1].strip() if user_messages else "",
            )

        return RagRouteDecision(
            use_rag=False,
            confidence=0.65,
            reason="no internal knowledge markers",
        )

    @staticmethod
    def _format_context_block(
        query: str,
        results: Sequence[VectorSearchResult],
    ) -> str:
        if not results:
            return (
                "\n\n## Контекст из внутренней базы знаний\n"
                f"По запросу: {query}\n"
                "В загруженных документах не найдено достаточно релевантной информации. "
                "Если вопрос требует ответа строго по документам, прямо скажи об этом."
            )

        rendered_results = []
        for index, result in enumerate(results, start=1):
            text = result.text.strip()
            if len(text) > 1800:
                text = text[:1800].rstrip() + "..."
            rendered_results.append(
                f"[{index}] Файл: {result.filename or 'неизвестно'}; "
                f"score: {result.score:.4f}; chunk_id: {result.chunk_id}\n{text}"
            )

        return (
            "\n\n## Контекст из внутренней базы знаний\n"
            f"Поисковый запрос: {query}\n"
            "Используй этот контекст только если он релевантен текущему запросу. "
            "Если в контексте нет ответа, скажи, что в загруженных документах "
            "не нашлось достаточно информации.\n\n" + "\n\n".join(rendered_results)
        )
