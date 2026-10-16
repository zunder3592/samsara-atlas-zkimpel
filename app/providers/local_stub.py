"""Optional local stub - different response shape. Behind PROVIDER_TYPE=local flag."""

import hashlib
import random

from app.providers.base import ModelProvider, CompletionResponse


class LocalStubProvider(ModelProvider):
    """Alternative stub with a different raw shape - tests provider abstraction robustness."""

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        if random.random() < 0.05:
            raise TimeoutError("Local stub timeout")

        key = hashlib.sha256((prompt + str(kwargs)).encode()).hexdigest()
        text = f"[local stub {key[:12]}]"
        raw = {"output": {"text": text}, "status": "ok"}
        return CompletionResponse(text=text, raw=raw)
