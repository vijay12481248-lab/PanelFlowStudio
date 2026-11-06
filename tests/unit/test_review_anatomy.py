import asyncio
import json
from pathlib import Path
import pytest

from engine.original import review as rv
from engine.original.models import Character, Claim, ItemVerdict, Review
from engine.original.shotspec import ShotSpec, CharPose


class MockVisionProvider:
    """Mock vision and text provider for testing review validation gates deterministically."""

    def __init__(self, vqa_answers=None, description="A person standing in a room", stated=None):
        # vqa_answers: dict of {question_index: (answer_str, evidence_str)}
        self.vqa_answers = vqa_answers or {}
        self.description = description
        self.stated = stated if stated is not None else True
        self.vqa_calls = []
        self.desc_calls = []

    async def analyze_vision(self, image, prompt, **kw):
        if "format_schema" in kw:
            self.vqa_calls.append((prompt, kw))
            answers = []
            for n in range(1, 20):
                ans, ev = self.vqa_answers.get(n, ("yes", "normal and visible"))
                answers.append({"n": n, "answer": ans, "evidence": ev})
            return json.dumps({"answers": answers})
        self.desc_calls.append((prompt, kw))
        return self.description

    async def generate_structured(self, prompt, model, **kw):
        if model is rv._Claims:
            return model(claims=[Claim(text="a person stands in a room", critical=True)])
        if model is rv._DescJudge:
            if isinstance(self.stated, list):
                return model(stated=self.stated)
            return model(stated=[self.stated] * 20)
        raise AssertionError(f"Unexpected model requested: {model}")


@pytest.fixture
def dummy_img(tmp_path):
    img = tmp_path / "test_panel.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef\x0fW\x00\x00\x00\x00IEND\xaeB`\x82")
    return img


# =====================================================================
# R1. Data Models Verification
# =====================================================================

def test_models_import_and_contracts():
    """Verify Claim, ItemVerdict, and Review data models export from both models.py and review.py."""
    from engine.original import models as mdl
    assert mdl.Claim is rv.Claim
    assert mdl.ItemVerdict is rv.ItemVerdict
    assert mdl.Review is rv.Review

    # Test Claim fields
    c = Claim(text="Mira holds a torch", critical=True, category="spatial_contact",
              defect_type="disconnected_interaction", interaction_target="torch")
    assert c.category == "spatial_contact"
    assert c.defect_type == "disconnected_interaction"
    assert c.interaction_target == "torch"

    # Test ItemVerdict fields
    iv = ItemVerdict(item="single head", critical=True, verdict="shown", confidence=0.9,
                     vision="yes", description_says=True, category="anatomy",
                     defect_type="polycephaly", passed=True)
    assert iv.category == "anatomy"
    assert iv.defect_type == "polycephaly"
    assert iv.passed is True

    # Failed ItemVerdict sets passed to False
    iv_failed = ItemVerdict(item="single head", critical=True, verdict="missing", confidence=0.9,
                            vision="no", description_says=False, category="anatomy",
                            defect_type="polycephaly")
    assert iv_failed.passed is False


def test_review_enforces_critical_regeneration_policy_on_failure():
    """Verify Review validator forces decision='regenerate' when quality gate failures exist."""
    failed_anatomy = ItemVerdict(item="single head", critical=True, verdict="missing", confidence=0.9,
                                 vision="no", description_says=False, category="anatomy",
                                 defect_type="polycephaly")
    rev = Review(items=[failed_anatomy], score=1.0, confidence=0.9, decision="accept")
    assert rev.decision == "regenerate"
    assert rev.anatomy_passed is False
    assert "polycephaly" in rev.defects
    assert len(rev.anatomical_failures) == 1

    failed_spatial = ItemVerdict(item="held object anchored", critical=True, verdict="missing",
                                 confidence=0.9, vision="no", description_says=False,
                                 category="spatial_contact", defect_type="unanchored_object")
    rev2 = Review(items=[failed_spatial], score=1.0, confidence=0.9, decision="accept")
    assert rev2.decision == "regenerate"
    assert rev2.spatial_contact_passed is False
    assert "unanchored_object" in rev2.defects
    assert len(rev2.spatial_contact_failures) == 1


# =====================================================================
# R2 & Functional Verification: _audit_anatomy
# =====================================================================

def test_audit_anatomy_positive_case(dummy_img):
    """Positive case: anatomically valid illustration passes all gates."""
    provider = MockVisionProvider(
        vqa_answers={i: ("yes", "natural and valid") for i in range(1, 10)},
        description="A warrior standing with normal arms, hands, and head.",
        stated=True
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))

    assert isinstance(verdicts, rv.AuditVerdictList)
    assert verdicts.passed is True
    assert len(verdicts.failures) == 0
    assert verdicts.decision == "accept"
    for v in verdicts:
        assert v.category == "anatomy"
        assert v.verdict == "shown"
        assert v.passed is True
        assert v.critical is True


def test_audit_anatomy_polycephaly_failure(dummy_img):
    """Flags polycephaly (duplicate heads / two heads) as critical failure."""
    # Question 1 corresponds to single head / polycephaly
    provider = MockVisionProvider(
        vqa_answers={1: ("no", "character has two heads on shoulders")},
        description="A figure with two heads looking in opposite directions.",
        stated=[False] + [True] * 10
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))

    assert verdicts.passed is False
    assert len(verdicts.failures) >= 1
    assert verdicts.decision == "regenerate"

    poly_failure = next(v for v in verdicts.failures if v.defect_type == "polycephaly")
    assert poly_failure.critical is True
    assert poly_failure.verdict == "missing"
    assert poly_failure.passed is False
    assert "two heads" in poly_failure.evidence.lower()


def test_audit_anatomy_extra_limbs_failure(dummy_img):
    """Flags extra limbs (extra arms / legs) as critical failure."""
    # Question 2 corresponds to extra limbs
    provider = MockVisionProvider(
        vqa_answers={2: ("no", "three arms are visible on the torso")},
        description="A character with three arms holding items.",
        stated=[True, False, True, True, True]
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))

    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"

    extra_limb_failure = next(v for v in verdicts.failures if v.defect_type == "extra_limbs")
    assert extra_limb_failure.critical is True
    assert extra_limb_failure.verdict == "missing"
    assert extra_limb_failure.passed is False
    assert "three arms" in extra_limb_failure.evidence.lower()


def test_audit_anatomy_missing_limbs_failure(dummy_img):
    """Flags missing limbs as critical failure."""
    # Question 3 corresponds to missing limbs
    provider = MockVisionProvider(
        vqa_answers={3: ("no", "left arm is missing or cut off abruptly")},
        description="A person with missing left arm.",
        stated=[True, True, False, True, True]
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))

    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"

    missing_limb_failure = next(v for v in verdicts.failures if v.defect_type == "missing_limbs")
    assert missing_limb_failure.critical is True
    assert missing_limb_failure.verdict == "missing"
    assert missing_limb_failure.passed is False
    assert "missing" in missing_limb_failure.evidence.lower()


def test_audit_anatomy_distorted_hands_failure(dummy_img):
    """Flags distorted hands / extra or fused digits as critical failure."""
    # Question 4 corresponds to distorted digits / hands
    provider = MockVisionProvider(
        vqa_answers={4: ("no", "six fingers on right hand, fused digits")},
        description="A person with deformed hand showing six fingers.",
        stated=[True, True, True, False, True]
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))

    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"

    hands_failure = next(v for v in verdicts.failures if v.defect_type == "distorted_digits")
    assert hands_failure.critical is True
    assert hands_failure.verdict == "missing"
    assert hands_failure.passed is False
    assert "six fingers" in hands_failure.evidence.lower()


def test_audit_anatomy_limb_topology_failure(dummy_img):
    """Flags invalid limb topology and unnatural joints as critical failure."""
    # Question 5 corresponds to limb topology / joint validity
    provider = MockVisionProvider(
        vqa_answers={5: ("no", "elbow is bent backwards unnaturally")},
        description="A figure with impossible joint bending.",
        stated=[True, True, True, True, False]
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))

    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"

    joint_failure = next(v for v in verdicts.failures if v.defect_type == "limb_topology")
    assert joint_failure.critical is True
    assert joint_failure.verdict == "missing"
    assert joint_failure.passed is False


# =====================================================================
# R2 & Functional Verification: _audit_spatial_contact
# =====================================================================

def test_audit_spatial_contact_positive_case(dummy_img):
    """Positive case: objects are grounded and held items have continuous grasp."""
    provider = MockVisionProvider(
        vqa_answers={i: ("yes", "grounded and properly held") for i in range(1, 10)},
        description="A scholar sitting at a desk, holding a quill firmly.",
        stated=True
    )
    claims = [Claim(text="Mira holds a quill", interaction_target="quill")]
    verdicts = asyncio.run(rv._audit_spatial_contact(provider, dummy_img, claims=claims))

    assert isinstance(verdicts, rv.AuditVerdictList)
    assert verdicts.passed is True
    assert len(verdicts.failures) == 0
    assert verdicts.decision == "accept"
    for v in verdicts:
        assert v.category == "spatial_contact"
        assert v.verdict == "shown"
        assert v.passed is True


def test_audit_spatial_contact_floating_object_failure(dummy_img):
    """Flags unanchored floating objects as critical failure."""
    # Question 1 in spatial contact check is unanchored floating objects
    provider = MockVisionProvider(
        vqa_answers={1: ("no", "a teacup is floating in mid-air above the table")},
        description="A room where a cup is floating in the air without support.",
        stated=[False, True]
    )
    verdicts = asyncio.run(rv._audit_spatial_contact(provider, dummy_img))

    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"

    floating_failure = next(v for v in verdicts.failures if v.defect_type == "unanchored_object")
    assert floating_failure.critical is True
    assert floating_failure.verdict == "missing"
    assert floating_failure.passed is False
    assert "floating" in floating_failure.evidence.lower()


def test_audit_spatial_contact_disconnected_interaction_failure(dummy_img):
    """Flags disconnected interaction objects (verb mentioned but object not anchored in grasp)."""
    # Claims mentions "holds a lantern"
    provider = MockVisionProvider(
        vqa_answers={
            1: ("yes", "furniture is grounded"),
            2: ("no", "the lantern is floating near the hand with no physical grasp contact"),
        },
        description="A girl reaching out, with a lantern hovering disconnected near her fingers.",
        stated=[True, False]
    )
    claims = [Claim(text="Elena holds a lantern in her hand")]
    verdicts = asyncio.run(rv._audit_spatial_contact(provider, dummy_img, claims=claims))

    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"

    grasp_failure = next(v for v in verdicts.failures if v.defect_type == "disconnected_interaction")
    assert grasp_failure.critical is True
    assert grasp_failure.verdict == "missing"
    assert grasp_failure.passed is False
    assert "lantern" in grasp_failure.item.lower()


# =====================================================================
# R3. Critical Regeneration Policy Integration
# =====================================================================

def test_critical_regeneration_policy_overrides_high_narration_score():
    """Even if narration requirements achieve 100% score, quality defects force decision='regenerate'."""
    qa = [rv._QA(n=1, answer="yes", evidence="clearly visible")]
    stated = [True]
    reqs = [("a silver bell hangs on the wall", True)]

    # 1. Without defect -> accept
    clean_rev = rv.combine(reqs, qa, stated, description="A bell on the wall")
    assert clean_rev.decision == "accept"
    assert clean_rev.score == 1.0

    # 2. With anatomical defect (polycephaly) -> regenerate
    anatomy_defect = [ItemVerdict(
        item="single head check", critical=True, verdict="missing", confidence=0.9,
        vision="no", description_says=False, evidence="two heads", category="anatomy",
        defect_type="polycephaly", passed=False
    )]
    rev_with_anatomy_defect = rv.combine(reqs, qa, stated, description="A bell and two heads", audit_items=anatomy_defect)
    assert rev_with_anatomy_defect.decision == "regenerate"
    assert rev_with_anatomy_defect.anatomy_passed is False
    assert any("critical anatomical failure" in r for r in rev_with_anatomy_defect.reasons)

    # 3. With spatial defect (floating cup) -> regenerate
    spatial_defect = [ItemVerdict(
        item="unanchored objects check", critical=True, verdict="missing", confidence=0.9,
        vision="no", description_says=False, evidence="floating cup", category="spatial_contact",
        defect_type="unanchored_object", passed=False
    )]
    rev_with_spatial_defect = rv.combine(reqs, qa, stated, description="A bell and floating cup", audit_items=spatial_defect)
    assert rev_with_spatial_defect.decision == "regenerate"
    assert rev_with_spatial_defect.spatial_contact_passed is False
    assert any("critical spatial contact failure" in r for r in rev_with_spatial_defect.reasons)


# =====================================================================
# Full review_image Integration Test
# =====================================================================

def test_review_image_integration_with_gates(dummy_img):
    """Full review_image pipeline running both narration requirements and validation gates."""
    spec = ShotSpec(
        shot="medium", setting="a library",
        characters=[CharPose(id="mira", pose="standing", expression="calm", action="holding a book")]
    )
    chars = {"mira": Character(id="mira", name="Mira", role="protagonist", age_group="child", look="brown hair", personality="calm")}
    claims = [Claim(text="Mira holds a book", critical=True)]

    # Clean case: all pass
    clean_provider = MockVisionProvider(
        vqa_answers={i: ("yes", "all clear and visible") for i in range(1, 20)},
        description="Mira stands in the library holding a book firmly in both hands.",
        stated=True
    )
    rev_clean = asyncio.run(rv.review_image(clean_provider, dummy_img, claims, spec, chars, audit_gates=True))
    assert rev_clean.decision == "accept"
    assert rev_clean.anatomy_passed is True
    assert rev_clean.spatial_contact_passed is True

    # Defect case: extra limbs detected during review
    # In review_image, reqs are checked first, then anatomy audit runs
    defect_provider = MockVisionProvider(
        vqa_answers={
            # Narration reqs pass
            1: ("yes", "book visible"),
            2: ("yes", "1 person visible"),
            3: ("yes", "brown hair visible"),
            4: ("yes", "library visible"),
            # In anatomy check: extra limbs fails
            2: ("no", "three arms are visible on character"),
        },
        description="A girl with three arms holding a book in the library.",
        stated=[True, True, True, True, True]
    )
    rev_defect = asyncio.run(rv.review_image(defect_provider, dummy_img, claims, spec, chars, audit_gates=True))
    assert rev_defect.decision == "regenerate"


# =====================================================================
# Generic Design Principles: Interaction Extraction
# =====================================================================

def test_generic_interaction_extraction_no_hardcoding():
    """Verify generic extraction of interaction targets from arbitrary verbs and sentences."""
    extract = rv._extract_interaction_targets

    # Claims with interaction verbs
    res1 = extract([Claim(text="a knight wields a massive sword", critical=True)])
    assert any(verb == "wields" and "sword" in obj for verb, obj in res1)

    res2 = extract([Claim(text="the detective holds a magnifying glass")])
    assert any("hold" in verb and "glass" in obj for verb, obj in res2)

    # Spec action with verb
    spec = ShotSpec(shot="medium", characters=[CharPose(id="x", action="carrying a heavy basket")])
    res3 = extract(spec=spec)
    assert any("carr" in verb and "basket" in obj for verb, obj in res3)

    # Caption with verb
    res4 = extract(caption="Elena touches the ancient stone.")
    assert any("touch" in verb and "stone" in obj for verb, obj in res4)

    # Adjective + noun extraction
    res5 = extract([Claim(text="Mira holds a glowing lantern in her hands")])
    assert any(verb == "holds" and obj == "glowing lantern" for verb, obj in res5)

    # Non-prop idioms are ignored
    assert extract([Claim(text="Mira holds her breath")]) == []
    assert extract([Claim(text="the child holds on tightly")]) == []
    assert extract([Claim(text="Elena holds both hands up")]) == []


# =====================================================================
# Edge Cases & Robustness
# =====================================================================

def test_audit_with_empty_or_none_inputs(dummy_img):
    """Audits behave gracefully with None/empty spec, claims, and caption."""
    provider = MockVisionProvider(
        vqa_answers={i: ("yes", "all clear") for i in range(1, 10)},
        description="A plain empty room.",
        stated=True
    )
    anat = asyncio.run(rv._audit_anatomy(provider, dummy_img, spec=None, description=""))
    assert anat.passed is True

    spat = asyncio.run(rv._audit_spatial_contact(provider, dummy_img, claims=None, spec=None, description="", caption=""))
    assert spat.passed is True


def test_empty_hands_do_not_fail_spatial_contact(dummy_img):
    """A character standing with empty hands (no interaction verb) does not trigger false grasp failure."""
    provider = MockVisionProvider(
        vqa_answers={1: ("yes", "furniture and props are resting on floor")},
        description="A girl standing with empty hands at her side in an empty corridor.",
        stated=True
    )
    # No interaction claims or actions
    claims = [Claim(text="a girl stands in the corridor", critical=True)]
    spec = ShotSpec(shot="medium", characters=[CharPose(id="mira", action="standing calmly")])

    verdicts = asyncio.run(rv._audit_spatial_contact(provider, dummy_img, claims=claims, spec=spec))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_zero_character_scene_passes_anatomy_audit(dummy_img):
    """An establishing shot or landscape with 0 characters automatically passes anatomy audit."""
    provider = MockVisionProvider(
        vqa_answers={i: ("no", "no people in picture") for i in range(1, 10)},
        description="A scenic mountain landscape with pine trees under moonlight.",
        stated=True
    )
    spec = ShotSpec(shot="wide", setting="a mountain range", characters=[])
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img, spec=spec))
    assert verdicts.passed is True
    assert len(verdicts) == 0
    assert verdicts.decision == "accept"


def test_clean_image_reaches_accept_decision_not_demoted_to_accept_low(dummy_img):
    """A clean image with narration requirements and audit gates achieves decision='accept'."""
    spec = ShotSpec(shot="medium", setting="a library", characters=[CharPose(id="mira", action="reading a book")])
    chars = {"mira": Character(id="mira", name="Mira", role="protagonist", age_group="child", look="brown hair", personality="calm")}
    claims = [Claim(text="Mira reads a book", critical=True)]

    provider = MockVisionProvider(
        vqa_answers={i: ("yes", "normal and clearly visible") for i in range(1, 20)},
        description="A girl with brown hair sitting at a table reading a book in a sunlit library.",
        stated=True
    )
    rev = asyncio.run(rv.review_image(provider, dummy_img, claims, spec, chars, audit_gates=True))
    assert rev.decision == "accept"
    assert rev.score == 1.0
    assert rev.confidence >= rv.ACCEPT_CONFIDENCE
    assert rev.anatomy_passed is True
    assert rev.spatial_contact_passed is True
    assert rev.reasons == []


def test_direct_review_model_enforces_regeneration_when_flags_are_false():
    """Review validator enforces decision='regenerate' even if items list is empty or flags are set."""
    rev_anat = Review(items=[], score=1.0, confidence=0.9, decision="accept", anatomy_passed=False)
    assert rev_anat.decision == "regenerate"
    assert rev_anat.anatomy_passed is False

    rev_spat = Review(items=[], score=1.0, confidence=0.9, decision="accept", spatial_contact_passed=False)
    assert rev_spat.decision == "regenerate"
    assert rev_spat.spatial_contact_passed is False

    rev_def = Review(items=[], score=1.0, confidence=0.9, decision="accept", defects=["extra_limbs"])
    assert rev_def.decision == "regenerate"


def test_witness_b_description_catches_defect_even_when_witness_a_hallucinates_yes(dummy_img):
    """If Witness B's free description spots a defect, the gate triggers regeneration even if Witness A said yes."""
    provider = MockVisionProvider(
        vqa_answers={i: ("yes", "looks ok") for i in range(1, 10)},
        description="A figure with two heads standing in the shadows.",
        stated=True
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))
    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"
    poly_fail = next(v for v in verdicts.failures if v.defect_type == "polycephaly")
    assert poly_fail.passed is False
    assert poly_fail.critical is True


def test_audit_partly_answer_on_anatomy_triggers_regeneration(dummy_img):
    """An ambiguous or partly visible deformity is rejected as critical failure."""
    provider = MockVisionProvider(
        vqa_answers={2: ("partly", "possible extra arm partially obscured")},
        description="A figure with unclear limb count.",
        stated=True
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))
    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"


def test_simultaneous_anatomy_and_spatial_failures(dummy_img):
    """Multiple defects across anatomy and spatial contact are both reported in defects and reasons."""
    items = [
        ItemVerdict(item="single head", critical=True, verdict="missing", confidence=0.9,
                    vision="no", description_says=False, evidence="two heads", category="anatomy",
                    defect_type="polycephaly", passed=False),
        ItemVerdict(item="anchored props", critical=True, verdict="missing", confidence=0.9,
                    vision="no", description_says=False, evidence="floating book", category="spatial_contact",
                    defect_type="unanchored_object", passed=False),
    ]
    rev = rv.combine([], [], [], description="", audit_items=items)
    assert rev.decision == "regenerate"
    assert rev.anatomy_passed is False
    assert rev.spatial_contact_passed is False
    assert "polycephaly" in rev.defects
    assert "unanchored_object" in rev.defects
    assert any("critical anatomical failure" in r for r in rev.reasons)
    assert any("critical spatial contact failure" in r for r in rev.reasons)


def test_resilience_to_malformed_provider_output(dummy_img):
    """Provider returning broken non-JSON or garbled text does not crash the audit."""
    class BrokenProvider:
        async def analyze_vision(self, image, prompt, **kw):
            return "NOT JSON AT ALL {[[["
        async def generate_structured(self, prompt, model, **kw):
            raise RuntimeError("Provider service timeout")

    verdicts = asyncio.run(rv._audit_anatomy(BrokenProvider(), dummy_img))
    assert isinstance(verdicts, rv.AuditVerdictList)
    # Default fallback for unconfirmed gates is partial/missing -> fails safe
    assert verdicts.passed is False
    assert verdicts.decision == "regenerate"


# =====================================================================
# R2 & R3: Negation, Animal Anatomy & Dynamic Poses
# =====================================================================

def test_negated_evidence_and_description_do_not_trigger_false_failures(dummy_img):
    """Phrases affirming absence of defects ('no extra limbs', 'no floating object') do not trigger failure."""
    provider = MockVisionProvider(
        vqa_answers={
            1: ("yes", "single head, no extra head or duplicate heads"),
            2: ("yes", "she has two arms and two legs, no extra limbs visible"),
            3: ("yes", "complete body visible, no missing limbs"),
            4: ("yes", "natural hands with five fingers, no extra digits"),
            5: ("yes", "natural joint connections with valid limb topology"),
        },
        description="A serene girl sitting quietly. There are no extra limbs or floating objects in the scene.",
        stated=True,
    )
    anat = asyncio.run(rv._audit_anatomy(provider, dummy_img))
    assert anat.passed is True
    assert anat.decision == "accept"
    assert len(anat.failures) == 0

    spat = asyncio.run(rv._audit_spatial_contact(provider, dummy_img, description="A serene room with bookshelves. No floating objects."))
    assert spat.passed is True
    assert spat.decision == "accept"
    assert len(spat.failures) == 0


def test_quadruped_animal_with_four_legs_passes_extra_limbs_check(dummy_img):
    """Quadruped animals (fox cub, dog, horse) described with four legs do not trigger extra limbs defect."""
    provider = MockVisionProvider(
        vqa_answers={i: ("yes", "animal with natural four legs") for i in range(1, 10)},
        description="An orange fox cub with four legs resting peacefully in the meadow.",
        stated=True,
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_mid_air_action_jump_does_not_fail_unanchored_objects(dummy_img):
    """Dynamic character jumping or leaping in mid-air does not trigger unanchored object defect."""
    provider = MockVisionProvider(
        vqa_answers={1: ("yes", "character is dynamically leaping")},
        description="A young warrior captured mid-air as she leaps across the stone chasm.",
        stated=True,
    )
    verdicts = asyncio.run(rv._audit_spatial_contact(provider, dummy_img))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_multi_word_noun_phrases_extract_head_noun():
    """Extract full noun phrase containing multiple adjectives up to the head noun."""
    extract = rv._extract_interaction_targets

    t1 = extract([rv.Claim(text="Elena holds the ancient golden key in her hand")])
    assert any(verb == "holds" and obj == "ancient golden key" for verb, obj in t1)

    t2 = extract([rv.Claim(text="He wields a massive iron greatsword")])
    assert any(verb == "wields" and obj == "massive iron greatsword" for verb, obj in t2)

    t3 = extract([rv.Claim(text="She carries an ornate silver chalice")])
    assert any(verb == "carries" and obj == "ornate silver chalice" for verb, obj in t3)


def test_compound_sentences_with_multiple_interaction_verbs():
    """Compound sentences with multiple verbs extract all interaction targets."""
    extract = rv._extract_interaction_targets
    t = extract([rv.Claim(text="The warrior holds a shield and wields a sword")])
    verbs = [v for v, _ in t]
    objs = [o for _, o in t]
    assert "holds" in verbs and "shield" in objs
    assert "wields" in verbs and "sword" in objs


def test_expanded_interaction_verbs():
    """Expanded verbs (pull, push, catch, brandish, hoist) extract interaction targets."""
    extract = rv._extract_interaction_targets

    t1 = extract(caption="Mira pulls a heavy iron lever to activate the gate.")
    assert any(verb == "pulls" and "lever" in obj for verb, obj in t1)

    t2 = extract(caption="The knight pushes a wooden cart.")
    assert any(verb == "pushes" and "cart" in obj for verb, obj in t2)

    t3 = extract(caption="Elena catches a golden coin in the air.")
    assert any(verb == "catches" and "coin" in obj for verb, obj in t3)

    t4 = extract(caption="He brandishes a glowing crystal orb.")
    assert any(verb == "brandishes" and "orb" in obj for verb, obj in t4)

    t5 = extract(caption="The sailor hoists a heavy anchor.")
    assert any(verb == "hoists" and "anchor" in obj for verb, obj in t5)


def test_body_parts_and_self_touches_not_extracted_as_held_props():
    """Self-touches, body parts, and static furniture are not extracted as held props."""
    extract = rv._extract_interaction_targets

    assert extract(caption="Elena clutches her chest in terror.") == []
    assert extract(caption="He touches his cheek in disbelief.") == []
    assert extract(caption="She touches her shoulder softly.") == []
    assert extract(caption="Elena touches the wooden table.") == []
    assert extract(caption="The child holds still in the dark.") == []


def test_deduplication_of_interaction_targets():
    """Explicit claim interaction_target deduplicates identical target in caption or actions."""
    extract = rv._extract_interaction_targets
    claims = [rv.Claim(text="Mira holds a torch", interaction_target="torch")]
    targets = extract(claims=claims, caption="Mira holds a torch in the dark")
    assert len(targets) == 1
    assert targets[0] == ("interact", "torch")


def test_item_verdict_passed_contract_for_narration():
    """ItemVerdict sets passed=False whenever verdict != 'shown', regardless of category."""
    iv_narration_missing = ItemVerdict(item="torch", critical=True, verdict="missing", confidence=0.9,
                                       vision="no", description_says=False, category="narration")
    assert iv_narration_missing.passed is False

    iv_narration_partial = ItemVerdict(item="torch", critical=True, verdict="partial", confidence=0.5,
                                       vision="partly", description_says=True, category="narration")
    assert iv_narration_partial.passed is False

    iv_narration_shown = ItemVerdict(item="torch", critical=True, verdict="shown", confidence=0.9,
                                     vision="yes", description_says=True, category="narration")
    assert iv_narration_shown.passed is True


def test_no_duplicate_reasons_in_combine():
    """combine() reasons do not duplicate failure messages for anatomy or spatial defects."""
    anatomy_defect = ItemVerdict(
        item="single head check", critical=True, verdict="missing", confidence=0.9,
        vision="no", description_says=False, evidence="two heads", category="anatomy",
        defect_type="polycephaly", passed=False
    )
    rev = rv.combine([], [], [], description="", audit_items=[anatomy_defect])
    assert rev.decision == "regenerate"
    # Should contain the specialized failure reason
    assert any("critical anatomical failure [polycephaly]" in r for r in rev.reasons)
    # Should NOT also contain the generic narration reason
    assert not any("critical item not shown" in r for r in rev.reasons)


# =====================================================================
# R2 & R3: Benign Framing, Phrasal Verbs & Data Model Contracts
# =====================================================================

def test_hands_in_pockets_or_concealed_does_not_fail_distorted_digits(dummy_img):
    """Concealed hands (hands in pockets, gloves, sleeves) do not trigger false distorted digits defect."""
    provider = MockVisionProvider(
        vqa_answers={4: ("partly", "Hands are inside the character's coat pockets and cannot be seen")},
        description="A detective in a trenchcoat standing in the rain with hands in his pockets.",
        stated=True,
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_portrait_close_up_crop_does_not_fail_missing_limbs(dummy_img):
    """Framing crops (portrait close-up, bust shot) do not trigger false missing limbs defect."""
    provider = MockVisionProvider(
        vqa_answers={3: ("partly", "Portrait close-up shot, lower body and legs are cropped out of frame")},
        description="A close-up portrait of a smiling woman with brown hair.",
        stated=True,
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_empty_landscape_without_characters_passes_anatomy_audit_without_spec(dummy_img):
    """Landscape / background shot passes anatomy audit without false polycephaly even when spec is None."""
    provider = MockVisionProvider(
        vqa_answers={1: ("no", "No characters or people are present in this landscape")},
        description="A serene mountain range under a cloudy sky.",
        stated=True,
    )
    verdicts = asyncio.run(rv._audit_anatomy(provider, dummy_img, spec=None))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_empty_scene_without_furniture_passes_spatial_contact_audit(dummy_img):
    """Scene without props or furniture passes spatial contact audit without false unanchored_object defect."""
    provider = MockVisionProvider(
        vqa_answers={1: ("no", "There are no objects, props, or furniture in this outdoor landscape")},
        description="An open grassy plain under a clear blue sky.",
        stated=True,
    )
    verdicts = asyncio.run(rv._audit_spatial_contact(provider, dummy_img))
    assert verdicts.passed is True
    assert verdicts.decision == "accept"
    assert len(verdicts.failures) == 0


def test_phrasal_interaction_verbs_with_particles_and_prepositions():
    """Phrasal verbs (reaches for, holds onto, pulls out, lifts up, picks up) extract target object cleanly."""
    extract = rv._extract_interaction_targets

    t1 = extract(caption="Elena reaches for the sword on the altar.")
    assert any(verb == "reaches" and obj == "sword" for verb, obj in t1)

    t2 = extract(caption="Elena holds onto the rope tightly.")
    assert any(verb == "holds" and obj == "rope" for verb, obj in t2)

    t3 = extract(caption="Elena pulls out a dagger from her belt.")
    assert any(verb == "pulls" and obj == "dagger" for verb, obj in t3)

    t4 = extract(caption="Elena lifts up the heavy crate.")
    assert any(verb == "lifts" and obj == "heavy crate" for verb, obj in t4)

    t5 = extract(caption="Elena picks up a magical crystal orb.")
    assert any(verb == "picks" and "crystal orb" in obj for verb, obj in t5)


def test_trailing_manner_adverbs_do_not_discard_valid_props():
    """Manner adverbs (firmly, tightly, gently, softly) after the object do not corrupt or discard prop extraction."""
    extract = rv._extract_interaction_targets

    t1 = extract(caption="Mira clasps the golden amulet firmly.")
    assert any(verb == "clasps" and obj == "golden amulet" for verb, obj in t1)

    t2 = extract(caption="The knight grips the iron hilt tightly.")
    assert any(verb == "grips" and obj == "iron hilt" for verb, obj in t2)

    t3 = extract(caption="She touches the glass gently.")
    assert any(verb == "touches" and obj == "glass" for verb, obj in t3)


def test_expanded_defect_keywords_caught():
    """Common natural language descriptions of deformities ('too many fingers', 'floating in the air') are caught."""
    assert rv._has_defect_keyword("The character has too many fingers on one hand", "distorted_digits")
    assert rv._has_defect_keyword("The right hand shows deformed fingers", "distorted_digits")
    assert rv._has_defect_keyword("Character appears to have too many arms", "extra_limbs")
    assert rv._has_defect_keyword("A silver dagger is floating in the air", "unanchored_object")
    assert rv._has_defect_keyword("A lamp is suspended in midair without support", "unanchored_object")


def test_object_pronouns_not_extracted_as_held_props():
    """Object pronouns (him, them, her, me, us) are not extracted as handheld props."""
    extract = rv._extract_interaction_targets
    assert extract(caption="He carries him into the sanctuary.") == []
    assert extract(caption="She holds them close.") == []


def test_review_defects_synchronize_anatomy_and_spatial_passed_flags():
    """Review validator synchronizes anatomy_passed and spatial_contact_passed when defects list is provided directly."""
    rev_anat = Review(items=[], score=1.0, confidence=0.9, decision="accept", defects=["polycephaly"])
    assert rev_anat.decision == "regenerate"
    assert rev_anat.anatomy_passed is False

    rev_spat = Review(items=[], score=1.0, confidence=0.9, decision="accept", defects=["unanchored_object"])
    assert rev_spat.decision == "regenerate"
    assert rev_spat.spatial_contact_passed is False


def test_item_verdict_partial_on_quality_gate_normalizes_to_missing():
    """Quality gate ItemVerdict with verdict='partial' normalizes to 'missing' and sets passed=False."""
    iv = ItemVerdict(item="single head check", critical=True, verdict="partial", confidence=0.5,
                     vision="partly", description_says=False, category="anatomy",
                     defect_type="polycephaly", passed=True)
    assert iv.passed is False
    assert iv.verdict == "missing"



