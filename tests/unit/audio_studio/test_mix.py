import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio.measure import measure_take
from engine.audio.studio.mix import measure_loudness, render_cue, render_master, render_roles
from engine.audio.studio.plan import Cue, PlanStore, Provenance, SoundPlan, Take
from engine.audio.studio.sources.synth import render

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
PROV = Provenance(source="test", licence="CC0")


def _write(path: Path, x) -> str:
    sf.write(str(path), np.asarray(x, dtype=np.float32), SR)
    return str(path)


def _take(tmp_path, name, x, tid=None) -> Take:
    p = _write(tmp_path / f"{name}.wav", x)
    m = measure_take(p)
    return Take(id=tid or name, path=p, provenance=PROV, onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s,
                peak_db=m.peak_db, rms_db=m.rms_db, clipped_samples=m.clipped_samples)


def _burst_at(at, total=1.0, amp=0.6):
    x = np.zeros(int(SR * total), dtype=np.float32)
    n = int(SR * 0.05)
    i = int(SR * at)
    x[i:i + n] = amp * np.sin(2 * np.pi * 1000 * np.arange(n) / SR)
    return x


def _tone(sec, amp=0.3, f=300):
    return amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)


def _plan(tmp_path, duration=4.0, dialogue=None) -> SoundPlan:
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=duration)
    plan.dialogue_path = dialogue
    return plan


def _add(plan, tmp_path, cue: Cue, take: Take):
    cue.takes, cue.chosen_take, cue.status = [take], take.id, "ready"
    plan.cues.append(cue)
    return cue


def _read(p):
    d, _ = sf.read(str(p), dtype="float32", always_2d=True)
    return d


def test_cue_lands_on_hit_within_one_frame(tmp_path):
    plan = _plan(tmp_path)
    cue = _add(plan, tmp_path, Cue(id="c1", track="sfx", kind="impact", hit_t=1.0), _take(tmp_path, "imp", render("impact", 1.2, 1)))
    out = render_cue(plan, cue, tmp_path / "c1.wav")
    m = measure_take(out)
    assert abs(m.onset_s - 1.0) <= 0.021 and m.duration_s == pytest.approx(plan.duration, abs=0.05)


def test_peak_anchor_lands_peak_on_hit(tmp_path):
    plan = _plan(tmp_path)
    take = _take(tmp_path, "wh", render("whoosh", 1.0, 3))
    cue = _add(plan, tmp_path, Cue(id="w", track="sfx", kind="whoosh", anchor="peak", hit_t=2.0), take)
    assert abs(measure_take(render_cue(plan, cue, tmp_path / "w.wav")).peak_s - 2.0) <= 0.025


def test_negative_start_trims_not_crashes(tmp_path):
    plan = _plan(tmp_path)
    cue = _add(plan, tmp_path, Cue(id="c1", track="sfx", kind="impact", hit_t=0.1), _take(tmp_path, "late", _burst_at(0.3)))
    m = measure_take(render_cue(plan, cue, tmp_path / "c1.wav"))
    assert abs(m.onset_s - 0.1) <= 0.021


def test_cue_past_video_end_is_clipped(tmp_path):
    plan = _plan(tmp_path)
    cue = _add(plan, tmp_path, Cue(id="c1", track="sfx", kind="impact", hit_t=9.0), _take(tmp_path, "imp", render("impact", 1.2, 1)))
    out = render_cue(plan, cue, tmp_path / "c1.wav")
    assert measure_take(out).duration_s == pytest.approx(plan.duration, abs=0.05)


def test_no_dialogue_no_crash(tmp_path):
    plan = _plan(tmp_path)
    _add(plan, tmp_path, Cue(id="m", track="music", kind="music", t_in=0, t_out=4.0), _take(tmp_path, "mus", _tone(4.0)))
    stems = render_roles(plan, tmp_path / "stems")
    assert np.abs(_read(stems["music"])).max() > 0.1 and np.abs(_read(stems["dialogue"])).max() < 1e-6


def test_stems_sum_to_premix(tmp_path):
    dlg = _write(tmp_path / "dlg.wav", np.concatenate([np.zeros(SR), _tone(1.0, 0.4, 500), np.zeros(2 * SR)]))
    plan = _plan(tmp_path, dialogue=dlg)
    _add(plan, tmp_path, Cue(id="m", track="music", kind="music", t_in=0, t_out=4.0), _take(tmp_path, "mus", _tone(4.0, 0.2)))
    _add(plan, tmp_path, Cue(id="c1", track="sfx", kind="impact", hit_t=2.5), _take(tmp_path, "imp", render("impact", 1.2, 1)))
    s = render_roles(plan, tmp_path / "stems")
    total = _read(s["dialogue"]) + _read(s["music"]) + _read(s["effects"])
    n = min(len(total), len(_read(s["premix"])))
    assert np.abs(total[:n] - _read(s["premix"])[:n]).max() < 1e-3  # below -60 dBFS


def test_music_ducks_under_dialogue(tmp_path):
    dlg = _write(tmp_path / "dlg.wav", np.concatenate([np.zeros(SR), _tone(2.0, 0.5, 500), np.zeros(SR)]))
    music = _take(tmp_path, "mus", _tone(4.0, 0.2, 200))

    def music_rms(dialogue):
        plan = _plan(tmp_path, dialogue=dialogue)
        _add(plan, tmp_path, Cue(id="m", track="music", kind="music", t_in=0, t_out=4.0), music)
        x = _read(render_roles(plan, tmp_path / ("a" if dialogue else "b"))["music"])
        seg = x[int(1.3 * SR):int(2.7 * SR)]
        return 20 * np.log10(np.sqrt(np.mean(seg ** 2)))
    assert music_rms(None) - music_rms(dlg) >= 6.0


def test_bed_shorter_than_span_is_filled(tmp_path):
    plan = _plan(tmp_path, duration=5.0)
    _add(plan, tmp_path, Cue(id="a", track="ambience", kind="noise_bed", t_in=0, t_out=5.0), _take(tmp_path, "bed", render("noise_bed", 1.0, 2)))
    x = _read(render_roles(plan, tmp_path / "stems")["effects"])
    tail = x[int(4.0 * SR):int(4.9 * SR)]
    assert 20 * np.log10(np.sqrt(np.mean(tail ** 2)) + 1e-9) > -50


def test_master_hits_loudness_target(tmp_path):
    plan = _plan(tmp_path, duration=10.0)
    _add(plan, tmp_path, Cue(id="m", track="music", kind="music", t_in=0, t_out=10.0), _take(tmp_path, "mus", _tone(10.0, 0.25, 220)))
    _add(plan, tmp_path, Cue(id="c1", track="sfx", kind="impact", hit_t=3.0), _take(tmp_path, "imp", render("impact", 1.2, 1)))
    res = render_master(plan, tmp_path / "master.wav", target_lufs=-14.0)
    assert res["integrated_lufs"] == pytest.approx(-14.0, abs=1.0) and res["true_peak_db"] <= -1.0
    again = measure_loudness(tmp_path / "master.wav")
    assert again["integrated_lufs"] == pytest.approx(res["integrated_lufs"], abs=0.2)


def test_ducked_music_stem_keeps_full_length_and_tail(tmp_path):
    dlg = _write(tmp_path / "dlg.wav", np.concatenate([np.zeros(SR), _tone(1.0, 0.4, 500), np.zeros(2 * SR)]))
    mus = _take(tmp_path, "mus", _tone(4.0, 0.2))
    for i in range(4):  # ffmpeg's sidechain output length varied from run to run
        plan = _plan(tmp_path, dialogue=dlg)
        _add(plan, tmp_path, Cue(id="m", track="music", kind="music", t_in=0, t_out=4.0), mus)
        x = _read(render_roles(plan, tmp_path / f"s{i}")["music"])
        assert len(x) == int(4.0 * SR)
        assert 20 * np.log10(np.sqrt(np.mean(x[-int(0.1 * SR):] ** 2)) + 1e-9) > -30


def test_mp3_whoosh_peak_lands_on_hit(tmp_path):
    """Regression from the real reel: mp3 library clips landed ~150 ms off (decoder start padding + unstable peak)."""
    wav = tmp_path / "wh.wav"
    sf.write(str(wav), render("whoosh", 1.5, 3), SR)
    mp3 = tmp_path / "wh.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "96k", str(mp3)], check=True)
    m = measure_take(mp3)
    take = Take(id="mp3", path=str(mp3), provenance=PROV, onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s,
                peak_db=m.peak_db, rms_db=m.rms_db, clipped_samples=m.clipped_samples)
    plan = _plan(tmp_path)
    cue = _add(plan, tmp_path, Cue(id="w", track="sfx", kind="whoosh", anchor="peak", hit_t=2.0), take)
    assert abs(measure_take(render_cue(plan, cue, tmp_path / "w.wav")).peak_s - 2.0) <= 0.021
