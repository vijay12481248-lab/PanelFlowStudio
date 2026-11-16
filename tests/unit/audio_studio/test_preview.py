import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import audio_studio as mod
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, PlanStore, Provenance, Take
from engine.audio.studio.preview import audio_signature, build_preview
from engine.audio.studio.sources.synth import SynthProvider, render

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
PROV = Provenance(source="test", licence="CC0")


def _take(tmp_path, name, x):
    p = tmp_path / f"{name}.wav"
    sf.write(str(p), np.asarray(x, dtype=np.float32), SR)
    m = measure_take(p)
    return Take(id=name, path=str(p), provenance=PROV, onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s, peak_db=m.peak_db,
                rms_db=m.rms_db, clipped_samples=m.clipped_samples)


def _plan(tmp_path, with_cues=True):
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=4.0)
    if with_cues:
        for cue, take in ((Cue(id="m", track="music", kind="music", t_in=0, t_out=4.0), _take(tmp_path, "mus", 0.2 * np.sin(2 * np.pi * 220 * np.arange(4 * SR) / SR))),
                          (Cue(id="c1", track="sfx", kind="impact", hit_t=2.0), _take(tmp_path, "imp", render("impact", 1.0, 1)))):
            cue.takes, cue.chosen_take, cue.status = [take], take.id, "ready"
            plan.cues.append(cue)
    return plan


def _dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout
    return float(out)


def test_three_m4a_stems_with_peaks_match_the_plan_length(tmp_path):
    res = build_preview(_plan(tmp_path), tmp_path / "pv")
    assert set(res["stems"]) == {"dialogue", "music", "effects"}
    for name, s in res["stems"].items():
        assert abs(_dur(tmp_path / "pv" / s["file"]) - 4.0) < 0.1 and s["file"].endswith(".m4a")
        assert len(s["peaks"]) == 1200 and all(0 <= p <= 1 for p in s["peaks"])
    assert max(res["stems"]["music"]["peaks"]) > 0.1 and max(res["stems"]["dialogue"]["peaks"]) == 0


def test_second_call_is_cached_and_an_audio_edit_rerenders(tmp_path):
    plan = _plan(tmp_path)
    a = build_preview(plan, tmp_path / "pv")
    stamp = (tmp_path / "pv" / "music.m4a").stat().st_mtime_ns
    assert build_preview(plan, tmp_path / "pv")["signature"] == a["signature"] and (tmp_path / "pv" / "music.m4a").stat().st_mtime_ns == stamp
    plan.cues[1].hit_t = 2.5
    assert audio_signature(plan) != a["signature"]
    assert build_preview(plan, tmp_path / "pv")["signature"] != a["signature"]


def test_signature_ignores_things_that_do_not_change_the_sound(tmp_path):
    plan = _plan(tmp_path)
    s = audio_signature(plan)
    plan.cues[1].intent, plan.cues[1].placement_error_ms, plan.version, plan.note = "reworded", 3.2, 9, "qa"
    assert audio_signature(plan) == s
    plan.tracks[1].gain_db = -3.0
    assert audio_signature(plan) != s


def test_plan_with_nothing_playable_gives_silent_stems(tmp_path):
    res = build_preview(_plan(tmp_path, with_cues=False), tmp_path / "pv")
    assert all(max(s["peaks"]) == 0 for s in res["stems"].values())


def test_preview_endpoints_report_stale_then_current(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3:r=24", "-f", "lavfi", "-i", "sine=frequency=300:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    engine = AudioEngine(PlanStore(tmp_path / "store"), [SynthProvider()])
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_engine] = lambda: engine
    c = TestClient(app)
    B = "/api/audio/studio"
    pid = c.post(f"{B}/plans", json={"video_path": str(video)}).json()["id"]
    assert c.get(f"{B}/plans/{pid}/preview").json() == {"stale": True}
    made = c.post(f"{B}/plans/{pid}/preview").json()
    assert made["stale"] is False and made["dir"].startswith("preview/") and set(made["stems"]) == {"dialogue", "music", "effects"}
    assert c.get(f"{B}/plans/{pid}/files/{made['dir']}/{made['stems']['music']['file']}").status_code == 200
    assert c.get(f"{B}/plans/{pid}/preview").json()["stale"] is False
    c.put(f"{B}/plans/{pid}", json={"cues": [{"id": "x", "track": "sfx", "kind": "click", "hit_t": 1.0}]})
    assert c.get(f"{B}/plans/{pid}/preview").json()["stale"] is False  # a draft cue has no sound yet
    c.post(f"{B}/plans/{pid}/cues/x/source", json={})
    assert c.get(f"{B}/plans/{pid}/preview").json()["stale"] is True


def test_preview_records_the_track_gains_it_was_rendered_with(tmp_path):
    plan = _plan(tmp_path)
    plan.tracks[1].gain_db = -4.0
    res = build_preview(plan, tmp_path / "pv")
    assert res["gains"]["music"] == -4.0 and res["gains"]["dialogue"] == 0.0 and set(res["gains"]) == {"dialogue", "music", "sfx", "ambience", "foley"}


def test_get_preview_returns_the_last_render_marked_stale_after_an_audio_edit(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3:r=24", "-f", "lavfi", "-i", "sine=frequency=300:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    engine = AudioEngine(PlanStore(tmp_path / "store"), [SynthProvider()])
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_engine] = lambda: engine
    c = TestClient(app)
    B = "/api/audio/studio"
    pid = c.post(f"{B}/plans", json={"video_path": str(video)}).json()["id"]
    made = c.post(f"{B}/plans/{pid}/preview").json()
    c.put(f"{B}/plans/{pid}", json={"tracks": [{"id": "music", "gain_db": -6.0}]})
    stale = c.get(f"{B}/plans/{pid}/preview").json()
    assert stale["stale"] is True and stale["dir"] == made["dir"] and set(stale["stems"]) == {"dialogue", "music", "effects"} and stale["gains"]["music"] == 0.0
