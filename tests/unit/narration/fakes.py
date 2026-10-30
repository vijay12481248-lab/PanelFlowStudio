"""Test doubles for the narration model client."""
from __future__ import annotations


class FakeModelClient:
    def __init__(self, responses: dict[str, list], models: dict[str, str] | None = None):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.models = models or {}
        self.calls: list[tuple] = []

    def model_for(self, role: str) -> str:
        return self.models.get(role, "qwen3.5:9b")

    def params_for(self, role: str) -> dict:
        return {}

    async def structured(self, role, prompt, schema, image=None, system=None):
        self.calls.append((role, prompt, image))
        queue = self.responses.get(role)
        if not queue:
            raise AssertionError(f"no queued response for role '{role}'")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(prompt) if callable(item) else item
