"""
Automated Anime Review & Recap Production Pipeline.
Orchestrates scene detection, dynamic 1080p cropping, audio transcription,
review story generation, Kokoro neural voice synthesis, millisecond-precise
video/voice synchronization, and YouTube packaging.
"""
import os
import sys
import json
import time
import uuid
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from engine.anime.models import (
    AnimeEpisodeSource,
    AnimeSceneCut,
    ReviewStoryBeat,
    AnimeReviewConfig,
    AnimeReviewResult,
)
from engine.anime.scene_detector import AnimeSceneClipper
from engine.anime.audio_processor import AnimeAudioProcessor
from engine.anime.story_generator import AnimeReviewStoryEngine
from engine.anime.voice_sync_editor import VoiceVideoSyncEngine

logger = logging.getLogger("panelflow.anime.pipeline")


class AnimeReviewPipeline:
    """
    Automated producer for Anime Review & Recap videos.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        project_root = Path(__file__).resolve().parent.parent.parent
        self.workspace_root = workspace_root or (project_root / "output" / "Anime_Reviews")
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        self.clipper = AnimeSceneClipper()
        self.story_engine = AnimeReviewStoryEngine()

    async def produce_review_video(
        self,
        config: AnimeReviewConfig,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> AnimeReviewResult:
        def report(pct: float, msg: str):
            logger.info(f"[{int(pct * 100)}%] {msg}")
            if progress_cb:
                try:
                    progress_cb(pct, msg)
                except Exception:
                    pass

        if config.rights is None:
            raise ValueError("A rights declaration is required before producing an anime review.")
        config.rights.validate_for_acquisition()

        # 1. Setup workspace
        clean_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in config.series_title).strip("_")
        ep_str = f"{int(config.episode_number)}" if config.episode_number.is_integer() else f"{config.episode_number:g}"
        review_dir = self.workspace_root / f"{clean_title}_EP{ep_str}_Review"
        review_dir.mkdir(parents=True, exist_ok=True)

        report(0.05, "Inspecting source anime video...")
        source = self.clipper.inspect_source(config.source_video, series_title=config.series_title, episode_num=config.episode_number)
        source.episode_title = config.episode_title

        # 2. Extract & Transcribe Audio (Dialogue Detection)
        report(0.15, "Extracting audio and detecting dialogue...")
        audio_wav = review_dir / "extracted_audio.wav"
        audio_proc = AnimeAudioProcessor()
        audio_proc.extract_audio(config.source_video, audio_wav)

        transcript_segments = []
        try:
            transcript_segments = audio_proc.transcribe_dialogue(audio_wav, translate_to_english=True)
        except Exception as e:
            logger.warning(f"ASR transcription skipped or fallback: {e}")

        # 3. Scene Detection & Dynamic 1080p Cropping
        report(0.30, "Detecting scene transitions and slicing dynamic cuts...")
        cuts_dir = review_dir / "scene_cuts"
        scene_intervals = self.clipper.detect_scenes_opencv(
            config.source_video,
            min_cut_sec=config.min_cut_sec,
            max_cut_sec=config.max_cut_length_sec,
        )
        cuts = self.clipper.extract_and_reframe_cuts(
            config.source_video,
            scene_intervals,
            cuts_dir,
        )

        if not cuts:
            raise RuntimeError("No scene cuts could be extracted from video.")

        # 4. Generate Structured 4-Act Review Script
        report(0.50, "Generating structured 4-act anime review story script...")
        beats = self.story_engine.generate_review_script(
            source=source,
            cuts=cuts,
            transcript_segments=transcript_segments,
        )

        # 5. Synthesize Kokoro Neural Voiceover
        report(0.65, f"Synthesizing Kokoro-82M neural voiceover ({config.tts_voice})...")
        sync_engine = VoiceVideoSyncEngine(voice_name=config.tts_voice)
        audio_dir = review_dir / "voice_audio"
        beats = sync_engine.synthesize_beats_audio(beats, audio_dir)

        # 6. Millisecond-Precise Voice & Video Synchronization
        report(0.75, "Synchronizing anime video cuts with neural voice duration...")
        cut_map = {c.cut_id: c for c in cuts}
        synced_beat_files = []

        for idx, beat in enumerate(beats, 1):
            if cancel_check and cancel_check():
                raise RuntimeError("Review video production cancelled by user.")
            pct = 0.75 + 0.15 * (idx / len(beats))
            report(pct, f"Synchronizing Review Beat {idx}/{len(beats)}: {beat.act_type.value}...")
            beat_mp4 = sync_engine.synchronize_beat_with_video(
                beat=beat,
                cut_map=cut_map,
                workspace_dir=review_dir,
                duck_db=config.original_audio_duck_db,
            )
            synced_beat_files.append(beat_mp4)

        # 7. Concatenate Synced Beats into Master Review MP4
        report(0.92, "Assembling master 1080p anime review video...")
        master_mp4 = review_dir / f"{clean_title}_Episode_{ep_str}_Full_Review_1080p.mp4"
        list_txt = review_dir / "final_concat_list.txt"

        with open(list_txt, "w", encoding="utf-8") as f:
            for bf in synced_beat_files:
                f.write(f"file '{str(bf.resolve()).replace('\\', '/')}'\n")

        cmd_final = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_txt),
            "-c", "copy",
            "-movflags", "+faststart",
            str(master_mp4),
        ]
        subprocess.run(cmd_final, check=True, capture_output=True)
        list_txt.unlink(missing_ok=True)

        total_voice_sec = sum(b.voice_duration_sec for b in beats)
        master_dur = self._probe_duration(master_mp4)

        # 8. Generate YouTube Release Package
        report(0.98, "Writing YouTube release packaging and chapter timestamps...")
        meta_txt = review_dir / f"{clean_title}_Episode_{ep_str}_YouTube_Package.txt"
        self._write_youtube_package(config, beats, master_mp4, meta_txt)

        report(1.0, f"Anime review video completed: {master_mp4.name}")

        return AnimeReviewResult(
            series_title=config.series_title,
            episode_number=config.episode_number,
            output_video_path=str(master_mp4.resolve()),
            video_duration_sec=round(master_dur, 2),
            total_scene_cuts=len(cuts),
            total_review_beats=len(beats),
            voice_voiceover_duration_sec=round(total_voice_sec, 2),
            youtube_metadata_path=str(meta_txt.resolve()),
            created_at=time.time(),
        )

    @staticmethod
    def _probe_duration(p: Path) -> float:
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
                capture_output=True,
                text=True,
                check=True,
            )
            return float(res.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def _write_youtube_package(config: AnimeReviewConfig, beats: List[ReviewStoryBeat], video_path: Path, output_file: Path):
        ep_num = f"{int(config.episode_number)}" if config.episode_number.is_integer() else f"{config.episode_number:g}"
        title = f"{config.series_title} Episode {ep_num} Review & Recap | Complete Breakdown [1080p 60fps]"

        lines = [
            "================================================================================",
            title,
            "================================================================================",
            "",
            f"An in-depth story review and scene-by-scene recap of {config.series_title} Episode {ep_num}.",
            "Covering key character moments, tactical plot revelations, and battle animation breakdowns.",
            "",
            "REVIEW CHAPTER TIMESTAMPS:",
        ]

        curr_time = 0.0
        for b in beats:
            s = int(curr_time)
            mins = s // 60
            secs = s % 60
            ts_str = f"{mins:02d}:{secs:02d}"
            label = b.act_type.value.replace("_", " ").title()
            lines.append(f"{ts_str} - {label} ({b.voiceover_text[:35]}...)")
            curr_time += b.voice_duration_sec

        lines.extend([
            "",
            "AUDIO CREDITS & PRODUCTION:",
            f"Narrated with Kokoro-82M Neural Audio ({config.tts_voice})",
            "Produced automatically via PanelFlow Studio Anime Review Engine.",
            "",
            "TAGS:",
            f"{config.series_title}, Episode {ep_num}, Anime Review, Anime Recap, Breakdown, PanelFlow Studio",
        ])

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
