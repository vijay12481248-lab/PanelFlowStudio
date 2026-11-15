import re
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import Candidate, Cue, PlanStore, Provenance
from engine.audio.studio.sources.base import Availability
from engine.audio.studio.sources.openverse import OpenverseProvider

SR = 48000


def _wav(path: Path, amp=0.5, dur=1.0):
    n = int(SR * dur)
    x = np.zeros(n, dtype=np.float32)
    x[2400:4800] = amp * np.sin(2 * np.pi * 800 * np.arange(2400) / SR)
    sf.write(str(path), x, SR)
    return str(path)


class Fake:
    def __init__(self, name, specs, ok=True, reason=None):
        self.name, self.specs, self.ok, self.reason, self.calls = name, specs, ok, reason, []

    def availability(self):
        return Availability(self.ok, self.reason)

    def find(self, cue, out_dir, plan, limit=3):
        self.calls.append((cue.id, limit))
        out = []
        for i, (amp, dur) in enumerate(self.specs[:limit]):
            out.append(Candidate(id=f"{self.name}{i}", path=_wav(Path(out_dir) / f"{self.name}{i}.wav", amp, dur), provider=self.name,
                                 provenance=Provenance(source=self.name, licence="CC0")))
        return out


@pytest.fixture
def rig(tmp_path):
    store = PlanStore(tmp_path)
    plan = store.create("v.mp4", 24.0, 10.0)
    plan.cues = [Cue(id="c1", track="sfx", kind="impact", intent="door", hit_t=1.0),
                 Cue(id="m1", track="music", kind="music", intent="calm", t_in=0, t_out=8.0)]
    return store, store.save(plan)


def test_auto_picks_and_marks_ready(rig):
    store, plan = rig
    eng = AudioEngine(store, [Fake("a", [(0.5, 1.0)])])
    out = eng.source_cue(plan.id, "c1")
    c = out.cue("c1")
    assert c.status == "ready" and c.chosen_take and c.chosen().onset_s == pytest.approx(0.05, abs=0.01)
    assert c.candidates == [] and store.load(plan.id).cue("c1").status == "ready"


def test_ask_mode_leaves_needs_pick_then_pick_makes_ready(rig):
    store, plan = rig
    eng = AudioEngine(store, [Fake("a", [(0.5, 1.0), (0.4, 1.0), (0.3, 1.0)])])
    out = eng.source_cue(plan.id, "c1", mode="ask")
    c = out.cue("c1")
    assert c.status == "needs_pick" and len(c.candidates) == 3 and c.chosen_take is None
    done = eng.pick(plan.id, "c1", "a1")
    assert done.cue("c1").status == "ready" and done.cue("c1").chosen_take == "a1" and done.cue("c1").candidates == []


def test_music_cue_never_asks_openverse(rig):
    store, plan = rig

    def boom(url):
        raise AssertionError("Openverse must not be called for music")
    eng = AudioEngine(store, [OpenverseProvider(boom), Fake("ace-step", [(0.5, 8.0)])])
    out = eng.source_cue(plan.id, "m1")
    assert out.cue("m1").status == "ready"


def test_all_providers_empty_fails_with_reasons(rig):
    store, plan = rig
    eng = AudioEngine(store, [Fake("openverse", [], ok=False, reason="Openverse unreachable: x"), Fake("synth", [])])
    c = eng.source_cue(plan.id, "c1").cue("c1")
    assert c.status == "failed" and "Openverse unreachable: x" in c.reason and "synth" in c.reason


def test_cue_mode_overrides_plan_mode(rig):
    store, plan = rig
    plan.cues[0].mode = "ask"
    store.save(plan)
    eng = AudioEngine(store, [Fake("a", [(0.5, 1.0), (0.4, 1.0)])])
    assert eng.source_cue(plan.id, "c1").cue("c1").status == "needs_pick"


def test_auto_never_takes_clipped_candidate_if_clean_one_exists(rig):
    store, plan = rig
    eng = AudioEngine(store, [Fake("a", [(1.0, 0.5), (0.5, 1.0)])])
    assert eng.source_cue(plan.id, "c1").cue("c1").chosen_take == "a1"


def test_pick_unknown_candidate_raises(rig):
    store, plan = rig
    eng = AudioEngine(store, [Fake("a", [(0.5, 1.0)])])
    eng.source_cue(plan.id, "c1", mode="ask")
    with pytest.raises(KeyError):
        eng.pick(plan.id, "c1", "nope")


def test_limit_is_one_for_auto_music_and_three_otherwise(rig):
    store, plan = rig
    f = Fake("ace-step", [(0.5, 8.0)] * 3)
    eng = AudioEngine(store, [f])
    eng.source_cue(plan.id, "m1")
    eng.source_cue(plan.id, "c1", mode="ask")
    assert f.calls == [("m1", 1), ("c1", 3)]


def test_only_engine_calls_providers():
    root = Path(__file__).resolve().parents[3]
    files = [p for p in (root / "engine/audio/studio").glob("*.py") if p.name != "engine.py"]
    files += [root / "engine/api/routers/audio_studio.py", root / "engine/mcp/tools/audio_studio_tools.py"]
    pat = re.compile(r"\bproviders?\b[^\n]*\.find\(|\bp\.find\(")
    assert [f.name for f in files if f.exists() and pat.search(f.read_text(encoding="utf-8"))] == []


def test_auto_prefers_a_clip_no_other_cue_already_uses(rig):
    store, plan = rig
    plan.cues = [Cue(id=f"k{i}", track="sfx", kind="impact", intent="door", hit_t=1.0 + i) for i in range(3)]
    store.save(plan)
    eng = AudioEngine(store, [Fake("a", [(0.5, 1.0), (0.5, 1.1), (0.5, 1.2)])])
    for i in range(3):
        eng.source_cue(plan.id, f"k{i}")
    chosen = [c.chosen_take for c in store.load(plan.id).cues]
    assert sorted(chosen) == ["a0", "a1", "a2"]
