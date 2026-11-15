import numpy as np
import soundfile as sf

from engine.audio.studio.plan import Cue, PlanStore, Provenance, Take
from engine.audio.studio.qa import check_plan

SR = 48000


def _render_at(delay_s):
    """A fake render_cue: the cue's burst lands `delay_s` after the requested hit."""
    def render(plan, cue, out):
        x = np.zeros(int(SR * plan.duration), dtype=np.float32)
        i = int(SR * ((cue.hit_t or 0.0) + delay_s))
        x[i:i + 2400] = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(2400) / SR)
        sf.write(str(out), x, SR)
        return out
    return render


def _plan(tmp_path, **take_kw):
    plan = PlanStore(tmp_path).create("v.mp4", 24.0, 10.0)
    t = Take(id="t1", path="x.wav", provenance=Provenance(source="t", licence="CC0"), onset_s=0.0, peak_s=0.02,
             duration_s=1.0, peak_db=-6.0, rms_db=-20.0, **take_kw)
    plan.cues = [Cue(id="c1", track="sfx", kind="impact", hit_t=2.0, takes=[t], chosen_take="t1", status="ready")]
    return plan


def _rules(findings):
    return {(f.cue_id, f.rule, f.severity) for f in findings}


def test_clean_plan_has_no_findings(tmp_path):
    assert check_plan(_plan(tmp_path), _render_at(0.0)) == []


def test_clipped_take_is_error(tmp_path):
    f = check_plan(_plan(tmp_path, clipped_samples=12), _render_at(0.0))
    assert ("c1", "clipping", "error") in _rules(f)


def test_missing_take_is_error_but_draft_is_skipped(tmp_path):
    plan = _plan(tmp_path)
    plan.cues += [Cue(id="c2", track="sfx", kind="impact", hit_t=3.0, status="needs_pick"),
                  Cue(id="c3", track="sfx", kind="impact", hit_t=4.0, status="draft")]
    rules = _rules(check_plan(plan, _render_at(0.0)))
    assert ("c2", "no_take", "error") in rules and not any(r[0] == "c3" for r in rules)


def test_silent_and_too_loud_takes(tmp_path):
    plan = _plan(tmp_path)
    plan.cues[0].takes[0].peak_db = -80.0
    assert ("c1", "silent", "error") in _rules(check_plan(plan, _render_at(0.0)))
    plan.cues[0].takes[0].peak_db = -0.2
    assert ("c1", "too_loud_take", "warn") in _rules(check_plan(plan, _render_at(0.0)))


def test_placement_error_over_40ms_is_error(tmp_path):
    f = check_plan(_plan(tmp_path), _render_at(0.06))
    assert ("c1", "placement_error", "error") in _rules(f)


def test_placement_error_20_to_40ms_is_warn(tmp_path):
    assert ("c1", "placement_error", "warn") in _rules(check_plan(_plan(tmp_path), _render_at(0.03)))


def test_placement_error_recorded_on_cue(tmp_path):
    plan = _plan(tmp_path)
    check_plan(plan, _render_at(0.01))
    assert 5 < plan.cues[0].placement_error_ms < 15


def test_hit_beyond_video_is_warned_not_measured(tmp_path):
    plan = _plan(tmp_path)
    plan.cues[0].hit_t = 99.0
    calls = []

    def render(p, c, out):
        calls.append(c.id)
        return _render_at(0.0)(p, c, out)
    assert ("c1", "beyond_video", "warn") in _rules(check_plan(plan, render))
    assert calls == []
