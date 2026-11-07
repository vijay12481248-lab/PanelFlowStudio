import json
import shutil
import subprocess

import pytest
from PIL import Image

from engine.original import batch as b
from engine.original import explainer as ex

SPEC = """title: Why Do We Yawn? The Contagious Mystery
slug: vox_batch_test
logline: Maya yawns.
scene: s1 | living_room | funny | The yawn | Maya yawns on the sofa.
beat: medium | living_room | maya | Maya yawns so wide that the whole room seems to blink twice. | Maya on the sofa with a huge yawn, eyes squeezed shut, hand over her mouth. | a big yawn
beat: close | living_room | maya | Her eyes water and she laughs at herself for a long time. | Maya laughing with clear tears of laughter on her cheeks.
"""


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "BATCH", tmp_path / "_batch")
    story = ex.build_story(SPEC)
    ws = tmp_path / "vox_batch_test"
    (ws / "panels").mkdir(parents=True)
    (ws / "story.json").write_text(story.model_dump_json(), encoding="utf-8")
    for p in story.panels:
        Image.new("RGB", (1344, 768), "#446688").save(ws / "panels" / f"{p.id}.png")
    art = [{"panel_id": "p001", "missing": ["dark brown eyes", "a huge yawn"]}, {"panel_id": "p002", "missing": []}]
    (ws / "art.json").write_text(json.dumps(art), encoding="utf-8")
    return ws


def test_review_sheet_has_one_cell_per_beat_and_skips_look_noise(ws):
    out = b.review_sheets(ws)
    assert [p.name for p in out] == ["sheet_1.jpg"]
    assert Image.open(out[0]).size == (1920, 2 * (270 + 78))
    # "dark brown eyes" is a fragment of Maya's look string (noise); "a huge yawn" is a real miss and stays visible
    only = b.review_sheets(ws, only=["p002"], name="picked")
    assert [p.name for p in only] == ["picked_1.jpg"]


def test_state_is_written_atomically_and_resumes(ws):
    b.set_stage("vox_a", "drawing", beats=3)
    b.set_stage("vox_a", "review", generated=3)
    st = b.load_state()
    assert st["vox_a"]["stage"] == "review" and st["vox_a"]["beats"] == 3 and st["vox_a"]["generated"] == 3
    assert not (b.BATCH / "state.json.tmp").exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_verify_flags_a_video_under_three_minutes(ws):
    mp4 = ws / "story_1080p.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:d=4:r=30", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=4", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mp4)], check=True)
    res = b.verify_video(ws, "a short script of words", est_seconds=4.0)
    assert res["size"] == "1920x1080"
    assert any("under 180s" in p for p in res["problems"]) and res["ok"] is False
