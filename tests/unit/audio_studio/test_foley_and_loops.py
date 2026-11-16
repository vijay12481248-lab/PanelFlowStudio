"""Unit tests for physical Foley synthesis, seamless looping, and score stem isolation."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.audio.studio.loop import create_seamless_loop, isolate_score_stems
from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, PlanStore, Provenance, SoundPlan, Take
from engine.audio.studio.sources.foley_synth import (
    FOLEY_KINDS,
    FoleySynthProvider,
    detect_foley_kind,
    render_foley,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
PROV = Provenance(source="test", licence="CC0")


def _write_wav(path: Path, x: np.ndarray) -> str:
    sf.write(str(path), np.asarray(x, dtype=np.float32), SR)
    return str(path)


def _tone(sec: float, f: float = 400.0, amp: float = 0.5) -> np.ndarray:
    return amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)


def test_foley_physical_rendering():
    # 1. Footstep surfaces
    for surface in ("wood", "concrete", "dirt", "water"):
        x = render_foley("footstep", duration=0.35, seed=101, surface=surface)
        assert len(x) == int(0.35 * SR)
        assert np.max(np.abs(x)) <= 1.0
        assert np.max(np.abs(x)) >= 0.70

    # 2. Cloth rustle
    x_cloth = render_foley("cloth_rustle", duration=0.5, seed=102)
    assert len(x_cloth) == int(0.5 * SR)
    assert np.max(np.abs(x_cloth)) >= 0.70

    # 3. Blade clash & sword ring
    x_clash = render_foley("blade_clash", duration=1.5, seed=103)
    assert len(x_clash) == int(1.5 * SR)
    x_ring = render_foley("sword_ring", duration=1.5, seed=104)
    assert len(x_ring) == int(1.5 * SR)

    # 4. Heavy impact
    x_impact = render_foley("heavy_impact", duration=1.2, seed=105)
    assert len(x_impact) == int(1.2 * SR)

    # 5. Explosion
    x_expl = render_foley("explosion", duration=2.5, seed=106)
    assert len(x_expl) == int(2.5 * SR)


def test_foley_kind_detection():
    c1 = Cue(id="c1", track="foley", kind="footsteps", intent="running boots on wet concrete")
    assert detect_foley_kind(c1) == "footstep"

    c2 = Cue(id="c2", track="foley", kind="jacket", intent="leather cloth rustle movement")
    assert detect_foley_kind(c2) == "cloth_rustle"

    c3 = Cue(id="c3", track="sfx", kind="katana", intent="samurai blade clash parry")
    assert detect_foley_kind(c3) == "blade_clash"

    c4 = Cue(id="c4", track="sfx", kind="detonation", intent="massive bomb explosion in bunker")
    assert detect_foley_kind(c4) == "explosion"

    c5 = Cue(id="c5", track="sfx", kind="smash", intent="body slam heavy impact against wall")
    assert detect_foley_kind(c5) == "heavy_impact"


def test_foley_provider_sourcing(tmp_path):
    store = PlanStore(tmp_path / "store")
    plan = store.create("v.mp4", fps=24.0, duration=10.0)
    provider = FoleySynthProvider()

    cue = Cue(id="cue_blade", track="sfx", kind="blade_clash", intent="iron sword strike")
    cands = provider.find(cue, tmp_path / "cands", plan, limit=2)

    assert len(cands) == 2
    for c in cands:
        assert c.provider == "foley"
        assert c.provenance.source == "foley"
        assert c.provenance.licence == "CC0"
        assert Path(c.path).is_file()
        data, sr = sf.read(c.path)
        assert sr == SR
        assert len(data) > 0


def test_seamless_loop_crossfade(tmp_path):
    # Create 4-second audio piece with subtle progression
    t = np.arange(int(4.0 * SR)) / SR
    audio = 0.4 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 440 * t)
    # Add slight envelope
    audio *= 0.8 + 0.2 * np.sin(2 * np.pi * 0.5 * t)

    in_wav = tmp_path / "score_bed.wav"
    _write_wav(in_wav, audio)

    out_loop = tmp_path / "score_bed_loop.wav"
    create_seamless_loop(in_wav, out_loop, crossfade_sec=0.8)

    assert out_loop.is_file()
    looped_data, sr = sf.read(str(out_loop))
    assert sr == SR
    assert len(looped_data) > 0

    # Verify loop boundary continuity: difference between tail sample and head sample
    diff = abs(float(np.ravel(looped_data)[-1]) - float(np.ravel(looped_data)[0]))
    assert diff < 0.2, f"Expected smooth seam transition, got difference {diff}"


def test_score_stem_isolation(tmp_path):
    # Create multi-frequency composite: sub bass (80 Hz) + mid melody (600 Hz) + high shimmer (4000 Hz)
    t = np.arange(int(2.0 * SR)) / SR
    bass_sig = 0.4 * np.sin(2 * np.pi * 80 * t)
    mid_sig = 0.3 * np.sin(2 * np.pi * 600 * t)
    high_sig = 0.2 * np.sin(2 * np.pi * 4000 * t)
    composite = bass_sig + mid_sig + high_sig

    in_wav = tmp_path / "composite_score.wav"
    _write_wav(in_wav, composite)

    stems = isolate_score_stems(in_wav, tmp_path / "stems")
    assert "bass" in stems and stems["bass"].is_file()
    assert "body" in stems and stems["body"].is_file()
    assert "air" in stems and stems["air"].is_file()

    d_bass, _ = sf.read(str(stems["bass"]))
    d_body, _ = sf.read(str(stems["body"]))
    d_air, _ = sf.read(str(stems["air"]))

    # Sum of stems should closely reconstruct input signal
    reconstructed = d_bass + d_body + d_air
    # Check correlation / RMS error between original and reconstructed
    error = float(np.mean((composite.flatten() - reconstructed.flatten()) ** 2))
    assert error < 0.05, f"Expected low reconstruction error, got {error}"


def test_router_loop_and_stem_endpoints(tmp_path):
    # Setup video
    video = tmp_path / "v.mp4"
    sf.write(str(tmp_path / "v.wav"), np.zeros(SR, dtype=np.float32), SR)
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=320x240:r=24",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                    "-c:v", "libx264", "-c:a", "aac", str(video)], check=True, capture_output=True)

    client = TestClient(app)

    # 1. Create plan
    res = client.post("/api/audio/studio/plans", json={"video_path": str(video)})
    assert res.status_code == 200
    pid = res.json()["id"]

    # 2. Add music cue
    score_sound = tmp_path / "my_music.wav"
    _write_wav(score_sound, _tone(3.0, f=440.0))
    client.put(f"/api/audio/studio/plans/{pid}", json={
        "cues": [{"id": "c_music", "track": "music", "kind": "theme", "hit_t": 0.0}]
    })
    client.post(f"/api/audio/studio/plans/{pid}/cues/c_music/import_file", json={
        "file_path": str(score_sound),
        "label": "Original Theme"
    })

    # 3. Call loop endpoint
    res = client.post(f"/api/audio/studio/plans/{pid}/cues/c_music/loop?crossfade_sec=0.5")
    assert res.status_code == 200, res.text
    loop_data = res.json()
    assert "loop_path" in loop_data
    assert Path(loop_data["loop_path"]).is_file()
    assert loop_data["duration_s"] > 0

    # 4. Call stems endpoint
    res = client.post(f"/api/audio/studio/plans/{pid}/cues/c_music/stems")
    assert res.status_code == 200, res.text
    stem_data = res.json()
    assert "bass" in stem_data["stems"]
    assert "body" in stem_data["stems"]
    assert "air" in stem_data["stems"]
    assert Path(stem_data["stems"]["bass"]).is_file()
