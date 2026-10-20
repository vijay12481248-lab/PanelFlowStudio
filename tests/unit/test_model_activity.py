import json

import httpx
import pytest
from pydantic import BaseModel

from engine.llm.activity import activity_sink
from engine.llm.providers.ollama import OllamaProvider


class Result(BaseModel):
    title: str


def use_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))


@pytest.mark.asyncio
async def test_stream_reports_activity_and_exact_final_usage_without_content(monkeypatch):
    def handler(request):
        assert json.loads(request.content)["stream"] is True
        events = [{"response": '{"title":'}, {"response": '"A gate"}'},
                  {"done": True, "eval_count": 12, "prompt_eval_count": 84, "eval_duration": 2_000_000_000}]
        return httpx.Response(200, content="\n".join(json.dumps(event) for event in events))
    use_transport(monkeypatch, handler)
    updates = []
    token = activity_sink.set(updates.append)
    try:
        result = await OllamaProvider().generate_structured("private input", Result)
    finally:
        activity_sink.reset(token)
    assert result.title == "A gate"
    assert updates[0]["phase"] == "preparing"
    assert any(event["phase"] == "generating" for event in updates)
    assert updates[-1]["output_tokens"] == 12
    assert updates[-1]["input_tokens"] == 84
    assert updates[-1]["tokens_per_second"] == 6
    assert "private input" not in json.dumps(updates)
    assert "A gate" not in json.dumps(updates)
    assert activity_sink.get() is None


@pytest.mark.asyncio
async def test_buffered_requests_remain_buffered_without_job_context(monkeypatch):
    def handler(request):
        assert json.loads(request.content)["stream"] is False
        return httpx.Response(200, json={"response": '{"title":"Buffered"}'})
    use_transport(monkeypatch, handler)
    assert (await OllamaProvider().generate_structured("test", Result)).title == "Buffered"


@pytest.mark.asyncio
async def test_repair_attempts_are_visible(monkeypatch):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        output = '{"title":' if count == 1 else '{"title":"Repaired"}'
        return httpx.Response(200, content=json.dumps({"response": output, "done": True}))
    use_transport(monkeypatch, handler)
    updates = []
    token = activity_sink.set(updates.append)
    try:
        assert (await OllamaProvider().generate_structured("test", Result)).title == "Repaired"
    finally:
        activity_sink.reset(token)
    assert [event["attempt"] for event in updates if event["phase"] == "preparing"] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [{"error": "model unavailable"}, {"response": "incomplete"}])
async def test_stream_errors_do_not_silently_return_partial_results(monkeypatch, event):
    use_transport(monkeypatch, lambda request: httpx.Response(200, content=json.dumps(event)))
    token = activity_sink.set(lambda update: None)
    try:
        with pytest.raises(RuntimeError):
            await OllamaProvider().generate_text("test")
    finally:
        activity_sink.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("tracked", [True, False])
async def test_output_limit_does_not_trigger_identical_json_repairs(monkeypatch, tracked):
    from engine.llm.errors import GenerationLimitError
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        response = {"response": '{"title":', "done": True, "done_reason": "length", "eval_count": 3072}
        return httpx.Response(200, content=json.dumps(response)) if tracked else httpx.Response(200, json=response)
    use_transport(monkeypatch, handler)
    token = activity_sink.set((lambda update: None) if tracked else None)
    try:
        with pytest.raises(GenerationLimitError):
            await OllamaProvider().generate_structured("test", Result, max_tokens=3072)
    finally:
        activity_sink.reset(token)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cancelled_generation_does_not_start_another_request(monkeypatch):
    import asyncio
    from engine.llm.activity import generation_cancelled
    calls = []
    use_transport(monkeypatch, lambda request: calls.append(request))
    token = generation_cancelled.set(lambda: True)
    try:
        with pytest.raises(asyncio.CancelledError):
            await OllamaProvider().generate_text("test")
    finally:
        generation_cancelled.reset(token)
    assert not calls
