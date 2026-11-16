"""Narration cues: plan fields, the local speech provider (fake synth), mixing into the dialogue stem, and QA."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.measure import measure_take
from engine.audio.studio.mix import render_roles
from engine.audio.studio.plan import Cue, PlanStore, Provenance, SoundPlan, Take
from engine.audio.studio.qa import check_plan
from engine.audio.studio.sources.narration import NarrationProvider, estimate_seconds, list_voices
from engine.audio.studio.sources.openverse import OpenverseProvider

SR = 48000
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _tone(sec, amp=0.3, f=220):
    return (amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)).astype(np.float32)


def fake_synth(calls=None, seconds=2.0):
    def synth(text, voice, speed, provider, language, out):
        if calls is not None:
            calls.append(dict(text=text, voice=voice, speed=speed, provider=provider, language=language))
        sf.write(str(out), _tone(seconds / speed), SR)
    return synth


def _plan(tmp_path, duration=10.0):
    return PlanStore(tmp_path / "store").create("v.mp4", fps=24.0, duration=duration)


def _vo(cid, text="Hello there, this is the narrator.", t_in=1.0, **kw):
    fields = dict(id=cid, track="dialogue", kind="narration", text=text, voice="af_heart", provider="kokoro", t_in=t_in)
    return Cue(**{**fields, **kw})


def test_old_plans_and_cues_keep_working_with_the_new_fields(tmp_path):
    plan = _plan(tmp_path)
    raw = json.loads(plan.model_dump_json())
    for k in ("keep_original_audio", "source"):
        raw.pop(k, None)
    again = SoundPlan.model_validate(raw)
    assert again.keep_original_audio is True and again.source == {}
    c = Cue(id="x", track="sfx", kind="click")
    assert (c.text, c.voice, c.provider, c.speed) == ("", "", "", 1.0)


def test_estimate_is_words_over_rate_plus_pauses():
    from engine.audio.studio.sources.narration import WORDS_PER_SECOND as WPS
    assert estimate_seconds(" ".join(["word"] * 26)) == pytest.approx(26 / WPS, abs=0.05)
    assert estimate_seconds(" ".join(["word"] * 26), speed=2.0) == pytest.approx(13 / WPS, abs=0.05)
    assert estimate_seconds("One. Two. Three.") > estimate_seconds("One Two Three")
    assert estimate_seconds("") == 0.0


def test_provider_speaks_the_cue_text_and_records_where_it_came_from(tmp_path):
    plan, calls = _plan(tmp_path), []
    cue = _vo("v1", speed=1.1)
    out = NarrationProvider(synth=fake_synth(calls)).find(cue, tmp_path / "t", plan, limit=1)
    assert len(out) == 1 and Path(out[0].path).is_file() and out[0].path.endswith(".wav")
    assert calls == [dict(text=cue.text, voice="af_heart", speed=1.1, provider="kokoro", language="English")]
    pv = out[0].provenance
    assert pv.source == "tts/kokoro" and pv.licence == "Apache-2.0" and pv.model == "kokoro-82m" and pv.author == "af_heart"


def test_more_candidates_differ_in_pace(tmp_path):
    calls = []
    out = NarrationProvider(synth=fake_synth(calls)).find(_vo("v1"), tmp_path / "t", _plan(tmp_path), limit=3)
    assert [round(c["speed"], 2) for c in calls] == [1.0, 0.92, 1.08] and len({c.id for c in out}) == 3


def test_only_narration_cues_with_words_are_served(tmp_path):
    prov, plan = NarrationProvider(synth=fake_synth()), _plan(tmp_path)
    assert prov.find(Cue(id="a", track="sfx", kind="impact"), tmp_path, plan) == []
    assert prov.find(_vo("v2", text="   "), tmp_path, plan) == []
    assert "words" in prov.availability_for(_vo("v2", text="")).reason


def test_unknown_provider_and_missing_voice_are_refused_with_a_reason(tmp_path):
    prov, plan = NarrationProvider(synth=fake_synth(), voices={"qwen3_tts": ["marcus_male"], "kokoro": ["af_heart"]}), _plan(tmp_path)
    bad = _vo("v1", provider="elevenlabs")
    assert prov.find(bad, tmp_path, plan) == [] and "elevenlabs" in prov.availability_for(bad).reason
    nov = _vo("v2", provider="qwen3_tts")
    nov.voice = "nobody"
    assert prov.find(nov, tmp_path, plan) == [] and "nobody" in prov.availability_for(nov).reason


def test_a_failing_synth_is_reported_not_faked(tmp_path):
    def boom(*a):
        raise RuntimeError("Kokoro: model not found")
    prov = NarrationProvider(synth=boom)
    cue = _vo("v1")
    assert prov.find(cue, tmp_path / "t", _plan(tmp_path)) == []
    assert "model not found" in prov.availability_for(cue).reason


def test_engine_sources_narration_and_never_asks_the_library(tmp_path):
    store = PlanStore(tmp_path / "store")
    plan = store.create("v.mp4", fps=24.0, duration=10.0)
    plan.cues = [_vo("v1")]
    store.save(plan)

    def boom(url):
        raise AssertionError("the library must not be asked for narration")
    eng = AudioEngine(store, [OpenverseProvider(boom), NarrationProvider(synth=fake_synth(seconds=2.5))])
    got = eng.source_cue(plan.id, "v1").cue("v1")
    assert got.status == "ready" and got.chosen().duration_s == pytest.approx(2.5, abs=0.05) and len(got.takes) == 1


def test_voices_lists_both_engines():
    v = list_voices()
    assert "af_heart" in v["kokoro"] and isinstance(v["qwen3_tts"], list)


def _take(tmp_path, name, sec, amp=0.3):
    p = tmp_path / f"{name}.wav"
    sf.write(str(p), _tone(sec, amp), SR)
    m = measure_take(p)
    return Take(id=name, path=str(p), provenance=Provenance(source="test", licence="CC0"), onset_s=m.onset_s, peak_s=m.peak_s, duration_s=m.duration_s,
                peak_db=m.peak_db, rms_db=m.rms_db, clipped_samples=m.clipped_samples)


def _ready(plan, tmp_path, cue, sec, amp=0.3):
    t = _take(tmp_path, cue.id, sec, amp)
    cue.takes, cue.chosen_take, cue.status = [t], t.id, "ready"
    plan.cues.append(cue)
    return cue


def _rms(x, a, b):
    seg = x[int(a * SR):int(b * SR)]
    return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)


def _read(p):
    d, _ = sf.read(str(p), dtype="float32", always_2d=True)
    return d


@needs_ffmpeg
def test_narration_lands_in_the_dialogue_stem_at_its_start_and_ducks_the_music(tmp_path):
    plan = _plan(tmp_path, 6.0)
    _ready(plan, tmp_path, _vo("v1", t_in=2.0), 2.0, 0.4)
    _ready(plan, tmp_path, Cue(id="m", track="music", kind="music", t_in=0, t_out=6.0), 6.0, 0.2)
    stems = render_roles(plan, tmp_path / "s")
    d = _read(stems["dialogue"])
    assert len(d) == int(6.0 * SR) and _rms(d, 0, 1.5) < -80 and _rms(d, 2.2, 3.8) > -20 and _rms(d, 4.3, 5.9) < -80
    m = _read(stems["music"])
    assert _rms(m, 2.4, 3.6) < _rms(m, 0.2, 1.5) - 6, "the music ducks under the narration even with no original audio"


@needs_ffmpeg
def test_original_audio_is_kept_or_muted_by_the_switch(tmp_path):
    import subprocess
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=6:r=24", "-f", "lavfi", "-i", "sine=frequency=300:duration=6",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
    plan = _plan(tmp_path, 6.0)
    plan.dialogue_path = str(video)
    _ready(plan, tmp_path, _vo("v1", t_in=3.0), 2.0, 0.4)
    keep = _read(render_roles(plan, tmp_path / "keep")["dialogue"])
    assert _rms(keep, 0.2, 2.5) > -30, "original audio is in the stem when kept"
    plan.keep_original_audio = False
    gone = _read(render_roles(plan, tmp_path / "gone")["dialogue"])
    assert _rms(gone, 0.2, 2.5) < -80 and _rms(gone, 3.2, 4.8) > -20, "muted: only the narration remains"


@needs_ffmpeg
def test_a_muted_dialogue_track_silences_narration_too(tmp_path):
    plan = _plan(tmp_path, 6.0)
    _ready(plan, tmp_path, _vo("v1", t_in=1.0), 2.0)
    plan.tracks[0].mute = True
    assert _rms(_read(render_roles(plan, tmp_path / "s")["dialogue"]), 0, 6) < -80


def _qa(plan, tmp_path):
    return {(f.cue_id, f.rule, f.severity) for f in check_plan(plan, _no_render)}


def _no_render(plan, cue, out):
    sf.write(str(out), np.zeros(int(SR * plan.duration), dtype=np.float32), SR)
    return out


def test_qa_flags_a_line_that_runs_into_the_next_one_and_past_the_end(tmp_path):
    plan = _plan(tmp_path, 10.0)
    _ready(plan, tmp_path, _vo("v1", t_in=1.0), 3.0)
    _ready(plan, tmp_path, _vo("v2", t_in=3.5), 3.0)
    _ready(plan, tmp_path, _vo("v3", t_in=9.0), 3.0)
    rules = _qa(plan, tmp_path)
    assert ("v1", "narration_overrun", "error") in rules and ("v3", "narration_past_end", "error") in rules and not any(r[0] == "v2" and r[1] == "narration_overrun" for r in rules)


def test_qa_lets_a_line_run_across_a_picture_cut_and_warns_when_it_is_too_fast(tmp_path):
    plan = _plan(tmp_path, 10.0)
    plan.cuts = [2.0]
    _ready(plan, tmp_path, _vo("v1", text=" ".join(["word"] * 40), t_in=1.0), 4.0)
    rules = _qa(plan, tmp_path)
    assert not any(r[1] in ("narration_overrun", "narration_past_end") for r in rules) and ("v1", "narration_too_fast", "warn") in rules


def test_a_slot_that_raises_does_not_leak_the_gpu_lock(tmp_path, monkeypatch):
    from engine.audio.studio.sources import narration as nar
    from engine.audio.studio.sources.music import _ONE_AT_A_TIME

    class BadSlot:
        def acquire(self, job):
            raise RuntimeError("resource manager down")

        def release(self, job):
            raise AssertionError("never acquired, never released")
    prov = NarrationProvider(slot=BadSlot(), voices={"kokoro": ["af_heart"], "qwen3_tts": ["aria"]})
    assert prov.find(_vo("v1", voice="aria", provider="qwen3_tts"), tmp_path / "t", _plan(tmp_path)) == []
    assert "resource manager down" in prov.availability_for(_vo("v1", voice="aria", provider="qwen3_tts")).reason
    assert _ONE_AT_A_TIME.acquire(blocking=False), "the GPU lock is free again"
    _ONE_AT_A_TIME.release()


def test_words_changed_while_speaking_are_not_saved_as_the_new_speech(tmp_path):
    store = PlanStore(tmp_path / "store")
    plan = store.create("v.mp4", fps=24.0, duration=10.0)
    plan.cues = [_vo("v1", text="Old words.")]
    store.save(plan)
    inner = fake_synth()

    def slow(text, voice, speed, provider, language, out):   # the owner edits the line while the model speaks the old one
        with store.lock(plan.id):
            p = store.load(plan.id)
            p.cue("v1").text = "New words."
            store.save(p)
        inner(text, voice, speed, provider, language, out)
    got = AudioEngine(store, [NarrationProvider(synth=slow)]).source_cue(plan.id, "v1", mode="auto").cue("v1")
    assert got.text == "New words." and got.status == "draft" and got.chosen_take is None and "changed" in got.reason


def test_kokoro_voices_are_the_ones_on_disk(tmp_path):
    from engine.audio.studio.sources.narration import kokoro_voices_on_disk
    d = tmp_path / "models--hexgrad--Kokoro-82M" / "snapshots" / "abc" / "voices"
    d.mkdir(parents=True)
    for v in ("am_adam", "af_heart", "bm_george"):
        (d / f"{v}.pt").write_bytes(b"x")
    assert kokoro_voices_on_disk(tmp_path) == ["af_heart", "am_adam", "bm_george"], "af_heart (the default) first, then by name"
    assert kokoro_voices_on_disk(tmp_path / "nothing") == []
