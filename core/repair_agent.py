"""Bounded repair loop that validates model actions and runs safe tools."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from core.models import ModelAction, RepairResult, TestResult
from core.ports import ChatClient, RepairToolsPort
from core.prompts import case_request, system_instruction, tool_result_message

DECISION_BUDGET = 8

_ALLOWED_TOOLS = frozenset({"read_file", "run_tests", "edit_file"})
_TOOL_FIELDS: dict[str, frozenset[str]] = {
    "read_file": frozenset({"tool", "path", "summary"}),
    "run_tests": frozenset({"tool", "summary"}),
    "edit_file": frozenset({"tool", "path", "content", "summary"}),
}
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "read_file": frozenset({"tool", "path"}),
    "run_tests": frozenset({"tool"}),
    "edit_file": frozenset({"tool", "path", "content"}),
}


class RepairAgent:
    """Traffic controller for one bounded repair attempt."""

    def __init__(self, client: ChatClient, tools: RepairToolsPort) -> None:
        self._client = client
        self._tools = tools

    def repair(
        self,
        case_name: str,
        relative_files: Sequence[str],
        workspace: Path | str,
    ) -> RepairResult:
        """Run the repair loop and always return a ``RepairResult``."""
        trace: list[dict[str, Any]] = [
            {"event": "repair_started", "case": case_name}
        ]
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_instruction()},
            {
                "role": "user",
                "content": case_request(case_name, relative_files),
            },
        ]

        read_succeeded = False
        saw_failing_tests = False
        edited_after_failure = False
        last_test_result: TestResult | None = None

        for _ in range(DECISION_BUDGET):
            try:
                raw_reply = self._client.chat(messages)
            except Exception as exc:  # noqa: BLE001 - convert any client failure
                trace.append(
                    {
                        "event": "repair_finished",
                        "passed": False,
                        "reason": f"client error: {exc}",
                    }
                )
                return self._result(
                    passed=False,
                    trace=trace,
                    workspace=workspace,
                    test_result=last_test_result,
                )

            try:
                action = parse_model_action(raw_reply)
            except ValueError as exc:
                trace.append(
                    {
                        "event": "model_response",
                        "ok": False,
                        "error": str(exc),
                    }
                )
                trace.append(
                    {
                        "event": "repair_finished",
                        "passed": False,
                        "reason": f"invalid reply: {exc}",
                    }
                )
                return self._result(
                    passed=False,
                    trace=trace,
                    workspace=workspace,
                    test_result=last_test_result,
                )

            messages.append({"role": "assistant", "content": raw_reply})
            trace.append(
                {
                    "event": "model_response",
                    "tool": action.tool,
                    "summary": action.summary,
                }
            )

            if action.tool == "edit_file" and (
                not read_succeeded or not saw_failing_tests
            ):
                observation = (
                    "policy-error: edit_file requires one successful "
                    "read_file observation and one failing run_tests "
                    "observation before any edit"
                )
                messages.append(
                    {
                        "role": "user",
                        "content": tool_result_message(observation),
                    }
                )
                trace.append(
                    {
                        "event": "tool_result",
                        "tool": "edit_file",
                        "ok": False,
                        "observation": observation,
                        "summary": action.summary,
                    }
                )
                continue

            observation, last_test_result, tool_ok = self._execute(
                action, last_test_result
            )
            messages.append(
                {"role": "user", "content": tool_result_message(observation)}
            )
            trace.append(
                {
                    "event": "tool_result",
                    "tool": action.tool,
                    "ok": tool_ok,
                    "observation": observation,
                    "summary": action.summary,
                }
            )

            if action.tool == "read_file" and tool_ok:
                read_succeeded = True
            elif action.tool == "edit_file" and tool_ok:
                edited_after_failure = True
            elif action.tool == "run_tests" and last_test_result is not None and tool_ok:
                if last_test_result.passed:
                    if edited_after_failure:
                        trace.append(
                            {
                                "event": "repair_finished",
                                "passed": True,
                                "reason": "tests passed after repair edit",
                            }
                        )
                        return self._result(
                            passed=True,
                            trace=trace,
                            workspace=workspace,
                            test_result=last_test_result,
                        )
                    trace.append(
                        {
                            "event": "repair_finished",
                            "passed": False,
                            "reason": (
                                "no reproducible bug: tests passed before "
                                "any edit"
                            ),
                        }
                    )
                    return self._result(
                        passed=False,
                        trace=trace,
                        workspace=workspace,
                        test_result=last_test_result,
                    )
                saw_failing_tests = True

        trace.append(
            {
                "event": "repair_finished",
                "passed": False,
                "reason": "decision budget exhausted",
            }
        )
        return self._result(
            passed=False,
            trace=trace,
            workspace=workspace,
            test_result=last_test_result,
        )

    def _execute(
        self,
        action: ModelAction,
        last_test_result: TestResult | None,
    ) -> tuple[str, TestResult | None, bool]:
        """Run one permitted tool and return observation text plus status."""
        try:
            if action.tool == "read_file":
                content = self._tools.read_file(str(action.arguments["path"]))
                return content, last_test_result, True
            if action.tool == "edit_file":
                self._tools.edit_file(
                    str(action.arguments["path"]),
                    str(action.arguments["content"]),
                )
                return "edit applied", last_test_result, True
            result = self._tools.run_tests()
            observation = (
                f"passed={result.passed} returncode={result.returncode}\n"
                f"{result.output}"
            )
            return observation, result, True
        except Exception as exc:  # noqa: BLE001 - surface tool failures
            return f"error: {exc}", last_test_result, False

    def _result(
        self,
        *,
        passed: bool,
        trace: list[dict[str, Any]],
        workspace: Path | str,
        test_result: TestResult | None,
    ) -> RepairResult:
        changed_files = list(getattr(self._tools, "changed_files", []))
        return RepairResult(
            passed=passed,
            trace=trace,
            changed_files=changed_files,
            workspace=workspace,
            test_result=test_result,
        )


def parse_model_action(raw_reply: str) -> ModelAction:
    """Parse one strict JSON action object into a ``ModelAction``."""
    text = raw_reply.strip()
    if not text:
        raise ValueError("empty reply")
    if "```" in text:
        raise ValueError("Markdown fences are not allowed")

    try:
        data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("reply must be exactly one JSON object")

    tool = data.get("tool")
    if not isinstance(tool, str) or tool not in _ALLOWED_TOOLS:
        raise ValueError(f"unknown tool: {tool!r}")

    allowed = _TOOL_FIELDS[tool]
    unexpected = set(data) - allowed
    if unexpected:
        raise ValueError(f"fields not allowed for {tool}: {sorted(unexpected)}")

    missing = _REQUIRED_FIELDS[tool] - set(data)
    if missing:
        raise ValueError(f"missing fields for {tool}: {sorted(missing)}")

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise ValueError("summary must be a string when provided")

    if tool == "read_file":
        path = data["path"]
        if not isinstance(path, str) or not path:
            raise ValueError("path must be a non-empty string")
        return ModelAction(tool=tool, arguments={"path": path}, summary=summary)

    if tool == "run_tests":
        return ModelAction(tool=tool, arguments={}, summary=summary)

    path = data["path"]
    content = data["content"]
    if not isinstance(path, str) or not path:
        raise ValueError("path must be a non-empty string")
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    return ModelAction(
        tool=tool,
        arguments={"path": path, "content": content},
        summary=summary,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject JSON objects that repeat the same key."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result
