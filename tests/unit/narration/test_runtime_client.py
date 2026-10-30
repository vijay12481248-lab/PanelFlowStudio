import asyncio

import httpx
import pytest
from pydantic import BaseModel

from engine.narration.runtime.client import ProviderModelClient, StepModelError
from engine.narration.runtime.roles import RoleConfig

ROLES = {
    "planner": RoleConfig(model="qwen3.5:9b", temperature=0.2, max_tokens=900),
    "vision": RoleConfig(model="vis:1", temperature=0.1, max_tokens=500),
}


class Out(BaseModel):
    x: int


class StubProvider:
    """Scripts one outcome (value or exception) per call and records kwargs."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def _next(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    async def generate_structured(self, *args, **kwargs):
        return self._next(*args, **kwargs)

    async def analyze_vision(self, *args, **kwargs):
        return self._next(*args, **kwargs)


def client(provider):
    return ProviderModelClient(provider, ROLES, backoff_s=(0, 0))


def test_text_call_passes_role_params():
    p = StubProvider([Out(x=1)])
    assert asyncio.run(client(p).structured("planner", "hi", Out)) == Out(x=1)
    kw = p.calls[0][1]
    assert kw["model"] == "qwen3.5:9b" and kw["temperature"] == 0.2
    assert kw["max_repair_retries"] == 1 and kw["num_ctx"] == 8192 and kw["max_tokens"] == 900


def test_vision_call_validates_json_and_retries_once_on_bad_json():
    p = StubProvider(["not json", '{"x": 2}'])
    assert asyncio.run(client(p).structured("vision", "look", Out, image=b"img")) == Out(x=2)
    assert len(p.calls) == 2
    assert "failed validation" in p.calls[1][0][1]


def test_vision_bad_json_twice_raises_step_model_error():
    p = StubProvider(["nope", "still nope"])
    with pytest.raises(StepModelError) as e:
        asyncio.run(client(p).structured("vision", "look", Out, image=b"img"))
    assert e.value.role == "vision"


def test_timeout_retries_with_backoff_then_fails():
    p = StubProvider([httpx.ConnectError("x")] * 3)
    with pytest.raises(StepModelError):
        asyncio.run(client(p).structured("planner", "hi", Out))
    assert len(p.calls) == 3


def test_timeout_then_success_returns_result():
    p = StubProvider([httpx.ReadTimeout("slow"), Out(x=3)])
    assert asyncio.run(client(p).structured("planner", "hi", Out)) == Out(x=3)
    assert len(p.calls) == 2
