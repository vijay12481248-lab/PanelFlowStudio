import io
from types import SimpleNamespace

import asyncio

from PIL import Image

from engine.original.anatomy.loop import SEED_STEP
from engine.original.anatomy.text_check import generate_text_free, has_stray_text, top_band


def _png(w=64, h=128):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, "PNG")
    return buf.getvalue()


class Engine:
    def __init__(self):
        self.seeds = []

    def generate(self, prompt, negative, width, height, seed, prefix, workflow_id=None):
        self.seeds.append(seed)
        self.workflows = getattr(self, "workflows", []) + [workflow_id]
        return SimpleNamespace(png=_png(), seed=seed)


class Judge:
    """Answers the whole picture and the top band in turn from a script of (whole, band) replies per picture."""

    name = "fake"

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    async def ask(self, image, prompt):
        reply = self.replies[self.calls // 2][self.calls % 2]
        self.calls += 1
        return reply


def test_top_band_is_the_upscaled_top_of_the_picture():
    out = Image.open(io.BytesIO(top_band(_png(64, 128), share=0.5)))
    assert max(out.size) == 1280 and out.width == out.height  # 64x64 top half, scaled up


def test_text_on_either_view_counts_and_unclear_is_unverified():
    run = lambda replies: asyncio.run(has_stray_text(Judge([replies]), _png()))
    assert run(["No. nothing", "Yes. a title"]) is True
    assert run(["No.", "No."]) is False
    assert run(["No.", "maybe"]) is None


def test_redraws_with_new_seeds_until_the_picture_has_no_text():
    eng, judge = Engine(), Judge([("yes", "no"), ("no", "yes"), ("no", "no")])
    got = generate_text_free(eng, judge, prompt="a boss runs, no text, no letters", width=64, height=128, seed=5, prefix="p", workflow_id="hidream_i1_fast")
    assert got.status == "clean" and eng.seeds == [5, 5 + SEED_STEP, 5 + 2 * SEED_STEP] and got.seed == 5 + 2 * SEED_STEP
    assert [a["text"] for a in got.attempts] == [True, True, False]


def test_every_attempt_with_text_delivers_the_last_picture_as_best_effort():
    eng, judge = Engine(), Judge([("yes", "yes")] * 2)
    got = generate_text_free(eng, judge, prompt="x", width=64, height=128, seed=1, prefix="p", workflow_id="w", max_attempts=2)
    assert got.status == "best_effort" and len(eng.seeds) == 2


def test_an_unreadable_judge_answer_is_delivered_unverified_without_a_redraw():
    eng, judge = Engine(), Judge([("hmm", "hmm")])
    got = generate_text_free(eng, judge, prompt="x", width=64, height=128, seed=1, prefix="p", workflow_id="w")
    assert got.status == "unverified" and eng.seeds == [1]


def test_a_prompt_that_asks_for_writing_is_not_judged():
    eng, judge = Engine(), Judge([])
    got = generate_text_free(eng, judge, prompt="a sign that says OPEN", width=64, height=128, seed=1, prefix="p", workflow_id="w")
    assert got.status == "unverified" and judge.calls == 0 and eng.seeds == [1]


def test_hooks_run_before_each_draw_and_each_judge_call():
    log = []
    eng, judge = Engine(), Judge([("yes", "no"), ("no", "no")])
    generate_text_free(eng, judge, prompt="x", width=64, height=128, seed=1, prefix="p", workflow_id="w", before_draw=lambda: log.append("draw"),
                       before_judge=lambda: log.append("judge"))
    assert log == ["draw", "judge", "draw", "judge"]


def test_from_the_third_attempt_on_the_fallback_model_draws():
    eng, judge = Engine(), Judge([("yes", "yes")] * 3 + [("no", "no")])
    got = generate_text_free(eng, judge, prompt="x", width=64, height=128, seed=1, prefix="p", workflow_id="hidream", fallback_workflow_id="zimage", fallback_after=2)
    assert eng.workflows == ["hidream", "hidream", "zimage", "zimage"] and got.status == "clean" and got.attempts[-1]["workflow"] == "zimage"
