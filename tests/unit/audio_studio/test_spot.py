import shutil
import subprocess

import pytest

from engine.audio.studio.plan import PlanStore, snap
from engine.audio.studio.spot import detect_cuts, draft_cues

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _video(path, audio: bool):
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for colour in ("black", "white", "black"):
        cmd += ["-f", "lavfi", "-i", f"color=c={colour}:s=160x120:d=2:r=24"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=300:duration=6"]
    cmd += ["-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]"]
    if audio:
        cmd += ["-map", "3:a", "-c:a", "aac"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@pytest.mark.parametrize("audio", [True, False])
def test_detect_cuts_finds_both_cuts(tmp_path, audio):
    cuts = detect_cuts(_video(tmp_path / "v.mp4", audio))
    assert len(cuts) == 2
    assert cuts[0] == pytest.approx(2.0, abs=1 / 24) and cuts[1] == pytest.approx(4.0, abs=1 / 24)


def _plan(tmp_path, fps=29.97, duration=6.0):
    return PlanStore(tmp_path).create("v.mp4", fps=fps, duration=duration)


def test_draft_cues_snap_to_frames_and_stay_in_range(tmp_path):
    plan = _plan(tmp_path)
    cues = [c for c in draft_cues(plan, [2.013, 4.02, 9.0, 0.0]) if c.track == "sfx"]
    assert [c.hit_t for c in cues] == [snap(2.013, 29.97), snap(4.02, 29.97)]
    assert all(0 <= c.t_in <= c.hit_t <= plan.duration and c.anchor == "peak" and c.kind == "whoosh" and c.status == "draft" for c in cues)
    assert len({c.id for c in cues}) == len(cues)


def test_draft_cues_music_spans_video(tmp_path):
    plan = _plan(tmp_path)
    music = [c for c in draft_cues(plan, [2.0]) if c.track == "music"]
    assert len(music) == 1 and music[0].kind == "music" and (music[0].t_in, music[0].t_out) == (0.0, plan.duration)


def test_no_cuts_gives_only_music_cue(tmp_path):
    assert [c.track for c in draft_cues(_plan(tmp_path), [])] == ["music"]
