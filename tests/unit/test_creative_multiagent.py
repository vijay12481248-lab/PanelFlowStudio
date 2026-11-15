"""Unit and integration tests for the Creative Multi-Agent System (Antigravity SDK & Local LLM)."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from engine.creative.schema import (
    StoryGenre,
    VisualStyle,
    StorySeed,
    CharacterProfile,
    WorldLore,
    ChapterBeat,
    ChapterOutline,
    StoryBible,
    NovelChapter,
    EditorialCritique,
    CinematicShot,
    CinematicScene,
    CreativeProject,
)
from engine.creative.vault import CreativeVault
from engine.creative.agents import PromptCompilerAgent
from engine.creative.orchestrator import CreativeOrchestrator
from fastapi.testclient import TestClient
from fastapi import FastAPI
from engine.api.routers import creative


@pytest.fixture
def temp_vault_dir(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    chars_file = vault / "characters.json"
    initial_chars = [
        {
            "id": "char_existing_001",
            "name": "Old Sentinel",
            "role": "Guardian",
            "image": "sentinel.png",
            "description": "Ancient guardian in weathered iron armor.",
            "tag": "<Picture 1>",
        }
    ]
    chars_file.write_text(json.dumps(initial_chars), encoding="utf-8")
    return vault


@pytest.fixture
def sample_bible():
    return StoryBible(
        title="MAHABHARATA: THE FALL OF BHISHMA",
        logline="On the tenth day of Kurukshetra, the grand sire of the Kuru dynasty must confront his own vow and destiny against Arjuna and Shikhandi.",
        thematic_core="Dharma, duty versus righteousness, destiny, tragic grandeur",
        emotional_arc="Solemn resolution leading to profound cosmic acceptance",
        lore=WorldLore(
            world_name="Ancient Aryavarta",
            era_or_timeline="Dvapara Yuga - Kurukshetra War",
            setting_overview="Dusty blood-soaked battlefield strewn with splintered chariots, golden armors, and divine arrows under a crimson dusk sky.",
            rules=[
                "Bhishma can only die by his own choice (Iccha Mrityu)",
                "Bhishma will lower his bow before Shikhandi",
                "Divyastras invoke celestial cosmic fires"
            ],
            key_factions=["Pandavas", "Kauravas"]
        ),
        characters=[
            CharacterProfile(
                id="bhishma_pitamaha",
                name="Bhishma Pitamaha",
                role="Grand Patriarch / Legendary Warrior",
                visual_tags="venerable 100-year-old warrior, flowing silver hair, snow-white beard, golden breastplate with sun crest, regal weathered features",
                personality="Stoic, honorable, carrying an unbearable burden of ancient oaths",
                signature_item="Golden bow of celestial light, nine-pointed celestial crown",
                facial_features="Piercing sorrowful amber eyes, deep laugh lines carved with grief",
                tag="<Picture 2>"
            ),
            CharacterProfile(
                id="arjuna_partha",
                name="Arjuna (Partha)",
                role="Pandava Champion Archer",
                visual_tags="youthful muscular warrior, dark skin, silver-embossed leather archer armguards, crimson silk sash",
                personality="Conflicted warrior driven by duty, weeping internally as he draws against his grandfather",
                signature_item="Gandiva divine longbow, celestial quiver",
                tag="<Picture 3>"
            )
        ],
        chapter_outlines=[
            ChapterOutline(
                chapter_number=1,
                title="The Twilight of the Patriarch",
                epigraph="O Son of Kunti, when duty and love war within, let righteous action be the chariot that carries thee.",
                dramatic_premise="Bhishma stands on the arrow-swept sands of Kurukshetra, preparing for the tenth day.",
                beats=[
                    ChapterBeat(
                        beat_index=1,
                        title="Dawn Over the Chariots",
                        narrative_summary="The conch shells sound across Kurukshetra as the mist lifts.",
                        emotional_shift="Apprehensive stillness to fierce solemn readiness",
                        characters_present=["bhishma_pitamaha"]
                    ),
                    ChapterBeat(
                        beat_index=2,
                        title="The Chariot Approaches",
                        narrative_summary="Arjuna's white chariot drawn by Krishna sweeps through the dust.",
                        emotional_shift="Ache of familial reverence meeting inexorable fate",
                        characters_present=["bhishma_pitamaha", "arjuna_partha"]
                    )
                ]
            )
        ]
    )


def test_schema_contracts(sample_bible):
    """Verify all creative schema contracts validate properly."""
    assert sample_bible.title == "MAHABHARATA: THE FALL OF BHISHMA"
    assert len(sample_bible.characters) == 2
    assert sample_bible.lore.rules[0] == "Bhishma can only die by his own choice (Iccha Mrityu)"

    chapter = NovelChapter(
        chapter_number=1,
        title="The Twilight of the Patriarch",
        epigraph=sample_bible.chapter_outlines[0].epigraph,
        prose="The crimson sun hung suspended over the red plains of Kurukshetra like a bleeding eye...",
        summary="Bhishma greets the 10th dawn of battle.",
        word_count=14,
        emotional_peak="The silence before the first divine arrow is drawn."
    )
    assert chapter.word_count == 14
    assert "crimson sun" in chapter.prose


def test_vault_character_sync_and_persistence(temp_vault_dir, sample_bible):
    """Verify CreativeVault syncs characters to characters.json without duplicating."""
    vault = CreativeVault(temp_vault_dir)

    # Initial state has 1 character
    initial = vault.load_characters()
    assert len(initial) == 1
    assert initial[0]["id"] == "char_existing_001"

    # Sync sample bible characters (2 new characters)
    added = vault.sync_characters_from_bible(sample_bible.characters)
    assert added == 2

    # Verify updated characters.json
    updated = vault.load_characters()
    assert len(updated) == 3
    ids = [c["id"] for c in updated]
    assert "bhishma_pitamaha" in ids
    assert "arjuna_partha" in ids

    # Second sync should add 0 duplicates
    added_second = vault.sync_characters_from_bible(sample_bible.characters)
    assert added_second == 0


def test_prompt_compiler_h3_and_qwen(sample_bible):
    """Verify PromptCompilerAgent produces valid MiniMax H3 6-heading schemas and Qwen art prompts."""
    compiler = PromptCompilerAgent()
    protagonist = sample_bible.characters[0]

    shot = CinematicShot(
        shot_index=1,
        scene_index=1,
        title="Shot 1: The Patriarch's Resolve",
        shot_type="Low-Angle Hero",
        duration=5.2,
        workflow="reference",
        camera_movement="Slow sweeping upward tilt from the bloodstained sand to Bhishma's stern countenance.",
        subject_description="Bhishma stands tall on his chariot, white beard whipping in the dry wind, golden bow raised.",
        environmental_details="Scattered broken javelins, smoking bronze braziers, churning dust under iron wheels.",
        lighting_and_atmosphere="High-contrast warm amber dawn piercing through thick smoke plumes.",
        soundscape="Distant blowing of war conches, heavy wind howl, flapping royal pennants. Strictly no speech.",
        non_diegetic_music="Resonant Indian percussion and mournful flute crescendo.",
    )

    # Compile H3 prompt
    h3_prompt = compiler.compile_h3_prompt(shot, protagonist)
    assert "subject_definitions:" in h3_prompt
    assert "summary:" in h3_prompt
    assert "retention_analysis:" in h3_prompt
    assert "detailed_description:" in h3_prompt
    assert "camera_movement:" in h3_prompt
    assert "overall_soundscape:" in h3_prompt
    assert "non_diegetic_music:" in h3_prompt
    assert "Bhishma Pitamaha" in h3_prompt

    # Compile Qwen Image 2.1 art prompt
    qwen_prompt = compiler.compile_qwen_art_prompt(shot, protagonist)
    assert "Masterpiece cinematic film still" in qwen_prompt
    assert "venerable 100-year-old warrior" in qwen_prompt
    assert "8k resolution" in qwen_prompt


def test_vault_project_save_and_screenplay_export(temp_vault_dir, sample_bible):
    """Verify CreativeVault saves project JSON, markdown chapters, and exports screenplay blueprint."""
    vault = CreativeVault(temp_vault_dir)
    compiler = PromptCompilerAgent()
    protagonist = sample_bible.characters[0]

    shot1 = CinematicShot(
        shot_index=1,
        scene_index=1,
        title="The Conches of Kurukshetra",
        shot_type="Wide Establishing",
        camera_movement="High-angle sweeping crane across chariot ranks.",
        subject_description="Armored legions assembled in diamond battle formation.",
        environmental_details="Endless expanse of red plains under blazing morning sky.",
        lighting_and_atmosphere="Harsh golden morning sunlight casting long shadows.",
        soundscape="Rumble of distant chariot wheels and conch blare.",
        non_diegetic_music="Deep resonant battlefield war drums."
    )
    shot2 = CinematicShot(
        shot_index=2,
        scene_index=1,
        title="The Patriarch's Gaze",
        shot_type="Medium Tracking",
        camera_movement="Steadicam push-in toward chariot.",
        subject_description="Bhishma grips his divine bow with sorrowful resolve.",
        environmental_details="Silver standards fluttering vigorously against the sky.",
        lighting_and_atmosphere="Warm rim light accentuating silver hair.",
        soundscape="Wind flap and armor clinking.",
        non_diegetic_music="Haunting solitary string melody."
    )

    scene1 = CinematicScene(
        scene_index=1,
        id="scene_1",
        name="Scene 1: The Gathering of Destiny",
        description="The two grand armies stare across the divide as Bhishma takes his chariot to the vanguard.",
        shots=[shot1, shot2]
    )

    compiler.process_scenes([scene1], protagonist)

    chapter = NovelChapter(
        chapter_number=1,
        title="The Twilight of the Patriarch",
        epigraph=sample_bible.chapter_outlines[0].epigraph,
        prose="The crimson sun rose above Kurukshetra, illuminating fifty thousand bronze spear-tips...",
        summary="Bhishma leads the army on the tenth morning.",
        word_count=500
    )

    project = CreativeProject(
        project_id="mahabharata_test_001",
        title=sample_bible.title,
        seed=StorySeed(prompt="Mahabharata tenth day of war", genre=StoryGenre.MYTHOLOGICAL_EPIC),
        bible=sample_bible,
        chapters=[chapter],
        scenes=[scene1],
        parent_path="D:\\panelflow_studio\\Kurukshetra"
    )

    saved_dir = vault.save_project(project)
    assert (saved_dir / "project.json").exists()
    assert (saved_dir / "chapter_01.md").exists()

    # Verify exported screenplay
    screenplay_file = temp_vault_dir / "screenplay_mahabharata_the_fall_of_bhishma.json"
    assert screenplay_file.exists()

    with open(screenplay_file, "r", encoding="utf-8") as f:
        blueprint = json.load(f)

    assert blueprint["title"] == "MAHABHARATA: THE FALL OF BHISHMA"
    assert len(blueprint["folders"]) == 1
    assert blueprint["folders"][0]["id"] == "scene_1"
    assert blueprint["folders"][0]["shot_indices"] == [1, 2]
    assert len(blueprint["scenes"]) == 2
    assert blueprint["scenes"][0]["workflow"] == "reference"
    assert blueprint["scenes"][1]["workflow"] == "sliding_window"
    assert "subject_definitions:" in blueprint["scenes"][0]["prompt"]


@pytest.mark.asyncio
async def test_orchestrator_pipeline_mocked(temp_vault_dir, sample_bible):
    """Verify CreativeOrchestrator coordinates agents, synthesizes chapters, and persists results."""
    vault = CreativeVault(temp_vault_dir)
    orchestrator = CreativeOrchestrator(vault)

    mock_chapter = NovelChapter(
        chapter_number=1,
        title="The Twilight of the Patriarch",
        prose="Arrows of celestial gold arched across the heavens. Bhishma stood motionless, his heart heavy with destiny...",
        summary="Bhishma prepares for the climactic battle.",
        word_count=20
    )

    mock_critique = EditorialCritique(
        score=9,
        continuity_pass=True,
        critique_notes=["Superb tragic gravitas", "Sensory descriptions are vivid"],
        polished_prose=mock_chapter.prose
    )

    mock_shots = [
        CinematicShot(
            shot_index=1,
            scene_index=1,
            title="Dawn at Kurukshetra",
            shot_type="Wide Establishing",
            camera_movement="High-angle sweeping crane.",
            subject_description="Grand armies assembled.",
            environmental_details="Red dust fields.",
            lighting_and_atmosphere="Crimson dawn light.",
            soundscape="Heavy wind, conch blares.",
            non_diegetic_music="Mournful war drums."
        )
    ]
    mock_scenes = [
        CinematicScene(
            scene_index=1,
            id="scene_1",
            name="Scene 1: The Gathering",
            description="Armies line up at dawn.",
            shots=mock_shots
        )
    ]

    from engine.creative.schema import SelfImprovementReport
    mock_report = SelfImprovementReport(
        agent_name="NovelistAgent",
        target_artifact="Chapter 1: The Twilight of the Patriarch",
        initial_score=8.5,
        final_score=9.5,
        iterations=1,
    )

    with patch.object(orchestrator.showrunner, "create_story_bible", new_callable=AsyncMock, return_value=sample_bible), \
         patch.object(orchestrator.novelist, "write_chapter", new_callable=AsyncMock, return_value=mock_chapter), \
         patch.object(orchestrator.self_improver, "execute_self_improvement_prose_cycle", new_callable=AsyncMock, return_value=(mock_chapter, mock_report)), \
         patch.object(orchestrator.cinematographer, "deconstruct_chapter_to_scenes", new_callable=AsyncMock, return_value=mock_scenes):

        seed = StorySeed(
            prompt="Mahabharata: Fall of Bhishma",
            genre=StoryGenre.MYTHOLOGICAL_EPIC,
            visual_style=VisualStyle.CINEMATIC_PHOTO,
            target_chapters=1
        )

        project = await orchestrator.synthesize_story(seed)
        assert project.title == "MAHABHARATA: THE FALL OF BHISHMA"
        assert len(project.chapters) == 1
        assert len(project.scenes) == 1
        assert len(project.scenes[0].shots) == 1
        assert project.scenes[0].shots[0].workflow == "reference"
        assert "subject_definitions:" in project.scenes[0].shots[0].prompt


def test_creative_api_endpoints(temp_vault_dir, sample_bible):
    """Test FastAPI router endpoints for creative projects."""
    app = FastAPI()
    app.include_router(creative.router)

    # Point the router's vault to temp_vault_dir
    creative.vault = CreativeVault(temp_vault_dir)
    creative.orchestrator = CreativeOrchestrator(creative.vault)

    # Pre-save a project in the vault
    chapter = NovelChapter(
        chapter_number=1,
        title="Chapter 1",
        prose="Prose text...",
        summary="Summary...",
        word_count=2
    )
    project = CreativeProject(
        project_id="proj_api_test",
        title="API TEST PROJECT",
        seed=StorySeed(prompt="Test Seed"),
        bible=sample_bible,
        chapters=[chapter],
        scenes=[]
    )
    creative.vault.save_project(project)

    client = TestClient(app)

    # 1. GET /api/creative/projects
    resp = client.get("/api/creative/projects")
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) >= 1
    assert any(p["project_id"] == "proj_api_test" for p in projects)

    # 2. GET /api/creative/project/proj_api_test
    resp = client.get("/api/creative/project/proj_api_test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "API TEST PROJECT"
    assert len(data["chapters"]) == 1

    # 3. POST /api/creative/export_storyboard
    resp = client.post("/api/creative/export_storyboard?project_id=proj_api_test")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
