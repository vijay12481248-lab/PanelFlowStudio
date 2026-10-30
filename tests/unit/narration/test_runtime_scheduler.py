import asyncio

import pytest

from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from tests.unit.narration.fakes import RecordingUnloader


def _role(model, concurrency=1):
    return RoleConfig(model=model, temperature=0.1, max_tokens=100, concurrency=concurrency)


def test_map_preserves_order_and_limits_concurrency():
    sched = ModelScheduler({"vision": _role("qwen", 3)}, RecordingUnloader())
    state = {"now": 0, "max": 0}

    async def fn(x):
        state["now"] += 1
        state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return x

    items = list(range(10))
    assert asyncio.run(sched.map("vision", items, fn)) == items
    assert state["max"] == 3


def test_switching_to_a_different_model_unloads_previous():
    unl = RecordingUnloader()
    sched = ModelScheduler({"vision": _role("qwen"), "planner": _role("gemma")}, unl)

    async def fn(x):
        return x

    async def run():
        await sched.map("vision", [1], fn)
        await sched.map("planner", [1], fn)

    asyncio.run(run())
    assert unl.unloaded == ["qwen"]


def test_same_model_across_roles_does_not_unload():
    unl = RecordingUnloader()
    sched = ModelScheduler({"vision": _role("qwen"), "planner": _role("qwen")}, unl)

    async def fn(x):
        return x

    async def run():
        await sched.map("vision", [1], fn)
        await sched.map("planner", [1], fn)

    asyncio.run(run())
    assert unl.unloaded == []


def test_out_of_memory_halves_concurrency_and_retries_once():
    unl = RecordingUnloader()
    sched = ModelScheduler({"vision": _role("qwen", 4)}, unl)
    state = {"now": 0, "max": 0, "failed": set()}

    async def fn(x):
        retry = x in state["failed"]
        if x < 4 and not retry:  # items 0-3 hit OOM on the first pass
            state["failed"].add(x)
            raise RuntimeError("CUDA out of memory")
        state["now"] += 1
        if retry:
            state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return x * 10

    assert asyncio.run(sched.map("vision", list(range(8)), fn)) == [x * 10 for x in range(8)]
    assert unl.unloaded == ["qwen"]
    assert state["max"] <= 2


def test_second_out_of_memory_propagates():
    sched = ModelScheduler({"vision": _role("qwen", 2)}, RecordingUnloader())

    async def fn(x):
        raise RuntimeError("Out Of Memory")

    with pytest.raises(RuntimeError):
        asyncio.run(sched.map("vision", [1, 2], fn))