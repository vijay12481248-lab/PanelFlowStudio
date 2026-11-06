"""Phase 3: the correction planner is pure logic, so every rule is checked here without a GPU or a model."""
import pytest

from engine.original.models import ItemVerdict, Review
from engine.original.planner import Budget, best_iteration, plan_correction


def item(text="x", *, ok=False, critical=True, category="narration", defect="", status="", bbox=None, local=False, evidence="", severity=""):
    v = ItemVerdict(item=text, critical=critical, verdict="shown" if ok else "missing", confidence=0.9, vision="yes" if ok else "no",
                    description_says=ok, category=category, defect_type=defect, passed=ok, status=status, evidence=evidence, severity=severity)
    if bbox:
        v.bbox, v.bbox_source = bbox, "vlm"
    v.repairable_locally = local
    return v


def review(items, decision="regenerate", confidence=0.8, score=0.5, unverifiable=()):
    return Review(items=items, score=score, confidence=confidence, decision=decision, unverifiable=list(unverifiable))


def hist(*entries):
    """entries: (kind, decision, score, failed[, parent])"""
    out = []
    for n, e in enumerate(entries, 1):
        kind, decision, score, failed = e[:4]
        d = {"n": n, "kind": kind, "review": {"decision": decision, "score": score, "confidence": 0.8, "defects": [], "failed": failed}}
        if kind == "repair":
            d["parent"] = e[4]
        out.append(d)
    return out


HAND = dict(text="natural hands", category="anatomy", defect="distorted_digits", bbox=[0.4, 0.4, 0.6, 0.6], local=True, status="missing")
FIRST = hist(("generate", "regenerate", 0.5, ["a"]))


def test_a_passing_review_stops_with_accept():
    p = plan_correction(review([item(ok=True)], decision="accept"), FIRST)
    assert (p.action, p.final, p.select) == ("accept", True, 1)


def test_no_verdict_or_untrusted_verdict_goes_to_a_human_not_to_another_attempt():
    assert plan_correction(None, FIRST).action == "human_review"
    p = plan_correction(review([item()], confidence=0.2), FIRST)
    assert p.action == "human_review" and "low_confidence" in p.flags and p.final


def test_one_located_defect_with_an_edit_tool_is_repaired_in_place():
    p = plan_correction(review([item(ok=True, text="fine"), item(**HAND)]), FIRST, edit_available=True)
    assert p.action == "repair_local" and not p.final and p.mask_source == "vlm"
    assert p.targets[0].bbox == [0.4, 0.4, 0.6, 0.6] and "fingers" in p.targets[0].correction


def test_without_an_edit_tool_the_same_defect_is_redrawn_and_says_why():
    p = plan_correction(review([item(**HAND)]), FIRST, edit_available=False)
    assert p.action == "regenerate" and "no edit tool" in p.reason and p.avoid_defects == ["distorted_digits"]


def test_a_missing_critical_requirement_blocks_the_local_repair():
    p = plan_correction(review([item(**HAND), item("a lamp on the table", status="missing")]), FIRST, edit_available=True)
    assert p.action == "regenerate" and p.emphasis == ["a lamp on the table"]


def test_a_minor_failure_elsewhere_does_not_block_the_local_repair():
    p = plan_correction(review([item(**HAND), item("soft light", critical=False, status="uncertain")]), FIRST, edit_available=True)
    assert p.action == "repair_local"


def test_a_defect_without_a_reported_box_is_never_given_an_invented_region():
    no_box = dict(HAND, bbox=None, local=False)
    assert plan_correction(review([item(**no_box)]), FIRST, edit_available=True).action == "regenerate"
    p = plan_correction(review([item(**no_box)]), FIRST, edit_available=True, allow_heuristic_masks=True)
    assert p.action == "repair_local" and p.mask_source == "heuristic" and p.targets[0].bbox is None  # opt-in, and labelled as a guess


def test_too_many_regions_are_cheaper_to_redraw():
    items = [item(**dict(HAND, text=f"h{i}")) for i in range(3)]
    assert plan_correction(review(items), FIRST, edit_available=True).action == "regenerate"


def test_a_repair_is_tried_once_per_generation():
    h = hist(("generate", "regenerate", 0.5, ["hand"]), ("repair", "regenerate", 0.5, ["hand"], 1))
    p = plan_correction(review([item(**HAND)]), h, edit_available=True)
    assert p.action == "regenerate"
    h2 = hist(("generate", "regenerate", 0.5, ["hand"]), ("repair", "regenerate", 0.5, ["hand"], 1), ("generate", "regenerate", 0.5, ["hand"]))
    assert plan_correction(review([item(**HAND)]), h2, edit_available=True).action == "repair_local"  # a new generation gets its own repair


def test_the_regenerate_ladder_matches_the_story_loop():
    items = [item("a lamp on the table", status="missing"), item("soft light", critical=False, status="uncertain"), item(**HAND)]
    second = plan_correction(review(items), FIRST)
    assert second.action == "regenerate" and second.new_seed and not second.widen_frame and not second.simplify
    assert second.emphasis == ["a lamp on the table", "soft light"]  # critical first; anatomy is steered away from, not emphasised
    third = plan_correction(review(items), hist(("generate", "regenerate", 0.4, ["a"]), ("generate", "regenerate", 0.5, ["a"])))
    assert third.widen_frame and third.simplify


def test_a_spent_budget_keeps_the_best_candidate_and_says_what_it_is():
    flagged = hist(("generate", "regenerate", 0.4, ["a"]), ("generate", "accept_low", 0.7, ["b"]), ("generate", "regenerate", 0.6, ["a"]))
    p = plan_correction(review([item()]), flagged)
    assert (p.action, p.final, p.select) == ("accept_low", True, 2)
    failing = hist(("generate", "regenerate", 0.4, ["a"]), ("generate", "regenerate", 0.7, ["a"]), ("generate", "regenerate", 0.6, ["a"]))
    p = plan_correction(review([item()]), failing)
    assert (p.action, p.final, p.select) == ("human_review", True, 2)


def test_the_last_attempt_may_still_be_repaired_in_place():
    h = hist(("generate", "regenerate", 0.4, ["a"]), ("generate", "regenerate", 0.4, ["a"]), ("generate", "regenerate", 0.5, ["hand"]))
    assert plan_correction(review([item(**HAND)]), h, edit_available=True).action == "repair_local"


def test_no_progress_stops_the_loop_early_but_progress_does_not():
    budget = Budget(max_attempts=6)
    stuck = hist(("generate", "regenerate", 0.50, ["a"]), ("generate", "regenerate", 0.51, ["a"]), ("generate", "regenerate", 0.50, ["a"]))
    p = plan_correction(review([item()]), stuck, budget=budget)
    assert p.action == "human_review" and "plateau" in p.flags
    improving = hist(("generate", "regenerate", 0.50, ["a", "b"]), ("generate", "regenerate", 0.60, ["a"]), ("generate", "regenerate", 0.70, ["a"]))
    assert plan_correction(review([item()]), improving, budget=budget).action == "regenerate"


def test_unverifiable_requirements_are_flagged_for_a_human_without_failing_the_picture():
    p = plan_correction(review([item(ok=True)], decision="accept", unverifiable=["birds chirp"]), FIRST)
    assert p.action == "accept" and p.flags == ["unverifiable_requirements"]


def test_best_iteration_orders_by_decision_then_score_and_keeps_the_earlier_tie():
    h = hist(("generate", "regenerate", 0.9, []), ("generate", "accept_low", 0.6, []), ("generate", "accept_low", 0.6, []), ("generate", "accept", 0.5, []))
    assert best_iteration(h)["n"] == 4
    assert best_iteration(h[:3])["n"] == 2
    assert best_iteration([{"n": 1, "kind": "generate", "review": None}, h[0] | {"n": 2}])["n"] == 2  # an unreviewed candidate only wins alone
    assert best_iteration([]) is None


def test_a_repair_plan_carries_the_boxes_of_everything_that_passes_so_the_mask_can_avoid_them():
    detail = item("the cat licks its paw", ok=True, bbox=[0.65, 0.53, 0.7, 0.6])
    plan = plan_correction(review([detail, item(**HAND)]), FIRST, edit_available=True)
    assert plan.action == "repair_local" and plan.protect == [[0.65, 0.53, 0.7, 0.6]]
