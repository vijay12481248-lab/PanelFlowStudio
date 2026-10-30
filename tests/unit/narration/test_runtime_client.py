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


def test_vision_call_passes_role_num_ctx_and_temperature():
    p = StubProvider(['{"x": 1}'])
    asyncio.run(client(p).structured("vision", "look", Out, image=b"img"))
    kw = p.calls[0][1]
    assert kw["num_ctx"] == 8192 and kw["temperature"] == 0.1 and kw["max_tokens"] == 500


def test_ollama_vision_honours_num_ctx_and_temperature(monkeypatch):
    from engine.llm.providers.ollama import OllamaProvider

    prov, sent = OllamaProvider(), []

    async def fake(payload, **kw):
        sent.append(payload["options"])
        return "{}"

    monkeypatch.setattr(prov, "_generate_response", fake)
    asyncio.run(prov.analyze_vision(b"x", "p", num_ctx=4096, temperature=0.3))
    asyncio.run(prov.analyze_vision(b"x", "p"))
    assert sent[0]["num_ctx"] == 4096 and sent[0]["temperature"] == 0.3
    assert sent[1]["num_ctx"] == prov.num_ctx and sent[1]["temperature"] == 0.1


@pytest.mark.parametrize("kind", ["text", "vision"])
def test_provider_error_becomes_step_model_error_with_role(kind):
    p = StubProvider([RuntimeError("Ollama generation failed: HTTP 400: bad")])
    args = ("planner", "hi", Out) if kind == "text" else ("vision", "look", Out)
    with pytest.raises(StepModelError) as e:
        asyncio.run(client(p).structured(*args, **({"image": b"i"} if kind == "vision" else {})))
    assert e.value.role == args[0] and len(p.calls) == 1


def test_http_5xx_is_transient_and_retried():
    p = StubProvider([RuntimeError("Ollama generation failed: HTTP 503: busy"), Out(x=4)])
    assert asyncio.run(client(p).structured("planner", "hi", Out)) == Out(x=4)
    assert len(p.calls) == 2


def test_out_of_memory_error_passes_through_for_the_scheduler():
    p = StubProvider([RuntimeError("model failed: Out Of Memory")])
    with pytest.raises(RuntimeError, match="(?i)out of memory") as e:
        asyncio.run(client(p).structured("planner", "hi", Out))
    assert not isinstance(e.value, StepModelError)


def test_vision_generation_limit_retries_once_then_fails():
    from engine.llm.errors import GenerationLimitError

    p = StubProvider([GenerationLimitError("length"), '{"x": 5}'])
    assert asyncio.run(client(p).structured("vision", "look", Out, image=b"i")) == Out(x=5)
    p = StubProvider([GenerationLimitError("length")] * 2)
    with pytest.raises(StepModelError):
        asyncio.run(client(p).structured("vision", "look", Out, image=b"i"))
    assert len(p.calls) == 2

def test_writer_top_p_reaches_provider():
    roles = {**ROLES, "writer": RoleConfig(model="w:1", temperature=0.7, top_p=0.9, max_tokens=500)}
    p = StubProvider([Out(x=1), Out(x=1)])
    c = ProviderModelClient(p, roles, backoff_s=(0, 0))
    asyncio.run(c.structured("writer", "hi", Out))
    asyncio.run(c.structured("planner", "hi", Out))
    assert p.calls[0][1]["top_p"] == 0.9 and "top_p" not in p.calls[1][1]
    assert c.params_for("writer")["top_p"] == 0.9


def test_ollama_text_path_sends_top_p(monkeypatch):
    from engine.llm.providers.ollama import OllamaProvider
    prov, sent = OllamaProvider(), []

    async def fake(payload, **kw):
        sent.append(payload)
        return '{"x": 1}'
    monkeypatch.setattr(prov, "_generate_response", fake)
    asyncio.run(prov.generate_structured("hi", Out, top_p=0.9))
    asyncio.run(prov.generate_structured("hi", Out))
    assert sent[0]["options"]["top_p"] == 0.9 and "top_p" not in sent[1]["options"]
