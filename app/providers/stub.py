import hashlib
import json
import random

from app.providers.base import ModelProvider, CompletionResponse


class StubProvider(ModelProvider):
    """Deterministic stub: same prompt+inputs -> same output. 2% chance TimeoutError."""

    def __init__(self, timeout_chance: float = 0.02):
        self.timeout_chance = timeout_chance

    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        if random.random() < self.timeout_chance:
            raise TimeoutError("Stub provider simulated timeout")

        key = hashlib.sha256((prompt + str(sorted(kwargs.items()))).encode()).hexdigest()
        if "subject" in prompt.lower() and "cited_snippets" in prompt.lower():
            text = json.dumps({
                "subject": f"Following up on your case: {key[:12]}",
                "body": "Thanks for reaching out. Here is what I found and the next steps.",
                "tone": kwargs.get("tone", "empathetic"),
                "cited_snippets": ["Snippet from leave-of-absence policy"],
            })
        elif "summary" in prompt.lower() and "action_items" in prompt.lower():
            text = json.dumps({
                "summary": f"Case summary for {key[:8]}",
                "action_items": ["Confirm eligibility with HRBP", "Share PTO balance"],
                "next_steps": ["Send policy link", "Follow up in 3 business days"],
            })
        elif "Generate" in prompt or "generate_response" in prompt.lower():
            text = json.dumps({
                "subject": f"Following up on your case: {key[:12]}",
                "body": "Thanks for reaching out. Here is what I found and the next steps.",
                "tone": kwargs.get("tone", "empathetic"),
                "cited_snippets": ["Snippet from leave-of-absence policy"],
            })
        else:
            text = f"[stub response for {key[:16]}]"
        raw = {
            "choices": [
                {"message": {"content": text, "role": "assistant"}}
            ],
            "model": "stub",
        }
        return CompletionResponse(text=text, raw=raw)
