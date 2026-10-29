"""
Audio Processing, Dialogue Transcription, and Translation Engine for Anime Episodes.
Extracts audio from video and uses faster-whisper to transcribe or translate dialogue
with word/sentence-level timestamps.
"""
import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("panelflow.anime.audio_processor")


class AnimeAudioProcessor:
    """
    Extracts and transcribes/translates anime audio streams.
    """

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            logger.info(f"Loading faster-whisper model ({self.model_size})...")
            # Run on CPU with INT8 quantization for sub-second initialization and low RAM
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def extract_audio(self, video_path: str, output_wav_path: Path) -> Path:
        """
        Extracts audio from video file to 16kHz mono 16-bit PCM WAV.
        """
        output_wav_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output_wav_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_wav_path

    def transcribe_dialogue(
        self,
        audio_path: Path,
        translate_to_english: bool = True,
        max_duration_sec: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Transcribes speech segments from audio with timestamps.
        If translate_to_english is True, automatically translates foreign (Japanese) speech to English!
        """
        model = self._get_model()
        task = "translate" if translate_to_english else "transcribe"
        logger.info(f"Starting ASR {task} on {audio_path.name}...")

        segments, info = model.transcribe(
            str(audio_path),
            task=task,
            beam_size=3,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        detected_lang = info.language
        lang_prob = round(info.language_probability, 2)
        logger.info(f"Detected audio language: {detected_lang} (confidence: {lang_prob})")

        transcript_segments = []
        for s in segments:
            if max_duration_sec and s.start > max_duration_sec:
                break
            transcript_segments.append({
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.text.strip(),
                "duration": round(s.end - s.start, 2),
            })

        logger.info(f"Transcribed {len(transcript_segments)} dialogue segments.")
        return transcript_segments
