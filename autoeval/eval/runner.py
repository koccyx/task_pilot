"""Evaluate run results with independent LLM-as-judge criteria prompts."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_RESULT = (
    PROJECT_ROOT / "autoeval" / "run" / "results" / "run_result_replay_latest.json"
)
DEFAULT_DATASET = PROJECT_ROOT / "dataset" / "run_example.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "autoeval" / "eval" / "results"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
logger = logging.getLogger(__name__)

CriteriaType = Literal["must_include", "must_not_include", "success_criteria"]
CRITERIA_TYPES: tuple[CriteriaType, ...] = (
    "must_include",
    "must_not_include",
    "success_criteria",
)


class EvalError(RuntimeError):
    """Raised when evaluation cannot continue."""


class CriterionJudgement(BaseModel):
    """LLM judgement for one criterion."""

    criterion: str = Field(description="Copy the evaluated criterion text.")
    is_success: bool = Field(description="Whether the criterion passed.")
    reason: str | None = Field(
        default=None,
        description=(
            "Null on success. On failure, one short Russian sentence, "
            "maximum 160 characters."
        ),
    )


class CriteriaJudgement(BaseModel):
    """Structured LLM output for a criteria group."""

    results: list[CriterionJudgement] = Field(
        description="One result per input criterion, preserving input order."
    )


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp with a Z suffix."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise EvalError(f"Expected JSON object in {path}")
    return data


def save_json(path: Path, data: dict[str, Any]) -> None:
    """Save JSON with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def configure_logging(quiet: bool = False) -> None:
    """Configure progress logging for CLI runs."""
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy_logger in ("httpx", "httpcore", "openai", "langchain"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def load_prompt(criteria_type: CriteriaType) -> str:
    """Load criteria-specific judge prompt."""
    prompt_path = PROMPTS_DIR / f"{criteria_type}.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def dataset_by_case_id(dataset: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Index dataset cases by case_id."""
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        raise EvalError('Dataset must contain a "cases" array')
    indexed: dict[int, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if isinstance(case_id, int):
            indexed[case_id] = case
    return indexed


def criteria_for_case(case: dict[str, Any], criteria_type: CriteriaType) -> list[str]:
    """Return criteria list for the selected type."""
    raw = case.get(criteria_type, [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def compact_sample_payload(
    sample: dict[str, Any],
    case: dict[str, Any],
    criteria_type: CriteriaType,
    eval_time: str,
    current_date: str,
) -> dict[str, Any]:
    """Build the payload passed to the judge."""
    return {
        "case_id": sample.get("case_id"),
        "case_name": sample.get("case_name"),
        "category": sample.get("category"),
        "criteria_type": criteria_type,
        "eval_time": eval_time,
        "eval_current_date": current_date,
        "criteria": criteria_for_case(case, criteria_type),
        "dialog": sample.get("dialog", []),
        "assistant_response": sample.get("assistant_response", ""),
        "expected_tools": case.get("expected_tools", []),
        "actual_tools": sample.get("actual_tools", []),
        "mock_tool_events": sample.get("mock_tool_events", []),
        "run_status": sample.get("status"),
        "run_error": sample.get("error"),
    }


def build_user_prompt(payload: dict[str, Any]) -> str:
    """Build the user message for the judge LLM."""
    return (
        "Оцени один sample benchmark-прогона.\n"
        "Верни результат только через structured output.\n\n"
        f"JSON payload:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def benchmark_current_date(
    dataset: dict[str, Any],
    run_result: dict[str, Any],
) -> str:
    """Return a stable date used to evaluate relative dates in benchmark cases."""
    for value in (
        dataset.get("reference_date"),
        dataset.get("run_time"),
        run_result.get("run_time"),
    ):
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    return utc_now()[:10]


def _format_path(path: tuple[Any, ...]) -> str:
    """Format a nested argument path for diagnostics."""
    rendered = ""
    for item in path:
        if isinstance(item, int):
            rendered += f"[{item}]"
        else:
            rendered += f".{item}" if rendered else str(item)
    return rendered


def _compare_expected_subset(
    expected: Any,
    actual: Any,
    path: tuple[Any, ...] = (),
) -> list[str]:
    """Return mismatches when expected is not a subset of actual."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [
                f"{_format_path(path)}: expected object, got {type(actual).__name__}"
            ]
        errors: list[str] = []
        for key, expected_value in expected.items():
            if key not in actual:
                errors.append(f"{_format_path(path + (key,))}: missing")
                continue
            errors.extend(
                _compare_expected_subset(
                    expected_value,
                    actual[key],
                    path + (key,),
                )
            )
        return errors

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{_format_path(path)}: expected list, got {type(actual).__name__}"]
        if len(expected) != len(actual):
            return [
                f"{_format_path(path)}: expected list length {len(expected)}, got {len(actual)}"
            ]
        errors = []
        for index, expected_item in enumerate(expected):
            errors.extend(
                _compare_expected_subset(
                    expected_item,
                    actual[index],
                    path + (index,),
                )
            )
        return errors

    if expected != actual:
        return [f"{_format_path(path)}: expected {expected!r}, got {actual!r}"]
    return []


def tool_contract_results(
    sample: dict[str, Any],
    case: dict[str, Any],
) -> list[dict[str, Any]]:
    """Deterministically evaluate expected tool calls against actual calls."""
    expected_tools = case.get("expected_tools", [])
    actual_tools = sample.get("actual_tools", [])
    if not isinstance(expected_tools, list):
        expected_tools = []
    if not isinstance(actual_tools, list):
        actual_tools = []

    if not expected_tools:
        return [
            {
                "criterion": "Tool contract: инструменты не должны быть вызваны",
                "is_success": len(actual_tools) == 0,
                "reason": (
                    None
                    if len(actual_tools) == 0
                    else f"Ожидалось 0 tool calls, фактически: {len(actual_tools)}"
                ),
            }
        ]

    expected_names = [tool.get("tool_name") for tool in expected_tools]
    actual_names = [tool.get("tool_name") for tool in actual_tools]
    count_and_order_ok = expected_names == actual_names
    results = [
        {
            "criterion": "Tool contract: порядок и имена инструментов совпадают с expected_tools",
            "is_success": count_and_order_ok,
            "reason": (
                None
                if count_and_order_ok
                else f"Ожидались {expected_names}, фактически {actual_names}"
            ),
        }
    ]

    argument_errors: list[str] = []
    for index, expected_tool in enumerate(expected_tools):
        if index >= len(actual_tools):
            argument_errors.append(f"tool[{index}]: actual call отсутствует")
            continue
        expected_args = expected_tool.get("arguments", {})
        actual_args = actual_tools[index].get("arguments", {})
        if not isinstance(expected_args, dict):
            expected_args = {}
        if not isinstance(actual_args, dict):
            actual_args = {}
        mismatches = _compare_expected_subset(
            expected_args,
            actual_args,
            path=(f"tool[{index}].arguments",),
        )
        argument_errors.extend(mismatches)

    results.append(
        {
            "criterion": "Tool contract: обязательные аргументы expected_tools присутствуют и совпадают",
            "is_success": not argument_errors,
            "reason": None if not argument_errors else "; ".join(argument_errors[:8]),
        }
    )
    return results


def build_llm() -> Any:
    """Create configured LLM for structured judge output."""
    try:
        from dotenv import load_dotenv
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise EvalError(
            "Eval requires bot dependencies. Run with `uv run --extra bot ...`."
        ) from exc

    load_dotenv()
    api_key = os.getenv("AI_API_KEY")
    model = os.getenv("AI_EVAL_MODEL") or os.getenv("AI_MODEL", "")
    if not api_key or not model:
        raise EvalError("AI_API_KEY and AI_EVAL_MODEL or AI_MODEL are required")

    kwargs: dict[str, Any] = {
        "api_key": SecretStr(api_key),
        "model": model,
        "temperature": float(os.getenv("AI_EVAL_TEMPERATURE", "0.0")),
        "base_url": os.getenv("AI_BASE_URL") or None,
        "max_completion_tokens": int(os.getenv("AI_EVAL_MAX_TOKENS", "3000")),
    }
    project = os.getenv("AI_PROJECT")
    if project:
        kwargs["default_headers"] = {"OpenAI-Project": project}
    return ChatOpenAI(**kwargs)


async def judge_criteria(
    llm: Any,
    sample: dict[str, Any],
    case: dict[str, Any],
    criteria_type: CriteriaType,
    run_time: str,
    current_date: str,
) -> dict[str, Any]:
    """Evaluate one criteria group with its own prompt and structured output."""
    criteria = criteria_for_case(case, criteria_type)
    logger.info(
        "[eval] case=%s criteria=%s started criteria_count=%d",
        sample.get("case_id"),
        criteria_type,
        len(criteria),
    )
    if not criteria:
        judgement = CriteriaJudgement(results=[])
    else:
        prompt = load_prompt(criteria_type)
        payload = compact_sample_payload(
            sample,
            case,
            criteria_type,
            run_time,
            current_date,
        )
        model = llm.with_structured_output(CriteriaJudgement)
        judgement = await model.ainvoke(
            [
                ("system", prompt),
                ("user", build_user_prompt(payload)),
            ]
        )

    normalized_results = []
    for index, criterion in enumerate(criteria):
        result = judgement.results[index] if index < len(judgement.results) else None
        if result is None:
            normalized_results.append(
                {
                    "criterion": criterion,
                    "is_success": False,
                    "reason": "Судья не вернул оценку для этого критерия",
                }
            )
            continue
        normalized_results.append(
            {
                "criterion": criterion,
                "is_success": bool(result.is_success),
                "reason": (
                    None
                    if result.is_success
                    else result.reason or "Критерий не выполнен"
                ),
            }
        )

    if criteria_type == "success_criteria":
        normalized_results.extend(tool_contract_results(sample, case))

    failed_count = sum(1 for result in normalized_results if not result["is_success"])
    logger.info(
        "[eval] case=%s criteria=%s done failed=%d total=%d",
        sample.get("case_id"),
        criteria_type,
        failed_count,
        len(normalized_results),
    )

    return {
        "criteria_type": criteria_type,
        "sample_id": sample.get("sample_id"),
        "case_id": sample.get("case_id"),
        "case_name": sample.get("case_name"),
        "run_time": run_time,
        "results": normalized_results,
    }


async def evaluate_run_result(
    run_result: dict[str, Any],
    dataset: dict[str, Any],
    criteria_types: tuple[CriteriaType, ...],
    case_ids: set[int] | None = None,
) -> dict[str, Any]:
    """Evaluate all samples in a run_result."""
    llm = build_llm()
    cases_by_id = dataset_by_case_id(dataset)
    eval_time = utc_now()
    current_date = benchmark_current_date(dataset, run_result)
    entries: list[dict[str, Any]] = []

    samples = run_result.get("samples")
    if not isinstance(samples, list):
        raise EvalError('Run result must contain a "samples" array')

    selected_samples = [
        sample
        for sample in samples
        if isinstance(sample, dict)
        and (case_ids is None or sample.get("case_id") in case_ids)
    ]
    logger.info(
        "[eval] started samples=%d criteria_types=%s",
        len(selected_samples),
        ",".join(criteria_types),
    )
    logger.info("[eval] reference_date=%s", current_date)

    evaluated_sample_count = 0
    for sample_index, sample in enumerate(selected_samples, start=1):
        case_id = sample.get("case_id")
        evaluated_sample_count += 1
        case = cases_by_id.get(case_id)
        if case is None:
            raise EvalError(f"Case {case_id} from run_result not found in dataset")
        logger.info(
            "[eval] sample %d/%d case=%s name=%s",
            sample_index,
            len(selected_samples),
            case_id,
            sample.get("case_name"),
        )
        for criteria_type in criteria_types:
            entries.append(
                await judge_criteria(
                    llm=llm,
                    sample=sample,
                    case=case,
                    criteria_type=criteria_type,
                    run_time=eval_time,
                    current_date=current_date,
                )
            )

    total_criteria = sum(len(entry["results"]) for entry in entries)
    failed_criteria = sum(
        1
        for entry in entries
        for result in entry["results"]
        if not result["is_success"]
    )
    logger.info(
        "[eval] completed samples=%d groups=%d failed=%d total=%d",
        evaluated_sample_count,
        len(entries),
        failed_criteria,
        total_criteria,
    )
    return {
        "benchmark_id": run_result.get(
            "benchmark_id", dataset.get("benchmark_id", "unknown")
        ),
        "run_id": run_result.get("run_id"),
        "eval_id": f"eval-{uuid4().hex}",
        "eval_time": eval_time,
        "source_run_result": run_result.get("source_run_result"),
        "judge": {
            "type": "llm_as_judge",
            "mode": "structured_output",
            "criteria_types": list(criteria_types),
            "reference_date": current_date,
            "model": os.getenv("AI_EVAL_MODEL") or os.getenv("AI_MODEL"),
        },
        "summary": {
            "samples": evaluated_sample_count,
            "criteria_groups": len(entries),
            "criteria_total": total_criteria,
            "criteria_succeeded": total_criteria - failed_criteria,
            "criteria_failed": failed_criteria,
        },
        "results": entries,
    }


def output_path(output_dir: Path, eval_result: dict[str, Any]) -> Path:
    """Build output path for eval result."""
    safe_time = str(eval_result["eval_time"]).replace(":", "-")
    return output_dir / f"eval_result_{safe_time}.json"


def parse_criteria(raw: str) -> tuple[CriteriaType, ...]:
    """Parse criteria CLI option."""
    if raw == "all":
        return CRITERIA_TYPES
    requested = tuple(item.strip() for item in raw.split(",") if item.strip())
    invalid = [item for item in requested if item not in CRITERIA_TYPES]
    if invalid:
        raise EvalError(f"Unsupported criteria type(s): {', '.join(invalid)}")
    return requested  # type: ignore[return-value]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate autoeval run_result with LLM structured output."
    )
    parser.add_argument(
        "--run-result",
        type=Path,
        default=DEFAULT_RUN_RESULT,
        help=f"Path to run_result JSON. Default: {DEFAULT_RUN_RESULT}",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Path to dataset JSON. Default: {DEFAULT_DATASET}",
    )
    parser.add_argument(
        "--criteria",
        default="all",
        help=(
            "Comma-separated criteria types or 'all'. "
            "Available: must_include,must_not_include,success_criteria."
        ),
    )
    parser.add_argument(
        "--case-id",
        type=int,
        action="append",
        default=None,
        help="Evaluate only selected case_id. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for eval_result files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Exact output file path. Overrides --output-dir.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable progress logs; only print final output path.",
    )
    return parser.parse_args()


async def async_main() -> None:
    """Async CLI entrypoint."""
    args = parse_args()
    configure_logging(quiet=args.quiet)
    run_result_path = args.run_result.resolve()
    logger.info("[eval] loading run_result=%s", run_result_path)
    run_result = load_json(run_result_path)
    run_result["source_run_result"] = str(run_result_path)
    dataset_path = args.dataset.resolve()
    logger.info("[eval] loading dataset=%s", dataset_path)
    dataset = load_json(dataset_path)
    criteria_types = parse_criteria(args.criteria)
    eval_result = await evaluate_run_result(
        run_result=run_result,
        dataset=dataset,
        criteria_types=criteria_types,
        case_ids=set(args.case_id) if args.case_id else None,
    )
    result_path = (
        args.output.resolve()
        if args.output
        else output_path(
            args.output_dir.resolve(),
            eval_result,
        )
    )
    save_json(result_path, eval_result)
    logger.info("[eval] saved %s", result_path)
    print(str(result_path))


def main() -> None:
    """CLI entrypoint."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
