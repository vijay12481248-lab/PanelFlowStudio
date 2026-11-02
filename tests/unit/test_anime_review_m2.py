import asyncio

import numpy as np

from engine.anime.review import clips, understanding
from engine.anime.review.models import Beat, EpisodeAnalysis, Shot


def _analysis(dur=1200.0):
    n = int(dur // 4)
    return EpisodeAnalysis(duration_sec=dur, shots=[Shot(idx=i, start=i * 4.0, end=(i + 1) * 4.0) for i in range(n)])


def _beats(k=10):
    kinds = ["opening"] + ["highlight", "funny", "weak", "smooth"] * 3
    return [Beat(id=f"b{i+1:02d}", start=60.0 * i + 10, end=60.0 * i + 40, kind=kinds[i % len(kinds)], label=f"l{i}", why="w")
            for i in range(k)]


def test_clips_respect_caps_and_budget():
    a = _analysis()
    plan = clips.select_clips(a, _beats(14), target_video_sec=300.0)
    assert plan.budget_sec == 75.0  # 25% of 300s beats 20% of 1200s
    assert plan.total_sec <= plan.budget_sec + 1e-6
    assert all(c.duration <= clips.MAX_CLIP_SEC for c in plan.clips)
    assert plan.dropped_beats  # the budget cannot hold every beat
    assert "b01" not in plan.dropped_beats  # opening is essential


def test_clips_never_whole_episode_even_with_huge_target():
    plan = clips.select_clips(_analysis(), _beats(), target_video_sec=10**6, clip_sec=500)
    assert plan.total_sec <= 0.2 * 1200 and all(c.duration <= 20 for c in plan.clips)


def test_loud_beat_prefers_energetic_shot():
    a = _analysis(100)
    rms = np.zeros(100)
    rms[32:36] = 1.0
    b = [Beat(id="b01", start=20, end=40, kind="highlight", label="x", why="y")]
    plan = clips.select_clips(a, b, 600, rms, clip_sec=4)
    assert plan.clips[0].start == 32.0


def test_clean_beats_drops_garbage():
    raw = [understanding._BeatOut(start=5, end=5.2, kind="highlight", label="a", why="b"),
           understanding._BeatOut(start=-3, end=900, kind="Funny", label="c", why="d"),
           understanding._BeatOut(start=10, end=20, kind="boring", label="e", why="f")]
    out = understanding.clean_beats(raw, 100.0)
    assert [(b.start, b.end, b.kind) for b in out] == [(0.0, 100.0, "funny")]


def test_understand_uses_provider():
    class P:
        async def generate_structured(self, prompt, model, **kw):
            assert "Timed transcript" in prompt
            return model(summary=" s ", characters=["A"], beats=[
                {"start": 1, "end": 9, "kind": "opening", "label": "l", "why": "w"}])
    u = asyncio.run(understanding.understand(_analysis(60), "T", P()))
    assert u.summary == "s" and u.beats[0].id == "b01"
