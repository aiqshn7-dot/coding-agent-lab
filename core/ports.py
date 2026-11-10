"""Type-level contracts for chat, repair tools, and optional tracing."""

from __future__ import annotations

from typing import Any, Protocol

from core.models import TestResult


class ChatClient(Protocol):
    """Object that turns a message list into one model reply string."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the next model reply for ``messages``."""
        ...


class RepairToolsPort(Protocol):
    """Safe workspace operations used by the repair loop.

    Task 2 provides a concrete ``RepairTools`` class that satisfies this port.
    """

    def read_file(self, path: str) -> str:
        """Return the UTF-8 text of a file inside the workspace."""
        ...

    def edit_file(self, path: str, content: str) -> None:
        """Write ``content`` to a file inside the workspace."""
        ...

    def run_tests(self) -> TestResult:
        """Run sandboxed tests and return a structured result."""
        ...


class TraceRecorder(Protocol):
    """Optional sink for public repair events."""

    def record(self, event: str, payload: dict[str, Any]) -> None:
        """Record one public ``event`` with a small ``payload``."""
        ...
