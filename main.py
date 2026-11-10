"""Terminal entry point for scripted repairs and the Gradio UI."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from bootstrap import build_repair_service
from core.models import RepairResult


def main(argv: list[str] | None = None) -> int:
    """Parse the selected command and run repair or the local UI."""
    parser = argparse.ArgumentParser(
        description="Run a bounded repair against one evals/ project."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    repair_parser = subparsers.add_parser(
        "repair", help="Repair one supplied evaluation project"
    )
    repair_parser.add_argument(
        "eval_path",
        help="Relative path to a project under evals/, for example evals/arithmetic",
    )
    repair_parser.add_argument(
        "--provider",
        required=True,
        choices=["scripted"],
        help="Chat provider used for repair decisions",
    )

    subparsers.add_parser(
        "ui", help="Open the local Gradio page for scripted repairs"
    )

    args = parser.parse_args(argv)
    if args.command == "ui":
        from adapters.gradio_ui import create_demo, launch_demo

        launch_demo(create_demo())
        return 0

    if args.command != "repair":
        parser.error(f"unsupported command: {args.command}")

    try:
        service = build_repair_service(args.provider)
        result = service.repair(args.eval_path)
    except Exception as exc:  # noqa: BLE001 - show a clear CLI failure
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _print_result(result)
    return 0 if result.passed else 1


def _print_result(result: RepairResult) -> None:
    """Print the visible trace, changed files, and final test result."""
    for event in result.trace:
        print(_format_event(event))

    print()
    print("Changed files:")
    if result.changed_files:
        for path in result.changed_files:
            print(f"  - {path}")
    else:
        print("  (none)")

    print()
    print("Final sandboxed test result:")
    if result.test_result is None:
        print("  (no test result)")
    else:
        print(f"  passed: {result.test_result.passed}")
        print(f"  returncode: {result.test_result.returncode}")
        output = result.test_result.output.rstrip() or "(empty)"
        print("  output:")
        for line in output.splitlines() or ["(empty)"]:
            print(f"    {line}")


def _format_event(event: dict[str, Any]) -> str:
    """Render one public trace event for the terminal."""
    name = event.get("event", "event")
    if name == "repair_started":
        return f"[repair_started] case={event.get('case')}"
    if name == "model_response":
        summary = event.get("summary") or ""
        tool = event.get("tool", "?")
        if event.get("ok") is False:
            return f"[model_response] invalid: {event.get('error')}"
        suffix = f" summary={summary!r}" if summary else ""
        return f"[model_response] tool={tool}{suffix}"
    if name == "tool_result":
        summary = event.get("summary") or ""
        suffix = f" summary={summary!r}" if summary else ""
        observation = str(event.get("observation", "")).replace("\n", "\\n")
        if len(observation) > 160:
            observation = observation[:157] + "..."
        return (
            f"[tool_result] tool={event.get('tool')} ok={event.get('ok')}"
            f"{suffix} observation={observation!r}"
        )
    if name == "repair_finished":
        return (
            f"[repair_finished] passed={event.get('passed')} "
            f"reason={event.get('reason')}"
        )
    return f"[{name}] {event}"


if __name__ == "__main__":
    raise SystemExit(main())
