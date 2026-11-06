"""Phase 5: the generic refinement loop, with scripted generate / review / repair callables (no GPU, no model)."""
import asyncio
import io
import itertools
import json

import pytest
from PIL import Image

from engine.original import refine as rf
from engine.original import review as review_mod
from engine.original.models import ItemVerdict, Review
from engine.original.planner import Budget, PlanTarget


def png(n, size=32):
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (n % 256, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def item(text="x", *, ok=False, critical=True, category="narration", defect="", bbox=None, local=False):
    v = ItemVerdict(item=text, critical=critical, verdict="shown" if ok else "missing", confidence=0.9, vision="yes" if ok else "no",
                    description_says=ok, category=category, defect_type=defect, passed=ok)
    if bbox:
        v.bbox, v.bbox_source = bbox, "vlm"
    v.repairable_locally = local
    return v


PASS = lambda: Review(items=[item(ok=True)], score=0.95, confidence=0.9, decision="accept")  # noqa: E731
FAIL = lambda s=0.4: Review(items=[item("a lamp on the table")], score=s, confidence=0.8, decision="regenerate")  # noqa: E731
HAND = lambda: Review(items=[item("natural hands", category="anatomy", defect="distorted_digits", bbox=[0.4, 0.4, 0.6, 0.6], local=True)],  # noqa: E731
                      score=0.7, confidence=0.8, decision="regenerate")


class Harness:
    def __init__(self, reviews, repair=None, repair_reviews=()):
        self.reviews, self.repair_reviews = iter(reviews), iter(repair_reviews)
        self.plans, self.iters, self.n = [], [], itertools.count(1)
        self.repair_calls = []
        self._repair = repair

    def generate(self, attempt, plan):
        self.plans.append(plan)
        return png(next(self.n)), {"seed": attempt}

    def review(self, data):
        out = next(self.repair_reviews if data[-1:] == b"R" else self.reviews)
        if isinstance(out, Exception):
            raise out
        return out

    def record(self, data, **meta):
        e = {"n": len(self.iters) + 1, "sha256": rf.sha256_hex(data), **meta}
        self.iters.append(e)
        return e

    def repair(self, data, rev, plan):
        self.repair_calls.append(plan)
        return self._repair(data, rev, plan)

    def run(self, **kw):
        return rf.refine_image(generate=self.generate, review=self.review, record=self.record, repair=self.repair if self._repair else None, **kw)


def test_a_passing_first_picture_stops_after_one_generation():
    h = Harness([PASS()])
    r = h.run()
    assert (r.status, r.generations, r.selected) == ("accept", 1, 1) and r.png == png(1) and h.plans == [None]


def test_a_failing_picture_is_redrawn_with_what_was_missing_until_one_passes():
    h = Harness([FAIL(), FAIL(0.5), PASS()])
    r = h.run()
    assert (r.status, r.generations, r.selected) == ("accept", 3, 3)
    assert h.plans[1].emphasis == ["a lamp on the table"] and h.plans[1].new_seed and not h.plans[1].widen_frame
    assert h.plans[2].widen_frame and h.plans[2].simplify  # the same ladder as the story loop
    assert [i["kind"] for i in h.iters] == ["generate"] * 3 and all(i["review"] for i in h.iters)


def test_a_picture_that_never_passes_is_needs_review_with_the_best_candidate_kept():
    h = Harness([FAIL(0.3), FAIL(0.6), FAIL(0.5)])
    r = h.run()
    assert (r.status, r.generations, r.selected) == ("needs_review", 3, 2) and r.png == png(2)


def test_a_located_defect_is_repaired_in_place_and_the_repair_is_kept_when_it_helps():
    h = Harness([HAND()], repair=lambda d, rev, plan: (d + b"R", {"seed": 9}), repair_reviews=[PASS()])
    r = h.run()
    assert r.status == "accept_low" and r.repaired and r.generations == 1 and len(h.repair_calls) == 1  # accepted, but flagged for a human glance
    rep = h.iters[1]
    assert rep["kind"] == "repair" and rep["parent"] == 1 and rep["kept"] is True and r.selected == 2
    assert h.repair_calls[0].targets[0].bbox == [0.4, 0.4, 0.6, 0.6]


def test_a_repair_that_does_not_help_is_kept_on_disk_but_never_selected():
    worse = Review(items=[item("natural hands", category="anatomy", defect="distorted_digits")], score=0.3, confidence=0.8, decision="regenerate")
    h = Harness([HAND(), PASS()], repair=lambda d, rev, plan: (d + b"R", {}), repair_reviews=[worse])
    r = h.run()
    assert h.iters[1]["kind"] == "repair" and h.iters[1]["kept"] is False
    assert r.status == "accept" and r.selected == 3 and len(h.repair_calls) == 1  # one repair per generation, then a fresh generation


def test_a_repair_that_cannot_be_made_falls_back_to_a_redraw_without_looping():
    h = Harness([HAND(), PASS()], repair=lambda d, rev, plan: None)
    r = h.run()
    assert len(h.repair_calls) == 1 and r.generations == 2 and r.status == "accept"


def test_a_reviewer_that_fails_leaves_the_picture_unverified_and_burns_no_attempts():
    h = Harness([RuntimeError("model down")])
    r = h.run()
    assert (r.status, r.generations, r.review) == ("unverified", 1, None) and h.iters[0]["review"] is None


def test_cancel_stops_the_loop():
    with pytest.raises(RuntimeError, match="cancelled"):
        Harness([PASS()]).run(is_cancelled=lambda: True)


def test_mask_is_built_only_from_reported_boxes():
    t = PlanTarget(item="x", status="missing", correction="c", bbox=[0.25, 0.25, 0.5, 0.5])
    assert rf.mask_from_boxes((100, 100), [PlanTarget(item="x", status="missing", correction="c")]) is None
    m = Image.open(io.BytesIO(rf.mask_from_boxes((100, 100), [t], padding=0, blur=0))).convert("L")
    assert m.getpixel((35, 35)) == 255 and m.getpixel((5, 5)) == 0 and m.size == (100, 100)


def test_repair_prompt_describes_the_result_not_an_instruction():
    t = [PlanTarget(item="the sword is in his right hand", status="incorrect", correction="change so that: ..."),
         PlanTarget(item="hands", status="missing", defect_type="distorted_digits", correction="redraw the hand with the correct number of fingers")]
    p = rf.repair_prompt("A warrior in a forest.", t)
    assert p.startswith("A warrior in a forest.") and "the sword is in his right hand; redraw the hand" in p and "change so that" not in p


def test_prompt_mode_loop_generates_reviews_and_keeps_every_candidate(tmp_path, monkeypatch):
    reviews = iter([FAIL(), PASS()])

    async def fake_eval(provider, image, prompt, **kw):
        return next(reviews)

    monkeypatch.setattr(review_mod, "evaluate_prompt_image", fake_eval)
    seen = []

    class Engine:
        def generate(self, prompt, negative, w, h, seed, prefix, **kw):
            seen.append((prompt, seed))
            return type("A", (), {"png": png(len(seen)), "width": w, "height": h, "workflow_id": "qwen_image_21", "workflow_sha256": "s", "prompt_id": "p"})()

    r = rf.refine_prompt_image(Engine(), object(), "a lamp on a table", "", 32, 32, ws=tmp_path, key="img1", seed=100)
    assert (r.status, r.generations, r.selected) == ("accept", 2, 2)
    assert seen[0] == ("a lamp on a table", 100) and seen[1][0].startswith("Most important: a lamp on the table.") and seen[1][1] == 100 + 7919
    assert [i["file"] for i in r.iterations] == [f"panels/_candidates/img1/c00{n}.png" for n in (1, 2)]
    assert all((tmp_path / i["file"]).exists() for i in r.iterations) and r.iterations[0]["workflow"] == "qwen_image_21"
    assert not (tmp_path / "_try_img1.png").exists()


def test_prompt_mode_repair_redraws_the_box_and_splices_the_original_back(tmp_path, monkeypatch):
    located = Review(items=[item("the sword is in his right hand", bbox=[0.5, 0.5, 0.75, 0.75], local=True)], score=0.7, confidence=0.8, decision="regenerate")
    located.items[0].status = "incorrect"
    reviews = iter([located, PASS()])

    async def fake_eval(provider, image, prompt, **kw):
        return next(reviews)

    monkeypatch.setattr(review_mod, "evaluate_prompt_image", fake_eval)

    class Engine:
        def generate(self, prompt, negative, w, h, seed, prefix, **kw):
            return type("A", (), {"png": png(1, 160), "width": w, "height": h, "workflow_id": "w", "workflow_sha256": "s", "prompt_id": "p"})()

    class Editor:
        qwen_inpaint_wf = object()
        calls = []

        def inpaint_qwen(self, base, mask, prompt, neg, seed, **kw):
            self.calls.append(prompt)
            buf = io.BytesIO()
            Image.new("RGB", (160, 160), "blue").save(buf, "PNG")
            return buf.getvalue()

    class Eyes:  # the vision model answering the close-up check of the repaired area
        crops = []

        async def analyze_vision(self, image, prompt, **kw):
            Eyes.crops.append(Image.open(io.BytesIO(image)).size)
            return json.dumps({"answers": [{"n": 1, "answer": "yes", "evidence": "sword in the right hand"}]})

    ed = Editor()
    r = rf.refine_prompt_image(Engine(), Eyes(), "a warrior holding a sword", "", 160, 160, ws=tmp_path, key="k", seed=1, editor=ed)
    assert r.status == "accept_low" and r.repaired and [i["kind"] for i in r.iterations] == ["generate", "repair"] and r.iterations[1]["kept"] is True
    assert "The redrawn area must show: the sword is in his right hand." in ed.calls[0]
    out = Image.open(io.BytesIO(r.png)).convert("RGB")
    assert out.getpixel((1, 1)) == (1, 0, 0) and out.getpixel((100, 100)) == (0, 0, 255)  # original outside the box, redraw inside
    assert (tmp_path / r.iterations[1]["mask"]).exists()
    assert r.iterations[1]["crop_check"][0]["answer"] == "yes" and max(Eyes.crops[0]) >= 448  # looked at up close, enlarged


def test_a_repair_that_fails_the_close_up_check_is_not_kept_even_if_the_whole_picture_passes():
    h = Harness([HAND(), PASS()], repair=lambda d, rev, plan: (d + b"R", {}), repair_reviews=[PASS()])
    r = h.run(verify=lambda png, plan: (False, [{"item": "natural hands", "answer": "partly", "evidence": "blurred"}]))
    assert h.iters[1]["kind"] == "repair" and h.iters[1]["kept"] is False and h.iters[1]["crop_check"][0]["answer"] == "partly"
    assert r.selected == 3  # a fresh generation replaced it; the unkept repair is only on disk for comparison


def test_a_verifier_that_crashes_does_not_keep_the_repair():
    def boom(png, plan):
        raise RuntimeError("model down")

    h = Harness([HAND(), PASS()], repair=lambda d, rev, plan: (d + b"R", {}), repair_reviews=[PASS()])
    h.run(verify=boom)
    assert h.iters[1]["kept"] is False and "model down" in h.iters[1]["crop_check"][0]["error"]


def _mask(targets, protect=(), size=(200, 100), **kw):
    return Image.open(io.BytesIO(rf.mask_from_boxes(size, targets, protect, blur=0, **kw))).convert("L")


def test_a_small_passing_detail_inside_the_target_box_is_cut_out_of_the_mask():
    target = PlanTarget(item="collar", status="incorrect", correction="c", bbox=[0.5, 0.4, 0.8, 0.7])
    paw = [0.5, 0.4, 0.58, 0.55]  # touches the target's corner, a fraction of its size
    m = _mask([target], [paw])
    assert m.getpixel((105, 45)) == 0  # inside the paw: original pixels stay
    assert m.getpixel((150, 60)) == 255  # inside the target, outside the paw: redrawn


def test_a_large_passing_box_is_never_cut_out_so_the_mask_cannot_vanish():
    target = PlanTarget(item="collar", status="incorrect", correction="c", bbox=[0.5, 0.4, 0.8, 0.7])
    whole_cat = [0.3, 0.1, 0.95, 1.0]
    assert _mask([target], [whole_cat]).getpixel((150, 60)) == 255
    assert _mask([target], [[0.0, 0.0, 0.1, 0.1]]).getpixel((150, 60)) == 255  # far away: irrelevant


def test_padding_follows_the_box_size_not_a_fixed_margin():
    small = PlanTarget(item="x", status="incorrect", correction="c", bbox=[0.5, 0.5, 0.55, 0.6])  # 10 x 10 px on 200 x 100
    m = _mask([small])
    assert m.getpixel((97, 47)) == 255 and m.getpixel((92, 42)) == 0  # a 6 px margin around a 10 px box (the floor), not a fixed 12 or 48
    assert _mask([small], padding=12).getpixel((92, 42)) == 255  # an explicit padding still wins


def test_verify_targets_asks_about_each_located_target_and_needs_a_plain_yes():
    class Eyes:
        def __init__(self, answer):
            self.answer, self.calls = answer, 0

        async def analyze_vision(self, image, prompt, **kw):
            self.calls += 1
            return json.dumps({"answers": [{"n": 1, "answer": self.answer, "evidence": "e"}]})

    t = [PlanTarget(item="a", status="incorrect", correction="c", bbox=[0.2, 0.2, 0.4, 0.4]),
         PlanTarget(item="b", status="missing", correction="c")]  # no box: nothing to look at
    ok, detail = rf.verify_targets(Eyes("yes"), png(1, 100), t)
    assert ok and [d["item"] for d in detail] == ["a"]
    assert not rf.verify_targets(Eyes("partly"), png(1, 100), t)[0]
    assert rf.verify_targets(Eyes("no"), png(1, 100), [t[1]]) == (True, [])


def test_padding_grows_with_the_box_but_is_capped():
    big = PlanTarget(item="x", status="incorrect", correction="c", bbox=[0.1, 0.1, 0.9, 0.9])
    m = _mask([big], size=(1000, 1000))
    assert m.getpixel((100 - 45, 500)) == 255 and m.getpixel((100 - 55, 500)) == 0  # capped at 48 px
    mid = PlanTarget(item="x", status="incorrect", correction="c", bbox=[0.5, 0.5, 0.6, 0.6])  # 100 px box -> 15 px
    m2 = _mask([mid], size=(1000, 1000))
    assert m2.getpixel((500 - 13, 550)) == 255 and m2.getpixel((500 - 18, 550)) == 0
