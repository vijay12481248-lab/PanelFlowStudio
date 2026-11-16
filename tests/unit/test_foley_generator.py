"""Unit and integration tests for ChronoFlow Sound Design & Automatic Foley Generation."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.api.routers.audio_studio import get_engine
from engine.audio.studio.foley_generator import (
    auto_populate_sound_plan,
    detect_action_cues,
    detect_ambience_kind,
    parse_scene_audio_cues,
)
from engine.audio.studio.plan import Cue, SoundPlan
from engine.audio.studio.sources.ambient_synth import (
    AmbientSynthProvider,
    render_fire,
    render_night,
    render_rain,
    render_room_tone,
    render_thunder,
    render_wind,
)


def test_detect_ambience_kind():
    assert detect_ambience_kind("A heavy rain storm outside the temple")[0] == "rain"
    assert detect_ambience_kind("Howling wind over the snowy mountain peaks")[0] == "wind"
    assert detect_ambience_kind("Sitting by the warm campfire under the trees")[0] == "fire"
    assert detect_ambience_kind("A quiet moonlit night with crickets chirping")[0] == "night"
    assert detect_ambience_kind("Sudden crack of lightning and thunder")[0] == "thunder"
    assert detect_ambience_kind("Inside the ancient castle hallway")[0] == "room_tone"
    # Fallback to room tone
    assert detect_ambience_kind("Two warriors standing face to face")[0] == "room_tone"


def test_detect_action_cues():
    cues = detect_action_cues("The warrior strikes with his sword, clashing blades against the dark knight")
    assert len(cues) >= 1
    assert any(c[1] == "blade_clash" for c in cues)

    cues2 = detect_action_cues("A massive punch causes a heavy impact, followed by an explosion")
    assert len(cues2) >= 2
    kinds = [c[1] for c in cues2]
    assert "heavy_impact" in kinds
    assert "explosion" in kinds


def test_parse_scene_audio_cues():
    scene = {
        "prompt": "Fierce storm with rain washing over the stone courtyard, swords clash violently",
        "narration": "They fought for the destiny of the realm.",
        "duration": 4.0,
    }
    cues = parse_scene_audio_cues(scene, shot_index=1, t_start=0.0, t_end=4.0, fps=24.0)

    # Must contain ambience, action foley, and dialogue
    tracks = [c.track for c in cues]
    assert "ambience" in tracks
    assert "foley" in tracks
    assert "dialogue" in tracks

    amb_cue = next(c for c in cues if c.track == "ambience")
    assert amb_cue.kind == "rain"
    assert amb_cue.t_in == 0.0
    assert amb_cue.t_out == 4.0
    assert amb_cue.fade_in > 0.0

    foley_cue = next(c for c in cues if c.track == "foley")
    assert foley_cue.kind == "blade_clash"
    assert foley_cue.t_in > 0.0


def test_ambient_synth_rendering():
    sr = 48000
    for render_fn in (render_rain, render_wind, render_thunder, render_fire, render_night, render_room_tone):
        audio = render_fn(duration=1.0, seed=42, sr=sr)
        assert isinstance(audio, np.ndarray)
        assert len(audio) == sr
        assert np.max(np.abs(audio)) > 0.01
        assert np.max(np.abs(audio)) <= 1.0


def test_ambient_synth_provider_find(tmp_path: Path):
    provider = AmbientSynthProvider()
    assert provider.availability().ok is True

    plan = SoundPlan(
        id="test_ambient_plan",
        video_path="dummy.mp4",
        fps=24.0,
        duration=10.0,
    )
    cue = Cue(
        id="cue_rain_1",
        track="ambience",
        kind="rain",
        intent="heavy rain shower",
        t_in=0.0,
        t_out=3.0,
    )

    cands = provider.find(cue, out_dir=tmp_path, plan=plan, limit=2)
    assert len(cands) == 2
    for c in cands:
        assert Path(c.path).exists()
        assert Path(c.path).stat().st_size > 1000
        assert c.provider == "ambient"
        assert c.provenance.licence == "CC0"


def test_auto_populate_sound_plan_end_to_end(tmp_path: Path):
    engine = get_engine()
    plan = engine.create_plan(
        video_path=tmp_path / "sequence.mp4",
        fps=24.0,
        duration=9.0,
    )

    scenes = [
        {
            "prompt": "Night storm with heavy rain, hero running fast across gravel",
            "narration": "He had only minutes remaining.",
            "duration": 3.0,
        },
        {
            "prompt": "Hero unsheathes glowing sword, sharp blade ring in the dark",
            "narration": "",
            "duration": 3.0,
        },
        {
            "prompt": "A sudden detonation explosion tears through the wall",
            "narration": "The stronghold was breached.",
            "duration": 3.0,
        },
    ]

    populated = auto_populate_sound_plan(plan.id, scenes, auto_source=True)
    assert len(populated.cues) >= 6

    # Verify that procedural cues were automatically sourced with valid files
    ready_cues = [c for c in populated.cues if c.status == "ready"]
    assert len(ready_cues) >= 4

    for c in ready_cues:
        chosen = c.chosen()
        assert chosen is not None
        assert Path(chosen.path).exists()
        assert Path(chosen.path).stat().st_size > 500


def test_api_auto_foley_endpoint(tmp_path: Path):
    engine = get_engine()
    plan = engine.create_plan(video_path=tmp_path / "vid.mp4", fps=24.0, duration=6.0)

    client = TestClient(app)
    scenes = [
        {"prompt": "Campfire burning in the night woods", "duration": 3.0},
        {"prompt": "Heavy impact slam on wooden door", "duration": 3.0},
    ]

    res = client.post(
        f"/api/audio/studio/plans/{plan.id}/auto_foley",
        json={"scenes": scenes, "auto_source": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["plan_id"] == plan.id
    assert data["cue_count"] >= 3
    assert "Auto-Designed Foley" in data["note"]
