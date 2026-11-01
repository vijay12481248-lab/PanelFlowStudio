import asyncio

import pytest
from pydantic import BaseModel

from engine.narration.__main__ import _hosted_providers
from engine.narration.runtime.client import ProviderModelClient, guard_prompt
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler


class Out(BaseModel):
    ok: bool


class Fake:
    def __init__(self, name):
        self.name, self.calls = name, 0

    async def generate_structured(self, prompt, schema, **kw):
        self.calls += 1
        return schema(ok=True)


def roles():
    base = dict(temperature=0.2, max_tokens=4096, num_ctx=8192)
    return {"writer": RoleConfig(model="qwen3.5:9b", **base),
            "planner": RoleConfig(model="gemini-x", provider="gemini", concurrency=4, **base)}


def test_hosted_role_uses_its_own_provider_and_skips_the_local_context_guard():
    local, remote = Fake("local"), Fake("remote")
    client = ProviderModelClient(local, roles(), overrides={"planner": remote})
    assert asyncio.run(client.structured("planner", "x", Out)).ok and (local.calls, remote.calls) == (0, 1)
    asyncio.run(client.structured("writer", "x", Out))
    assert (local.calls, remote.calls) == (1, 1)
    assert "num_ctx" not in client.params_for("planner")
    guard_prompt(client, "planner", "word " * 20000)  # far over 8192 tokens, but the hosted model has its own limit


def test_hosted_role_needs_an_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _hosted_providers(roles())
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert set(_hosted_providers(roles())) == {"planner"}


def test_scheduler_runs_hosted_roles_wide_without_touching_the_local_model():
    async def unload(model):
        raise AssertionError("must not unload")

    async def one(i):
        return i * 2

    assert asyncio.run(ModelScheduler(roles(), unload).map("planner", [1, 2, 3], one)) == [2, 4, 6]
