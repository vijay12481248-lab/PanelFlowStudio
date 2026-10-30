"""
Voice & Video Synchronization Engine for Anime Reviews.
Synthesizes neural voiceover per review beat, dynamically retimes and stitches
anime scene cuts to match exact voice duration down to the millisecond, and
mixes ducked original background audio with high-clarity voiceover.
"""
import os
import sys
import json
import time
import uuid
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import soundfile as sf
import torch
from kokoro import KPipeline

from engine.anime.models import (
    ReviewStoryBeat,
    AnimeSceneCut,
    AnimeReviewConfig,
)

logger = logging.getLogger("panelflow.anime.voice_sync")


class VoiceVideoSyncEngine:
    """
    Coordinates millisecond-precise voice-to-video synchronization.
    """

    def __init__(self, voice_name: str = "am_michael"):
        self.voice_name = voice_name
        self._pipeline = None

    def _get_pipeline(self):
        if self._pipeline is None:
            logger.info(f"Initializing Kokoro TTS Pipeline (voice={self.voice_name})...")
            self._pipeline = KPipeline(lang_code="a")
        return self._pipeline

    def synthesize_beats_audio(
        self,
        beats: List[ReviewStoryBeat],
        output_dir: Path,
        voice_name: Optional[str] = None,
    ) -> List[ReviewStoryBeat]:
        """
        Synthesizes Kokoro-82M neural TTS audio for each review beat,
        measuring exact audio durations in seconds.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        pipeline = self._get_pipeline()
        v_name = voice_name or self.voice_name

        for beat in beats:
            content_hash = hashlib.sha256(beat.voiceover_text.encode("utf-8")).hexdigest()[:12]
            wav_path = output_dir / f"{beat.beat_id}_{content_hash}.wav"

            if not wav_path.exists() or wav_path.stat().st_size < 1000:
                logger.info(f"Synthesizing {beat.beat_id}: '{beat.voiceover_text[:40]}...'")
                speed = float(getattr(beat, "voice_speed", 1.0) or getattr(beat, "speed", 1.0) or 1.0)
                generator = pipeline(beat.voiceover_text, voice=v_name, speed=speed)
                chunks = [audio for _, _, audio in generator]
                if not chunks:
                    raise RuntimeError(f"Kokoro failed to generate audio for {beat.beat_id}")
                audio_tensor = torch.cat(chunks, dim=0) if len(chunks) > 1 else chunks[0]
                audio_np = audio_tensor.numpy() if hasattr(audio_tensor, "numpy") else audio_tensor
                # Normalize peak to 0.95
                peak = abs(audio_np).max()
                if peak > 0.001:
                    audio_np = (audio_np / peak) * 0.95
                sf.write(str(wav_path), audio_np, 24000, format="WAV", subtype="PCM_16")

            info = sf.info(str(wav_path))
            beat.voice_audio_path = str(wav_path.resolve())
            beat.voice_duration_sec = round(info.duration, 3)
            logger.info(f"  -> Beat {beat.beat_id} duration: {beat.voice_duration_sec:.2f}s")

        return beats

    def synchronize_beat_with_video(
        self,
        beat: ReviewStoryBeat,
        cut_map: Dict[str, AnimeSceneCut],
        workspace_dir: Path,
        duck_db: float = -18.0,
    ) -> Path:
        """
        Synchronizes a single review beat:
        Takes the assigned scene cuts, adjusts speed/duration to match beat.voice_duration_sec,
        mixes original audio (ducked) with review voice (100%), and renders a synchronized MP4.
        """
        synced_dir = workspace_dir / "synced_beats"
        synced_dir.mkdir(parents=True, exist_ok=True)
        output_mp4 = synced_dir / f"{beat.beat_id}_synced.mp4"

        target_duration = beat.voice_duration_sec
        voice_wav = beat.voice_audio_path

        # Find available cut files for this beat
        assigned_cuts = [cut_map[cid] for cid in beat.assigned_cut_ids if cid in cut_map and cut_map[cid].clip_path]
        if not assigned_cuts:
            # Fallback to any cut in map
            assigned_cuts = list(cut_map.values())[:1]

        # Calculate time allocated to each cut
        time_per_cut = target_duration / max(1, len(assigned_cuts))
        temp_cut_pieces = []

        for c_idx, cut in enumerate(assigned_cuts):
            piece_path = synced_dir / f"{beat.beat_id}_cut_{c_idx:02d}.mp4"
            # Trim or loop cut to match time_per_cut
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "3",  # Loop if cut is shorter than required
                "-i", cut.clip_path,
                "-t", str(round(time_per_cut, 3)),
                "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-ar", "48000",
                str(piece_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            temp_cut_pieces.append(piece_path)

        # Concatenate cut pieces for this beat
        merged_video = synced_dir / f"{beat.beat_id}_video_only.mp4"
        if len(temp_cut_pieces) == 1:
            merged_video = temp_cut_pieces[0]
        else:
            list_txt = synced_dir / f"{beat.beat_id}_list.txt"
            with open(list_txt, "w", encoding="utf-8") as f:
                for tp in temp_cut_pieces:
                    f.write(f"file '{str(tp.resolve()).replace('\\', '/')}'\n")
            cmd_concat = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_txt),
                "-c", "copy",
                str(merged_video),
            ]
            subprocess.run(cmd_concat, check=True, capture_output=True)
            list_txt.unlink(missing_ok=True)

        # Final audio mix: Duck original anime audio and overlay reviewer voice
        # Original audio ducked to duck_db (e.g. -18dB = ~0.12 amplitude), voice at 1.0 (0dB)
        duck_vol = 10.0 ** (duck_db / 20.0)

        cmd_mix = [
            "ffmpeg", "-y",
            "-i", str(merged_video),
            "-i", str(voice_wav),
            "-filter_complex",
            f"[0:a]volume={duck_vol:.3f},apad[a_orig]; [1:a]volume=1.0[a_voice]; [a_orig][a_voice]amix=inputs=2:duration=first:dropout_transition=2[a_out]",
            "-map", "0:v:0",
            "-map", "[a_out]",
            "-t", str(target_duration),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_mp4),
        ]
        subprocess.run(cmd_mix, check=True, capture_output=True)

        # Clean up temporary pieces
        for tp in temp_cut_pieces:
            if tp != merged_video and tp.exists():
                tp.unlink(missing_ok=True)
        if merged_video != temp_cut_pieces[0] and merged_video.exists():
            merged_video.unlink(missing_ok=True)

        return output_mp4
