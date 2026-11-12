"""Unit tests for the Metacognitive Self-Improvement & Continuous Learning Engine."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from engine.creative.schema import (
    StoryGenre,
    StorySeed,
    StoryBible,
    WorldLore,
    CharacterProfile,
    ChapterOutline,
    NovelChapter,
    SelfCritiqueVerdict,
    SelfImprovementReport,
    LearnedHeuristic,
)
from engine.creative.self_improvement import (
    ExperienceMemoryVault,
    SelfImprovementEngine,
)
from engine.creative.orchestrator import CreativeOrchestrator
from engine.creative.vault import CreativeVault


@pytest.fixture
def temp_memory_file(tmp_path):
    return tmp_path / "heuristics.json"


@pytest.fixture
def sample_bible():
    return StoryBible(
        title="THE CURSE OF KARNA",
        logline="The tragic hero of Anga confronts his destiny on the battlefield.",
        thematic_core="Loyalty, unacknowledged nobility, tragic destiny",
        emotional_arc="Longing for recognition leading to resolute sacrifice",
        lore=WorldLore(
            world_name="Kurukshetra",
            era_or_timeline="Dvapara Yuga",
            setting_overview="Dusty plain strewn with chariots under crimson dusk.",
            rules=["Karna's golden armor was surrendered to Indra", "His chariot wheel will sink into the earth"],
            key_factions=["Kauravas", "Pandavas"]
        ),
        characters=[
            CharacterProfile(
                id="karna_anga",
                name="Karna",
                role="Tragic Champion",
                visual_tags="tall muscular warrior, radiant golden complexion, pierced earlobes, austere battle-worn silver armor, dark curly hair tied back",
                personality="Fiercely loyal, painfully proud, endlessly generous",
                tag="<Picture 1>"
            )
        ],
        chapter_outlines=[
            ChapterOutline(
                chapter_number=1,
                title="The Sun's Son",
                dramatic_premise="Karna stands before his sunken chariot wheel.",
                beats=[]
            )
        ]
    )


def test_experience_memory_defaults_and_filtering(temp_memory_file):
    """Verify ExperienceMemoryVault seeds baseline heuristics and filters by domain."""
    vault = ExperienceMemoryVault(temp_memory_file)
    assert temp_memory_file.exists()

    all_heuristics = vault.load_heuristics()
    assert len(all_heuristics) >= 5

    prose_heuristics = vault.load_heuristics("novel_prose")
    assert len(prose_heuristics) >= 2
    assert all(h.domain == "novel_prose" for h in prose_heuristics)

    guidelines = vault.get_guidelines_text("novel_prose")
    assert "1. " in guidelines
    assert len(guidelines.splitlines()) >= 2


def test_experience_memory_learning_new_heuristics(temp_memory_file):
    """Verify ExperienceMemoryVault records newly learned rules and prevents duplicate bloat."""
    vault = ExperienceMemoryVault(temp_memory_file)
    initial_count = len(vault.load_heuristics())

    # Add a new unique heuristic
    success = vault.record_heuristic(
        domain="novel_prose",
        rule="When describing celestial weapons (divyastras), focus on the unnatural sudden vacuum of sound before detonation.",
        source_project="The Curse of Karna"
    )
    assert success is True
    assert len(vault.load_heuristics()) == initial_count + 1

    # Adding the identical rule again should return False (no duplicate bloat)
    duplicate_success = vault.record_heuristic(
        domain="novel_prose",
        rule="When describing celestial weapons (divyastras), focus on the unnatural sudden vacuum of sound before detonation.",
        source_project="The Curse of Karna"
    )
    assert duplicate_success is False
    assert len(vault.load_heuristics()) == initial_count + 1


@pytest.mark.asyncio
async def test_self_critique_and_refinement_cycle(temp_memory_file, sample_bible):
    """Verify SelfImprovementEngine audits prose, executes refinement pass when below threshold, and stores new principles."""
    vault = ExperienceMemoryVault(temp_memory_file)
    improver = SelfImprovementEngine(vault)

    draft_chapter = NovelChapter(
        chapter_number=1,
        title="The Sun's Son",
        prose="Karna looked at his chariot. He felt sad. The wheel was stuck in the mud. He tried to pull it out.",
        summary="Karna struggles with his chariot wheel.",
        word_count=23
    )

    # Mock initial critique verdict: low score (6.0), detected flaws, and a learned principle
    mock_critique_1 = SelfCritiqueVerdict(
        quality_score=6.0,
        passed_rubric=False,
        detected_weaknesses=["Lacks sensory immersion", "Tells emotion ('felt sad') instead of showing visceral somatic cues"],
        continuity_violations=[],
        actionable_improvements=["Ground sorrow in physical tension: mud clinging to bare calloused hands, veins bulging in temples"],
        learned_principles=["Never use flat emotional verbs like 'felt sad'; depict the physical toll on the warrior's body"]
    )

    # Mock elevated refined chapter
    mock_refined_chapter = NovelChapter(
        chapter_number=1,
        title="The Sun's Son",
        prose=(
            "The red soil of Kurukshetra drank the sweat from Karna's brow as he hauled against the iron rim of the chariot wheel. "
            "His bare fingers, once delicate enough to release seven arrows in a single heartbeat, slipped against the slick clay. "
            "The axle groaned under the weight of cosmic destiny. A sharp metallic pang vibrated up his spine, but no cry broke from his cracked lips. "
            "The sun, his divine father, beat mercilessly against his bare shoulders, illuminating the scar tissue where celestial armor had once fused to his flesh. "
            "He was alone, abandoned by the gods, yet his stance remained unbroken."
        ),
        summary="Karna strains against destiny at his sunken chariot wheel.",
        word_count=98
    )

    # Mock second critique post-refinement: high score (9.2)
    mock_critique_2 = SelfCritiqueVerdict(
        quality_score=9.2,
        passed_rubric=True,
        detected_weaknesses=[],
        continuity_violations=[],
        actionable_improvements=[],
        learned_principles=["Highlight the father-son solar motif when describing Karna's endurance"]
    )

    with patch.object(improver, "self_critique_prose", side_effect=[mock_critique_1, mock_critique_2]), \
         patch.object(improver, "refine_novel_chapter", new_callable=AsyncMock, return_value=mock_refined_chapter):

        final_chapter, report = await improver.execute_self_improvement_prose_cycle(sample_bible, draft_chapter)

        # 1. Assert quality elevated
        assert report.initial_score == 6.0
        assert report.final_score == 9.2
        assert report.iterations == 2
        assert "red soil of Kurukshetra" in final_chapter.prose

        # 2. Assert learned principles were permanently stored in memory vault
        heuristics = vault.load_heuristics("novel_prose")
        rules = [h.rule for h in heuristics]
        assert any("flat emotional verbs" in r for r in rules)
        assert any("solar motif" in r for r in rules)


@pytest.mark.asyncio
async def test_orchestrator_records_self_improvement_audit_trail(tmp_path, sample_bible):
    """Verify CreativeOrchestrator tracks self_improvement_reports in CreativeProject."""
    vault = CreativeVault(tmp_path / "vault")
    orchestrator = CreativeOrchestrator(vault)

    mock_chapter = NovelChapter(
        chapter_number=1,
        title="The Sun's Son",
        prose="The iron wheels groaned in the crimson dust...",
        summary="Karna faces destiny.",
        word_count=8
    )
    mock_report = SelfImprovementReport(
        agent_name="NovelistAgent",
        target_artifact="Chapter 1: The Sun's Son",
        initial_score=7.0,
        final_score=9.0,
        iterations=2,
        new_heuristics_stored=["Show mud and iron texture"]
    )

    with patch.object(orchestrator.showrunner, "create_story_bible", new_callable=AsyncMock, return_value=sample_bible), \
         patch.object(orchestrator.novelist, "write_chapter", new_callable=AsyncMock, return_value=mock_chapter), \
         patch.object(orchestrator.self_improver, "execute_self_improvement_prose_cycle", new_callable=AsyncMock, return_value=(mock_chapter, mock_report)), \
         patch.object(orchestrator.cinematographer, "deconstruct_chapter_to_scenes", new_callable=AsyncMock, return_value=[]):

        seed = StorySeed(prompt="The Curse of Karna", genre=StoryGenre.MYTHOLOGICAL_EPIC)
        project = await orchestrator.synthesize_story(seed)

        assert len(project.self_improvement_reports) == 1
        assert project.self_improvement_reports[0].initial_score == 7.0
        assert project.self_improvement_reports[0].final_score == 9.0
        assert project.self_improvement_reports[0].agent_name == "NovelistAgent"
