"""Small Prometheus-compatible metrics registry for AI requests."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, Iterator, Tuple
from uuid import uuid4

from .logging_config import get_logger

logger = get_logger(__name__)

MAX_REQUEST_SERIES = 200


@dataclass(frozen=True)
class TokenUsage:
    """Token counts returned by an LLM provider."""

    prompt: int = 0
    completion: int = 0
    total: int = 0


@dataclass(frozen=True)
class RequestMetric:
    """Per-request gauge values kept for Grafana tables."""

    request_id: str
    operation: str
    model: str
    status: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_seconds: float
    timestamp_seconds: float
    chat_id: int | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    message_id: int | None = None


_lock = threading.Lock()
_request_counts: Counter[Tuple[str, str, str]] = Counter()
_token_totals: Counter[Tuple[str, str, str]] = Counter()
_latest_requests: Deque[RequestMetric] = deque(maxlen=MAX_REQUEST_SERIES)
_user_request_counts: Counter[Tuple[str, str]] = Counter()
_latest_user_requests: Deque[RequestMetric] = deque(maxlen=MAX_REQUEST_SERIES)
_current_user_request: ContextVar["_UserRequestAccumulator | None"] = ContextVar(
    "current_user_request",
    default=None,
)


@dataclass
class _UserRequestAccumulator:
    request_id: str
    operation: str
    model: str
    started_at: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    status: str = "success"
    chat_id: int | None = None
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    message_id: int | None = None
    nested_models: set[str] = field(default_factory=set)


@contextmanager
def track_user_request(
    *,
    operation: str,
    model: str | None = None,
    chat_id: int | None = None,
    telegram_user_id: int | None = None,
    telegram_username: str | None = None,
    message_id: int | None = None,
) -> Iterator[str]:
    """Aggregate all nested AI calls into one user-request metric."""

    parent = _current_user_request.get()
    if parent is not None:
        yield parent.request_id
        return

    accumulator = _UserRequestAccumulator(
        request_id=uuid4().hex,
        operation=operation,
        model=model or "unknown",
        started_at=time.perf_counter(),
        chat_id=chat_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        message_id=message_id,
    )
    token = _current_user_request.set(accumulator)
    try:
        yield accumulator.request_id
    except Exception:
        accumulator.status = "error"
        raise
    finally:
        _current_user_request.reset(token)
        _record_user_request(accumulator)


@asynccontextmanager
async def track_user_request_async(
    *,
    operation: str,
    model: str | None = None,
    chat_id: int | None = None,
    telegram_user_id: int | None = None,
    telegram_username: str | None = None,
    message_id: int | None = None,
    on_complete: Callable[[RequestMetric], Awaitable[None]] | None = None,
) -> Iterator[str]:
    """Aggregate nested AI calls and optionally persist the final metric."""

    parent = _current_user_request.get()
    if parent is not None:
        yield parent.request_id
        return

    accumulator = _UserRequestAccumulator(
        request_id=uuid4().hex,
        operation=operation,
        model=model or "unknown",
        started_at=time.perf_counter(),
        chat_id=chat_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        message_id=message_id,
    )
    token = _current_user_request.set(accumulator)
    try:
        yield accumulator.request_id
    except Exception:
        accumulator.status = "error"
        raise
    finally:
        _current_user_request.reset(token)
        metric = _record_user_request(accumulator)
        if on_complete is not None:
            try:
                await on_complete(metric)
            except Exception as exc:
                logger.warning("Failed to persist user request metric: %s", exc)


def record_ai_request(
    *,
    operation: str,
    model: str | None,
    status: str,
    started_at: float,
    response: Any = None,
) -> str:
    """Record one AI request and return its generated request id."""

    request_id = uuid4().hex
    usage = extract_token_usage(response)
    model_name = model or "unknown"
    duration_seconds = max(time.perf_counter() - started_at, 0.0)
    metric = RequestMetric(
        request_id=request_id,
        operation=operation,
        model=model_name,
        status=status,
        prompt_tokens=usage.prompt,
        completion_tokens=usage.completion,
        total_tokens=usage.total,
        duration_seconds=duration_seconds,
        timestamp_seconds=time.time(),
    )

    with _lock:
        _request_counts[(operation, model_name, status)] += 1
        _token_totals[(operation, model_name, "prompt")] += usage.prompt
        _token_totals[(operation, model_name, "completion")] += usage.completion
        _token_totals[(operation, model_name, "total")] += usage.total
        _latest_requests.append(metric)

    user_request = _current_user_request.get()
    if user_request is not None:
        user_request.prompt_tokens += usage.prompt
        user_request.completion_tokens += usage.completion
        user_request.total_tokens += usage.total
        if model_name != "unknown":
            user_request.nested_models.add(model_name)
        if status == "error":
            user_request.status = "error"

    logger.info(
        "AI request metrics recorded",
        extra={
            "event_type": "ai_request_metrics_recorded",
            "ai_request_id": request_id,
            "operation": operation,
            "model": model_name,
            "status": status,
            "prompt_tokens": usage.prompt,
            "completion_tokens": usage.completion,
            "total_tokens": usage.total,
            "duration_ms": round(duration_seconds * 1000, 2),
        },
    )
    return request_id


def extract_token_usage(response: Any) -> TokenUsage:
    """Best-effort extraction of LangChain/OpenAI token usage metadata."""

    raw_response = response.get("raw") if isinstance(response, dict) else response
    candidates = [
        getattr(raw_response, "usage_metadata", None),
        getattr(raw_response, "response_metadata", None),
        getattr(raw_response, "additional_kwargs", None),
    ]
    if isinstance(response, dict):
        candidates.extend(
            [response.get("usage_metadata"), response.get("response_metadata")]
        )

    for candidate in candidates:
        usage = _usage_from_mapping(candidate)
        if usage is not None:
            return usage

    return TokenUsage()


def render_prometheus_metrics() -> str:
    """Render all metrics in Prometheus text exposition format."""

    with _lock:
        request_counts = dict(_request_counts)
        token_totals = dict(_token_totals)
        latest_requests = list(_latest_requests)
        user_request_counts = dict(_user_request_counts)
        latest_user_requests = list(_latest_user_requests)

    lines = [
        "# HELP task_pilot_user_requests_total Total user requests by operation and status.",
        "# TYPE task_pilot_user_requests_total counter",
    ]
    for (operation, status), value in sorted(user_request_counts.items()):
        labels = _labels(operation=operation, status=status)
        lines.append(f"task_pilot_user_requests_total{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP task_pilot_user_request_tokens Total AI tokens spent by one user request.",
            "# TYPE task_pilot_user_request_tokens gauge",
        ]
    )
    for metric in latest_user_requests:
        labels = _request_labels(metric, token_type="total")
        lines.append(
            f"task_pilot_user_request_tokens{{{labels}}} {metric.total_tokens}"
        )

    lines.extend(
        [
            "# HELP task_pilot_user_request_duration_seconds Duration of one user request.",
            "# TYPE task_pilot_user_request_duration_seconds gauge",
        ]
    )
    for metric in latest_user_requests:
        labels = _request_labels(metric)
        lines.append(
            "task_pilot_user_request_duration_seconds"
            f"{{{labels}}} {_format_float(metric.duration_seconds)}"
        )

    lines.extend(
        [
            "# HELP task_pilot_ai_requests_total Total AI requests by operation, model and status.",
            "# TYPE task_pilot_ai_requests_total counter",
        ]
    )
    for (operation, model, status), value in sorted(request_counts.items()):
        labels = _labels(operation=operation, model=model, status=status)
        lines.append(f"task_pilot_ai_requests_total{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP task_pilot_ai_tokens_total Total AI tokens by operation, model and token type.",
            "# TYPE task_pilot_ai_tokens_total counter",
        ]
    )
    for (operation, model, token_type), value in sorted(token_totals.items()):
        labels = _labels(operation=operation, model=model, token_type=token_type)
        lines.append(f"task_pilot_ai_tokens_total{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP task_pilot_ai_request_tokens Tokens spent by an individual AI request.",
            "# TYPE task_pilot_ai_request_tokens gauge",
        ]
    )
    for metric in latest_requests:
        for token_type, value in (
            ("prompt", metric.prompt_tokens),
            ("completion", metric.completion_tokens),
            ("total", metric.total_tokens),
        ):
            labels = _request_labels(metric, token_type=token_type)
            lines.append(f"task_pilot_ai_request_tokens{{{labels}}} {value}")

    lines.extend(
        [
            "# HELP task_pilot_ai_request_duration_seconds Duration of an individual AI request.",
            "# TYPE task_pilot_ai_request_duration_seconds gauge",
        ]
    )
    for metric in latest_requests:
        labels = _request_labels(metric)
        lines.append(
            "task_pilot_ai_request_duration_seconds"
            f"{{{labels}}} {_format_float(metric.duration_seconds)}"
        )

    lines.extend(
        [
            "# HELP task_pilot_ai_request_timestamp_seconds Unix timestamp of an individual AI request.",
            "# TYPE task_pilot_ai_request_timestamp_seconds gauge",
        ]
    )
    for metric in latest_requests:
        labels = _request_labels(metric)
        lines.append(
            "task_pilot_ai_request_timestamp_seconds"
            f"{{{labels}}} {_format_float(metric.timestamp_seconds)}"
        )

    return "\n".join(lines) + "\n"


def _record_user_request(accumulator: _UserRequestAccumulator) -> RequestMetric:
    duration_seconds = max(time.perf_counter() - accumulator.started_at, 0.0)
    model = _aggregate_user_request_model(accumulator)
    metric = RequestMetric(
        request_id=accumulator.request_id,
        operation=accumulator.operation,
        model=model,
        status=accumulator.status,
        prompt_tokens=accumulator.prompt_tokens,
        completion_tokens=accumulator.completion_tokens,
        total_tokens=accumulator.total_tokens,
        duration_seconds=duration_seconds,
        timestamp_seconds=time.time(),
        chat_id=accumulator.chat_id,
        telegram_user_id=accumulator.telegram_user_id,
        telegram_username=accumulator.telegram_username,
        message_id=accumulator.message_id,
    )
    with _lock:
        _user_request_counts[(accumulator.operation, accumulator.status)] += 1
        _latest_user_requests.append(metric)

    logger.info(
        "User request metrics recorded",
        extra={
            "event_type": "user_request_metrics_recorded",
            "user_request_id": accumulator.request_id,
            "operation": accumulator.operation,
            "model": model,
            "status": accumulator.status,
            "prompt_tokens": accumulator.prompt_tokens,
            "completion_tokens": accumulator.completion_tokens,
            "total_tokens": accumulator.total_tokens,
            "duration_ms": round(duration_seconds * 1000, 2),
        },
    )
    return metric


def _aggregate_user_request_model(accumulator: _UserRequestAccumulator) -> str:
    """Return the actual model footprint for an aggregated user request."""
    if not accumulator.nested_models:
        return accumulator.model

    models = sorted(accumulator.nested_models)
    if len(models) == 1:
        return models[0]

    return "mixed(" + ",".join(models) + ")"


def _usage_from_mapping(candidate: Any) -> TokenUsage | None:
    if not isinstance(candidate, dict):
        return None

    token_usage = candidate.get("token_usage")
    if isinstance(token_usage, dict):
        candidate = token_usage

    prompt = _first_int(candidate, "prompt_tokens", "input_tokens")
    completion = _first_int(candidate, "completion_tokens", "output_tokens")
    total = _first_int(candidate, "total_tokens")

    if total == 0 and (prompt or completion):
        total = prompt + completion

    if prompt == 0 and completion == 0 and total == 0:
        return None
    return TokenUsage(prompt=prompt, completion=completion, total=total)


def _first_int(mapping: Dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(value):
            return max(int(value), 0)
    return 0


def _request_labels(metric: RequestMetric, token_type: str | None = None) -> str:
    values = {
        "request_id": metric.request_id,
        "operation": metric.operation,
        "model": metric.model,
        "status": metric.status,
    }
    if token_type is not None:
        values["token_type"] = token_type
    return _labels(**values)


def _labels(**values: str) -> str:
    return ",".join(f'{key}="{_escape_label(value)}"' for key, value in values.items())


def _escape_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_float(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")
