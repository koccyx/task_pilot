"""Tests for RAG context injection into the agent pipeline."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from chat_bot.models import Message
from chat_bot.rag.agent_context import AgentRagContextBuilder
from chat_bot.rag.vector_store import VectorSearchResult


def make_message(
    message_id: int,
    text: str,
    is_bot_message: bool = False,
) -> Message:
    return Message(
        message_id=message_id,
        timestamp=f"2026-06-21T10:{message_id:02d}:00",
        sender_name="bot" if is_bot_message else "user",
        text=text,
        is_bot_message=is_bot_message,
    )


class TestAgentRagContextBuilder:
    def test_last_user_messages_uses_history_and_current_message(self) -> None:
        history = [
            make_message(1, "первый вопрос"),
            make_message(2, "ответ", is_bot_message=True),
            make_message(3, "второй вопрос"),
            make_message(4, "третий вопрос"),
        ]

        messages = AgentRagContextBuilder._last_user_messages(
            message="четвертый вопрос",
            history=history,
            limit=3,
        )

        assert messages == ["второй вопрос", "третий вопрос", "четвертый вопрос"]

    def test_last_dialog_messages_uses_last_four_user_and_agent_messages(self) -> None:
        history = [
            make_message(1, "первый вопрос"),
            make_message(2, "первый ответ", is_bot_message=True),
            make_message(3, "второй вопрос"),
            make_message(4, "второй ответ", is_bot_message=True),
        ]

        messages = AgentRagContextBuilder._last_dialog_messages(
            message="а что по этому в документах?",
            history=history,
            limit=4,
        )

        assert messages == [
            "assistant: первый ответ",
            "user: второй вопрос",
            "assistant: второй ответ",
            "user: а что по этому в документах?",
        ]

    @pytest.mark.asyncio
    async def test_build_context_searches_rag_for_document_request(self) -> None:
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        rag_service = MagicMock()
        rag_service.search = AsyncMock(
            return_value=[
                VectorSearchResult(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    filename="policy.md",
                    text="Отпуска согласуются с руководителем.",
                    score=0.42,
                )
            ]
        )
        builder = AgentRagContextBuilder(llm=llm, rag_service=rag_service)

        context = await builder.build_context(
            message="что написано в регламенте по отпускам?",
            history=[],
        )

        assert context.used is True
        assert "policy.md" in context.context_block
        assert "Отпуска согласуются" in context.context_block
        rag_service.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_build_context_skips_rag_for_plain_task_action(self) -> None:
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("router unavailable")
        rag_service = MagicMock()
        rag_service.search = AsyncMock()
        builder = AgentRagContextBuilder(llm=llm, rag_service=rag_service)

        context = await builder.build_context(
            message="создай карточку проверить интеграцию",
            history=[],
        )

        assert context.used is False
        rag_service.search.assert_not_awaited()
