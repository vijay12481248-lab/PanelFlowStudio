"""Phase 1 of the image-refinement plan: evidence-grade review of any image against any prompt (no GPU, fake provider)."""
import asyncio
import json

import pytest

from engine.original import review as rv
from engine.original.models import ItemVerdict


def test_negated_list_does_not_flag_a_clean_picture():
    # real evidence text from a clean panel that the old comma split flagged as polycephaly
    ev = "The illustration shows one head for both characters. There are no duplicate heads, fused faces, or polycephaly present."
    assert not rv._has_defect_keyword(ev, "polycephaly")
    assert not rv._has_defect_keyword("No extra fingers, fused digits or polydactyly visible.", "distorted_digits")


def test_negation_does_not_hide_a_second_clause_defect():
    assert rv._has_defect_keyword("There is no sword, and the hand has six fingers.", "distorted_digits")
    assert rv._has_defect_keyword("No problems with the face, but the girl has two heads.", "polycephaly")
    assert rv._has_defect_keyword("The girl has two heads.", "polycephaly")


@pytest.mark.parametrize("raw,expected", [
    ([100, 100, 400, 600], [0.1, 0.1, 0.4, 0.6]),
    ([0, 0, 1000, 1000], None),  # the whole picture is not a location
    ([500, 500, 500, 600], None),  # empty
    ([600, 100, 400, 300], None),  # inverted
    ([-5, 0, 100, 100], None),
    ([1, 2, 3], None),
    ([], None),
    (None, None),
    (["a", "b", "c", "d"], None),
    ([10, 10, 12, 12], None),  # a speck
])
def test_valid_box(raw, expected):
    assert rv._valid_box(raw) == expected


def test_clean_prompt_requirements_drops_negations_duplicates_and_invented_requirements():
    prompt = "A warrior in golden armor holding a sword in his right hand, in a forest"
    reqs = [rv._PromptReq(text="a warrior wears golden armor", kind="clothing"),
            rv._PromptReq(text="A warrior wears golden armor", kind="clothing"),
            rv._PromptReq(text="there is no visible castle", kind="environment"),
            rv._PromptReq(text="a dragon circles overhead", kind="object"),
            rv._PromptReq(text="the sword is in his right hand", kind="nonsense")]
    out = rv.clean_prompt_requirements(reqs, prompt)
    assert [c.text for c in out] == ["a warrior wears golden armor", "the sword is in his right hand"]
    assert out[1].kind == "object"  # unknown kinds fall back, they are not trusted


class FakeProvider:
    def __init__(self, grounded, reqs, anatomy_no_on=None, locate_box=None, stated=None):
        self.grounded, self.reqs, self.anatomy_no_on, self.locate_box, self.stated = grounded, reqs, anatomy_no_on, locate_box, stated
        self.locate_calls = 0

    async def generate_structured(self, prompt, model, **kw):
        if model is rv._PromptReqs:
            return model(requirements=self.reqs)
        if model is rv._DescJudge:
            return model(stated=self.stated)
        raise AssertionError(model)

    async def analyze_vision(self, image, prompt, **kw):
        title = (kw.get("format_schema") or {}).get("title")
        if title == "_GroundedList":
            return json.dumps({"items": self.grounded})
        if title == "_Box":
            self.locate_calls += 1
            return json.dumps({"bbox_2d": self.locate_box or []})
        if title == "_VQA":
            n_questions = prompt.count("Is this true of the picture")
            return json.dumps({"answers": [
                {"n": n, "answer": "no" if n == self.anatomy_no_on else "yes",
                 "evidence": "two heads on one body" if n == self.anatomy_no_on else "normal"} for n in range(1, n_questions + 1)]})
        return "A warrior stands in a forest."


PROMPT = "A warrior in golden armor holding a sword in his right hand in a forest wearing a red cape, birds chirp"
REQS = [rv._PromptReq(text="a warrior wears golden armor", kind="clothing"),
        rv._PromptReq(text="the sword is in his right hand", kind="placement"),
        rv._PromptReq(text="the background is a forest", kind="environment"),
        rv._PromptReq(text="birds chirp", kind="object", critical=False),
        rv._PromptReq(text="the warrior wears a red cape", kind="clothing")]
GROUNDED = [
    {"n": 1, "status": "correct", "evidence": "golden armour", "bbox_1000": [100, 100, 400, 600]},
    {"n": 2, "status": "incorrect", "evidence": "sword is in the left hand", "bbox_1000": [600, 300, 700, 500]},
    {"n": 3, "status": "correct", "evidence": "trees", "bbox_1000": []},
    {"n": 4, "status": "not_verifiable", "evidence": "sound", "bbox_1000": []},
    {"n": 5, "status": "missing", "evidence": "no cape", "bbox_1000": [10, 10, 50, 50]},
]


def _run(provider, tmp_path, **kw):
    img = tmp_path / "x.png"
    img.write_bytes(b"png")
    return asyncio.run(rv.evaluate_prompt_image(provider, img, PROMPT, **kw))


def test_prompt_review_reports_status_evidence_box_severity_and_repairability(tmp_path):
    # witness B (the description judge) agrees with witness A on every checked item except that it never saw the cape
    review = _run(FakeProvider(GROUNDED, REQS, stated=[True, False, True, False]), tmp_path)
    by = {i.item: i for i in review.items if i.category == "narration"}

    ok = by["a warrior wears golden armor"]
    assert (ok.status, ok.passed, ok.severity) == ("correct", True, "")
    assert ok.bbox == [0.1, 0.1, 0.4, 0.6] and ok.bbox_source == "vlm"

    wrong = by["the sword is in his right hand"]
    assert wrong.status == "incorrect" and not wrong.passed and wrong.severity == "critical"
    assert wrong.bbox == [0.6, 0.3, 0.7, 0.5] and wrong.repairable_locally  # existing but wrong, located, a local kind

    absent = by["the warrior wears a red cape"]
    assert absent.status == "missing" and absent.bbox is None and not absent.repairable_locally  # a box for an absent thing is a guess

    assert by["the background is a forest"].bbox is None  # [] from the model stays None, nothing is invented
    assert review.unverifiable == ["birds chirp"]
    assert "birds chirp" not in by  # not scored, and not counted as shown or missing
    assert any("not visually verifiable" in r for r in review.reasons)
    assert review.decision == "regenerate"


def test_unparseable_witness_answer_is_uncertain_not_a_pass(tmp_path):
    class Garbage(FakeProvider):
        async def analyze_vision(self, image, prompt, **kw):
            if (kw.get("format_schema") or {}).get("title") == "_GroundedList":
                return "not json"
            return await super().analyze_vision(image, prompt, **kw)

    review = _run(Garbage(GROUNDED, REQS[:1], stated=[True]), tmp_path, audit_gates=False)
    item = review.items[0]
    assert item.status == "uncertain" and not item.passed and item.bbox is None


def test_anatomy_defect_gets_a_model_box_or_none(tmp_path):
    p = FakeProvider(GROUNDED[:1], REQS[:1], anatomy_no_on=1, locate_box=[200, 50, 400, 300], stated=[True])
    review = _run(p, tmp_path)
    bad = [i for i in review.items if i.category == "anatomy" and not i.passed]
    assert [i.defect_type for i in bad] == ["polycephaly"]
    assert bad[0].bbox == [0.2, 0.05, 0.4, 0.3] and bad[0].bbox_source == "vlm" and bad[0].repairable_locally
    mask = rv.extract_defect_mask((1000, 500), review)
    assert mask is not None  # the repair mask is built around the reported box (existing consumer, unchanged)

    nothing = _run(FakeProvider(GROUNDED[:1], REQS[:1], anatomy_no_on=1, locate_box=[0, 0, 1000, 1000], stated=[True]), tmp_path)
    still = [i for i in nothing.items if i.category == "anatomy" and not i.passed][0]
    assert still.bbox is None and not still.repairable_locally  # an unusable box is dropped, the heuristic region stays the fallback


def test_contact_check_on_an_object_that_is_not_in_the_picture_is_never_boxed():
    # seen on a real panel: "the sword is held" failed because there was no sword, and the locate step boxed the cat's paw instead
    review = rv.Review(items=[ItemVerdict(item="the lamp is physically held with continuous grasp contact", critical=True, verdict="missing",
                                          confidence=0.9, vision="no", description_says=False, category="spatial_contact",
                                          defect_type="disconnected_interaction", evidence="There is no lamp visible in the image.")],
                       score=0.0, confidence=0.9, decision="regenerate")
    p = FakeProvider([], [], locate_box=[650, 540, 720, 630])
    assert asyncio.run(rv.locate_failed_items(p, "x.png", review)) == 0
    assert p.locate_calls == 0 and review.items[0].bbox is None and not review.items[0].repairable_locally


def test_old_items_derive_a_status():
    assert ItemVerdict(item="x", critical=True, verdict="shown", confidence=0.9, vision="yes", description_says=True).status == "correct"
    assert ItemVerdict(item="x", critical=True, verdict="partial", confidence=0.5, vision="partly", description_says=True).status == "uncertain"
    assert ItemVerdict(item="x", critical=True, verdict="missing", confidence=0.9, vision="no", description_says=False).status == "missing"


@pytest.mark.parametrize("text", ["The scene must take place in a kitchen.", "She takes care of the plants.", "The crowd took part in the march.",
                                  "He holds control of the room."])
def test_idioms_with_a_verb_are_not_contact_checks(text):
    # seen on a real run: "the scene must take place in a kitchen" became "the place is physically held", which failed every attempt on a correct picture
    assert rv._extract_interaction_targets(caption=text) == []


def test_a_real_held_object_is_still_a_contact_check():
    assert [o for _, o in rv._extract_interaction_targets(caption="the girl holds a red mug in her right hand")] == ["red mug"]


@pytest.mark.parametrize("text,expected", [
    ("The image must show exactly seven red apples.", (7, "red apples")),
    ("two glasses on the table", (2, "glasses")),
    ("A girl holds 2 mugs", (2, "mugs")),
    ("The wall clock must display the time as exactly three o'clock.", None),  # a time, not a count
    ("She waited three minutes", None),
    ("one apple", None),
    ("a glass of water", None),
])
def test_count_expectation_only_matches_counts_of_things(text, expected):
    assert rv.count_expectation(text) == expected


def test_a_stated_number_is_checked_by_counting_not_by_recognising(tmp_path):
    class Counter(FakeProvider):
        def __init__(self, counted, *a, **kw):
            super().__init__(*a, **kw)
            self.counted, self.asked = counted, []

        async def analyze_vision(self, image, prompt, **kw):
            if (kw.get("format_schema") or {}).get("title") == "_Count":
                self.asked.append(prompt)
                return json.dumps({"count": self.counted, "evidence": "five on the left"})
            return await super().analyze_vision(image, prompt, **kw)

    reqs = [rv._PromptReq(text="exactly seven red apples are in the bowl", kind="object")]
    grounded = [{"n": 1, "status": "correct", "evidence": "exactly seven red apples", "bbox_1000": [100, 100, 500, 500]}]
    img = tmp_path / "x.png"
    img.write_bytes(b"png")
    wrong = Counter(5, grounded, reqs, stated=[True])
    review = asyncio.run(rv.evaluate_prompt_image(wrong, img, "exactly seven red apples in a bowl", audit_gates=False, locate_defects=False))
    item = review.items[0]
    assert item.status != "correct" and not item.passed and "counted 5" in item.evidence and review.decision == "regenerate"
    assert item.verdict == "missing"  # the count is evidence: the description that "states" seven does not turn it into a mere disagreement
    assert "seven" not in wrong.asked[0] and "7" not in wrong.asked[0]  # the expected number is never leaked to the counter
    right = Counter(7, grounded, reqs, stated=[True])
    assert asyncio.run(rv.evaluate_prompt_image(right, img, "exactly seven red apples in a bowl", audit_gates=False, locate_defects=False)).items[0].passed
    assert asyncio.run(rv._count_check(object(), img, "apples")) is None  # a counter that cannot answer changes nothing


class _Contact:
    def __init__(self, answer, evidence):
        self.answer, self.evidence = answer, evidence

    async def analyze_vision(self, image, prompt, **kw):
        if (kw.get("format_schema") or {}).get("title") == "_VQA":
            return json.dumps({"answers": [{"n": 1, "answer": self.answer, "evidence": self.evidence}]})
        return "A room."


@pytest.mark.parametrize("evidence", [
    "The clock is mounted on the wall and not resting on any surface.",  # seen on a real picture: a wall clock failed the audit
    "A lamp hangs from the ceiling on a cord.",
    "The apples are piled in the bowl, resting on each other.",
])
def test_mounted_hanging_and_stacked_objects_are_not_unanchored(evidence, tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"png")
    out = asyncio.run(rv._audit_spatial_contact(_Contact("no", evidence), img))
    assert [i.passed for i in out] == [True]


def test_a_really_floating_object_still_fails_the_contact_audit(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"png")
    out = asyncio.run(rv._audit_spatial_contact(_Contact("no", "A cup is floating in mid-air above the table."), img))
    assert [i.passed for i in out] == [False]
