"""Narrator Voiceover Engine for Infinite Series Production.

Generates a unified, dramatic narrator voice track for 20-minute episodes
using EdgeTTS Neural Voices (e.g. en-US-ChristopherNeural) and multiplexes
it directly into the final video, padding or syncing to exact episode duration,
and cleans up unused intermediate render files to conserve disk space.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import edge_tts

logger = logging.getLogger("narrator_engine")

NARRATOR_VOICE = "en-US-ChristopherNeural"  # Deep, epic manhua storyteller voice
TARGET_DURATION_SECONDS = 1200  # 20.00 minutes


def prepare_narration_script(title: str, prose: str, epigraph: str = "") -> str:
    """Formats and cleans novel prose into a dramatic spoken narration script."""
    # Clean up formatting artifacts, brackets, markdown headers
    clean_prose = re.sub(r"\[.*?\]", "", prose)
    clean_prose = re.sub(r"#+\s*", "", clean_prose)
    # Normalize typography
    clean_prose = clean_prose.replace("—", ", ").replace("–", ", ").replace("…", "... ")
    clean_prose = re.sub(r"\s+", " ", clean_prose).strip()

    parts = []
    if title:
        parts.append(f"{title}.")
    if epigraph:
        parts.append(f"{epigraph}.")
    parts.append(clean_prose)
    return "\n\n".join(parts)


async def synthesize_narrator_voice(
    text: str,
    output_audio_path: Path,
    voice: str = NARRATOR_VOICE,
    rate: str = "-6%",
    pitch: str = "-2Hz",
) -> Path:
    """Synthesizes the unified narrator voice track for the episode with deep storytelling cadence."""
    output_audio_path = Path(output_audio_path)
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(output_audio_path))
    logger.info(f"Synthesized narrator voiceover: {output_audio_path} ({output_audio_path.stat().st_size / 1024:.1f} KB)")
    return output_audio_path


def mux_narrator_audio_into_video(
    video_path: Path,
    audio_path: Path,
    output_video_path: Optional[Path] = None,
    target_duration: int = TARGET_DURATION_SECONDS,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    """Muxes the narrator audio track into the 20-minute video without re-encoding video.
    
    Pads audio with clean silence using -af 'apad=whole_dur=1200' so the video and audio
    both terminate at exactly target_duration (1,200.00 seconds).
    """
    video_path = Path(video_path).resolve()
    audio_path = Path(audio_path).resolve()
    if output_video_path is None:
        temp_out = video_path.parent / f"{video_path.stem}_voiced_temp.mp4"
    else:
        temp_out = Path(output_video_path).resolve()

    cmd = [
        ffmpeg_bin, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-af", f"apad=whole_dur={target_duration}",
        "-t", str(target_duration),
        str(temp_out)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if output_video_path is None:
        # Atomic replace original
        os.replace(temp_out, video_path)
        final_path = video_path
    else:
        final_path = temp_out
        
    logger.info(f"Successfully muxed narrator voice into {final_path} (Target: {target_duration}s)")
    return final_path


def cleanup_unused_episode_files(episode_dir: Path) -> int:
    """Deletes intermediate clips, manifests, and temporary artifacts to free up disk space.
    
    Preserves:
    - chapter.json
    - manhua_storyboard.json
    - panel_*.png
    - episode_*_master.mp4
    - narration.mp3
    """
    episode_dir = Path(episode_dir).resolve()
    if not episode_dir.exists():
        return 0
        
    bytes_freed = 0
    patterns_to_remove = [
        "clip_*.mp4",
        "motion_preset_*.mp4",
        "concat*.txt",
        "*_voiced_temp.mp4",
        "*_temp.mp4",
    ]
    
    # Identify master video
    master_mp4 = None
    for f in episode_dir.glob("episode_*_master.mp4"):
        if not f.name.endswith("_20min_master.mp4"):
            master_mp4 = f
            break

    # If there is a duplicate like episode_0001_20min_master.mp4 alongside episode_0001_master.mp4, remove the duplicate
    if master_mp4:
        for dup in episode_dir.glob("*_20min_master.mp4"):
            if dup.resolve() != master_mp4.resolve():
                try:
                    s = dup.stat().st_size
                    dup.unlink()
                    bytes_freed += s
                    logger.info(f"Deleted duplicate master: {dup.name} ({s / (1024 * 1024):.1f} MB)")
                except Exception as e:
                    logger.warning(f"Could not remove duplicate {dup}: {e}")

    for pat in patterns_to_remove:
        for file_path in episode_dir.glob(pat):
            if master_mp4 and file_path.resolve() == master_mp4.resolve():
                continue
            try:
                size = file_path.stat().st_size
                file_path.unlink()
                bytes_freed += size
                logger.debug(f"Removed unused file: {file_path.name} ({size / 1024:.1f} KB)")
            except Exception as e:
                logger.warning(f"Could not remove {file_path}: {e}")
                
    logger.info(f"Cleaned {episode_dir.name}: freed {bytes_freed / (1024 * 1024):.2f} MB")
    return bytes_freed
