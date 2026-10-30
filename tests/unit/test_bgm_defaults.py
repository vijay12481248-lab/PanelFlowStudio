"""The shared default-BGM helper returns exactly what legacy autopilot used to inline."""
from engine.audio.bgm_defaults import default_bgm_tracks

# Copied verbatim from the legacy autopilot block before it was extracted.
LEGACY_LITERAL = [{"id": "bgm_default", "audio_url": "/assets/demo/crystal_resonance_bgm.mp3",
                   "volume": 0.35, "ducking": -14.0}]


def test_default_bgm_tracks_matches_legacy_literal():
    assert default_bgm_tracks([]) == LEGACY_LITERAL
    assert default_bgm_tracks(None) == LEGACY_LITERAL


def test_existing_tracks_are_kept_and_result_is_a_fresh_copy():
    mine = [{"id": "mine"}]
    assert default_bgm_tracks(mine) == mine
    default_bgm_tracks([])[0]["volume"] = 9
    assert default_bgm_tracks([]) == LEGACY_LITERAL


def test_legacy_autopilot_calls_the_helper_not_an_inline_literal():
    from pathlib import Path
    src = (Path(__file__).parents[2] / "engine" / "pipeline" / "autopilot.py").read_text(encoding="utf-8")
    assert "crystal_resonance_bgm.mp3\"," not in src and "default_bgm_tracks(" in src
