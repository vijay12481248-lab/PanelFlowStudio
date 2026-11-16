"""Script -> narration cues, and the one-click 'fix problems' pass."""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.fix import fix_plan
from engine.audio.studio.plan import Candidate, Cue, PlanStore, Provenance
from engine.audio.studio.script import add_script, place_lines, split_script
from engine.audio.studio.sources.base import Availability
from engine.audio.studio.sources.narration import WORDS_PER_SECOND, estimate_seconds

SR = 48000


def test_split_script_uses_paragraphs_then_sentences():
    assert split_script("First line here.\n\nSecond line here.\n\n\nThird.") == ["First line here.", "Second line here.", "Third."]
    assert split_script("One. Two? Three! Four") == ["One.", "Two?", "Three!", "Four"]
    assert split_script("A single paragraph\nthat wraps over two lines, with one sentence.") == ["A single paragraph that wraps over two lines, with one sentence."]
    assert split_script("  \n \n") == []


def test_sequential_placement_follows_estimated_lengths_and_the_gap():
    lines = ["one two three six", "four five six seven eight"]
    out = place_lines(lines, mode="sequential", start=2.0, gap=0.5, cuts=[], speed=1.0)
    assert out[0] == (lines[0], 2.0)
    assert out[1][1] == pytest.approx(2.0 + estimate_seconds(lines[0]) + 0.5, abs=0.01)


def test_per_cut_placement_puts_line_i_on_cut_i_then_continues_after_the_last_line():
    lines = ["a b c", "d e f", "g h i", "j k l"]
    out = place_lines(lines, mode="per_cut", start=0.0, gap=0.4, cuts=[3.0, 8.0], speed=1.0)
    assert [t for _, t in out[:3]] == [0.0, 3.0, 8.0]
    assert out[3][1] == pytest.approx(8.0 + estimate_seconds("g h i") + 0.4, abs=0.01)


def test_add_script_makes_draft_narration_cues_with_fresh_ids(tmp_path):
    plan = PlanStore(tmp_path).create("v.mp4", 24.0, 60.0)
    plan.cues = [Cue(id="vo_01", track="dialogue", kind="narration", text="old")]
    new = add_script(plan, "Hello world today.\n\nGoodbye world tomorrow.", mode="sequential", start=1.0, gap=0.3, voice="af_heart", provider="kokoro", speed=1.1)
    assert [c.id for c in new] == ["vo_02", "vo_03"]
    c = new[0]
    assert (c.track, c.kind, c.text, c.voice, c.provider, c.speed, c.status, c.t_in) == ("dialogue", "narration", "Hello world today.", "af_heart", "kokoro", 1.1, "draft", 1.0)
    assert new[1].t_in > new[0].t_in


# ---- fix ----
def _wav(path, amp=0.5, dur=1.0):
    n = int(SR * dur)
    x = np.zeros(n, dtype=np.float32)
    x[2400:4800] = amp * np.sin(2 * np.pi * 800 * np.arange(2400) / SR)
    sf.write(str(path), x, SR)
    return str(path)


class Fake:
    name = "fake"

    def __init__(self, specs):
        self.specs = specs   # list of (amp, dur) tried in order across calls
        self.calls = 0

    def availability(self):
        return Availability(True, None)

    def find(self, cue, out_dir, plan, limit=3):
        self.calls += 1
        out = []
        for i, (amp, dur) in enumerate(self.specs[:limit]):
            out.append(Candidate(id=f"{cue.id}_{i}", path=_wav(Path(out_dir) / f"{cue.id}_{i}.wav", amp, dur), provider="fake",
                                 provenance=Provenance(source="fake", licence="CC0", url=f"u{i}")))
        return out


def _no_render(plan, cue, out):
    sf.write(str(out), np.zeros(int(SR * plan.duration), dtype=np.float32), SR)
    return out


def test_fix_re_sources_a_clipped_cue_to_a_different_clean_clip(tmp_path):
    store = PlanStore(tmp_path)
    plan = store.create("v.mp4", 24.0, 10.0)
    plan.cues = [Cue(id="c1", track="sfx", kind="impact", intent="hit")]
    store.save(plan)
    eng = AudioEngine(store, [Fake([(1.0, 0.5), (0.5, 1.0)])])
    eng.source_cue(plan.id, "c1", mode="ask")
    eng.pick(plan.id, "c1", "c1_0")   # the clipped one
    assert store.load(plan.id).cue("c1").chosen().clipped_samples > 0
    res = fix_plan(eng, plan.id, render_cue=_no_render)
    assert [f["cue_id"] for f in res["fixed"]] == ["c1"] and res["fixed"][0]["rule"] == "clipping"
    assert store.load(plan.id).cue("c1").chosen().clipped_samples == 0 and res["remaining"] == []


def test_fix_pushes_following_narration_later_when_a_line_overruns(tmp_path):
    store = PlanStore(tmp_path)
    plan = store.create("v.mp4", 24.0, 20.0)
    plan.cues = [Cue(id="v1", track="dialogue", kind="narration", text="aaa", t_in=1.0), Cue(id="v2", track="dialogue", kind="narration", text="bbb", t_in=3.0),
                 Cue(id="v3", track="dialogue", kind="narration", text="ccc", t_in=6.0)]
    store.save(plan)
    eng = AudioEngine(store, [Fake([(0.5, 4.0)])])
    for cid in ("v1", "v2", "v3"):
        eng.source_cue(plan.id, cid)   # each line is 4 s long: v1 (1-5) overruns v2 (3), v2 (3-7) overruns v3 (6)
    res = fix_plan(eng, plan.id, render_cue=_no_render)
    after = {c.id: c.t_in for c in store.load(plan.id).cues}
    assert after["v1"] == 1.0 and after["v2"] >= 5.0 - 1e-6 and after["v3"] >= after["v2"] + 4.0 - 0.15 - 1e-6
    assert {f["rule"] for f in res["fixed"]} == {"narration_overrun"} and res["remaining"] == []


def test_fix_reports_what_it_could_not_fix(tmp_path):
    store = PlanStore(tmp_path)
    plan = store.create("v.mp4", 24.0, 6.0)
    plan.cues = [Cue(id="v1", track="dialogue", kind="narration", text="aaa", t_in=3.0)]
    store.save(plan)
    eng = AudioEngine(store, [Fake([(0.5, 4.0)])])
    eng.source_cue(plan.id, "v1")   # 3 + 4 = 7 s: past the 6 s video, and nothing can move it earlier
    res = fix_plan(eng, plan.id, render_cue=_no_render)
    assert res["fixed"] == [] and [f["rule"] for f in res["remaining"]] == ["narration_past_end"]
