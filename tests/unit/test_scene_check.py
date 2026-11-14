"""Task 5 of the scene-director plan: the picture is checked against the plan (fake vision model, no GPU)."""
import asyncio
import io
import json
import re

from PIL import Image

from engine.original import scene_check as sc
from engine.original.models import ItemVerdict, Review
from engine.original.scene_check import check_scene, spatial_failure
from engine.original.scene_prompt import plan_requirements
from scene_fixtures import fight_plan


class FakeVision:
    """Answers the reviewer's two question styles from rules and records every prompt it is asked."""

    def __init__(self, status=lambda text: "correct", box=None, count=2, error: Exception | None = None,
                 blind: dict | None = None, blind_error: bool = False):
        self.status, self.count, self.error, self.calls = status, count, error, []
        self.blind = blind if blind is not None else {"camera": "looks_up", "figures": ["striking", "blocking"]}  # what the fight_plan fixture asks for
        self.blind_error = blind_error
        self.box = box or (lambda text: [100, 200, 400, 800] if "left of the picture" in text else [600, 200, 900, 800] if "right of the picture" in text else [])

    async def analyze_vision(self, image, prompt, **kw):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        if prompt.startswith("Describe only what you see"):
            if self.blind_error:
                raise TimeoutError("blind read timed out")
            return json.dumps(self.blind)
        if prompt.startswith("How many"):
            return json.dumps({"count": self.count, "evidence": "seen"})
        lines = re.findall(r"^(\d+)\. (.*)$", prompt, flags=re.M)
        return json.dumps({"items": [{"n": int(n), "status": self.status(t), "evidence": "seen", "bbox_1000": self.box(t)} for n, t in lines]})


def picture(tmp_path):
    p = tmp_path / "pic.png"
    Image.new("RGB", (1344, 768), "grey").save(p)
    return p


def run(coro):
    return asyncio.run(coro)


def test_all_correct_is_accepted_with_single_witness_policy(tmp_path):
    review = run(check_scene(FakeVision(), picture(tmp_path), fight_plan()))
    assert review.decision == "accept" and all(i.passed for i in review.items)
    assert 0.8 <= review.confidence < 0.9  # all but the contact item have a second, blind witness


def test_wrong_actor_count_fails_even_if_vision_agrees(tmp_path):
    review = run(check_scene(FakeVision(count=3), picture(tmp_path), fight_plan()))
    bad = [i for i in review.items if not i.passed]
    assert [i.item for i in bad] == ["exactly two figures are in the picture"]
    assert bad[0].status == "incorrect" and "counted 3" in bad[0].evidence
    assert review.decision != "accept"


def test_left_actor_on_right_fails_placement(tmp_path):
    vision = FakeVision(box=lambda t: [650, 200, 950, 800] if "left of the picture" in t else [650, 200, 950, 800] if "right of the picture" in t else [])
    review = run(check_scene(vision, picture(tmp_path), fight_plan()))
    bad = [i for i in review.items if not i.passed]
    assert len(bad) == 1 and "on the left of the picture" in bad[0].item and bad[0].status == "incorrect"


def test_fast_mode_skips_noncritical_and_description(tmp_path):
    vision = FakeVision()
    run(check_scene(vision, picture(tmp_path), fight_plan()))
    assert len(vision.calls) == 3  # one batched question for the critical items, one count, one blind read of camera and poses
    asked = vision.calls[0]
    assert "framing" not in asked and "main light" not in asked and "foreground" not in asked
    assert not any(c.startswith("Describe this illustration") for c in vision.calls)  # the reviewer's free-description pass


def _sizes_seen(tmp_path, **kw):
    seen = []

    class Spy(FakeVision):
        async def analyze_vision(self, image, prompt, **kwargs):
            seen.append(Image.open(io.BytesIO(image) if isinstance(image, bytes) else image).size)
            return await super().analyze_vision(image, prompt, **kwargs)

    run(check_scene(Spy(), picture(tmp_path), fight_plan(), **kw))
    return seen


def test_picture_goes_to_the_model_at_full_size_by_default(tmp_path):
    # measured on this PC: the same low-angle picture was read "looks_up" at 1344x768 and "level" at 1024 and below, so fast mode does not shrink it
    assert set(_sizes_seen(tmp_path)) == {(1344, 768)}


def test_max_side_shrinks_the_picture_when_a_caller_asks(tmp_path):
    seen = _sizes_seen(tmp_path, max_side=512)
    assert seen and all(max(s) <= 512 for s in seen)


def test_all_uncertain_is_accept_low_unverified(tmp_path):
    review = run(check_scene(FakeVision(status=lambda t: "uncertain"), picture(tmp_path), fight_plan()))
    assert review.decision == "accept_low" and any("unverified" in r for r in review.reasons)
    assert review.confidence < 0.35  # the correction planner reads this as "do not trust": it stops and flags


def test_unreachable_reviewer_is_unverified_never_a_pass(tmp_path):
    review = run(check_scene(FakeVision(error=ConnectionError("ollama down")), picture(tmp_path), fight_plan()))
    assert review.decision == "accept_low" and any("unverified" in r for r in review.reasons)
    assert not any(i.passed for i in review.items)


def test_not_verifiable_answers_are_never_dropped_into_an_accept(tmp_path):
    # review finding: every plan claim is visible by construction, so "not_verifiable" on camera, poses and contact means the picture was NOT judged
    vision = FakeVision(status=lambda t: "not_verifiable" if ("camera looks up" in t or t.endswith(("is striking", "is blocking")) or " reaches " in t) else "correct")
    review = run(check_scene(vision, picture(tmp_path), fight_plan()))
    assert review.decision != "accept"
    assert any("camera looks up" in i.item and not i.passed for i in review.items)
    assert review.unverifiable == []


def test_spatial_failure_true_for_pose_false_for_style_only():
    def item(kind, passed):
        return ItemVerdict(item="x", critical=True, verdict="shown" if passed else "missing", confidence=0.9, vision="yes", description_says=True, kind=kind)

    def rev(*items):
        return Review(items=list(items), score=0.5, confidence=0.9, decision="regenerate")

    assert spatial_failure(rev(item("pose", False)))
    assert spatial_failure(rev(item("placement", False)))
    assert spatial_failure(rev(item("camera", False)))
    assert not spatial_failure(rev(item("style", False)))
    assert not spatial_failure(rev(item("pose", True)))


def test_full_mode_hands_every_plan_claim_to_the_full_review(tmp_path, monkeypatch):
    got = {}

    async def fake_eval(provider, image, prompt, audit_gates=True, locate_defects=True, claims=None):
        got["claims"], got["prompt"] = claims, prompt
        return Review(items=[], score=1.0, confidence=1.0, decision="accept")

    monkeypatch.setattr(sc, "evaluate_prompt_image", fake_eval)
    run(check_scene(FakeVision(), picture(tmp_path), fight_plan(), full=True))
    assert [c.text for c in got["claims"]] == [c.text for c in plan_requirements(fight_plan())]
    assert "striking" in got["prompt"].lower()


def test_blind_camera_disagreement_fails_the_camera_item(tmp_path):
    # real finding: the yes/no check accepted an eye-level picture as "low angle"; a blind read (not told the expected angle) saw it level
    review = run(check_scene(FakeVision(blind={"camera": "level", "figures": ["striking", "blocking"]}), picture(tmp_path), fight_plan()))
    bad = [i for i in review.items if not i.passed]
    assert len(bad) == 1 and "camera looks up" in bad[0].item and "level" in bad[0].evidence
    assert spatial_failure(review) and review.decision != "accept"


def test_blind_state_disagreement_fails_only_that_actor(tmp_path):
    review = run(check_scene(FakeVision(blind={"camera": "looks_up", "figures": ["readying", "blocking"]}), picture(tmp_path), fight_plan()))
    bad = [i for i in review.items if not i.passed]
    assert len(bad) == 1 and bad[0].item.endswith("is striking") and "readying" in bad[0].evidence


def test_blind_figures_are_matched_left_to_right(tmp_path):
    plan = fight_plan(actors=list(reversed(fight_plan().actors)))  # plan lists the right-hand actor first; the picture is read left to right
    review = run(check_scene(FakeVision(), picture(tmp_path), plan))
    assert all(i.passed for i in review.items)


def test_blind_figure_count_mismatch_skips_the_state_witness(tmp_path):
    review = run(check_scene(FakeVision(blind={"camera": "looks_up", "figures": ["striking"]}), picture(tmp_path), fight_plan()))
    assert all(i.passed for i in review.items) and review.confidence < 0.8  # no second witness for the states, no false failure
    assert review.decision == "accept_low" and any("second witness" in r for r in review.reasons)


def test_blind_read_failure_falls_back_to_one_witness(tmp_path):
    review = run(check_scene(FakeVision(blind_error=True), picture(tmp_path), fight_plan()))
    assert review.decision == "accept_low" and review.confidence < 0.8  # camera and poses rest on the agreeable yes/no witness alone: never a plain accept
    assert any("second witness" in r for r in review.reasons) and all(i.passed for i in review.items)


def test_blind_prompt_never_states_the_plan(tmp_path):
    vision = FakeVision()
    run(check_scene(vision, picture(tmp_path), fight_plan()))
    blind_prompt = next(c for c in vision.calls if c.startswith("Describe only what you see"))
    assert "scarred cheek" not in blind_prompt and "low angle" not in blind_prompt and "left of the picture" not in blind_prompt


def emotion_plan(state: str):
    from engine.original.scene_plan import ActorPlan, CameraPlan, LightPlan, ScenePlan
    return ScenePlan(scene_type="emotion", brief="a girl who lost her friend", camera=CameraPlan(angle="eye_level", distance="close"), light=LightPlan(direction="left"),
                     actors=[ActorPlan(id="girl", description="messy hair, hoodie, sneakers", gender="female", age_group="teen", side="center", action_state=state)])


def test_emotion_words_in_the_same_family_agree(tmp_path):
    # real finding: the plan said "grieving", the blind read said "lost" for the same sad face: a synonym is not a failure
    blind = {"camera": "level", "figures": ["lost"]}
    assert all(i.passed for i in run(check_scene(FakeVision(blind=blind, count=1), picture(tmp_path), emotion_plan("grieving"))).items)


def test_emotion_words_from_another_family_fail(tmp_path):
    blind = {"camera": "level", "figures": ["joyful"]}
    bad = [i for i in run(check_scene(FakeVision(blind=blind, count=1), picture(tmp_path), emotion_plan("grieving"))).items if not i.passed]
    assert len(bad) == 1 and "joyful" in bad[0].evidence
