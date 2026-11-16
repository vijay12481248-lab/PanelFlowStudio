import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.audio.studio.measure import measure_take
from engine.audio.studio.mix import _cue_chain, _duck_filter, _pan_filter, render_cue
from engine.audio.studio.plan import Cue, PlanStore, Provenance, SoundPlan, Take
from engine.audio.studio.sources.local_bank import LocalBankProvider
from engine.audio.studio.spot import draft_cues

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
PROV = Provenance(source="test", licence="CC0")


def _write_wav(path: Path, x: np.ndarray) -> str:
    sf.write(str(path), np.asarray(x, dtype=np.float32), SR)
    return str(path)


def _make_take(tmp_path: Path, name: str, x: np.ndarray) -> Take:
    p = _write_wav(tmp_path / f"{name}.wav", x)
    m = measure_take(p)
    return Take(id=name, path=p, provenance=PROV, onset_s=m.onset_s, peak_s=m.peak_s,
                duration_s=m.duration_s, peak_db=m.peak_db, rms_db=m.rms_db, clipped_samples=m.clipped_samples)


def _tone(sec: float, f: float = 400.0, amp: float = 0.5) -> np.ndarray:
    return amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)


def test_pan_filter_syntax():
    left = _pan_filter(-1.0)
    assert "stereotools" in left
    assert "mpan=-1.000" in left

    right = _pan_filter(1.0)
    assert "mpan=1.000" in right

    # Clamping beyond [-1, 1]
    clamped = _pan_filter(2.5)
    assert "mpan=1.000" in clamped


def test_duck_filter_generation():
    f = _duck_filter(depth_db=-12.0, attack_ms=30, release_ms=500)
    assert "sidechaincompress" in f
    assert "ratio=12.0" in f
    assert "attack=30" in f
    assert "release=500" in f


def test_cue_chain_dsp_parameters(tmp_path):
    x = _tone(1.0)
    take = _make_take(tmp_path, "take_dsp", x)
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=4.0)

    cue = Cue(id="c1", track="sfx", kind="whoosh", hit_t=1.0, pan=-0.75, pitch_semitones=2.0,
              hpf_hz=100.0, lpf_hz=8000.0, takes=[take], chosen_take=take.id, status="ready")

    chain = _cue_chain(plan, cue)
    assert "stereotools=mpan=-0.750" in chain
    assert "highpass=f=100" in chain
    assert "lowpass=f=8000" in chain
    assert "rubberband=pitch=" in chain


def test_rendered_pan_energy_distribution(tmp_path):
    x = _tone(0.5, f=1000.0)
    take = _make_take(tmp_path, "pan_take", x)
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=2.0)

    # Hard left cue
    cue_l = Cue(id="cue_l", track="sfx", kind="impact", hit_t=0.5, pan=-1.0, takes=[take], chosen_take=take.id, status="ready")
    out_l = render_cue(plan, cue_l, tmp_path / "left.wav")
    d_l, _ = sf.read(str(out_l), dtype="float32", always_2d=True)
    energy_l_left = np.sum(d_l[:, 0] ** 2)
    energy_l_right = np.sum(d_l[:, 1] ** 2)
    assert energy_l_left > energy_l_right * 10, "Left panned signal should dominate channel 0"

    # Hard right cue
    cue_r = Cue(id="cue_r", track="sfx", kind="impact", hit_t=0.5, pan=1.0, takes=[take], chosen_take=take.id, status="ready")
    out_r = render_cue(plan, cue_r, tmp_path / "right.wav")
    d_r, _ = sf.read(str(out_r), dtype="float32", always_2d=True)
    energy_r_left = np.sum(d_r[:, 0] ** 2)
    energy_r_right = np.sum(d_r[:, 1] ** 2)
    assert energy_r_right > energy_r_left * 10, "Right panned signal should dominate channel 1"


def test_rendered_hpf_attenuation(tmp_path):
    # Low frequency sub-rumble at 40 Hz
    x = _tone(1.0, f=40.0, amp=0.8)
    take = _make_take(tmp_path, "sub_take", x)
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=2.0)

    cue_raw = Cue(id="raw", track="sfx", kind="impact", hit_t=0.5, takes=[take], chosen_take=take.id, status="ready")
    out_raw = render_cue(plan, cue_raw, tmp_path / "raw.wav")
    d_raw, _ = sf.read(str(out_raw), dtype="float32")

    cue_hpf = Cue(id="hpf", track="sfx", kind="impact", hit_t=0.5, hpf_hz=200.0, takes=[take], chosen_take=take.id, status="ready")
    out_hpf = render_cue(plan, cue_hpf, tmp_path / "hpf.wav")
    d_hpf, _ = sf.read(str(out_hpf), dtype="float32")

    energy_raw = np.sum(d_raw ** 2)
    energy_hpf = np.sum(d_hpf ** 2)
    assert energy_hpf < energy_raw * 0.15, "200 Hz HPF should heavily attenuate 40 Hz sub-rumble"


def test_local_bank_provider(tmp_path):
    lib_dir = tmp_path / "user_lib"
    lib_dir.mkdir()
    _write_wav(lib_dir / "door_slam_heavy.wav", _tone(0.4, f=250.0))
    _write_wav(lib_dir / "laser_gun.wav", _tone(0.2, f=1200.0))

    provider = LocalBankProvider(library_dir=lib_dir)
    files = provider.scan_library()
    assert len(files) == 2

    cue = Cue(id="c_door", track="sfx", kind="impact", intent="heavy wooden door slam shut")
    cands = provider.find(cue, tmp_path / "takes", SoundPlan(id="p1", video_path="v.mp4", fps=24, duration=3.0))
    assert len(cands) >= 1
    assert "Door Slam Heavy" in cands[0].label
    assert cands[0].provenance.licence == "User-Supplied"


def test_local_bank_import_file(tmp_path):
    sample = tmp_path / "my_custom_stinger.wav"
    _write_wav(sample, _tone(0.3, f=600.0))

    provider = LocalBankProvider(library_dir=tmp_path / "user_lib")
    cue = Cue(id="c_stinger", track="sfx", kind="ding")
    take = provider.import_take(sample, cue, tmp_path / "takes", label="Signature Stinger")

    assert take.label == "Signature Stinger"
    assert Path(take.path).exists()
    assert take.provenance.source == "user_import"
    assert take.provenance.licence == "User-Supplied"


def test_spot_with_vision_graceful_fallback(tmp_path):
    # Tests that when Ollama is offline or not running vision, draft_cues falls back to deterministic whooshes
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=5.0)
    cuts = [1.0, 3.0]
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy")

    cues = draft_cues(plan, cuts, use_vision=True, video_path=dummy_video)
    assert len(cues) == 3  # 2 cut cues + 1 music underscore
    assert cues[0].kind == "whoosh"
    assert cues[1].kind == "whoosh"
    assert cues[2].kind == "music"


def test_router_import_file_and_library_endpoints(tmp_path):
    # Set up temporary video
    video = tmp_path / "v.mp4"
    sf.write(str(tmp_path / "v.wav"), np.zeros(SR, dtype=np.float32), SR)
    # create short 1-sec mp4
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=320x240:r=24",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                    "-c:v", "libx264", "-c:a", "aac", str(video)], check=True, capture_output=True)

    client = TestClient(app)

    # 1. Create plan
    res = client.post("/api/audio/studio/plans", json={"video_path": str(video)})
    assert res.status_code == 200, res.text
    pid = res.json()["id"]

    # 2. Add a cue
    res = client.put(f"/api/audio/studio/plans/{pid}", json={
        "cues": [{"id": "imported_cue", "track": "sfx", "kind": "ding", "hit_t": 0.5, "pan": -0.5, "pitch_semitones": 3}]
    })
    assert res.status_code == 200, res.text
    c = next(c for c in res.json()["cues"] if c["id"] == "imported_cue")
    assert c["pan"] == -0.5
    assert c["pitch_semitones"] == 3

    # 3. Import custom local file
    custom_sound = tmp_path / "custom_sound.wav"
    _write_wav(custom_sound, _tone(0.4, f=500))

    res = client.post(f"/api/audio/studio/plans/{pid}/cues/imported_cue/import_file", json={
        "file_path": str(custom_sound),
        "label": "My Custom Boom"
    })
    assert res.status_code == 200, res.text
    updated = next(c for c in res.json()["cues"] if c["id"] == "imported_cue")
    assert updated["status"] == "ready"
    assert updated["chosen_take"] is not None
    assert len(updated["takes"]) == 1
    assert updated["takes"][0]["label"] == "My Custom Boom"

    # 4. Library files listing
    res = client.get("/api/audio/studio/library/files")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 5. Cue waveform peak extraction
    res = client.get(f"/api/audio/studio/plans/{pid}/cues/imported_cue/waveform?bins=50")
    assert res.status_code == 200, res.text
    peaks = res.json()["peaks"]
    assert isinstance(peaks, list)
    assert len(peaks) == 50
    assert any(p > 0 for p in peaks)

    # 6. Stream audio
    res = client.get(f"/api/audio/studio/stream?path={custom_sound}")
    assert res.status_code == 200
    assert len(res.content) > 0

    # 7. Upload to user sound library
    upload_sound = tmp_path / "incoming_whoosh.wav"
    _write_wav(upload_sound, _tone(0.2, f=800))
    with open(upload_sound, "rb") as f:
        res = client.post("/api/audio/studio/library/upload", files={"file": ("incoming_whoosh.wav", f, "audio/wav")})
    assert res.status_code == 200, res.text
    uploaded_info = res.json()
    assert uploaded_info["name"] == "incoming_whoosh.wav"
    assert Path(uploaded_info["path"]).exists()

    # 8. Search catalog (local sound bank match)
    res = client.post("/api/audio/studio/search", json={"query": "whoosh", "track": "sfx", "limit": 5})
    assert res.status_code == 200
    search_results = res.json()
    assert isinstance(search_results, list)
    assert any("whoosh" in r["name"].lower() for r in search_results)
