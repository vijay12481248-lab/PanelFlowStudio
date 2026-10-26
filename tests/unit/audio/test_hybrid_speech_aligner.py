"""
Unit and integration tests for the Offline Hybrid Speech Aligner.
Tests Whisper token alignment, Scipy/Numpy RMS energy envelope VAD,
zero-crossing acoustic boundary snapping, and the 4-tier fallback hierarchy.
"""
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

from engine.audio.alignment import (
    OfflineHybridSpeechAligner,
    compute_rms_envelope,
    find_silence_valleys,
    snap_to_acoustic_zero_crossing,
    _split_into_sentences,
    local_speech_aligner,
)


def _generate_synthetic_speech_with_gap(sr=24000, dur1=1.5, gap=0.5, dur2=1.5):
    """Generates two sine tone bursts separated by pure silence."""
    t1 = np.linspace(0, dur1, int(sr * dur1), endpoint=False)
    wave1 = 0.4 * np.sin(2 * np.pi * 440 * t1)

    silence = np.zeros(int(sr * gap), dtype=np.float32)

    t2 = np.linspace(0, dur2, int(sr * dur2), endpoint=False)
    wave2 = 0.4 * np.sin(2 * np.pi * 880 * t2)

    return np.concatenate([wave1, silence, wave2]).astype(np.float32), sr


def test_compute_rms_envelope_and_silence_detection():
    data, sr = _generate_synthetic_speech_with_gap(sr=24000, dur1=1.0, gap=0.6, dur2=1.0)
    times, dbs, hop_sec = compute_rms_envelope(data, sr)

    assert len(times) == len(dbs)
    assert np.max(dbs) > -20.0  # Tones have energy

    valleys = find_silence_valleys(dbs, times, silence_threshold_db=-35.0, min_silence_duration_s=0.1)
    assert len(valleys) >= 1

    # Silence gap is located between 1.0s and 1.6s
    gap_start, gap_end, min_db = valleys[0]
    assert 0.95 <= gap_start <= 1.05
    assert 1.55 <= gap_end <= 1.65
    assert min_db < -60.0  # True silence


def test_snap_to_acoustic_zero_crossing_synthetic():
    data, sr = _generate_synthetic_speech_with_gap(sr=24000, dur1=1.0, gap=0.5, dur2=1.0)

    # Search window around target time 1.25s (in middle of silence gap)
    target_t = 1.25
    snapped_t, min_db, is_clean = snap_to_acoustic_zero_crossing(data, sr, target_t, search_window_s=0.15)

    assert is_clean
    assert min_db < -60.0
    # Boundary sample should be zero or adjacent to zero crossing
    sample_idx = int(snapped_t * sr)
    assert abs(data[sample_idx]) < 1e-4


def test_split_into_sentences_and_panel_mapping():
    text = "The barrier shattered. Marcus looked up in shock. A dragon descended from the clouds."
    sentences = _split_into_sentences(text)
    assert len(sentences) == 3
    assert sentences[0] == "The barrier shattered."
    assert sentences[1] == "Marcus looked up in shock."
    assert sentences[2] == "A dragon descended from the clouds."


def test_pure_vad_fallback_tier_2():
    """Simulates speech with two clear pauses and tests pure VAD segmentation."""
    data, sr = _generate_synthetic_speech_with_gap(sr=24000, dur1=1.0, gap=0.4, dur2=1.0)
    total_dur = len(data) / float(sr)
    times, dbs, _ = compute_rms_envelope(data, sr)

    aligner = OfflineHybridSpeechAligner()
    target_units = [
        {"id": "cue_0", "text": "Sentence one.", "panel_ids": ["panel_A"]},
        {"id": "cue_1", "text": "Sentence two.", "panel_ids": ["panel_B"]},
    ]

    cues, ok = aligner._align_with_pure_vad(target_units, data, sr, times, dbs, total_dur)
    assert ok is True
    assert len(cues) == 2
    assert cues[0]["status"] == "VAD_SEGMENTED"
    assert cues[0]["alignment_method"] == "vad_energy"
    assert cues[0]["panel_ids"] == ["panel_A"]
    assert cues[1]["panel_ids"] == ["panel_B"]

    # Cut point should be inside the silence gap [1.0s, 1.4s]
    cut_t = cues[0]["end_sec"]
    assert 0.98 <= cut_t <= 1.42
    assert cues[1]["start_sec"] == cut_t
    assert cues[1]["end_sec"] == total_dur


def test_proportional_fallback_tier_4():
    """Verifies proportional character-count estimation when acoustic detection fails."""
    aligner = OfflineHybridSpeechAligner()
    target_units = [
        {"id": "c0", "text": "Short.", "panel_ids": ["p1"]},
        {"id": "c1", "text": "This is a significantly longer sentence describing the environment.", "panel_ids": ["p2"]},
    ]
    total_dur = 10.0
    cues = aligner._align_proportional_fallback(target_units, total_dur)

    assert len(cues) == 2
    assert cues[0]["status"] == "NEEDS_REVIEW"
    assert cues[0]["confidence"] < 0.70
    assert cues[0]["end_sec"] < cues[1]["end_sec"]
    # Long sentence gets proportionally more duration
    dur_0 = cues[0]["end_sec"] - cues[0]["start_sec"]
    dur_1 = cues[1]["end_sec"] - cues[1]["start_sec"]
    assert dur_1 > dur_0 * 3


def test_real_audio_take_alignment_tier_1():
    """
    Evaluates real Chatterbox-generated dialogue take against local Whisper Large v3 Turbo
    and acoustic energy VAD snapping.
    """
    wav_path = Path("scratch/tts_benchmark/chatterbox/02_fearful_suspense.wav")
    if not wav_path.exists():
        pytest.skip(f"Benchmark audio {wav_path} not available on this host")

    script_text = "Wait... do you hear that? Something is moving in the shadows beneath us. Don't make a sound."
    panel_ids = ["panel_01", "panel_02", "panel_03", "panel_04"]

    aligner = OfflineHybridSpeechAligner()
    res = aligner.align(
        audio_path_or_bytes=wav_path,
        script_text=script_text,
        panel_ids=panel_ids,
    )

    assert res["success"] is True
    assert res["measured_duration_sec"] == pytest.approx(6.32, abs=0.1)
    assert res["alignment_tier"] in ("tier_1_whisper_vad", "tier_2_vad")
    assert res["confidence"] >= 0.80

    cues = res["cues"]
    assert len(cues) >= 3

    # Check temporal ordering and continuity
    for i in range(len(cues)):
        cue = cues[i]
        assert cue["end_sec"] > cue["start_sec"]
        if i > 0:
            assert cue["start_sec"] == cues[i - 1]["end_sec"]

    # Verify boundary samples are in silence valleys (zero audio pop)
    data, sr = sf.read(str(wav_path))
    if data.ndim > 1:
        data = data.mean(axis=1)

    for cue in cues[:-1]:
        boundary_idx = int(cue["end_sec"] * sr)
        # Check that amplitude at boundary is near zero
        assert abs(data[boundary_idx]) < 0.05
