from abc import ABC, abstractmethod
from typing import Any


class CompletionResponse:
    """Normalized response - use .text for provider-agnostic access."""

    def __init__(self, text: str, raw: Any = None):
        self.text = text
        self.raw = raw


class ModelProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        pass
