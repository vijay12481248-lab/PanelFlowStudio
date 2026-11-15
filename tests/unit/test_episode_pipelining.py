"""Unit tests for WP-3.3: Hardware-Aware Pipelining and CPU/GPU Overlapping."""
import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.anime.review.channels import ChannelPreset
from engine.original import episode, video
from engine.original.models import Bible, Character, OriginalStory, Panel, Premise, Scene


def make_test_story():
    mira = Character(
        id="mira",
        name="Mira",
        role="protagonist",
        age_group="child",
        look="short brown hair, green eyes",
        personality="curious",
    )
    bible = Bible(
        premise=Premise(title="T", genre="bedtime", logline="L", tone="T", setting="S"),
        characters=[mira],
        locations=[],
    )
    panels = [
        Panel(
            id="p001",
            scene_id="sc01",
            shot="medium",
            angle="eye_level",
            location_id="attic",
            character_ids=["mira"],
            action="Mira smiles.",
            caption="Mira looked out the window.",
        ),
        Panel(
            id="p002",
            scene_id="sc01",
            shot="close",
            angle="eye_level",
            location_id="attic",
            character_ids=["mira"],
            action="Mira waves.",
            caption="The stars shone brightly in the night sky.",
        ),
    ]
    return OriginalStory(
        bible=bible,
        scenes=[
            Scene(
                id="sc01",
                location_id="attic",
                character_ids=["mira"],
                summary="S",
                mood="M",
            )
        ],
        panels=panels,
    )


def test_pre_synthesize_episode_audio_async_runs_in_background_thread(tmp_path, monkeypatch):
    story = make_test_story()
    ws = tmp_path / "ep001"
    ws.mkdir(parents=True, exist_ok=True)

    channel = ChannelPreset(
        id="bedtime_ch",
        name="Bedtime Tales",
        voice="af_bella",
        voice_rate=1.0,
        music_path="",
    )

    synthesized_panels = []

    def mock_voice_panel(tts, panel, narrator, chars, fps, out):
        synthesized_panels.append(panel.id)
        out.write_bytes(b"RIFFdummywavdata")
        return 1.5

    monkeypatch.setattr("engine.original.video.voice_panel", mock_voice_panel)

    # Launch async pre-synthesis
    thread = episode._pre_synthesize_episode_audio_async(
        story=story,
        ws=ws,
        channel=channel,
        is_cancelled=lambda: False,
    )

    assert isinstance(thread, threading.Thread)
    assert thread.name == "kokoro_tts_overlap"
    assert thread.daemon is True

    # Join and verify completion
    thread.join(timeout=10.0)
    assert not thread.is_alive()

    assert (ws / "voice" / "p001.wav").exists()
    assert (ws / "voice" / "p002.wav").exists()
    assert synthesized_panels == ["p001", "p002"]

    meta_path = ws / "video_meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert "p001" in meta
    assert "voice" in meta["p001"]
    assert "p002" in meta
    assert "voice" in meta["p002"]


def test_pre_synthesize_episode_audio_async_handles_cancellation(tmp_path, monkeypatch):
    story = make_test_story()
    ws = tmp_path / "ep002"
    ws.mkdir(parents=True, exist_ok=True)

    channel = ChannelPreset(
        id="ch",
        name="Ch",
        voice="af_bella",
        voice_rate=1.0,
    )

    cancelled = True
    thread = episode._pre_synthesize_episode_audio_async(
        story=story,
        ws=ws,
        channel=channel,
        is_cancelled=lambda: cancelled,
    )
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    # When cancelled immediately, no panel audio was synthesized
    assert not (ws / "voice" / "p001.wav").exists()
