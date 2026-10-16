"""Ollama provider - calls local Ollama API. No API key required."""

import os
import requests

from app.providers.base import ModelProvider, CompletionResponse


class OllamaProvider(ModelProvider):
    """Calls local Ollama API at http://localhost:11434."""

    def __init__(self, base_url: str | None = None, model: str = "llama3.2"):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", model)

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        resp = requests.post(
            f"{self.base_url.rstrip('/')}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "")
        raw = {"response": text, "model": self.model}
        return CompletionResponse(text=text, raw=raw)
