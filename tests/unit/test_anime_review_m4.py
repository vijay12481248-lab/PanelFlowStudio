import numpy as np
import pytest

from engine.anime.review import timeline as tl
from engine.anime.review.models import Clip, ClipPlan, ReviewScript, ScriptSegment
from engine.narration.runtime import audio as rt


class FakeTts:
    def synth(self, text, voice, rate):  # 0.1 s per word of tone
        n = len(text.split())
        return (0.3 * np.sin(np.linspace(0, 400, int(rt.SR * 0.1 * n)))).astype(np.float32)


def test_audio_is_frame_aligned_and_measured(tmp_path):
    d = tl.synth_segment(FakeTts(), "one two three four five", "v", 1.0, 30.0, tmp_path / "a.wav")
    assert d == pytest.approx(tl.wav_seconds(tmp_path / "a.wav"))
    assert (d * 30) == pytest.approx(round(d * 30), abs=1e-3)  # whole frames
    assert d >= 0.5 + 0.25 + 0.16 - 0.04  # speech + pause + pads


@pytest.mark.parametrize("d,speed,hold,src_len", [(4, 1.0, 0, 4), (8, 0.8, 1.75, 5), (10, 0.8, 3.75, 5)])
def test_plan_entry(d, speed, hold, src_len):
    clip = Clip(id="c1", beat_id="b", start=10, end=15, purpose="p")
    s, ln, sp, h, _ = tl.plan_entry(d, clip, 10)
    assert (s, ln) == (10, src_len) and sp == pytest.approx(speed)
    assert h == pytest.approx(hold)


def test_plan_entry_wraps_and_flags():
    clip = Clip(id="c1", beat_id="b", start=10, end=15, purpose="p")
    s, ln, sp, h, w = tl.plan_entry(2, clip, 14.5)
    assert s == 10 and "reused" in w[0]
    assert "long freeze" in " ".join(tl.plan_entry(30, clip, 10)[4])


def test_timeline_sums_audio_exactly_and_shares_clip(tmp_path):
    plan = ClipPlan(clips=[Clip(id="c01", beat_id="b", start=0, end=10, purpose="p")], total_sec=10, budget_sec=20)
    sc = ReviewScript(title_hook="t", rating=7, segments=[ScriptSegment(id=f"s{i}", clip_id="c01", role="recap", text="x " * 15) for i in range(3)])
    t = tl.voice_script(sc, plan, tmp_path, tts=FakeTts())
    assert t.total_sec == pytest.approx(sum(e.audio_sec for e in t.entries))
    assert [e.timeline_start for e in t.entries] == pytest.approx(np.cumsum([0] + [e.audio_sec for e in t.entries[:-1]]))
    assert t.entries[1].src_start >= t.entries[0].src_start + t.entries[0].src_len - 1e-6 or "reused" in t.entries[1].warnings[0]
