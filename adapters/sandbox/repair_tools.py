"""Safe read, edit, and sandboxed test tools for one workspace copy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from adapters.sandbox.runner import run_tests as docker_run_tests
from core.models import TestResult


def safe_path(workspace: Path | str, requested_path: str) -> Path:
    """Resolve ``requested_path`` inside ``workspace`` or raise ``ValueError``.

    Rejects absolute paths and any path that resolves outside the workspace.
    """
    workspace_root = Path(workspace).resolve()
    candidate = Path(requested_path)
    if candidate.is_absolute():
        raise ValueError(f"absolute paths are not allowed: {requested_path}")

    resolved = (workspace_root / candidate).resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError(
            f"path escapes workspace: {requested_path}"
        ) from exc
    return resolved


class RepairTools:
    """RepairToolsPort implementation bounded to one disposable workspace."""

    def __init__(
        self,
        workspace: Path | str,
        run_tests_fn: Callable[[Path], TestResult] | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.changed_files: list[str] = []
        self._run_tests_fn = run_tests_fn or docker_run_tests

    def read_file(self, path: str) -> str:
        """Return UTF-8 text for a file inside the workspace."""
        target = safe_path(self.workspace, path)
        return target.read_text(encoding="utf-8")

    def edit_file(self, path: str, content: str) -> None:
        """Write UTF-8 ``content`` and record the relative path once."""
        target = safe_path(self.workspace, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        relative = Path(path).as_posix()
        if relative not in self.changed_files:
            self.changed_files.append(relative)

    def run_tests(self) -> TestResult:
        """Delegate to the Docker-backed runner for this workspace."""
        return self._run_tests_fn(self.workspace)
