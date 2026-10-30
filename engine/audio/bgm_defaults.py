"""Default background music, shared by legacy autopilot and the narration projection."""
from __future__ import annotations


def default_bgm_tracks(existing: list[dict] | None = None) -> list[dict]:
    """The project's own tracks if it has any, else the cinematic default."""
    if existing:
        return existing
    return [{"id": "bgm_default", "audio_url": "/assets/demo/crystal_resonance_bgm.mp3",
             "volume": 0.35, "ducking": -14.0}]
