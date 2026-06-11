"""Loader for scenario files from the scenarios directory."""

import logging
import re
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def load_scenarios(scenarios_dir: Path | None = None) -> str:
    """Load all scenario markdown files and combine them into a single string.

    Reads all .md files from the scenarios directory and concatenates them
    with proper formatting for inclusion in the system prompt.

    Args:
        scenarios_dir: Path to scenarios directory. Defaults to
            chat_bot/scenarios/ relative to this file.

    Returns:
        Combined scenario content as a formatted string.
        Returns empty string if no scenarios found.
    """
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent / "scenarios"

    if not scenarios_dir.exists():
        logger.warning(f"Scenarios directory not found: {scenarios_dir}")
        return ""

    scenario_files: List[Path] = sorted(scenarios_dir.glob("*.md"))

    if not scenario_files:
        logger.info("No scenario files found")
        return ""

    scenarios_content: List[str] = []
    scenarios_content.append("\n\n## 📋 Сценарии работы\n")
    scenarios_content.append(
        "Ниже описаны сложные сценарии. "
        "Следуй им пошагово при соответствующих запросах.\n"
    )

    for scenario_file in scenario_files:
        try:
            content = scenario_file.read_text(encoding="utf-8")
            scenarios_content.append(f"\n---\n\n{content}")
            logger.info(f"Loaded scenario: {scenario_file.name}")
        except Exception as e:
            logger.error(f"Failed to load scenario {scenario_file}: {e}")

    logger.info(f"Loaded {len(scenario_files)} scenario(s)")
    return "\n".join(scenarios_content)


def load_relevant_scenarios(
    message: str,
    scenarios_dir: Path | None = None,
) -> str:
    """Load only scenarios that match the current user message."""
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent / "scenarios"

    if not scenarios_dir.exists():
        logger.warning(f"Scenarios directory not found: {scenarios_dir}")
        return ""

    normalized_message = message.lower()
    matched_contents: List[str] = []

    for scenario_file in sorted(scenarios_dir.glob("*.md")):
        try:
            content = scenario_file.read_text(encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to load scenario {scenario_file}: {exc}")
            continue

        triggers = _extract_triggers(content)
        if not triggers:
            continue

        if any(trigger in normalized_message for trigger in triggers):
            logger.info("Matched scenario %s with triggers %s", scenario_file.name, triggers)
            matched_contents.append(f"\n---\n\n{content}")

    if not matched_contents:
        return ""

    header = (
        "\n\n## 📋 Релевантные сценарии\n"
        "Ниже только сценарии, которые подходят к текущему запросу.\n"
    )
    return header + "".join(matched_contents)


def _extract_triggers(content: str) -> List[str]:
    """Extract trigger phrases from a scenario markdown file."""
    match = re.search(r"\*\*Триггер\*\*:\s*(.+)", content)
    if not match:
        return []

    trigger_line = match.group(1)
    return [
        trigger.strip().lower()
        for trigger in re.findall(r'"([^"]+)"', trigger_line)
        if trigger.strip()
    ]



