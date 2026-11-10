"""Gradio presentation layer for the existing repair service."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Any

import gradio as gr

from bootstrap import build_repair_service
from core.models import RepairResult
from core.repair_service import RepairService

CASE_CHOICES = [
    "arithmetic",
    "balanced_brackets",
    "median",
    "multi_function",
    "unique_words",
]

# Gradio may only move/serve files from cwd, system temp, or launch(allowed_paths=...).
DOWNLOAD_ROOT = Path(tempfile.gettempdir()) / "coding-agent-lab-gradio-downloads"


def create_demo(service: RepairService | None = None) -> gr.Blocks:
    """Build the Gradio page that starts repairs through ``RepairService``."""
    repair_service = service or build_repair_service("scripted")

    def run_repair(
        case_name: str,
    ) -> tuple[str, str, str, str | None]:
        """Run one scripted repair and return display payloads."""
        if case_name not in CASE_CHOICES:
            raise gr.Error(f"unsupported case: {case_name}")

        result = repair_service.repair(f"evals/{case_name}")
        zip_path = _zip_workspace(result.workspace)
        return (
            _format_trace(result),
            _format_changed_files(result),
            _format_test_output(result),
            zip_path,
        )

    with gr.Blocks(title="Python Repair Agent") as demo:
        gr.Markdown(
            "# Python Repair Agent\n"
            "Select one supplied evaluation project and run the existing "
            "scripted repair service."
        )
        case = gr.Dropdown(
            choices=CASE_CHOICES,
            value="arithmetic",
            label="Evaluation project",
        )
        start = gr.Button("Start repair", variant="primary")
        trace = gr.Textbox(label="Visible trace", lines=16)
        changed = gr.Textbox(label="Changed files", lines=16)
        tests = gr.Textbox(label="Final test output", lines=10)
        download = gr.File(label="Repaired workspace ZIP")

        start.click(
            fn=run_repair,
            inputs=[case],
            outputs=[trace, changed, tests, download],
        )

    return demo


def _format_trace(result: RepairResult) -> str:
    """Render the public repair trace as plain text."""
    return "\n".join(_format_event(event) for event in result.trace)


def _format_changed_files(result: RepairResult) -> str:
    """Show each changed relative path with its repaired text."""
    workspace = Path(result.workspace)
    if not result.changed_files:
        return "(none)"

    sections: list[str] = []
    for relative in result.changed_files:
        path = workspace / relative
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        sections.append(f"## {relative}\n{text}")
    return "\n\n".join(sections)


def _format_test_output(result: RepairResult) -> str:
    """Show the final sandboxed test result."""
    if result.test_result is None:
        return "(no test result)"
    output = result.test_result.output.rstrip() or "(empty)"
    return (
        f"passed: {result.test_result.passed}\n"
        f"returncode: {result.test_result.returncode}\n"
        f"output:\n{output}"
    )


def _format_event(event: dict[str, Any]) -> str:
    """Render one public trace event."""
    name = event.get("event", "event")
    if name == "repair_started":
        return f"[repair_started] case={event.get('case')}"
    if name == "model_response":
        if event.get("ok") is False:
            return f"[model_response] invalid: {event.get('error')}"
        summary = event.get("summary") or ""
        suffix = f" summary={summary!r}" if summary else ""
        return f"[model_response] tool={event.get('tool')}{suffix}"
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


def _zip_workspace(workspace: Path | str) -> str:
    """Zip the workspace into a Gradio-approved temporary download path."""
    root = Path(workspace)
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    archive = DOWNLOAD_ROOT / f"{root.name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root).as_posix())
    return str(archive.resolve())


def launch_demo(demo: gr.Blocks | None = None, **launch_kwargs: Any) -> None:
    """Launch the UI while allowing the temporary ZIP download directory."""
    blocks = demo or create_demo()
    allowed_paths = list(launch_kwargs.pop("allowed_paths", []) or [])
    download_root = str(DOWNLOAD_ROOT.resolve())
    if download_root not in allowed_paths:
        allowed_paths.append(download_root)
    blocks.launch(allowed_paths=allowed_paths, **launch_kwargs)
