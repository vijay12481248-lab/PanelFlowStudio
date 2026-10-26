"""
Tests AudioDirectorService integration with OfflineHybridSpeechAligner.
Verifies that generated audio segments and master timelines automatically
attach measured speech cues and persist alignment metadata.
"""
from pathlib import Path
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from engine.audio.service import AudioService


def test_synthesize_narration_segment_produces_measured_cues(tmp_path, monkeypatch):
    # Synthetic tones exercise VAD; they must not load a speech model or imply
    # that sentence order establishes which panel its words describe.
    monkeypatch.setattr('engine.audio.alignment.get_offline_whisper_pipeline', lambda *_: None)
    service = AudioService()

    # Mock synthesizer to write a short synthetic WAV rather than loading full TTS
    def mock_synthesize(directory, text, voice, emotion, intensity, pace, text_revision, force):
        import numpy as np
        import soundfile as sf
        p = Path(directory) / "test_seg.wav"
        sr = 24000
        # 2 seconds of 440Hz tone with silence gap in middle
        t1 = np.linspace(0, 0.8, int(sr * 0.8), endpoint=False)
        w1 = 0.3 * np.sin(2 * np.pi * 440 * t1)
        silence = np.zeros(int(sr * 0.4), dtype=np.float32)
        t2 = np.linspace(0, 0.8, int(sr * 0.8), endpoint=False)
        w2 = 0.3 * np.sin(2 * np.pi * 880 * t2)
        samples = np.concatenate([w1, silence, w2]).astype(np.float32)
        sf.write(str(p), samples, sr)
        return p

    service.synthesizer = MagicMock()
    service.synthesizer.synthesize.side_effect = mock_synthesize

    res = service.synthesize_narration_segment(
        workspace_path=tmp_path,
        segment_id="seg_test_123",
        text="First sentence here. Second sentence follows.",
        voice="Narrator",
        panel_ids=["panel_1", "panel_2"],
    )

    assert res["success"] is True
    assert res["segment_id"] == "seg_test_123"
    assert res["measured_duration_sec"] == pytest.approx(2.0, abs=0.1)
    assert "speech_cues" in res
    cues = res["speech_cues"]
    assert len(cues) == 2
    assert cues[0]["panel_ids"] == ["panel_1", "panel_2"]
    assert cues[1]["panel_ids"] == ["panel_1", "panel_2"]
    assert cues[0]["end_sec"] == cues[1]["start_sec"]
