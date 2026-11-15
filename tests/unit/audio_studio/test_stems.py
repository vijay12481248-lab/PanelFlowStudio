import csv
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, PlanStore, Provenance, Take
from engine.audio.studio.sources.synth import render
from engine.audio.studio.stems import export

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000


def _take(tmp_path, name, x, prov):
    p = tmp_path / f"{name}.wav"
    sf.write(str(p), np.asarray(x, dtype=np.float32), SR)
    m = measure_take(p)
    return Take(id=name, path=str(p), provenance=prov, onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s,
                peak_db=m.peak_db, rms_db=m.rms_db, clipped_samples=m.clipped_samples)


def _rig(tmp_path):
    cc0 = Provenance(source="synth", licence="CC0", seed=1)
    by = Provenance(source="openverse/freesound", licence="BY 4.0", url="https://freesound.org/s/9", author="bob")
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=6.0)
    tone = 0.2 * np.sin(2 * np.pi * 220 * np.arange(6 * SR) / SR)
    dlg = tmp_path / "dlg.wav"
    sf.write(str(dlg), np.concatenate([np.zeros(SR), 0.4 * np.sin(2 * np.pi * 500 * np.arange(SR) / SR), np.zeros(4 * SR)]).astype(np.float32), SR)
    plan.dialogue_path = str(dlg)
    for cue, take in (
        (Cue(id="m", track="music", kind="music", t_in=0, t_out=6.0), _take(tmp_path, "mus", tone, cc0)),
        (Cue(id="c1", track="sfx", kind="impact", hit_t=3.0), _take(tmp_path, "imp", render("impact", 1.2, 1), cc0)),
        (Cue(id="c2", track="sfx", kind="door", hit_t=4.0), _take(tmp_path, "door", render("impact", 1.0, 2), by)),
    ):
        cue.takes, cue.chosen_take, cue.status = [take], take.id, "ready"
        plan.cues.append(cue)
    return plan


def _read(p):
    d, _ = sf.read(str(p), dtype="float32", always_2d=True)
    return d


def test_export_writes_all_files(tmp_path):
    plan = _rig(tmp_path)
    res = export(plan, tmp_path / "out")
    for name in ("dialogue.wav", "music.wav", "effects.wav", "me.wav", "master.wav", "cuesheet.json", "cuesheet.csv", "credits.txt", "export.json"):
        assert (tmp_path / "out" / name).is_file(), name
    assert res["loudness"]["integrated_lufs"] == pytest.approx(-14.0, abs=1.0)
    meta = json.loads((tmp_path / "out" / "export.json").read_text(encoding="utf-8"))
    assert meta["plan_id"] == plan.id and "findings" in meta


def test_me_equals_music_plus_effects(tmp_path):
    export(_rig(tmp_path), tmp_path / "out")
    o = tmp_path / "out"
    me, m, e = _read(o / "me.wav"), _read(o / "music.wav"), _read(o / "effects.wav")
    n = min(len(me), len(m), len(e))
    assert np.abs(me[:n] - (m[:n] + e[:n])).max() < 1e-3


def test_credits_only_for_cc_by(tmp_path):
    export(_rig(tmp_path), tmp_path / "out")
    text = (tmp_path / "out" / "credits.txt").read_text(encoding="utf-8")
    assert "bob" in text and "https://freesound.org/s/9" in text and "synth" not in text


def test_refuses_incomplete_cues_unless_allowed(tmp_path):
    plan = _rig(tmp_path)
    plan.cues.append(Cue(id="c3", track="sfx", kind="door", hit_t=5.0, status="needs_pick"))
    with pytest.raises(ValueError, match="c3"):
        export(plan, tmp_path / "out")
    export(plan, tmp_path / "out2", allow_incomplete=True)
    assert (tmp_path / "out2" / "master.wav").is_file()


def test_csv_has_one_row_per_cue(tmp_path):
    plan = _rig(tmp_path)
    export(plan, tmp_path / "out")
    rows = list(csv.DictReader((tmp_path / "out" / "cuesheet.csv").open(encoding="utf-8")))
    assert [r["id"] for r in rows] == ["m", "c1", "c2"] and rows[2]["licence"] == "BY 4.0" and rows[1]["placement_error_ms"] != ""


def test_master_mp4_when_video_given(tmp_path):
    plan = _rig(tmp_path)
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=6:r=24", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(video)], check=True)
    export(plan, tmp_path / "out", video_in=video)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                            str(tmp_path / "out" / "master.mp4")], capture_output=True, text=True).stdout
    assert "audio" in probe and "video" in probe
