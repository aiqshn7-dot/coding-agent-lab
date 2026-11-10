"""Focused checks for safe workspace tools and runner delegation."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.sandbox.repair_tools import RepairTools
from core.models import TestResult


def test_read_file_returns_workspace_contents(tmp_path: Path) -> None:
    """A normal relative path inside the workspace can be read."""
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    tools = RepairTools(tmp_path, run_tests_fn=_unused_runner)

    assert tools.read_file("notes.txt") == "hello\n"


def test_read_file_rejects_absolute_path(tmp_path: Path) -> None:
    """Absolute paths must be rejected before any file access."""
    target = tmp_path / "notes.txt"
    target.write_text("hello\n", encoding="utf-8")
    tools = RepairTools(tmp_path, run_tests_fn=_unused_runner)

    with pytest.raises(ValueError, match="absolute"):
        tools.read_file(str(target))


def test_read_file_rejects_parent_traversal(tmp_path: Path) -> None:
    """Paths that resolve outside the workspace must be rejected."""
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    tools = RepairTools(tmp_path, run_tests_fn=_unused_runner)

    with pytest.raises(ValueError, match="escapes workspace"):
        tools.read_file("../secret.txt")


def test_edit_file_saves_and_records_once(tmp_path: Path) -> None:
    """Edits persist on disk and each relative path is recorded once."""
    (tmp_path / "module.py").write_text("old\n", encoding="utf-8")
    tools = RepairTools(tmp_path, run_tests_fn=_unused_runner)

    tools.edit_file("module.py", "new\n")
    tools.edit_file("module.py", "newer\n")

    assert (tmp_path / "module.py").read_text(encoding="utf-8") == "newer\n"
    assert tools.changed_files == ["module.py"]


def test_run_tests_delegates_to_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_tests must call the Docker-backed runner, not host pytest."""
    calls: list[Path] = []

    def fake_runner(workspace: Path) -> TestResult:
        calls.append(Path(workspace))
        return TestResult(passed=True, output="1 passed", returncode=0)

    def fail_if_host_pytest(command, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError(f"host process started: {command!r}")

    monkeypatch.setattr("adapters.sandbox.runner.subprocess.run", fail_if_host_pytest)
    monkeypatch.setattr("subprocess.run", fail_if_host_pytest)

    tools = RepairTools(tmp_path, run_tests_fn=fake_runner)
    result = tools.run_tests()

    assert result == TestResult(passed=True, output="1 passed", returncode=0)
    assert calls == [tmp_path]


def _unused_runner(workspace: Path) -> TestResult:
    """Stub runner for tests that never invoke run_tests."""
    raise AssertionError(f"run_tests should not be called for {workspace}")
