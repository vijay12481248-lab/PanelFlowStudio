"""ChronoFlow <-> Motion Bank: start/end pose pictures for a First + last card."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from starlette.testclient import TestClient

from engine.acquisition.rights.models import RightsDeclaration
from engine.api.app import app
from engine.chronoflow import motion_frames
from engine.motion_bank.models import FramePoseData, MotionRecord
from engine.motion_bank.storage import MotionBankStorage


def _walk_tensor(frames: int = 40) -> np.ndarray:
    """[T,133,3] with a body that moves left to right; the first 3 and last 2 frames are empty (actor not found)."""
    kp = np.zeros((frames, 133, 3), np.float32)
    for t in range(3, frames - 2):
        x0 = 0.2 + 0.5 * t / frames
        for j in range(18):
            kp[t, j] = (x0 + 0.01 * (j % 3), 0.15 + 0.04 * j, 0.9)
        kp[t, 18:39] = (x0 - 0.05, 0.5, 0.8)
        kp[t, 39:60] = (x0 + 0.05, 0.5, 0.8)
    return kp


def test_pick_keyframes_snaps_to_frames_that_have_a_pose():
    kp = _walk_tensor()
    first, last = motion_frames.pick_keyframes(kp, 0.0, 1.0)
    assert first == 3 and last == 37                   # the empty edge frames are skipped
    mid_a, mid_b = motion_frames.pick_keyframes(kp, 0.25, 0.75)
    assert 3 <= mid_a < mid_b <= 37
    with pytest.raises(ValueError):
        motion_frames.pick_keyframes(kp, 0.5, 0.5)
    with pytest.raises(ValueError):
        motion_frames.pick_keyframes(np.zeros((10, 133, 3), np.float32), 0.0, 1.0)


def test_pose_canvas_keeps_the_source_proportions():
    """A square clip on a 16:9 card is centred with bars, not stretched."""
    pose = FramePoseData(frame_index=0, timestamp_sec=0.0, body=[(0.0, 0.5, 0.9), (1.0, 0.5, 0.9)] + [(0.5, 0.5, 0.0)] * 16)
    canvas = motion_frames.render_pose_canvas(pose, 1000, 1000, 1600, 900)
    assert canvas.shape == (900, 1600, 3)
    cols = np.where(canvas.sum(axis=(0, 2)) > 0)[0]
    assert cols.min() >= 1600 // 2 - 450 - 8 and cols.max() <= 1600 // 2 + 450 + 8   # drawn inside the 900-wide centred square


@pytest.fixture
def bank(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PANELFLOW_MOTION_BANK_DIR", str(tmp_path / "bank"))
    from engine.api.routers import chronoflow_motion as r

    inputs = tmp_path / "comfy_input"
    inputs.mkdir()
    monkeypatch.setattr(r, "COMFY_INPUT_DIR", inputs)
    storage = r.bank.get_storage()

    def add(motion_id: str, *, synthetic: bool = False, rights: bool = True, source: bool = True) -> MotionRecord:
        d = tmp_path / "bank" / "motions" / motion_id
        d.mkdir(parents=True)
        src = tmp_path / f"{motion_id}_source.mp4"
        if source:
            out = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (200, 200))
            for i in range(40):
                out.write(np.full((200, 200, 3), (i * 5) % 255, np.uint8))
            out.release()
        rec = MotionRecord(
            id=motion_id, source_uri=str(src), action_title=f"Move {motion_id}", duration_sec=1.6, fps=24, frame_count=40, resolution=(1080, 1080),
            keypoints_path=str(d / "motion.safetensors"), control_video_path=str(d / "c.mp4"),
            metadata={"synthetic": synthetic, **({"rights": RightsDeclaration(status="USER_OWNED").model_dump(mode="json")} if rights else {})},
        )
        from safetensors.torch import save_file
        import torch
        save_file({"keypoints": torch.from_numpy(_walk_tensor())}, rec.keypoints_path)
        storage.save_motion(rec)
        return rec

    return add, inputs


def test_motion_list_hides_fake_and_unlicensed_motions(bank):
    add, _ = bank
    add("mot_real"); add("mot_fake", synthetic=True); add("mot_norights", rights=False)
    out = TestClient(app).get("/api/chronoflow/motions").json()["motions"]
    assert [m["id"] for m in out] == ["mot_real"]
    assert out[0]["rights"] == "USER_OWNED"


def test_pose_only_request_writes_two_pose_pictures(bank):
    add, inputs = bank
    add("mot_real")
    (inputs / "hero.png").write_bytes(b"png")
    res = TestClient(app).post("/api/chronoflow/storyboard/motion_frames", json={
        "motion_id": "mot_real", "character_picture": "hero.png", "width": 640, "height": 360, "stylize": False})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["first_index"], body["last_index"]) == (3, 37)
    for key in ("pose_first", "pose_last", "ref_first", "ref_last"):
        assert (inputs / body[key]).is_file()
    from PIL import Image
    assert Image.open(inputs / body["ref_first"]).size == (640, 360)   # the source frame is fitted to the card canvas
    assert "first_frame" not in body                      # nothing is drawn without stylize


def test_motion_frames_refuses_bad_requests(bank):
    add, inputs = bank
    add("mot_fake", synthetic=True); add("mot_norights", rights=False); add("mot_real")
    (inputs / "hero.png").write_bytes(b"png")
    c = TestClient(app)
    post = lambda **kw: c.post("/api/chronoflow/storyboard/motion_frames", json={"character_picture": "hero.png", "stylize": False, **kw})
    assert post(motion_id="nope").status_code == 404
    assert post(motion_id="mot_fake").status_code == 400
    assert post(motion_id="mot_norights").status_code == 400
    assert post(motion_id="mot_real", character_picture="missing.png").status_code == 400
    assert post(motion_id="mot_real", character_picture="../hero.png").status_code == 400
    assert post(motion_id="mot_real", start_pct=0.8, end_pct=0.2).status_code == 400


def test_stylize_failure_is_reported_never_replaced_by_the_raw_skeleton(bank, monkeypatch):
    add, inputs = bank
    add("mot_real")
    (inputs / "hero.png").write_bytes(b"png")

    def boom(*a, **k):
        raise RuntimeError("ComfyUI is not running")

    monkeypatch.setattr(motion_frames, "stylize_pose", boom)
    res = TestClient(app).post("/api/chronoflow/storyboard/motion_frames", json={"motion_id": "mot_real", "character_picture": "hero.png"})
    assert res.status_code == 502 and "ComfyUI is not running" in res.json()["detail"]


def test_stylize_returns_both_pictures_through_the_engine(bank, monkeypatch):
    add, inputs = bank
    add("mot_real")
    (inputs / "hero.png").write_bytes(b"png")
    calls = []
    monkeypatch.setattr(motion_frames, "stylize_pose", lambda ch, pose, hint="", **kw: (calls.append(pose[:4]) or (b"PNGDATA", "caption")))
    res = TestClient(app).post("/api/chronoflow/storyboard/motion_frames", json={"motion_id": "mot_real", "character_picture": "hero.png"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(calls) == 2 and all(c[1:4] == b"PNG" for c in calls)  # two real PNG frames went in as the pose picture (not skeletons)
    assert (inputs / body["first_frame"]).read_bytes() == b"PNGDATA" and (inputs / body["last_frame"]).is_file()


def test_stylize_needs_the_source_video_but_preview_does_not(bank):
    add, inputs = bank
    add("mot_nosrc", source=False)
    (inputs / "hero.png").write_bytes(b"png")
    c = TestClient(app)
    base = {"motion_id": "mot_nosrc", "character_picture": "hero.png"}
    assert c.post("/api/chronoflow/storyboard/motion_frames", json={**base, "stylize": False}).status_code == 200
    res = c.post("/api/chronoflow/storyboard/motion_frames", json={**base, "stylize": True})
    assert res.status_code == 400 and "source video" in res.json()["detail"]


def test_source_frame_canvas_fits_without_stretching(tmp_path: Path):
    video = tmp_path / "v.mp4"
    out = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (200, 200))
    for _ in range(5):
        out.write(np.full((200, 200, 3), 128, np.uint8))
    out.release()
    img = motion_frames.source_frame_canvas(video, 2, 400, 200)
    assert img.shape == (200, 400, 3)
    with pytest.raises(ValueError):
        motion_frames.source_frame_canvas(video, 999, 400, 200)
