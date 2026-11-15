from engine.creative.emotion_guider import (
    SOMATIC_LEXICON,
    SomaticArchetype,
    SomaticDescriptor,
    SomaticEmotionGuiderAgent,
)


def test_somatic_descriptor_clause_compilation():
    descriptor = SomaticDescriptor(
        archetype=SomaticArchetype.LETHAL_WRATH,
        cranial_micro_anatomy="brows furrowed",
        oral_and_dental="teeth bared",
        vascular_tension="neck muscles bulging",
        biomechanical_posture="lunging forward",
        kinetic_fx="directional lines",
    )
    clause = descriptor.compile_somatic_clause()
    assert "brows furrowed" in clause
    assert "teeth bared" in clause
    assert "neck muscles bulging" in clause
    assert "lunging forward" in clause
    assert "directional lines" in clause


def test_infer_archetype_victim_and_striker():
    guider = SomaticEmotionGuiderAgent()

    # Victim receiving strike
    archetype = guider.infer_archetype("calm", is_victim_receiving_strike=True)
    assert archetype == SomaticArchetype.VISCERAL_TRAUMA

    # Striker attacking
    archetype = guider.infer_archetype("focused", is_striker_attacking=True)
    assert archetype == SomaticArchetype.LETHAL_WRATH


def test_infer_archetype_by_emotion_tone():
    guider = SomaticEmotionGuiderAgent()

    assert guider.infer_archetype("sheer terror") == SomaticArchetype.PARALYZING_DREAD
    assert guider.infer_archetype("mockery and arrogance") == SomaticArchetype.CRUEL_ARROGANCE
    assert guider.infer_archetype("exhaustion after battle") == SomaticArchetype.DESPERATE_EXHAUSTION
    assert guider.infer_archetype("sovereign epiphany") == SomaticArchetype.SOVEREIGN_AWE
    assert guider.infer_archetype("neutral contemplation") == SomaticArchetype.TENSION_STANDOFF


def test_guide_prompt_enhancement():
    guider = SomaticEmotionGuiderAgent()
    prompt, neg = guider.guide_prompt(
        base_prompt="A warrior facing the enemy",
        base_negative_prompt="blurry, low quality",
        emotion_tone="furious battle clash",
        is_striker_attacking=True,
    )

    assert "[SOMATIC EMOTION & INTENSITY:" in prompt
    assert "blurry, low quality" in neg
    assert "calm face" in neg
    assert "stoic" in neg
