"""Assemble concrete adapters with core repair services."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.models.ollama import OllamaClient
from adapters.models.scripted import ScriptedClient
from adapters.sandbox.repair_tools import RepairTools
from adapters.sandbox.runner import create_workspace
from core.ports import ChatClient
from core.repair_service import RepairService

ROOT = Path(__file__).resolve().parent
EVALS_ROOT = ROOT / "evals"


def build_repair_service(
    provider: str,
    *,
    model: str | None = None,
    temperature: float | None = None,
) -> RepairService:
    """Connect the selected chat provider to runner-backed repair tools."""
    if provider == "scripted":

        def make_client(case_name: str) -> ChatClient:
            try:
                replies = SCRIPTED_SEQUENCES[case_name]
            except KeyError as exc:
                raise ValueError(
                    f"no scripted sequence for case: {case_name}"
                ) from exc
            return ScriptedClient(replies)

    elif provider == "ollama":
        client = OllamaClient(
            model=model,
            temperature=0.0 if temperature is None else temperature,
        )

        def make_client(case_name: str) -> ChatClient:
            return client

    else:
        raise ValueError(f"unsupported provider: {provider}")

    def make_tools(workspace: Path) -> RepairTools:
        return RepairTools(workspace)

    return RepairService(
        make_client=make_client,
        create_workspace=create_workspace,
        make_tools=make_tools,
        evals_root=EVALS_ROOT,
    )


def _card(**fields: object) -> str:
    """Serialize one answer-card action as JSON text."""
    return json.dumps(fields, ensure_ascii=True)


SCRIPTED_SEQUENCES: dict[str, list[str]] = {
    "arithmetic": [
        _card(
            tool="read_file",
            path="test_calculator.py",
            summary="Read the test",
        ),
        _card(tool="run_tests", summary="Reproduce the failure"),
        _card(
            tool="edit_file",
            path="calculator.py",
            content=(
                "def add(left, right):\n"
                '    """Return the sum of two numbers."""\n'
                "    return left + right\n"
            ),
            summary="Fix addition",
        ),
        _card(tool="run_tests", summary="Verify the repair"),
    ],
    "balanced_brackets": [
        _card(
            tool="read_file",
            path="test_brackets.py",
            summary="Read the test",
        ),
        _card(tool="run_tests", summary="Reproduce the failure"),
        _card(
            tool="edit_file",
            path="brackets.py",
            content=(
                "def is_balanced(text):\n"
                '    """Return whether parentheses, brackets, and braces '
                'are properly nested."""\n'
                '    opening = "([{"\n'
                '    closing = ")]}"\n'
                '    pairs = {")": "(", "]": "[", "}": "{"}\n'
                "    stack = []\n"
                "\n"
                "    for character in text:\n"
                "        if character in opening:\n"
                "            stack.append(character)\n"
                "        elif character in closing:\n"
                "            if not stack or stack[-1] != pairs[character]:\n"
                "                return False\n"
                "            stack.pop()\n"
                "\n"
                "    return not stack\n"
            ),
            summary="Check matching pairs",
        ),
        _card(tool="run_tests", summary="Verify the repair"),
    ],
    "median": [
        _card(
            tool="read_file",
            path="test_statistics_tools.py",
            summary="Read the test",
        ),
        _card(tool="run_tests", summary="Reproduce the failure"),
        _card(
            tool="edit_file",
            path="statistics_tools.py",
            content=(
                "def median(values):\n"
                '    """Return the median value without changing the '
                'input sequence."""\n'
                "    ordered = sorted(values)\n"
                "    count = len(ordered)\n"
                "    middle = count // 2\n"
                "    if count % 2 == 0:\n"
                "        return (ordered[middle - 1] + ordered[middle]) / 2\n"
                "    return ordered[middle]\n"
            ),
            summary="Fix even-length median",
        ),
        _card(tool="run_tests", summary="Verify the repair"),
    ],
    "multi_function": [
        _card(
            tool="read_file",
            path="test_text_tools.py",
            summary="Read the test",
        ),
        _card(tool="run_tests", summary="Reproduce the failure"),
        _card(
            tool="edit_file",
            path="text_tools.py",
            content=(
                "def normalize_name(name):\n"
                '    """Trim surrounding whitespace and lowercase a '
                'supplied name."""\n'
                "    return name.strip().lower()\n"
                "\n"
                "\n"
                "def greeting(name):\n"
                '    """Create a greeting from a normalized name."""\n'
                '    return f"Hello, {normalize_name(name).title()}!"\n'
                "\n"
                "\n"
                "def initials(name):\n"
                '    """Return uppercase initials for the '
                'whitespace-separated parts of a name."""\n'
                '    return "".join(part[0].upper() for part in name.split())\n'
            ),
            summary="Fix greeting capitalization",
        ),
        _card(tool="run_tests", summary="Verify the repair"),
    ],
    "unique_words": [
        _card(
            tool="read_file",
            path="test_word_tools.py",
            summary="Read the test",
        ),
        _card(tool="run_tests", summary="Reproduce the failure"),
        _card(
            tool="edit_file",
            path="word_tools.py",
            content=(
                "def unique_words(text):\n"
                '    """Return lowercase words once, in the order '
                'first seen."""\n'
                "    seen = []\n"
                "    for word in text.lower().split():\n"
                "        if word not in seen:\n"
                "            seen.append(word)\n"
                "    return seen\n"
            ),
            summary="Preserve first-seen order",
        ),
        _card(tool="run_tests", summary="Verify the repair"),
    ],
}
