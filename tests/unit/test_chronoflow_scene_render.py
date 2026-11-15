"""Per-mode clip dispatch for ChronoFlow storyboard cards. make_clip and the ComfyUI pipeline are faked at the boundary; the routing and validation are real."""
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from engine.chronoflow import scene_render as sr
from engine.original import h3_modes as hm
from engine.original.film import snap_frames


class FakePipeline:
    def __init__(self, tmp: Path):
        self.tmp, self.graph_kw, self.executed = tmp, None, 0

    def build_h3_prompt(self, **kw):
        self.graph_kw = kw
        return {"graph": True}

    async def execute_prompt(self, graph, on_step=None):
        self.executed += 1
        p = self.tmp / "comfy_out.mp4"
        p.write_bytes(b"mp4")
        return p

    def extract_tail_frame(self, video, out):
        Path(out).write_bytes(b"png")
        return True


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = []

    def fake_make_clip(mode, prompt, **kw):
        calls.append({"mode": mode, "prompt": prompt, **kw})
        return b"mp4"

    monkeypatch.setattr(hm, "make_clip", fake_make_clip)
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    for name in ("a.png", "b.png", "c.png", "tail.png"):
        (inp / name).write_bytes(b"png")
    return {"calls": calls, "pipe": FakePipeline(tmp_path), "inp": inp, "out": out}


def scene(mode="text", **kw):
    s = {"start_mode": mode, "prompt": "a fox runs through snow", "duration": 5.2, "first_frame": "", "last_frame": "", "ref_images": [],
         "inherits_tail": False, "prev_tail": ""}
    s.update(kw)
    return s


def run(env, s, index=0, width=1344, height=768):
    return asyncio.run(sr.render_scene(env["pipe"], s, index, width=width, height=height, steps=4, lora_name="lora.safetensors",
                                       out_dir=env["out"], input_dir=env["inp"], tail_name=f"tail_{index + 1}.png"))


def test_text_mode_uses_t2va_with_size(env):
    path, tail = run(env, scene("text"))
    c = env["calls"][0]
    assert c["mode"] == "t2va" and c["size"] == (960, 544) and path.read_bytes() == b"mp4" and tail == "tail_1.png"
    assert c["prompt"].startswith("integrated_multimodal_description: [Shot 1] a fox runs through snow")
    run(env, scene("text"), width=768, height=1344)
    assert env["calls"][1]["size"] == (544, 960)


def test_prompt_already_in_official_format_is_sent_as_written(env):
    p = "detailed_description: a fox\n\noverall_soundscape: wind"
    run(env, scene("text", prompt=p))
    assert env["calls"][0]["prompt"] == p


def test_first_last_passes_both_frames(env):
    run(env, scene("first_last", first_frame="a.png", last_frame="b.png", duration=3.0))
    c = env["calls"][0]
    assert c["mode"] == "fl2va" and c["first"] == env["inp"] / "a.png" and c["last"] == env["inp"] / "b.png" and c["seconds"] == 3.0


def test_last_only_uses_l2va(env):
    run(env, scene("last", last_frame="b.png"))
    c = env["calls"][0]
    assert c["mode"] == "l2va" and c["last"] == env["inp"] / "b.png" and c.get("first") is None


def test_reference_passes_one_or_two_refs_and_rejects_three(env):
    run(env, scene("reference", ref_images=["a.png"]))
    run(env, scene("reference", ref_images=["a.png", "b.png"]))
    assert env["calls"][0]["mode"] == "ref2va" and env["calls"][0]["refs"] == [env["inp"] / "a.png"]
    assert env["calls"][1]["refs"] == [env["inp"] / "a.png", env["inp"] / "b.png"]
    with pytest.raises(HTTPException) as e:
        run(env, scene("reference", ref_images=["a.png", "b.png", "c.png"]))
    assert e.value.status_code == 400 and len(env["calls"]) == 2


def test_first_mode_uses_the_existing_graph_not_make_clip(env):
    path, _ = run(env, scene("first", first_frame="a.png", duration=3.0))
    kw = env["pipe"].graph_kw
    assert env["calls"] == [] and env["pipe"].executed == 1
    assert kw["first_frame_filename"] == "a.png" and kw["length"] == snap_frames(3.0) and kw["workflow_mode"] == "sliding_window"
    assert path.read_bytes() == b"mp4"


def test_missing_frame_file_is_400_and_renders_nothing(env):
    with pytest.raises(HTTPException) as e:
        run(env, scene("first_last", first_frame="a.png", last_frame="gone.png"))
    assert e.value.status_code == 400 and "gone.png" in e.value.detail
    assert env["calls"] == [] and env["pipe"].executed == 0


def test_missing_prompt_or_slot_is_400(env):
    with pytest.raises(HTTPException) as e:
        run(env, scene("last", prompt="  "))
    assert e.value.status_code == 400 and "last" in e.value.detail and "prompt" in e.value.detail


def test_inherited_tail_used_when_first_frame_empty(env):
    run(env, scene("first", inherits_tail=True, prev_tail="tail.png"), index=1)
    assert env["pipe"].graph_kw["first_frame_filename"] == "tail.png"
    with pytest.raises(HTTPException) as e:
        run(env, scene("first", inherits_tail=True, prev_tail="not_there.png"), index=1)
    assert e.value.status_code == 400 and "tail frame" in e.value.detail


def test_chained_text_card_continues_from_the_tail(env):
    run(env, scene("text", inherits_tail=True, prev_tail="tail.png"), index=1)
    assert env["calls"] == [] and env["pipe"].graph_kw["first_frame_filename"] == "tail.png"


# ---- endpoint: wizard cards go through render_scene, legacy cards (no start_mode) do not
def _client(monkeypatch, fake):
    from fastapi.testclient import TestClient

    from engine.api.app import app
    from engine.api.routers import chronoflow as router

    monkeypatch.setattr(router, "render_scene", fake)
    return TestClient(app), router


def test_endpoint_routes_wizard_cards_and_returns_the_tail(monkeypatch, tmp_path):
    seen = {}

    async def fake(pipeline, scene, index, **kw):
        seen.update(index=index, mode=scene["start_mode"], tail_name=kw["tail_name"])
        return tmp_path / "shot_2_abc123.mp4", kw["tail_name"]

    client, _ = _client(monkeypatch, fake)
    r = client.post("/api/chronoflow/storyboard/render_shot", json={"scene": {"start_mode": "text", "prompt": "x"}, "shot_index": 2})
    body = r.json()
    assert r.status_code == 200 and body["video_url"] == "/chronoflow/outputs/shot_2_abc123.mp4" and body["tail_frame"] == seen["tail_name"]
    assert seen["index"] == 1 and seen["mode"] == "text"


def test_endpoint_keeps_validation_errors_as_400(monkeypatch):
    async def fake(*a, **kw):
        raise HTTPException(status_code=400, detail="Shot 1 cannot render in 'last' mode, it still needs: last")

    client, _ = _client(monkeypatch, fake)
    r = client.post("/api/chronoflow/storyboard/render_shot", json={"scene": {"start_mode": "last", "prompt": "x"}, "shot_index": 1})
    assert r.status_code == 400 and "still needs: last" in r.json()["detail"]


def test_legacy_cards_without_start_mode_skip_render_scene(monkeypatch):
    async def fake(*a, **kw):
        raise AssertionError("render_scene must not run for legacy cards")

    client, router = _client(monkeypatch, fake)

    async def boom(graph, on_step=None):
        raise RuntimeError("legacy path reached ComfyUI")

    monkeypatch.setattr(router.pipeline, "execute_prompt", boom)
    r = client.post("/api/chronoflow/storyboard/render_shot", json={"scene": {"prompt": "old card"}, "shot_index": 1})
    assert r.status_code == 500 and "legacy path reached ComfyUI" in r.json()["detail"]
