"""Create run results from an autoeval dataset."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "dataset" / "run_example.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "autoeval" / "run" / "results"


class DatasetError(ValueError):
    """Raised when the run dataset has an unsupported shape."""


class RunError(RuntimeError):
    """Raised when the agent runner cannot be initialized."""


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a Z suffix."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise DatasetError(f"Expected JSON object in {path}")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Save a JSON object with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def require_cases(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and validate dataset cases."""
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        raise DatasetError('Dataset must contain a "cases" array')

    normalized: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise DatasetError(f"Case #{index} must be an object")
        if "case_id" not in case:
            raise DatasetError(f"Case #{index} is missing case_id")
        if not isinstance(case.get("dialog", []), list):
            raise DatasetError(f"Case {case['case_id']} dialog must be an array")
        normalized.append(case)
    return normalized


def select_cases(
    cases: list[dict[str, Any]],
    case_ids: set[int] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Filter cases by ids and/or cap the number of selected cases."""
    selected = cases
    if case_ids is not None:
        selected = [case for case in selected if case.get("case_id") in case_ids]
        found_ids = {case.get("case_id") for case in selected}
        missing_ids = sorted(case_id for case_id in case_ids if case_id not in found_ids)
        if missing_ids:
            raise DatasetError(
                "Requested case_id not found in dataset: "
                + ", ".join(str(case_id) for case_id in missing_ids)
            )

    if limit is not None:
        if limit < 1:
            raise DatasetError("--limit must be greater than 0")
        selected = selected[:limit]

    return selected


def append_assistant_to_dialog(
    dialog: list[Any],
    assistant_response: str,
) -> list[dict[str, str]]:
    """Return a dialog copy with the final assistant response appended."""
    normalized: list[dict[str, str]] = []
    for item in dialog:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if isinstance(role, str) and isinstance(content, str):
            normalized.append({"role": role, "content": content})
    if assistant_response:
        normalized.append({"role": "assistant", "content": assistant_response})
    return normalized


def mock_tool_events(
    case: dict[str, Any],
    actual_tools: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build mock tool events for actual tool calls."""
    mock_results = case.get("mock_tool_results", [])
    if not isinstance(mock_results, list):
        mock_results = []

    events: list[dict[str, Any]] = []
    remaining_results = [item for item in mock_results if isinstance(item, dict)]

    for index, tool_call in enumerate(actual_tools, start=1):
        if not isinstance(tool_call, dict):
            continue
        tool_name = tool_call.get("tool_name")
        mock_result = remaining_results.pop(0) if remaining_results else None
        events.append(
            {
                "call_index": index,
                "tool_name": tool_name,
                "arguments": tool_call.get("arguments", {}),
                "mocked": mock_result is not None,
                "result": mock_result.get("result") if mock_result else None,
            }
        )
    return events


def replay_case(case: dict[str, Any]) -> dict[str, Any]:
    """Replay one saved case into the normalized run-result sample shape."""
    started = time.perf_counter()
    assistant_response = case.get("assistant_response")
    actual_tools = case.get("actual_tools", [])
    if not isinstance(actual_tools, list):
        actual_tools = []

    status = "success" if isinstance(assistant_response, str) else "failed"
    error = None if status == "success" else "assistant_response is missing"
    response_text = assistant_response or ""

    return {
        "sample_id": case["case_id"],
        "case_id": case["case_id"],
        "case_name": case.get("case_name"),
        "category": case.get("category"),
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "dialog": append_assistant_to_dialog(case.get("dialog", []), response_text),
        "expected_tools": case.get("expected_tools", []),
        "actual_tools": actual_tools,
        "mock_tool_events": mock_tool_events(case, actual_tools),
        "assistant_response": response_text,
        "error": error,
    }


def build_replay_run_result(
    dataset: dict[str, Any],
    dataset_path: Path,
    cases: list[dict[str, Any]] | None = None,
    runner_name: str = "dataset_replay",
) -> dict[str, Any]:
    """Build a run_result object by replaying saved dataset outputs."""
    cases = cases if cases is not None else require_cases(dataset)
    run_time = utc_now()
    samples = [replay_case(case) for case in cases]
    failed = [sample for sample in samples if sample["status"] != "success"]

    return {
        "benchmark_id": dataset.get("benchmark_id", "unknown"),
        "source_dataset": str(dataset_path),
        "run_id": f"run-{uuid4().hex}",
        "run_time": run_time,
        "runner": {
            "name": runner_name,
            "mode": "mock_replay",
            "mock_tools": True,
        },
        "summary": {
            "total": len(samples),
            "succeeded": len(samples) - len(failed),
            "failed": len(failed),
        },
        "samples": samples,
    }


def dialog_to_agent_input(case: dict[str, Any], run_time: str) -> tuple[str, list[Any]]:
    """Split a case dialog into current user message and agent history."""
    from chat_bot.models import Message

    dialog = case.get("dialog", [])
    if not isinstance(dialog, list) or not dialog:
        raise DatasetError(f"Case {case['case_id']} has empty dialog")

    last_user_index = None
    for index in range(len(dialog) - 1, -1, -1):
        item = dialog[index]
        if isinstance(item, dict) and item.get("role") == "user":
            last_user_index = index
            break
    if last_user_index is None:
        raise DatasetError(f"Case {case['case_id']} has no user message")

    current_item = dialog[last_user_index]
    current_message = current_item.get("content")
    if not isinstance(current_message, str) or not current_message.strip():
        raise DatasetError(f"Case {case['case_id']} has empty current user message")

    history = []
    message_id = 1
    for item in dialog[:last_user_index]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        history.append(
            Message(
                message_id=message_id,
                timestamp=run_time,
                sender_name="assistant" if role == "assistant" else "user",
                text=content,
                is_bot_message=role == "assistant",
            )
        )
        message_id += 1
    return current_message, history


class MockToolRegistry:
    """LangChain tool factory that records calls and returns dataset mocks."""

    FALLBACK_TOOL_NAMES = (
        "manage_spaces",
        "manage_boards",
        "manage_columns",
        "manage_cards",
        "manage_comments",
        "manage_members",
        "manage_tags",
        "manage_time_logs",
        "manage_users",
        "move_card",
        "mass_update",
        "auto_archive",
        "break_into_tasks",
    )

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case
        self.calls: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        mock_results = case.get("mock_tool_results", [])
        self._mock_results = (
            [item for item in mock_results if isinstance(item, dict)]
            if isinstance(mock_results, list)
            else []
        )

    def tools(self) -> list[Any]:
        """Create task-agent-compatible mock tools."""
        from langchain_core.tools import StructuredTool
        from pydantic import ConfigDict, Field, create_model

        fields: dict[str, Any] = {
            "action": (str | None, Field(default=None)),
            "title": (str | None, Field(default=None)),
            "description": (str | None, Field(default=None)),
            "board": (str | None, Field(default=None)),
            "board_id": (int | None, Field(default=None)),
            "space": (str | None, Field(default=None)),
            "space_id": (int | None, Field(default=None)),
            "column": (str | None, Field(default=None)),
            "column_id": (int | None, Field(default=None)),
            "card": (str | None, Field(default=None)),
            "card_id": (int | None, Field(default=None)),
            "query": (str | None, Field(default=None)),
            "owner_id": (int | None, Field(default=None)),
            "owner_name": (str | None, Field(default=None)),
            "due_date": (str | None, Field(default=None)),
            "due_date_after": (str | None, Field(default=None)),
            "due_date_before": (str | None, Field(default=None)),
            "status": (str | None, Field(default=None)),
            "comment": (str | None, Field(default=None)),
            "text": (str | None, Field(default=None)),
            "comment_id": (int | None, Field(default=None)),
            "user_name": (str | None, Field(default=None)),
            "user_id": (int | None, Field(default=None)),
            "email": (str | None, Field(default=None)),
            "role_id": (int | None, Field(default=None)),
            "guest": (bool | None, Field(default=None)),
            "send_email": (bool | None, Field(default=None)),
            "tag": (str | None, Field(default=None)),
            "tag_id": (int | None, Field(default=None)),
            "name": (str | None, Field(default=None)),
            "time_spent": (int | float | str | None, Field(default=None)),
            "for_date": (str | None, Field(default=None)),
            "time_log_id": (int | None, Field(default=None)),
            "days_threshold": (int | None, Field(default=None)),
            "dry_run": (bool | None, Field(default=None)),
            "target_board": (str | None, Field(default=None)),
            "target_board_id": (int | None, Field(default=None)),
            "target_column": (str | None, Field(default=None)),
            "target_column_id": (int | None, Field(default=None)),
            "filter_tag": (str | None, Field(default=None)),
            "filter_owner_id": (int | None, Field(default=None)),
            "filter_column_id": (int | None, Field(default=None)),
            "confirm": (bool | None, Field(default=None)),
            "inherit_owner": (bool | None, Field(default=None)),
            "auto_confirm": (bool | None, Field(default=None)),
            "offset": (int | None, Field(default=None)),
            "limit": (int | None, Field(default=None)),
        }
        args_schema = create_model(
            "AutoevalMockToolInput",
            __config__=ConfigDict(extra="allow"),
            **fields,
        )

        tools = []
        for tool_name in self.tool_names():
            tools.append(
                StructuredTool.from_function(
                    name=tool_name,
                    description=(
                        "Mocked Kaiten task tool for autoeval. Use it instead of "
                        "real Kaiten API calls."
                    ),
                    func=None,
                    coroutine=self._make_tool(tool_name),
                    args_schema=args_schema,
                )
            )
        return tools

    @classmethod
    def tool_names(cls) -> tuple[str, ...]:
        """Return the full MCP tool list used by production discovery."""
        tools_file = PROJECT_ROOT / "chat_bot" / "mcp_server" / "mcp_tools.json"
        try:
            data = load_json(tools_file)
        except (OSError, DatasetError, json.JSONDecodeError):
            return cls.FALLBACK_TOOL_NAMES

        tool_names = data.get("tools")
        if not isinstance(tool_names, list):
            return cls.FALLBACK_TOOL_NAMES

        normalized = tuple(name for name in tool_names if isinstance(name, str))
        return normalized or cls.FALLBACK_TOOL_NAMES

    def _make_tool(self, tool_name: str) -> Any:
        async def tool_func(**kwargs: Any) -> str:
            call_index = len(self.calls) + 1
            call = {
                "tool_name": tool_name,
                "arguments": kwargs,
            }
            self.calls.append(call)

            mock_result = self._mock_results.pop(0) if self._mock_results else None
            event = {
                "call_index": call_index,
                "tool_name": tool_name,
                "arguments": kwargs,
                "mocked": mock_result is not None,
                "result": (
                    mock_result.get("result")
                    if mock_result
                    else {
                        "status": "ok",
                        "message": f"Mock result for {tool_name}",
                    }
                ),
            }
            self.events.append(event)
            return json.dumps(event["result"], ensure_ascii=False)

        tool_func.__name__ = tool_name
        return tool_func


def build_llm() -> Any:
    """Create the configured chat model for the current agent."""
    try:
        from dotenv import load_dotenv
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr
    except ImportError as exc:
        raise RunError(
            "Agent mode requires bot dependencies. Install the project with "
            "`uv run --extra bot ...` or install requirements."
        ) from exc

    load_dotenv()
    api_key = os.getenv("AI_API_KEY")
    model = os.getenv("AI_MODEL", "")
    if not api_key or not model:
        raise RunError("AI_API_KEY and AI_MODEL are required for --mode agent")

    kwargs: dict[str, Any] = {
        "api_key": SecretStr(api_key),
        "model": model,
        "temperature": float(os.getenv("AI_TEMPERATURE", "0.0")),
        "base_url": os.getenv("AI_BASE_URL") or None,
        "max_completion_tokens": int(os.getenv("AI_MAX_TOKENS", "700")),
    }
    project = os.getenv("AI_PROJECT")
    if project:
        kwargs["default_headers"] = {"OpenAI-Project": project}
    return ChatOpenAI(**kwargs)


def default_user_profiles() -> tuple[list[Any], Any]:
    """Return a small deterministic user directory for benchmark runs."""
    from chat_bot.models import UserProfile

    current_user = UserProfile(
        chat_id=1,
        telegram_user_id=1001,
        telegram_username="current_user",
        telegram_display_name="Текущий пользователь",
        introduced_name="Текущий пользователь",
        kaiten_user_name="current_user",
        kaiten_user_id=1001,
    )
    ivan = UserProfile(
        chat_id=1,
        telegram_user_id=1002,
        telegram_username="ivan",
        telegram_display_name="Иван",
        introduced_name="Иван",
        kaiten_user_name="Иван",
        kaiten_user_id=1002,
    )
    return [current_user, ivan], current_user


async def run_agent_case(
    case: dict[str, Any],
    llm: Any,
    run_time: str,
) -> dict[str, Any]:
    """Run one case through SimpleTaskAgent with mocked Kaiten tools."""
    from chat_bot.simple_task_agent import SimpleTaskAgent

    started = time.perf_counter()
    registry = MockToolRegistry(case)
    current_message, history = dialog_to_agent_input(case, run_time)
    user_profiles, current_user = default_user_profiles()
    agent = SimpleTaskAgent(llm=llm, allowed_tool_names=None)

    try:
        response = await agent.run(
            message=current_message,
            tools=registry.tools(),
            history=history,
            user_profiles=user_profiles,
            current_user=current_user,
        )
        status = "success"
        error = None
    except Exception as exc:
        response = ""
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"

    return {
        "sample_id": case["case_id"],
        "case_id": case["case_id"],
        "case_name": case.get("case_name"),
        "category": case.get("category"),
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "dialog": append_assistant_to_dialog(case.get("dialog", []), response),
        "expected_tools": case.get("expected_tools", []),
        "actual_tools": registry.calls,
        "mock_tool_events": registry.events,
        "assistant_response": response,
        "error": error,
    }


async def build_agent_run_result(
    dataset: dict[str, Any],
    dataset_path: Path,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a run_result by executing the current SimpleTaskAgent."""
    os.environ.setdefault("RAG_AGENT_ENABLED", "false")
    cases = cases if cases is not None else require_cases(dataset)
    run_time = utc_now()
    llm = build_llm()
    samples = []
    for case in cases:
        samples.append(await run_agent_case(case=case, llm=llm, run_time=run_time))
    failed = [sample for sample in samples if sample["status"] != "success"]

    return {
        "benchmark_id": dataset.get("benchmark_id", "unknown"),
        "source_dataset": str(dataset_path),
        "run_id": f"run-{uuid4().hex}",
        "run_time": run_time,
        "runner": {
            "name": "simple_task_agent",
            "mode": "agent",
            "mock_tools": True,
            "agent": "chat_bot.simple_task_agent.SimpleTaskAgent",
            "tool_names": list(MockToolRegistry.tool_names()),
        },
        "summary": {
            "total": len(samples),
            "succeeded": len(samples) - len(failed),
            "failed": len(failed),
        },
        "samples": samples,
    }


async def build_run_result(
    dataset: dict[str, Any],
    dataset_path: Path,
    mode: str,
    case_ids: set[int] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build a run_result in the requested mode."""
    cases = select_cases(require_cases(dataset), case_ids=case_ids, limit=limit)
    if mode == "agent":
        return await build_agent_run_result(
            dataset=dataset,
            dataset_path=dataset_path,
            cases=cases,
        )
    if mode == "replay":
        return build_replay_run_result(
            dataset=dataset,
            dataset_path=dataset_path,
            cases=cases,
        )
    raise RunError(f"Unsupported run mode: {mode}")


def output_path(output_dir: Path, run_result: dict[str, Any]) -> Path:
    """Build the output path for a run_result file."""
    safe_run_time = str(run_result["run_time"]).replace(":", "-")
    return output_dir / f"run_result_{safe_run_time}.json"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Create a run_result JSON from an autoeval run dataset."
    )
    parser.add_argument(
        "--mode",
        choices=("agent", "replay"),
        default="agent",
        help=(
            "agent runs SimpleTaskAgent with mocked Kaiten tools; replay uses "
            "saved assistant_response and actual_tools from the dataset."
        ),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
        help=f"Path to run dataset JSON. Default: {DEFAULT_DATASET_PATH}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for run_result JSON files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Exact output file path. Overrides --output-dir when provided.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases after optional --case-id filtering.",
    )
    parser.add_argument(
        "--case-id",
        type=int,
        action="append",
        default=None,
        help="Run only selected case_id. Can be passed multiple times.",
    )
    return parser.parse_args()


async def async_main() -> None:
    """Async CLI entrypoint."""
    args = parse_args()
    dataset_path = args.dataset.resolve()
    dataset = load_json(dataset_path)
    run_result = await build_run_result(
        dataset=dataset,
        dataset_path=dataset_path,
        mode=args.mode,
        case_ids=set(args.case_id) if args.case_id else None,
        limit=args.limit,
    )
    result_path = (
        args.output.resolve()
        if args.output
        else output_path(args.output_dir.resolve(), run_result)
    )
    save_json(result_path, run_result)
    print(str(result_path))


def main() -> None:
    """CLI entrypoint."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
