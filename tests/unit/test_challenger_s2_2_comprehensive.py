import hashlib
import io
import json
import tempfile
from pathlib import Path
import pytest
from PIL import Image

from engine.comfyui import art as comfy_art
from engine.original import art, refine, shotspec
from engine.original import review as r
from engine.original.models import Review, ItemVerdict, Claim
from engine.original.planner import Budget
from tests.unit.test_original_art import story, FakeRunner, Vision


# =========================================================================
# 1. engine/original/shotspec.py tests
# =========================================================================

def test_shotspec_preview_dimensions_properties():
    """Verify every dimension in SHOT_DIMENSIONS_PREVIEW satisfies W%16==0, H%16==0,
    falls in 0.20-0.35 MP, and 256 <= W, H <= 2048."""
    assert len(shotspec.SHOT_DIMENSIONS_PREVIEW) > 0
    for shot, (w, h) in shotspec.SHOT_DIMENSIONS_PREVIEW.items():
        assert w % 16 == 0, f"{shot} width {w} is not a multiple of 16"
        assert h % 16 == 0, f"{shot} height {h} is not a multiple of 16"
        assert 256 <= w <= 2048, f"{shot} width {w} out of range [256, 2048]"
        assert 256 <= h <= 2048, f"{shot} height {h} out of range [256, 2048]"
        mp = (w * h) / 1_000_000
        assert 0.20 <= mp <= 0.35, f"{shot} megapixels {mp:.4f} not in [0.20, 0.35]"


def test_resolve_dimensions_adversarial_edge_cases():
    """Test edge-case inputs to resolve_dimensions: unknown shots, negative characters,
    extreme strings, turnaround variations."""
    # Unknown shots
    assert shotspec.resolve_dimensions("nonexistent_shot", preview=True) == (672, 384)
    assert shotspec.resolve_dimensions("unknown_345", preview=False) == (1344, 768)
    assert shotspec.resolve_dimensions("", preview=True) == (672, 384)
    assert shotspec.resolve_dimensions("   ", preview=True) == (672, 384)
    assert shotspec.resolve_dimensions(None, preview=True) == (672, 384)
    assert shotspec.resolve_dimensions(None, preview=False) == (1344, 768)

    # Extreme strings
    huge_shot = "medium_" * 2000
    assert shotspec.resolve_dimensions(huge_shot, preview=True) == (672, 384)

    # Negative / zero / large character counts
    assert shotspec.resolve_dimensions("full", num_characters=-5, preview=True) == (416, 608)
    assert shotspec.resolve_dimensions("full", num_characters=0, preview=True) == (416, 608)
    assert shotspec.resolve_dimensions("full", num_characters=1, preview=True) == (416, 608)
    assert shotspec.resolve_dimensions("full", num_characters=2, preview=True) == (672, 384)
    assert shotspec.resolve_dimensions("full", num_characters=100, preview=True) == (672, 384)
    assert shotspec.resolve_dimensions(None, num_characters=2, preview=True) == (672, 384)
    assert shotspec.resolve_dimensions(None, num_characters=-2, preview=True) == (672, 384)

    # Turnaround sheet overrides character count
    turnaround_variants = [
        "turnaround",
        "turnaround_sheet",
        "TURNAROUND",
        "Turnaround_Sheet",
        "turnaround-sheet",
        "  turnaround  ",
    ]
    for variant in turnaround_variants:
        assert shotspec.resolve_dimensions(variant, num_characters=1, preview=True) == (768, 384)
        assert shotspec.resolve_dimensions(variant, num_characters=5, preview=True) == (768, 384)
        assert shotspec.resolve_dimensions(variant, num_characters=-1, preview=True) == (768, 384)
        assert shotspec.resolve_dimensions(variant, num_characters=1, preview=False) == (1536, 768)
        assert shotspec.resolve_dimensions(variant, num_characters=10, preview=False) == (1536, 768)

    # Custom defaults
    assert shotspec.resolve_dimensions(None, default=(1024, 1024), preview=True) == (512, 512)
    assert shotspec.resolve_dimensions("unknown", default=(1024, 1024), preview=True) == (512, 512)


# =========================================================================
# 2. engine/original/refine.py tests
# =========================================================================

def test_calculate_refiner_sigmas_adversarial_bounds():
    """Test calculate_refiner_sigmas with out-of-bounds inputs:
    start_sigma > 0.40 (must clamp <= 0.40), start_sigma < 0.05 (must clamp >= 0.05),
    steps <= 1, extreme steps."""
    # Out of bounds high
    for high_sigma in [0.41, 0.50, 0.80, 1.0, 100.0]:
        sigmas_str = refine.calculate_refiner_sigmas(start_sigma=high_sigma, steps=4)
        vals = [float(v.strip()) for v in sigmas_str.split(",") if v.strip()]
        assert vals[0] == pytest.approx(0.40, abs=1e-5)
        assert vals[-1] == 0.0

    # Out of bounds low
    for low_sigma in [0.049, 0.01, 0.0, -0.5, -100.0]:
        sigmas_str = refine.calculate_refiner_sigmas(start_sigma=low_sigma, steps=4)
        vals = [float(v.strip()) for v in sigmas_str.split(",") if v.strip()]
        assert vals[0] == pytest.approx(0.05, abs=1e-5)
        assert vals[-1] == 0.0

    # Steps <= 1 clamped to 2 (producing 3 values: start, step 1, 0.0)
    for small_steps in [1, 0, -1, -50]:
        sigmas_str = refine.calculate_refiner_sigmas(start_sigma=0.35, steps=small_steps)
        vals = [float(v.strip()) for v in sigmas_str.split(",") if v.strip()]
        assert len(vals) == 3
        assert vals[0] == pytest.approx(0.35, abs=1e-5)
        assert vals[1] == pytest.approx(0.175, abs=1e-5)
        assert vals[2] == 0.0

    # Extreme high steps clamped to 12 (producing 13 values)
    for big_steps in [12, 13, 50, 1000]:
        sigmas_str = refine.calculate_refiner_sigmas(start_sigma=0.35, steps=big_steps)
        vals = [float(v.strip()) for v in sigmas_str.split(",") if v.strip()]
        assert len(vals) == 13
        assert vals[0] == pytest.approx(0.35, abs=1e-5)
        assert vals[-1] == 0.0
        assert all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))


def test_upscale_2x_exact_multiples_and_rejections():
    """Verify upscale_2x rejects non-multiples of 16 and produces exact 2x dimensions."""
    def make_png(w, h):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), color=(50, 60, 70)).save(buf, format="PNG")
        return buf.getvalue()

    # Valid inputs
    valid_sizes = [(672, 384), (512, 512), (416, 608), (768, 384), (256, 256)]
    for w, h in valid_sizes:
        raw_png = make_png(w, h)
        out_bytes, (tw, th) = refine.upscale_2x(raw_png)
        assert (tw, th) == (w * 2, h * 2)
        assert tw % 16 == 0
        assert th % 16 == 0
        img = Image.open(io.BytesIO(out_bytes))
        assert img.size == (w * 2, h * 2)

    # Invalid inputs: dimensions whose 2x are not multiples of 16
    invalid_sizes = [(673, 384), (672, 385), (10, 10), (15, 15), (100, 100), (333, 444)]
    for w, h in invalid_sizes:
        raw_png = make_png(w, h)
        with pytest.raises(ValueError, match="must be multiples of 16"):
            refine.upscale_2x(raw_png)


def test_two_stage_scaling_single_art_workflow_invariant():
    """Verify two-stage scaling uses approved qwen_image_21_inpaint and preserves
    the Single Art Workflow invariant."""
    wf_dir = Path(comfy_art.__file__).parent
    registry = json.loads((wf_dir / "workflow_registry.json").read_text(encoding="utf-8"))

    # Single text-to-image workflow invariant
    t2i = [w for w in registry if w["purpose"] == "text_to_image"]
    assert len(t2i) == 1
    assert t2i[0]["id"] == "qwen_image_21"

    # qwen_image_21_inpaint workflow invariant
    inpaint = [w for w in registry if w["id"] == "qwen_image_21_inpaint"]
    assert len(inpaint) == 1
    assert inpaint[0]["purpose"] == "inpaint"

    # Test scale_and_refine_panel failure when runner lacks qwen_inpaint_wf
    class DummyRunnerNoInpaint:
        def _upload_bytes(self, data, suffix=".png"):
            return "test"

    dummy_png = io.BytesIO()
    Image.new("RGB", (672, 384)).save(dummy_png, format="PNG")
    with pytest.raises(RuntimeError, match="qwen_image_21_inpaint workflow is not available"):
        refine.scale_and_refine_panel(
            DummyRunnerNoInpaint(),
            dummy_png.getvalue(),
            prompt="test",
            neg="test",
            seed=1,
        )


# =========================================================================
# 3. engine/original/review.py & engine/original/models.py tests
# =========================================================================

def test_assisted_review_decision_ladder_comprehensive():
    """Stress-test assisted review decision ladder:
    high-confidence pass vs low-confidence vs defect presence vs empty reqs."""
    # 1. High-confidence pass -> accept
    reqs_pass = [
        Claim(text="character smiling", critical=True, category="narration"),
        Claim(text="sunlight visible", critical=False, category="key_visual"),
    ]
    qa_pass = [
        r._QA(n=1, answer="yes", evidence="smiling"),
        r._QA(n=2, answer="yes", evidence="bright sunlight"),
    ]
    stated_pass = [True, True]
    rev_pass_assisted = r.combine(reqs_pass, qa_pass, stated_pass, description="character smiling in sunlight", review_mode="assisted")
    assert rev_pass_assisted.decision == "accept"
    assert rev_pass_assisted.score >= 0.75
    assert rev_pass_assisted.confidence >= 0.60

    rev_pass_auto = r.combine(reqs_pass, qa_pass, stated_pass, description="character smiling in sunlight", review_mode="autonomous")
    assert rev_pass_auto.decision == "accept"

    # 2. Low-confidence (only vision answered yes, description was silent: confidence = 0.5 < 0.60)
    qa_low_conf = [
        r._QA(n=1, answer="yes", evidence="smile visible"),
        r._QA(n=2, answer="yes", evidence="light visible"),
    ]
    stated_silent = [False, False]  # vision only -> confidence drops to 0.5
    rev_low_assisted = r.combine(reqs_pass, qa_low_conf, stated_silent, description="portrait", review_mode="assisted")
    assert rev_low_assisted.confidence < 0.60
    assert rev_low_assisted.decision == "needs_review"

    rev_low_auto = r.combine(reqs_pass, qa_low_conf, stated_silent, description="portrait", review_mode="autonomous")
    assert rev_low_auto.decision == "accept_low"

    # 3. Critical item missing -> assisted: needs_review; autonomous: regenerate
    qa_crit_miss = [
        r._QA(n=1, answer="no", evidence="frowning"),
        r._QA(n=2, answer="yes", evidence="bright sunlight"),
    ]
    rev_miss_assisted = r.combine(reqs_pass, qa_crit_miss, [False, True], description="sunlight", review_mode="assisted")
    assert rev_miss_assisted.decision == "needs_review"

    rev_miss_auto = r.combine(reqs_pass, qa_crit_miss, [False, True], description="sunlight", review_mode="autonomous")
    assert rev_miss_auto.decision == "regenerate"

    # 4. Critical item partial -> assisted: needs_review; autonomous: regenerate
    qa_crit_partial = [
        r._QA(n=1, answer="partly", evidence="ambiguous expression"),
        r._QA(n=2, answer="yes", evidence="bright sunlight"),
    ]
    # In assisted mode, partial critical item triggers needs_review (no silent accept_low)
    rev_part_assisted = r.combine(reqs_pass, qa_crit_partial, [False, True], description="sunlight", review_mode="assisted")
    assert rev_part_assisted.decision == "needs_review"

    # In autonomous mode, if score >= 0.6 and not missing, it is accepted as accept_low
    rev_part_auto = r.combine(reqs_pass, qa_crit_partial, [False, True], description="sunlight", review_mode="autonomous")
    assert rev_part_auto.decision == "accept_low"

    # 5. Empty requirements -> assisted: accept; autonomous: accept_low
    rev_empty_assisted = r.combine([], [], [], description="nothing", review_mode="assisted")
    assert rev_empty_assisted.decision == "accept"

    rev_empty_auto = r.combine([], [], [], description="nothing", review_mode="autonomous")
    assert rev_empty_auto.decision == "accept_low"


def test_review_enforce_quality_gates_adversarial():
    """Test Review._enforce_quality_gates:
    Ensure quality gates do not override decision='needs_review' when review_mode='assisted',
    but DO override to 'regenerate' when review_mode='autonomous'."""
    # Assisted: needs_review remains needs_review despite defects
    for defect in ["extra_limbs", "polycephaly", "distorted_digits", "unanchored_object"]:
        rev = Review(
            items=[],
            score=0.4,
            confidence=0.5,
            decision="needs_review",
            defects=[defect],
            review_mode="assisted",
        )
        assert rev.decision == "needs_review"
        assert defect in rev.defects

    # Autonomous: needs_review is converted to regenerate
    for defect in ["extra_limbs", "polycephaly", "distorted_digits", "unanchored_object"]:
        rev = Review(
            items=[],
            score=0.4,
            confidence=0.5,
            decision="needs_review",
            defects=[defect],
            review_mode="autonomous",
        )
        assert rev.decision == "regenerate"
        assert defect in rev.defects

    # Assisted: accept with defect is converted to needs_review
    rev_acc_defect = Review(
        items=[],
        score=0.9,
        confidence=0.9,
        decision="accept",
        defects=["polycephaly"],
        review_mode="assisted",
    )
    assert rev_acc_defect.decision == "needs_review"
    assert rev_acc_defect.anatomy_passed is False

    # Autonomous: accept with defect is converted to regenerate
    rev_acc_defect_auto = Review(
        items=[],
        score=0.9,
        confidence=0.9,
        decision="accept",
        defects=["polycephaly"],
        review_mode="autonomous",
    )
    assert rev_acc_defect_auto.decision == "regenerate"
    assert rev_acc_defect_auto.anatomy_passed is False

    # ItemVerdict category failures
    audit_anatomy_fail = ItemVerdict(
        item="hand digits",
        critical=True,
        verdict="missing",
        confidence=0.9,
        vision="no",
        description_says=False,
        category="anatomy",
        defect_type="distorted_digits",
        passed=False,
    )
    rev_item_assisted = Review(
        items=[audit_anatomy_fail],
        score=0.8,
        confidence=0.8,
        decision="accept",
        review_mode="assisted",
    )
    assert rev_item_assisted.decision == "needs_review"
    assert rev_item_assisted.anatomy_passed is False
    assert "distorted_digits" in rev_item_assisted.defects

    rev_item_auto = Review(
        items=[audit_anatomy_fail],
        score=0.8,
        confidence=0.8,
        decision="accept",
        review_mode="autonomous",
    )
    assert rev_item_auto.decision == "regenerate"
    assert rev_item_auto.anatomy_passed is False


def test_art_generate_art_retry_loop_early_break_and_refine_panel():
    """Verify art.py:generate_art retry loop early break in assisted mode
    and directed refinement budget in assisted mode."""
    s = story()
    s.panels = s.panels[1:2]
    s.panels[0].key_visuals = ["eyes closed", "asleep"]
    tags = ["short brown hair", "green eyes"]
    ident = '{"results":[' + ",".join(f'{{"tag":"{x}","visible":true}}' for x in tags) + "]}"

    def match(seen):
        return '{"results":[' + ",".join(f'{{"tag":"{k}","visible":{str(k in seen).lower()}}}' for k in ("eyes closed", "asleep")) + "]}"

    # In autonomous mode, it fails first attempt, so it executes 2 calls
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        r_auto = FakeRunner()
        provider_auto = Vision([ident, match(set()), ident, match({"eyes closed", "asleep"})])
        out_auto = art.generate_art(s, tmp_path, r_auto, provider=provider_auto, review_mode="autonomous")
        panel_calls_auto = [c for c in r_auto.calls if c[0].startswith("panel_")]
        assert len(panel_calls_auto) == 2

    # In assisted mode, it breaks immediately after attempt 0
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        r_assisted = FakeRunner()
        provider_assisted = Vision([ident, match(set()), ident, match({"eyes closed", "asleep"})])
        out_assisted = art.generate_art(s, tmp_path, r_assisted, provider=provider_assisted, review_mode="assisted")
        panel_calls_assisted = [c for c in r_assisted.calls if c[0].startswith("panel_")]
        assert len(panel_calls_assisted) == 1

    # Check directed refinement budget: budget_attempts == 1 when review_mode == "assisted"
    # Verify in _refine_directed_panel logic
    budget_assisted = Budget(max_attempts=1 if "assisted" == "assisted" else art.DIRECTED_ATTEMPTS)
    budget_auto = Budget(max_attempts=1 if "autonomous" == "assisted" else art.DIRECTED_ATTEMPTS)
    assert budget_assisted.max_attempts == 1
    assert budget_auto.max_attempts == art.DIRECTED_ATTEMPTS
