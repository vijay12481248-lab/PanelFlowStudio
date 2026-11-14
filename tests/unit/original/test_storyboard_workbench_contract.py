"""Unit tests for Original Story Storyboard Workbench data contract and serialization."""

import pytest
from engine.api.routers.original import get_storyboard_workbench, _resolve_story_ws, STORY_ROOT
from fastapi import HTTPException


def test_storyboard_workbench_contract_mahabharata():
    """Verify that get_storyboard_workbench correctly parses mahabharata_adi_parva workspace."""
    ws = _resolve_story_ws("mahabharata_adi_parva")
    assert ws.exists(), f"Expected workspace {ws} to exist"

    data = get_storyboard_workbench("mahabharata_adi_parva")
    assert data.slug == "mahabharata_adi_parva"
    assert "Mahabharata" in data.title
    assert data.genre == "mythology"
    assert data.total_panels == 18
    assert len(data.beats) == 18

    # Verify beat fields
    first_beat = data.beats[0]
    assert first_beat.panel_id == "p001"
    assert first_beat.order == 1
    assert first_beat.shot in ("wide", "extreme_wide", "medium", "close_up")
    assert len(first_beat.caption) > 0
    assert first_beat.status in ("accept", "needs_review", "unverified")
    assert first_beat.audio_duration > 0.0
    assert "p001" in first_beat.image_url


def test_storyboard_workbench_contract_godfall():
    """Verify that get_storyboard_workbench correctly parses godfall_ep1 workspace."""
    ws = _resolve_story_ws("godfall_ep1")
    assert ws.exists(), f"Expected workspace {ws} to exist"

    data = get_storyboard_workbench("godfall_ep1")
    assert data.slug == "godfall_ep1"
    assert "GODFALL" in data.title
    assert data.total_panels == 26
    assert len(data.beats) == 26

    # Verify first beat
    b0 = data.beats[0]
    assert b0.panel_id == "p01"
    assert b0.order == 1
    assert len(b0.caption) > 0
    assert b0.audio_duration > 0.0


def test_storyboard_workbench_missing_workspace():
    """Verify that requesting a non-existent slug raises 404 HTTPException."""
    with pytest.raises(HTTPException) as exc_info:
        get_storyboard_workbench("non_existent_story_slug_xyz_12345")
    assert exc_info.value.status_code == 404


def test_somatic_archetypes_dictionary():
    """Verify that all 6 Somatic Emotional Archetypes are defined with micro-anatomy, posture, and anti-stoic negatives."""
    from engine.chronoflow.somatic import SOMATIC_ARCHETYPES
    expected_archetypes = [
        "visceral_pain",
        "lethal_wrath",
        "dread_terror",
        "cruel_arrogance",
        "desperate_exhaustion",
        "sovereign_awe",
    ]
    for key in expected_archetypes:
        assert key in SOMATIC_ARCHETYPES, f"Missing archetype {key}"
        arch = SOMATIC_ARCHETYPES[key]
        assert "title" in arch
        assert len(arch["micro_anatomy"]) > 10
        assert len(arch["posture"]) > 10
        assert "calm face" in arch["anti_stoic_negative"] or "stoic" in arch["anti_stoic_negative"] or "frown" in arch["anti_stoic_negative"]

