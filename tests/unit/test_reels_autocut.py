"""Unit and integration tests for YouTube Shorts & Reels 9:16 Auto-Cut Engine."""
from __future__ import annotations

import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.reels.publisher import (
    ReelAutoCutRequest,
    autocut_horizontal_to_reel,
    has_audio_stream,
)
from engine.reels.reframer import (
    FocalPoint,
    ReframingKeyframe,
    ReframingTrajectory,
    VideoFocalTracker,
    compute_reframing_plan,
    probe_video_meta,
)
from engine.reels.subtitles import (
    SubtitleWord,
    align_transcript_words,
    build_karaoke_ass,
    chunk_words,
    format_ass_time,
)


def test_format_ass_time():
    assert format_ass_time(0.0) == "0:00:00.00"
    assert format_ass_time(1.25) == "0:00:01.25"
    assert format_ass_time(65.4) == "0:01:05.40"
    assert format_ass_time(3661.05) == "1:01:01.05"


def test_chunk_words():
    words = [
        SubtitleWord("Hello", 0.0, 0.3),
        SubtitleWord("world,", 0.3, 0.6),
        SubtitleWord("this", 0.6, 0.9),
        SubtitleWord("is", 0.9, 1.2),
        SubtitleWord("great.", 1.2, 1.5),
    ]
    chunks = chunk_words(words, max_words=3)
    assert len(chunks) == 2
    # Check that punctuation at 'world,' caused chunk boundary
    assert chunks[0][-1].word == "world,"
    assert chunks[1][-1].word == "great."
    # Check all words are preserved
    flat = [w.word for ch in chunks for w in ch]
    assert flat == [w.word for w in words]


def test_build_karaoke_ass(tmp_path: Path):
    words = [
        SubtitleWord("WELCOME", 0.2, 0.6),
        SubtitleWord("WARRIORS", 0.6, 1.2),
    ]
    ass_path = tmp_path / "test.ass"
    ass_text = build_karaoke_ass(
        words=words,
        hook="DON'T BLINK",
        output_path=ass_path,
    )

    assert ass_path.exists()
    assert "PlayResX: 1080" in ass_text
    assert "PlayResY: 1920" in ass_text
    assert "Style: Cap,Impact,92" in ass_text
    assert "Style: Hook,Impact,115" in ass_text
    assert "DON'T BLINK" in ass_text
    assert "\\c&H0000E5FF&\\fscx120\\fscy120" in ass_text
    assert "WELCOME" in ass_text
    assert "WARRIORS" in ass_text


def test_align_transcript_words_fallback():
    transcript = "The ancient seal awakens once again."
    words = align_transcript_words(audio_path=None, transcript=transcript, duration_sec=3.0)
    assert len(words) == 6
    assert words[0].word == "The"
    assert words[-1].word == "again."
    assert words[0].start >= 0.15
    assert words[-1].end <= 3.0
    for i in range(len(words) - 1):
        assert words[i].end <= words[i + 1].start + 1e-4


def test_detect_frame_focus_center_fallback():
    tracker = VideoFocalTracker(enable_face_detect=False)
    blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
    focal = tracker.detect_frame_focus(blank)
    assert focal.source in ("center", "saliency")
    assert abs(focal.x - 960.0) < 50.0


def test_detect_frame_focus_saliency():
    tracker = VideoFocalTracker(enable_face_detect=False)
    # Create an image with high energy block on the right side
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    img[400:680, 1400:1700] = 255
    focal = tracker.detect_frame_focus(img)
    assert focal.source == "saliency"
    # Saliency center must be strongly shifted to the right (> 1200 px)
    assert focal.x > 1200.0


def test_reframing_trajectory_filter():
    trajectory = ReframingTrajectory(
        source_width=1920,
        source_height=1080,
        crop_width=608,
        crop_height=1080,
        target_width=1080,
        target_height=1920,
        mode="shot_stable",
        shot_crops=[
            {"shot_index": 1, "start_t": 0.0, "end_t": 3.0, "crop_x": 400},
            {"shot_index": 2, "start_t": 3.0, "end_t": 6.5, "crop_x": 900},
        ],
    )
    expr = trajectory.to_ffmpeg_crop_expr()
    assert "if(lt(t" in expr
    assert "3.000" in expr
    assert "400" in expr
    assert "900" in expr

    vf = trajectory.to_ffmpeg_vf()
    assert "crop=608:1080:" in vf
    assert "scale=1080:1920:flags=lanczos,setsar=1" in vf


def test_autocut_real_video(tmp_path: Path):
    source_video = Path("output/autonomous_story/clip_1.mp4")
    if not source_video.exists():
        pytest.skip("Test sample video not found on disk")

    out_reel = tmp_path / "clip_1_reel.mp4"
    req = ReelAutoCutRequest(
        input_video_path=str(source_video),
        output_path=str(out_reel),
        hook_text="SHOCKING REVEAL",
        transcript="The dragon descends upon the forgotten temple.",
        burn_subtitles=True,
        target_duration=3.0,
        reframing_mode="shot_stable",
        title="Dragon Legend",
        tags="#shorts #anime #dragon",
    )

    result = autocut_horizontal_to_reel(req)
    assert result.success is True
    assert out_reel.exists()
    assert out_reel.stat().st_size > 1000

    meta = probe_video_meta(out_reel)
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["duration"] > 0.5

    # Check publish file
    pub_file = tmp_path / f"{source_video.stem}_PUBLISH.md"
    assert pub_file.exists()
    pub_text = pub_file.read_text(encoding="utf-8")
    assert "SHOCKING REVEAL" in pub_text
    assert "#shorts" in pub_text
    assert "synthetic" in pub_text or "AI-generated" in pub_text


def test_autocut_missing_input(tmp_path: Path):
    req = ReelAutoCutRequest(
        input_video_path=str(tmp_path / "non_existent.mp4"),
        output_path=str(tmp_path / "out.mp4"),
    )
    result = autocut_horizontal_to_reel(req)
    assert result.success is False
    assert "does not exist" in result.message


def test_reels_api_preview_endpoint():
    source_video = Path("output/autonomous_story/clip_1.mp4")
    if not source_video.exists():
        pytest.skip("Test sample video not found on disk")

    client = TestClient(app)
    res = client.post(
        "/api/reels/preview_reframing",
        json={"video_path": str(source_video), "reframing_mode": "shot_stable"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source_width"] == 1920
    assert data["source_height"] == 1080
    assert data["crop_width"] == 608
    assert data["target_width"] == 1080
    assert data["target_height"] == 1920
    assert "crop=" in data["ffmpeg_filter"]
    assert "scale=1080:1920" in data["ffmpeg_filter"]


def test_reels_api_generate_subtitles_endpoint():
    client = TestClient(app)
    res = client.post(
        "/api/reels/generate_subtitles",
        json={
            "transcript": "Victory belongs only to those who endure.",
            "hook": "MUST WATCH",
            "duration_sec": 4.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["word_count"] == 7
    assert "PlayResX: 1080" in data["ass_content"]
    assert "MUST WATCH" in data["ass_content"]
