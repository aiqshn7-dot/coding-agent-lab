"""Shared result shapes used across the repair workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TestResult:
    """Outcome of one sandboxed pytest run."""

    __test__ = False

    passed: bool
    output: str
    returncode: int


@dataclass
class ModelAction:
    """One permitted tool request parsed from a model reply."""

    tool: str
    arguments: dict[str, Any]
    summary: str | None = None


@dataclass
class RepairResult:
    """Final outcome of one repair attempt."""

    passed: bool
    trace: list[dict[str, Any]]
    changed_files: list[str]
    workspace: Path | str
    test_result: TestResult | None
