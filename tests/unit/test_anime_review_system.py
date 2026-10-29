import pytest
from pathlib import Path
from engine.anime.models import (
    AnimeEpisodeSource,
    AnimeSceneCut,
    ReviewStoryBeat,
    AnimeReviewConfig,
    ActType,
)
from engine.anime.story_generator import AnimeReviewStoryEngine


def test_anime_models_validation():
    source = AnimeEpisodeSource(
        source_uri="test.mp4",
        series_title="Solo Leveling",
        episode_number=12.0,
        episode_title="Arise",
        duration_sec=1440.0,
        width=1920,
        height=1080,
        fps=24.0,
    )
    assert source.series_title == "Solo Leveling"
    assert source.episode_number == 12.0
    assert source.duration_sec == 1440.0


def test_story_engine_generation():
    source = AnimeEpisodeSource(
        source_uri="test.mp4",
        series_title="Demon Slayer",
        episode_number=1.0,
        episode_title="Cruelty",
        duration_sec=1200.0,
    )
    dummy_cuts = [
        AnimeSceneCut(
            cut_id=f"cut_{i:03d}",
            sequence=i,
            start_sec=float(i * 3),
            end_sec=float(i * 3 + 3),
            duration_sec=3.0,
        )
        for i in range(1, 21)
    ]
    engine = AnimeReviewStoryEngine()
    beats = engine.generate_review_script(source, dummy_cuts)
    assert len(beats) == 8
    # Act types must cover Hook, Development, Battle, Climax, and Verdict
    act_types = [b.act_type for b in beats]
    assert ActType.HOOK_AND_SETUP in act_types
    assert ActType.PLOT_DEVELOPMENT in act_types
    assert ActType.KEY_BATTLE in act_types
    assert ActType.TURNING_POINT_CLIMAX in act_types
    assert ActType.REVIEWER_VERDICT in act_types
    # Every beat must have at least 1 assigned cut
    for b in beats:
        assert len(b.assigned_cut_ids) >= 1


def test_story_engine_custom_outline():
    source = AnimeEpisodeSource(
        source_uri="test.mp4",
        series_title="Jujutsu Kaisen",
        episode_number=5.0,
        duration_sec=1200.0,
    )
    dummy_cuts = [
        AnimeSceneCut(
            cut_id=f"cut_{i:03d}",
            sequence=i,
            start_sec=float(i * 4),
            end_sec=float(i * 4 + 4),
            duration_sec=4.0,
        )
        for i in range(1, 11)
    ]
    custom_lines = [
        "Megumi confronts the special grade curse inside the detention center.",
        "Sukuna takes over Itadori's body and tears out his heart.",
        "The battle ends in tragedy as Megumi realizes Itadori cannot switch back.",
    ]
    engine = AnimeReviewStoryEngine()
    beats = engine.generate_review_script(source, dummy_cuts, custom_outline=custom_lines)
    assert len(beats) == 3
    assert beats[0].voiceover_text == custom_lines[0]
    assert beats[1].voiceover_text == custom_lines[1]
    assert beats[2].voiceover_text == custom_lines[2]


def test_ducking_volume_calculation():
    # -18 dB should equal approximately 0.12589 amplitude
    duck_db = -18.0
    vol = 10.0 ** (duck_db / 20.0)
    assert 0.125 <= vol <= 0.126

    # 0 dB should equal 1.0 amplitude
    assert 10.0 ** (0.0 / 20.0) == 1.0
