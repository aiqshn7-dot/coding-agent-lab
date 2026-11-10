"""Deterministic answer-card chat client for tests and scripted repairs."""

from __future__ import annotations

from collections.abc import Sequence


class ScriptedClient:
    """Return prepared reply strings in order, one per ``chat`` call."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self._index = 0

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the next prepared reply, or raise if none remain."""
        if self._index >= len(self._replies):
            raise RuntimeError("ScriptedClient has no replies remaining")
        reply = self._replies[self._index]
        self._index += 1
        return reply
