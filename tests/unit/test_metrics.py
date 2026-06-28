"""Tests for AI request metrics aggregation."""

from __future__ import annotations

import time

import pytest

from chat_bot.metrics import RequestMetric, record_ai_request, track_user_request_async


class _Response:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.usage_metadata = {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }


@pytest.mark.asyncio
async def test_user_request_model_is_mixed_for_multiple_nested_models() -> None:
    """Aggregated Telegram metrics should expose mixed model usage."""
    persisted: list[RequestMetric] = []

    async def _save(metric: RequestMetric) -> None:
        persisted.append(metric)

    async with track_user_request_async(
        operation="telegram_message",
        model="strong",
        on_complete=_save,
    ):
        record_ai_request(
            operation="tool_orchestrate",
            model="light",
            status="success",
            started_at=time.perf_counter(),
            response=_Response(prompt_tokens=10, completion_tokens=2),
        )
        record_ai_request(
            operation="chat_agent_step",
            model="strong",
            status="success",
            started_at=time.perf_counter(),
            response=_Response(prompt_tokens=20, completion_tokens=3),
        )

    assert len(persisted) == 1
    assert persisted[0].model == "mixed(light,strong)"
    assert persisted[0].prompt_tokens == 30
    assert persisted[0].completion_tokens == 5
    assert persisted[0].total_tokens == 35


@pytest.mark.asyncio
async def test_user_request_model_uses_single_nested_model() -> None:
    """Pure light-model requests should not be reported as the default model."""
    persisted: list[RequestMetric] = []

    async def _save(metric: RequestMetric) -> None:
        persisted.append(metric)

    async with track_user_request_async(
        operation="telegram_message",
        model="strong",
        on_complete=_save,
    ):
        record_ai_request(
            operation="chat_direct_answer",
            model="light",
            status="success",
            started_at=time.perf_counter(),
            response=_Response(prompt_tokens=10, completion_tokens=2),
        )

    assert len(persisted) == 1
    assert persisted[0].model == "light"
