"""Unit tests for the Mistake Ledger, Anti-Pattern Memory, and Regression Auditor."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from engine.creative.schema import (
    CinematicScene,
    CinematicShot,
    MistakeRecord,
    MistakeSeverity,
    NovelChapter,
    RegressionAuditVerdict,
    SelfCritiqueVerdict,
    StoryBible,
    StorySeed,
    WorldLore,
    CharacterProfile,
    ChapterOutline,
)
from engine.creative.mistakes import MistakeAuditor, MistakeLedger
from engine.creative.self_improvement import SelfImprovementEngine, ExperienceMemoryVault


@pytest.fixture
def temp_mistakes_file(tmp_path):
    return tmp_path / "mistakes_ledger.json"


@pytest.fixture
def sample_bible():
    return StoryBible(
        title="MAHABHARATA: THE FALL OF BHISHMA",
        logline="The grand patriarch meets destiny on Kurukshetra.",
        thematic_core="Duty vs righteousness",
        emotional_arc="Tragic acceptance",
        lore=WorldLore(
            world_name="Kurukshetra",
            era_or_timeline="Dvapara Yuga",
            setting_overview="Scorched plains under crimson sunset.",
            rules=["Bhishma can choose time of death"],
            key_factions=["Kauravas", "Pandavas"]
        ),
        characters=[
            CharacterProfile(
                id="bhishma",
                name="Bhishma Pitamaha",
                role="Grand Patriarch",
                visual_tags="venerable warrior, white beard, golden armor",
                personality="Resolute and sorrowful",
                tag="<Picture 1>"
            )
        ],
        chapter_outlines=[
            ChapterOutline(
                chapter_number=1,
                title="The Twilight",
                dramatic_premise="Bhishma on the arrow bed.",
                beats=[]
            )
        ]
    )


def test_mistake_ledger_persistence_and_defaults(temp_mistakes_file):
    """Verify MistakeLedger seeds default anti-patterns and formats prompt constraints."""
    ledger = MistakeLedger(temp_mistakes_file)
    assert temp_mistakes_file.exists()

    all_mistakes = ledger.load_mistakes()
    assert len(all_mistakes) >= 4

    h3_mistakes = ledger.load_mistakes("h3_prompting")
    assert len(h3_mistakes) >= 1
    assert any("soundscape" in m.mistake_id for m in h3_mistakes)

    prompt_text = ledger.get_anti_patterns_prompt("h3_prompting")
    assert "CRITICAL ANTI-PATTERNS" in prompt_text
    assert "err_h3_soundscape_speech" in prompt_text
    assert "BAD:" in prompt_text
    assert "GOOD:" in prompt_text


def test_regression_auditor_catches_soundscape_speech(temp_mistakes_file):
    """Verify MistakeAuditor catches dialogue speech inside video soundscapes and increments recurrence."""
    ledger = MistakeLedger(temp_mistakes_file)
    auditor = MistakeAuditor(ledger)

    # Flawed shot: contains quoted speech in soundscape
    flawed_shot = CinematicShot(
        shot_index=1,
        title="Flawed Shot",
        camera_movement="Push in",
        subject_description="Warrior on chariot",
        environmental_details="Dusty plain",
        lighting_and_atmosphere="Sunset",
        soundscape="Heavy wind, soldiers shouting 'Charge into battle!'",
        non_diegetic_music="War drums",
        prompt=(
            "subject_definitions:\nWarrior: Golden armor\n\n"
            "summary:\nShot 1\n\n"
            "retention_analysis:\nPreserved\n\n"
            "detailed_description:\ncamera_movement: Push in\n\n"
            "overall_soundscape:\nHeavy wind, soldiers shouting 'Charge into battle!'\n\n"
            "non_diegetic_music:\nWar drums"
        )
    )

    initial_rec = next(m.recurrence_count for m in ledger.load_mistakes() if m.mistake_id == "err_h3_soundscape_speech")
    verdict = auditor.audit_h3_prompt(flawed_shot)

    assert verdict.passed is False
    assert len(verdict.detected_mistakes) >= 1
    assert any("err_h3_soundscape_speech" == m.mistake_id for m in verdict.detected_mistakes)

    # Verify recurrence counter incremented
    post_rec = next(m.recurrence_count for m in ledger.load_mistakes() if m.mistake_id == "err_h3_soundscape_speech")
    assert post_rec == initial_rec + 1

    # Clean shot: strictly diegetic foley with mandatory rule
    clean_shot = CinematicShot(
        shot_index=2,
        title="Clean Shot",
        camera_movement="Sweeping crane",
        subject_description="Warrior on chariot",
        environmental_details="Dusty plain",
        lighting_and_atmosphere="Sunset",
        soundscape="Heavy wind, distant conch blare, bronze shield clink. Strict rule: absolutely no human speech or dialogue.",
        non_diegetic_music="War drums",
        prompt=(
            "subject_definitions:\nWarrior: Golden armor\n\n"
            "summary:\nShot 2\n\n"
            "retention_analysis:\nPreserved\n\n"
            "detailed_description:\ncamera_movement: Sweeping crane\n\n"
            "overall_soundscape:\nHeavy wind, distant conch blare, bronze shield clink. Strict rule: absolutely no human speech or dialogue.\n\n"
            "non_diegetic_music:\nWar drums"
        )
    )

    clean_verdict = auditor.audit_h3_prompt(clean_shot)
    assert clean_verdict.passed is True
    assert len(clean_verdict.detected_mistakes) == 0


def test_regression_auditor_catches_flat_prose_emotion(temp_mistakes_file, sample_bible):
    """Verify MistakeAuditor catches flat emotional verb labels in novel prose."""
    ledger = MistakeLedger(temp_mistakes_file)
    auditor = MistakeAuditor(ledger)

    flawed_chapter = NovelChapter(
        chapter_number=1,
        title="Flawed Chapter",
        prose="Bhishma lay on the arrows. Arjuna arrived and felt sad. He looked at his teacher and felt terrified.",
        summary="Arjuna feels sad.",
        word_count=19
    )

    verdict = auditor.audit_prose(flawed_chapter, sample_bible)
    assert verdict.passed is False
    assert any("felt sad" in w for w in verdict.regression_warnings)

    clean_chapter = NovelChapter(
        chapter_number=1,
        title="Elevated Chapter",
        prose=(
            "Bhishma lay on the arrow lattice, his breath wheezing through parched lips. "
            "A suffocating ache clamped around Arjuna's chest as his knuckles blanched against the cold horn of the Gandiva. "
            "Sweat stung his eyelids, mingling with the alkaline dust of Kurukshetra."
        ),
        summary="Arjuna approaches Bhishma.",
        word_count=42
    )

    clean_verdict = auditor.audit_prose(clean_chapter, sample_bible)
    assert clean_verdict.passed is True


def test_regression_auditor_catches_camera_monotony(temp_mistakes_file):
    """Verify MistakeAuditor flags repetitive camera movement and identical framings."""
    ledger = MistakeLedger(temp_mistakes_file)
    auditor = MistakeAuditor(ledger)

    shots = [
        CinematicShot(shot_index=1, title="Shot 1", shot_type="Wide Establishing", camera_movement="Slow push-in", subject_description="", environmental_details="", lighting_and_atmosphere="", soundscape="", non_diegetic_music=""),
        CinematicShot(shot_index=2, title="Shot 2", shot_type="Wide Establishing", camera_movement="Steadicam push-in", subject_description="", environmental_details="", lighting_and_atmosphere="", soundscape="", non_diegetic_music=""),
        CinematicShot(shot_index=3, title="Shot 3", shot_type="Wide Establishing", camera_movement="Slow push-in", subject_description="", environmental_details="", lighting_and_atmosphere="", soundscape="", non_diegetic_music=""),
    ]
    scene = CinematicScene(scene_index=1, id="scene_1", name="Scene 1", description="Monotonous scene", shots=shots)

    verdict = auditor.audit_cinematography([scene])
    assert verdict.passed is False
    assert any("share identical framing" in w for w in verdict.regression_warnings)


def test_mistake_record_escalation_and_learning(temp_mistakes_file):
    """Verify new mistakes are cataloged and severity escalates from HIGH to CRITICAL after 3 recurrences."""
    ledger = MistakeLedger(temp_mistakes_file)

    # 1. Record new mistake
    record = ledger.record_or_escalate_mistake(
        domain="art_engine",
        flawed_pattern="Hallucinating modern digital watches on ancient historical figures",
        prevention_rule="Explicitly include 'wrist watch, modern jewelry, glasses' in negative prompt.",
        severity=MistakeSeverity.HIGH
    )
    assert record.recurrence_count == 1
    assert record.severity == MistakeSeverity.HIGH

    # 2. Recur once more
    rec2 = ledger.increment_recurrence(record.mistake_id)
    assert rec2.recurrence_count == 2
    assert rec2.severity == MistakeSeverity.HIGH

    # 3. Third recurrence: escalates to CRITICAL
    rec3 = ledger.increment_recurrence(record.mistake_id)
    assert rec3.recurrence_count == 3
    assert rec3.severity == MistakeSeverity.CRITICAL


@pytest.mark.asyncio
async def test_self_improvement_resolves_regression_via_refinement(tmp_path, sample_bible):
    """Verify that when a draft has a regression, SelfImprovementEngine forces a refinement pass to resolve it."""
    heuristics_file = tmp_path / "heuristics.json"
    memory_vault = ExperienceMemoryVault(heuristics_file)
    engine = SelfImprovementEngine(memory_vault)

    # Draft with regression ("felt sad")
    draft_chapter = NovelChapter(
        chapter_number=1,
        title="Chapter 1",
        prose="Arjuna stood before Bhishma and felt sad about the war.",
        summary="Arjuna is sad.",
        word_count=10
    )

    # Mock initial critique (score 8.8, but regression auditor will flag "felt sad" and force refinement!)
    mock_critique_1 = SelfCritiqueVerdict(
        quality_score=8.8,
        passed_rubric=True,
        detected_weaknesses=[],
        actionable_improvements=[],
        learned_principles=["Physical somatic cues deepen historical gravitas"]
    )

    # Mock refined chapter with visceral prose replacing "felt sad"
    mock_refined_chapter = NovelChapter(
        chapter_number=1,
        title="Chapter 1",
        prose="Arjuna stood before Bhishma, a cold knot twisting in his throat as the dust swirled across the red earth.",
        summary="Arjuna stands before Bhishma.",
        word_count=21
    )

    mock_critique_2 = SelfCritiqueVerdict(
        quality_score=9.5,
        passed_rubric=True,
        detected_weaknesses=[],
        actionable_improvements=[]
    )

    with patch.object(engine, "self_critique_prose", side_effect=[mock_critique_1, mock_critique_2]), \
         patch.object(engine, "refine_novel_chapter", new_callable=AsyncMock, return_value=mock_refined_chapter):

        final_chapter, report = await engine.execute_self_improvement_prose_cycle(sample_bible, draft_chapter)

        # Refinement was triggered because regression auditor caught "felt sad"
        assert report.iterations == 2
        assert "felt sad" not in final_chapter.prose
        assert "cold knot twisting" in final_chapter.prose
