import pytest
from engine.original import review as r
from engine.original.models import Review, ItemVerdict, Claim


def test_rank_dictionary_contains_needs_review():
    assert "needs_review" in r.RANK
    assert r.RANK["needs_review"] == 0
    assert r.RANK["accept"] == 2
    assert r.RANK["accept_low"] == 1
    assert r.RANK["regenerate"] == 0


def test_review_model_allows_needs_review_in_assisted_mode():
    # In assisted mode, quality gates allow needs_review to pass without being overridden to regenerate
    rev_assisted = Review(
        items=[],
        decision="needs_review",
        review_mode="assisted",
        score=0.5,
        confidence=0.5,
        defects=["extra_limbs"],
        anatomy_passed=False,
        spatial_contact_passed=True,
    )
    assert rev_assisted.decision == "needs_review"
    assert rev_assisted.anatomy_passed is False
    assert "extra_limbs" in rev_assisted.defects

    # In autonomous mode, quality gates enforce regenerate
    rev_auto = Review(
        items=[],
        decision="needs_review",
        review_mode="autonomous",
        score=0.5,
        confidence=0.5,
        defects=["extra_limbs"],
        anatomy_passed=False,
        spatial_contact_passed=True,
    )
    assert rev_auto.decision == "regenerate"


def test_combine_assisted_mode_high_confidence_accept():
    # High confidence items -> accept
    reqs = [
        Claim(text="mira smiling", critical=True, category="narration"),
        Claim(text="warm lamp", critical=False, category="key_visual"),
    ]
    qa = [
        r._QA(n=1, answer="yes", evidence="smiling clearly"),
        r._QA(n=2, answer="yes", evidence="bright warm lamp"),
    ]
    stated = [True, True]

    rev = r.combine(reqs, qa, stated, description="Mira is smiling next to a warm lamp", review_mode="assisted")
    assert rev.decision == "accept"
    assert rev.score >= 0.75
    assert rev.confidence >= 0.60


def test_combine_assisted_mode_ambiguous_panel_flags_needs_review():
    # Missing critical item -> in autonomous it is regenerate, in assisted it is needs_review
    reqs = [
        Claim(text="mira smiling", critical=True, category="narration"),
        Claim(text="warm lamp", critical=False, category="key_visual"),
    ]
    qa = [
        r._QA(n=1, answer="no", evidence="no smile visible"),
        r._QA(n=2, answer="yes", evidence="bright lamp"),
    ]
    stated = [False, True]

    rev_assisted = r.combine(reqs, qa, stated, description="A dark room with a lamp", review_mode="assisted")
    assert rev_assisted.decision == "needs_review"
    assert rev_assisted.review_mode == "assisted"

    # In autonomous mode, the same inputs result in regenerate
    rev_auto = r.combine(reqs, qa, stated, description="A dark room with a lamp", review_mode="autonomous")
    assert rev_auto.decision == "regenerate"


def test_combine_assisted_mode_anatomical_failure_flags_needs_review():
    # Anatomy defect via audit_items -> needs_review in assisted, regenerate in autonomous
    reqs = [Claim(text="mira smiling", critical=False, category="narration")]
    qa = [r._QA(n=1, answer="yes", evidence="smile")]
    stated = [True]

    anatomy_fail_item = ItemVerdict(
        item="distorted digits",
        critical=True,
        verdict="missing",
        confidence=0.9,
        vision="no",
        description_says=False,
        category="anatomy",
        defect_type="distorted_digits",
        passed=False,
    )

    rev_assisted = r.combine(
        reqs,
        qa,
        stated,
        description="A girl with warped hands",
        audit_items=[anatomy_fail_item],
        review_mode="assisted",
    )
    assert rev_assisted.decision == "needs_review"

    rev_auto = r.combine(
        reqs,
        qa,
        stated,
        description="A girl with warped hands",
        audit_items=[anatomy_fail_item],
        review_mode="autonomous",
    )
    assert rev_auto.decision == "regenerate"
