"""Effects are levelled against the voice: not louder than the speech, lower on top of words, lowest where the voice is soft."""
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio import autolevel
from engine.audio.studio.measure import measure_take
from engine.audio.studio.mix import render_roles
from engine.audio.studio.plan import Cue, PlanStore, Provenance, Take

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
PROV = Provenance(source="test", licence="CC0")


def _tone(sec, amp, f=300):
    return amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)


def _plan(tmp_path, dlg, duration=8.0):
    p = tmp_path / "dlg.wav"
    if dlg is not None:
        sf.write(str(p), np.asarray(dlg, dtype=np.float32), SR)
    plan = PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=duration)
    plan.dialogue_path = str(p) if dlg is not None else None
    return plan


def _add(plan, tmp_path, cue, x, name):
    p = tmp_path / f"{name}.wav"
    sf.write(str(p), np.asarray(x, dtype=np.float32), SR)
    m = measure_take(p)
    take = Take(id=name, path=str(p), provenance=PROV, onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s, peak_db=m.peak_db, rms_db=m.rms_db)
    cue.takes, cue.chosen_take, cue.status = [take], name, "ready"
    plan.cues.append(cue)


def _loud_hit():   # a stock impact: peaks near full scale
    x = np.zeros(SR)
    x[:int(0.3 * SR)] = 0.95 * np.sin(2 * np.pi * 120 * np.arange(int(0.3 * SR)) / SR) * np.exp(-np.arange(int(0.3 * SR)) / (0.1 * SR))
    return x


def _db(x):
    return 20 * np.log10(np.abs(x).max() + 1e-9)


def _rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def _effects(plan, tmp_path):
    return sf.read(str(render_roles(plan, tmp_path / "r")["effects"]), dtype="float32", always_2d=True)[0]


def _speech_ref(tmp_path):   # the speech level of the rendered dialogue stem (what the effects are levelled against; stereo, so 3 dB under the mono file)
    return autolevel.profile(tmp_path / "r" / "dialogue.wav").ref_db


def test_a_full_scale_hit_is_brought_under_the_speech(tmp_path):
    speech = np.concatenate([_tone(3.0, 0.1), np.zeros(5 * SR)])   # speech about -23 dBFS RMS
    plan = _plan(tmp_path, speech)
    _add(plan, tmp_path, Cue(id="h", track="sfx", kind="impact", hit_t=5.0), _loud_hit(), "hit")   # lands in silence
    peak = _db(_effects(plan, tmp_path))
    ref = _speech_ref(tmp_path)
    assert peak == pytest.approx(ref + 6.0, abs=1.0) and peak < -10.0, (peak, ref)


def test_a_hit_on_top_of_words_is_lower_than_the_same_hit_in_silence(tmp_path):
    speech = np.concatenate([_tone(3.0, 0.1), np.zeros(5 * SR)])
    levels = {}
    for name, t in (("on_words", 1.5), ("in_silence", 5.0)):
        plan = _plan(tmp_path / name if (tmp_path / name).mkdir() is None else tmp_path, speech)
        _add(plan, tmp_path / name, Cue(id="h", track="sfx", kind="impact", hit_t=t), _loud_hit(), "hit")
        levels[name] = _db(_effects(plan, tmp_path / name))
    assert levels["in_silence"] - levels["on_words"] >= 2.5, levels


def test_a_hit_in_a_soft_passage_is_quieter_than_in_a_loud_one(tmp_path):
    speech = np.concatenate([_tone(3.0, 0.5), np.zeros(SR), _tone(3.0, 0.03), np.zeros(SR)])   # loud line, then a very soft one
    levels = {}
    for name, t in (("loud", 1.5), ("soft", 5.5)):
        (tmp_path / name).mkdir()
        plan = _plan(tmp_path / name, speech)
        _add(plan, tmp_path / name, Cue(id="h", track="sfx", kind="impact", hit_t=t), _loud_hit(), "hit")
        levels[name] = _db(_effects(plan, tmp_path / name))
    assert levels["loud"] - levels["soft"] >= 4.0, levels


def test_ambience_bed_sinks_under_speech_and_stays_quiet(tmp_path):
    speech = np.concatenate([np.zeros(2 * SR), _tone(3.0, 0.1), np.zeros(3 * SR)])
    plan = _plan(tmp_path, speech)
    noise = np.random.default_rng(1).normal(0, 0.3, 8 * SR)   # a loud noisy bed
    _add(plan, tmp_path, Cue(id="a", track="ambience", kind="noise_bed", t_in=0, t_out=8.0), noise, "bed")
    x = _effects(plan, tmp_path)
    ref = _speech_ref(tmp_path)
    open_air, under = _rms_db(x[int(0.3 * SR):int(1.5 * SR)]), _rms_db(x[int(3.0 * SR):int(4.5 * SR)])
    assert open_air < ref - 8.0, (open_air, ref)   # the bed alone is well below the speech
    assert open_air - under >= 6.0, (open_air, under)   # and sinks further while someone talks


def test_without_dialogue_effects_use_the_default_speech_level(tmp_path):
    plan = _plan(tmp_path, None)
    _add(plan, tmp_path, Cue(id="h", track="sfx", kind="impact", hit_t=2.0), _loud_hit(), "hit")
    assert _db(_effects(plan, tmp_path)) == pytest.approx(autolevel.DEFAULT_REF_DB + 6.0, abs=1.0)


def test_the_cues_own_gain_still_works_on_top(tmp_path):
    speech = np.concatenate([_tone(2.0, 0.1), np.zeros(6 * SR)])
    out = {}
    for name, g in (("flat", 0.0), ("plus6", 6.0)):
        (tmp_path / name).mkdir()
        plan = _plan(tmp_path / name, speech)
        _add(plan, tmp_path / name, Cue(id="h", track="sfx", kind="impact", hit_t=5.0, gain_db=g), _loud_hit(), "hit")
        out[name] = _db(_effects(plan, tmp_path / name))
    assert out["plus6"] - out["flat"] == pytest.approx(6.0, abs=0.5)
