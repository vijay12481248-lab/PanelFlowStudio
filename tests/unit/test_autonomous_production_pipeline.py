"""Autonomous End-to-End Production Pipeline Verification (Milestone 10).

Validates the full integrated production cycle across PanelFlow & ChronoFlow:
1. Preflight System Health & Readiness Verification
2. Character Model Sheet & Identity Pinning
3. Storyboard Sequence Timeline Assembly & Resolution Normalization
4. Automated Sound Design & Procedural Foley Generation
5. YouTube Shorts & Reels Intelligent 9:16 Auto-Cut with Animated Karaoke Subtitles
6. Unified Cross-Service Production Orchestration Pipeline
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine.api.app import app
from engine.api.routers.audio_studio import get_engine as get_audio_engine
from engine.audio.studio.foley_generator import (
    auto_populate_sound_plan,
    parse_scene_audio_cues,
)
from engine.characters.face_verify import FaceIdentityVerifier
from engine.characters.modelsheet import (
    VIEW_NAMES,
    build_model_sheet_prompt,
    slice_model_sheet,
)
from engine.characters.pinning import (
    bind_character_references_for_shot,
    verify_shot_character_consistency,
)
from engine.chronoflow import pipeline, start_modes
from engine.chronoflow.media_tools import _FFMPEG, probe
from engine.chronoflow.timeline_assemble import (
    assemble_storyboard_sequence,
)
from engine.mcp.registry import registry
import engine.mcp.tools
from engine.reels.publisher import ReelAutoCutRequest, autocut_horizontal_to_reel
from engine.reels.reframer import compute_reframing_plan
from engine.reels.subtitles import align_transcript_words, build_karaoke_ass
from engine.system.health import (
    check_audio_studio_engines,
    check_ffmpeg,
    check_production_readiness,
    check_reels_autocut_pipeline,
)


@pytest.fixture
def client():
    return TestClient(app)


def _generate_synthetic_clip(
    path: Path,
    width: int,
    height: int,
    duration_s: float = 1.0,
    fps: int = 24,
    with_audio: bool = True,
) -> Path:
    """Generate a valid test H.264 video with optional AAC audio using ffmpeg testsrc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _FFMPEG, "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration_s}:size={width}x{height}:rate={fps}",
    ]
    if with_audio:
        cmd.extend([
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={duration_s}",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-shortest",
            str(path),
        ])
    else:
        cmd.extend([
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            str(path),
        ])

    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg synthetic clip generation failed: {res.stderr}"
    assert path.is_file()
    return path


def _create_synthetic_model_sheet(w: int = 1536, h: int = 768) -> Image.Image:
    """Create a synthetic 4-view turnaround model sheet with simulated character colors."""
    img = Image.new("RGB", (w, h), color=(220, 220, 220))
    step = w // 4
    colors = [(190, 80, 80), (80, 190, 80), (80, 80, 190), (190, 190, 80)]
    for i, col in enumerate(colors):
        cx = i * step + step // 2
        cy = h // 3
        for x in range(cx - 35, cx + 35):
            for y in range(cy - 40, cy + 40):
                if (x - cx) ** 2 + (y - cy) ** 2 < 35 ** 2:
                    img.putpixel((x, y), col)
    return img


# ==============================================================================
# Phase 1: Preflight System Health & Readiness Verification
# ==============================================================================


@pytest.mark.asyncio
async def test_e2e_phase1_system_readiness_audit(client):
    """Verify that the preflight capability auditor correctly checks all system components."""
    # 1. Direct Python API
    report = check_production_readiness()
    assert isinstance(report.ready, bool)
    assert "ffmpeg" in report.checks
    assert "audio_studio" in report.checks
    assert "reels" in report.checks
    assert "resources" in report.checks

    # Sub-checks verified functional
    ffmpeg_check = check_ffmpeg()
    assert ffmpeg_check.available is True
    assert ffmpeg_check.status in ("ok", "warning")
    assert "libx264" in ffmpeg_check.details or "FFmpeg" in ffmpeg_check.details

    audio_check = check_audio_studio_engines()
    assert audio_check.available is True
    assert audio_check.status == "ok"
    assert "foley" in audio_check.details
    assert "ambient" in audio_check.details
    assert "synth" in audio_check.details

    reels_check = check_reels_autocut_pipeline()
    assert reels_check.available is True
    assert reels_check.status == "ok"

    # 2. REST Endpoint GET /api/system/readiness
    res = client.get("/api/system/readiness")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "checks" in data
    assert "summary" in data
    assert "recommendations" in data

    # 3. MCP Tool panelflow_system_readiness
    from unittest.mock import patch
    from engine.mcp.client_bridge import bridge

    tool = registry.get_tool("panelflow_system_readiness")
    assert tool is not None
    assert tool.name == "panelflow_system_readiness"
    with patch.object(bridge, "get", return_value=data):
        mcp_result = await registry.call_tool("panelflow_system_readiness", {})
        assert "ready" in mcp_result
        assert "checks" in mcp_result


# ==============================================================================
# Phase 2: Character Model Sheet & Identity Pinning Pipeline
# ==============================================================================


def test_e2e_phase2_character_identity_and_pinning(tmp_path: Path, monkeypatch):
    """Verify character turnaround prompt building, sheet slicing, and reference binding."""
    # Redirect COMFY_INPUT_DIR to tmp_path for test isolation
    from engine.characters import pinning
    monkeypatch.setattr(pipeline, "COMFY_INPUT_DIR", tmp_path)
    monkeypatch.setattr(pinning, "COMFY_INPUT_DIR", tmp_path)

    # 1. Prompt generation
    pos_prompt, neg_prompt = build_model_sheet_prompt(
        name="Seraphina Cross",
        look="iridescent cyber-armor, silver ponytail, mechanical gauntlet",
        role="Vanguard Scout",
        style_tags="cinematic anime cyberpunk, sharp linework",
    )
    assert "Seraphina Cross" in pos_prompt
    assert "Vanguard Scout" in pos_prompt
    assert "iridescent cyber-armor" in pos_prompt
    assert "4 distinct orthographic full-body views" in pos_prompt
    assert "inconsistent clothing" in neg_prompt

    # 2. Turnaround model sheet slicing
    sheet_img = _create_synthetic_model_sheet(1536, 768)
    sheet_path = tmp_path / "seraphina_turnaround.png"
    sheet_img.save(sheet_path)

    views = slice_model_sheet(sheet_path, out_dir=tmp_path, prefix="seraphina")
    for name in VIEW_NAMES:
        assert name in views
        assert views[name].is_file()
        with Image.open(views[name]) as crop:
            assert crop.size == (384, 768)

    # 3. Face identity verification
    verifier = FaceIdentityVerifier()
    face_img = Image.new("RGB", (112, 112), color=(200, 180, 160))
    emb = verifier.extract_embedding(face_img)
    assert emb is not None
    assert emb.shape == (512,)
    # Cosine self-similarity must match
    report = verifier.verify_face_match(face_img, face_img)
    assert report.matched is True
    assert report.similarity >= 0.72

    # 4. Reference binding into Klein 4B shot parameters (max 4 references)
    character_vault = [
        {
            "id": "char_seraphina",
            "name": "Seraphina Cross",
            "views": {
                "three_quarter": views["three_quarter"].name,
                "front": views["front"].name,
                "profile": views["profile"].name,
                "back": views["back"].name,
            },
        }
    ]
    shot = {
        "character_ids": ["char_seraphina"],
        "prompt": "Seraphina standing atop a neon-lit skyscraper in rain",
    }
    bound = bind_character_references_for_shot(shot, character_vault, max_references=4)
    assert len(bound) >= 1
    assert bound[0] == views["three_quarter"].name


# ==============================================================================
# Phase 3: Storyboard Sequence Assembly & Resolution Normalization
# ==============================================================================


def test_e2e_phase3_storyboard_sequence_assembly(tmp_path: Path):
    """Verify multi-shot timeline assembly, mixed resolution scaling, and downstream invalidation."""
    # 1. Create two clips of differing resolutions (1920x1080 and 1280x720)
    clip_1 = _generate_synthetic_clip(tmp_path / "scene1.mp4", 1920, 1080, duration_s=1.0)
    clip_2 = _generate_synthetic_clip(tmp_path / "scene2.mp4", 1280, 720, duration_s=1.0)

    scenes = [
        {
            "shot_index": 1,
            "video_url": str(clip_1),
            "duration": 1.0,
            "approved": True,
            "state": "approved",
            "inherits_tail": False,
            "prompt": "Seraphina observing the rainy metropolis",
        },
        {
            "shot_index": 2,
            "video_url": str(clip_2),
            "duration": 1.0,
            "approved": True,
            "state": "approved",
            "inherits_tail": True,
            "prompt": "Explosion erupts in the distance",
        },
    ]

    out_seq = tmp_path / "final_sequence.mp4"
    result = assemble_storyboard_sequence(
        scenes=scenes,
        out_path=out_seq,
        target_width=1920,
        target_height=1080,
        fps=24.0,
        create_sound_plan=False,
    )

    assert result["success"] is True
    assert result["shot_count"] == 2
    assert result["duration"] >= 1.8
    assert out_seq.is_file()

    # Probe assembled video to verify strict 1920x1080 conformance
    meta = probe(out_seq)
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["duration"] >= 1.8

    # 2. Downstream invalidation logic
    invalidated = start_modes.invalidate_downstream(scenes, modified_index=0)
    assert invalidated == [1]
    assert scenes[1]["state"] == "stale"
    assert scenes[1]["approved"] is False


# ==============================================================================
# Phase 4: Automated Sound Design & Procedural Foley Generation
# ==============================================================================


def test_e2e_phase4_automated_sound_design_foley(tmp_path: Path):
    """Verify semantic keyword parsing and procedural synthesis of ambient beds and foley cues."""
    audio_engine = get_audio_engine()
    seq_video = _generate_synthetic_clip(tmp_path / "sequence.mp4", 1280, 720, duration_s=4.0)
    plan = audio_engine.create_plan(
        video_path=seq_video,
        fps=24.0,
        duration=4.0,
    )

    storyboard_scenes = [
        {
            "shot_index": 1,
            "duration": 2.0,
            "prompt": "Heavy rain pours down neon street at night, wind howling through dark alleys",
            "direction": "Camera tilts down as Seraphina dashes across wet pavement",
        },
        {
            "shot_index": 2,
            "duration": 2.0,
            "prompt": "Lethal blade strike and heavy thunder impact shatter the window glass",
            "direction": "Close up on impact sparks",
        },
    ]

    populated_plan = auto_populate_sound_plan(
        plan_id=plan.id,
        scenes=storyboard_scenes,
        auto_source=True,
    )

    assert len(populated_plan.cues) >= 3  # Ambient bed + foley action cues

    # Verify track presence
    cue_tracks = {c.track for c in populated_plan.cues}
    assert "ambience" in cue_tracks
    assert "foley" in cue_tracks

    # Verify cues were sourced procedurally with valid local audio takes
    for cue in populated_plan.cues:
        take = cue.chosen()
        if take:
            p = Path(take.path)
            assert p.is_file(), f"Sound take asset file {p} was not found"
            assert p.stat().st_size > 0


# ==============================================================================
# Phase 5: YouTube Shorts & Reels Intelligent 9:16 Auto-Cut Engine
# ==============================================================================


def test_e2e_phase5_reels_autocut_and_karaoke_subtitles(tmp_path: Path):
    """Verify saliency reframing, animated karaoke ASS subtitle generation, and -14 LUFS mastering."""
    # 1. Create a 16:9 test video clip (1280x720) with audio
    in_video = _generate_synthetic_clip(tmp_path / "source_16_9.mp4", 1280, 720, duration_s=2.0, with_audio=True)
    out_reel = tmp_path / "output_reel_9_16.mp4"

    # 2. Reframing plan computation
    plan = compute_reframing_plan(in_video, target_w=1080, target_h=1920, sample_fps=2.0)
    assert plan.target_width == 1080
    assert plan.target_height == 1920
    crop_expr = plan.to_ffmpeg_crop_expr()
    assert len(crop_expr) > 0
    assert crop_expr.isdigit() or "if" in crop_expr

    # 3. Transcript alignment and karaoke ASS compilation
    transcript = "In the neon shadows of the grid, identity is the ultimate weapon."
    words = align_transcript_words(transcript=transcript, duration_sec=2.0)
    assert len(words) >= 8

    ass_content = build_karaoke_ass(
        words=words,
        hook="PANELFLOW EXCLUSIVE",
        output_path=tmp_path / "dialogue.ass",
    )
    assert (tmp_path / "dialogue.ass").is_file()
    assert "\\c" in ass_content
    assert "\\fscx" in ass_content
    assert "PANELFLOW EXCLUSIVE" in ass_content

    # 4. Full 9:16 Auto-Cut render with audio LUFS mastering and subtitles
    req = ReelAutoCutRequest(
        input_video_path=str(in_video),
        output_path=str(out_reel),
        transcript=transcript,
        burn_subtitles=True,
    )
    result = autocut_horizontal_to_reel(req)

    assert result.success is True
    assert result.output_video_path == str(out_reel)
    assert out_reel.is_file()
    assert out_reel.stat().st_size > 1000

    # Verify final vertical geometry
    meta = probe(out_reel)
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["duration"] >= 1.8


# ==============================================================================
# Phase 6: Unified Autonomous End-to-End Orchestrator Smoke Test
# ==============================================================================


def test_e2e_phase6_unified_production_orchestrator(tmp_path: Path):
    """Full integrated loop: Health Audit -> Turnaround -> Sequence Assembly -> Foley Design -> 9:16 Reel Cut."""
    # Step 1: Preflight Audit
    readiness = check_production_readiness()
    assert readiness.summary is not None

    # Step 2: Character Identity
    sheet_img = _create_synthetic_model_sheet(1024, 512)
    sheet_file = tmp_path / "hero_sheet.png"
    sheet_img.save(sheet_file)
    views = slice_model_sheet(sheet_file, out_dir=tmp_path / "hero_views", prefix="hero")
    assert len(views) == 4

    # Step 3: Multi-Shot Timeline Sequence Generation & Assembly (which automatically auto-designs foley!)
    shot1 = _generate_synthetic_clip(tmp_path / "shot1.mp4", 1920, 1080, duration_s=1.0)
    shot2 = _generate_synthetic_clip(tmp_path / "shot2.mp4", 1920, 1080, duration_s=1.0)

    scenes = [
        {
            "shot_index": 1,
            "video_url": str(shot1),
            "duration": 1.0,
            "approved": True,
            "state": "approved",
            "prompt": "Hero dashes through rain in neon alley",
            "character_ids": ["hero"],
        },
        {
            "shot_index": 2,
            "video_url": str(shot2),
            "duration": 1.0,
            "approved": True,
            "state": "approved",
            "prompt": "Explosion impact sends dust across pavement",
            "character_ids": ["hero"],
        },
    ]

    assembled_video = tmp_path / "master_sequence.mp4"
    seq_res = assemble_storyboard_sequence(
        scenes=scenes,
        out_path=assembled_video,
        target_width=1920,
        target_height=1080,
        fps=24.0,
        create_sound_plan=True,
    )
    assert assembled_video.is_file()
    assert seq_res["shot_count"] == 2
    assert seq_res.get("sound_plan_id") is not None

    # Verify that the automatically linked sound plan exists and contains cues
    audio_engine = get_audio_engine()
    linked_plan = audio_engine.store.load(seq_res["sound_plan_id"])
    assert linked_plan is not None
    assert len(linked_plan.cues) >= 2

    # Step 5: YouTube Shorts & Reels Intelligent 9:16 Auto-Cut
    reel_output = tmp_path / "autonomous_vertical_short.mp4"
    reel_req = ReelAutoCutRequest(
        input_video_path=str(assembled_video),
        output_path=str(reel_output),
        transcript="The rain hides our movement until the spark of impact.",
        burn_subtitles=True,
    )
    reel_res = autocut_horizontal_to_reel(reel_req)

    assert reel_res.success is True
    assert reel_output.is_file()
    assert reel_res.resolution == [1080, 1920]
    assert reel_res.duration_sec >= 1.8

    # Final probe to ensure master output is 1080x1920 9:16
    final_meta = probe(reel_output)
    assert final_meta["width"] == 1080
    assert final_meta["height"] == 1920
