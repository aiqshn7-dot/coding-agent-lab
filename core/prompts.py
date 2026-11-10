"""Message text sent to the repair model."""

from __future__ import annotations

from collections.abc import Sequence


def system_instruction() -> str:
    """Return the fixed system rules for one repair attempt."""
    return (
        "You repair one buggy Python project using only the supplied local "
        "files and tools.\n"
        "Follow this evidence order:\n"
        "1. Inspect local code with read_file.\n"
        "2. Reproduce a failing test with run_tests before any edit.\n"
        "3. Make one focused edit with edit_file.\n"
        "4. Verify the repair with run_tests.\n"
        "Reply with exactly one JSON object and nothing else. No Markdown, "
        "no code fences, and no prose.\n"
        "The optional summary field is a short public label for the trace; "
        "it must not contain private reasoning.\n"
        "Allowed actions:\n"
        '{"tool":"read_file","path":"test_calculator.py","summary":"Read the test"}\n'
        '{"tool":"run_tests","summary":"Reproduce the failure"}\n'
        '{"tool":"edit_file","path":"calculator.py","content":"..."}'
    )


def case_request(case_name: str, relative_files: Sequence[str]) -> str:
    """Return the user request naming the case and its relative files."""
    files = "\n".join(f"- {path}" for path in relative_files)
    return (
        f"Repair the evaluation case `{case_name}`.\n"
        "These relative files are available in the workspace:\n"
        f"{files}\n"
        "Choose the next permitted action."
    )


def tool_result_message(observation: str) -> str:
    """Return a user message that reports one tool observation."""
    return f"Tool observation:\n{observation}"
