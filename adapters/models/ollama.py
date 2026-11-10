"""Local Ollama chat client for live repair decisions."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"


class OllamaClient:
    """Send prepared chat messages to a local Ollama server."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return Ollama reply text only; callers validate JSON separately."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": self.temperature},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Ollama HTTP {exc.code} for model {self.model!r}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama server unreachable at {self.base_url}: {exc.reason}"
            ) from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Ollama returned non-JSON response: {body[:200]!r}"
            ) from exc

        message = data.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama response missing message object")
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("Ollama response missing message content")
        return content
