import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("motionkit")

from engine.api.routers.motion_graphics import router
from engine.render.motion.registry import MotionRegistry

client = TestClient(FastAPI())
client.app.include_router(router)


def test_default_preset_renders_at_requested_size():
    frame = MotionRegistry.create_scene("motionkit", bounds=(640, 360), duration_sec=5.5).render_frame(2.0)
    assert frame.size == (640, 360)


def test_time_past_end_holds_last_frame():
    scene = MotionRegistry.create_scene("motionkit", bounds=(320, 180))
    assert scene.render_frame(999.0).size == (320, 180)


def test_preview_endpoint_lists_and_renders():
    assert "motionkit" in [p["id"] for p in client.get("/api/motion-graphics/presets").json()]
    r = client.post("/api/motion-graphics/preview", json={"preset_id": "motionkit", "width": 640, "height": 360})
    assert r.status_code == 200 and r.json()["image_base64"]


def test_character_mouth_follows_external_narration_wav(tmp_path):
    sf = pytest.importorskip("soundfile")
    import numpy as np

    t = np.arange(48000) / 24000
    wav = tmp_path / "narration.wav"
    sf.write(wav, 0.5 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0), 24000)
    spec = {"scenes": [{"dur": 3, "elements": [{"type": "character", "pack": "ava", "x": 0.5, "w": 240,
            "timeline": [["say", 0.0, "hi", {"speech": "file", "path": str(wav)}]]}]}]}
    scene = MotionRegistry.create_scene("motionkit", props={"spec": spec}, bounds=(320, 180))
    assert len({scene.render_frame(i / 10).tobytes() for i in range(2, 18)}) > 3


def test_narration_prop_lip_syncs_first_character(tmp_path):
    sf = pytest.importorskip("soundfile")
    import numpy as np

    t = np.arange(48000) / 24000
    wav = tmp_path / "n.wav"
    sf.write(wav, 0.5 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0), 24000)
    spec = {"scenes": [{"dur": 3, "elements": [{"type": "character", "pack": "ava", "x": 0.5, "w": 240}]}]}
    narration = [{"at": 0.0, "audio_path": str(wav), "text": "hi"}]
    scene = MotionRegistry.create_scene("motionkit", props={"spec": spec, "narration": narration}, bounds=(320, 180))
    assert len({scene.render_frame(i / 10).tobytes() for i in range(2, 18)}) > 3
    assert "timeline" not in spec["scenes"][0]["elements"][0]   # caller's spec is not mutated


def test_invalid_spec_is_a_400():
    r = client.post(
        "/api/motion-graphics/preview",
        json={"preset_id": "motionkit", "props": {"spec": {"scenes": [{"template": "nope"}]}}},
    )
    assert r.status_code == 400
