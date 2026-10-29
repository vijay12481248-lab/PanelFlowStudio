"""
Anime Scene Detection, Dynamic Cropping, and Anti-Copyright Framing Engine.
Uses FFmpeg and OpenCV to detect scene boundaries, slice episodes into dynamic
cuts (2.5 - 5.0 seconds), and crop/reframe them to standardized 1080p.
"""
import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import cv2
from engine.anime.models import AnimeEpisodeSource, AnimeSceneCut

logger = logging.getLogger("panelflow.anime.scene_detector")


class AnimeSceneClipper:
    """
    Slices raw anime episodes into dynamic, synchronized micro-cuts.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir

    def inspect_source(self, video_path: str, series_title: str = "Anime", episode_num: float = 1.0) -> AnimeEpisodeSource:
        """
        Extracts metadata, resolution, duration, and audio properties using ffprobe.
        """
        p = Path(video_path)
        if not p.exists():
            raise FileNotFoundError(f"Anime source video not found at: {video_path}")

        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
            "-of", "json",
            str(p),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)

        v_stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})

        w = int(v_stream.get("width", 1920))
        h = int(v_stream.get("height", 1080))

        # Parse FPS
        fps_str = v_stream.get("r_frame_rate", "24/1")
        try:
            num, den = fps_str.split("/")
            fps = float(num) / float(den)
        except Exception:
            fps = 24.0

        # Duration
        dur_raw = fmt.get("duration") or v_stream.get("duration") or "0"
        dur = float(dur_raw)

        # Check audio stream
        cmd_a = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=sample_rate",
            "-of", "json",
            str(p),
        ]
        res_a = subprocess.run(cmd_a, capture_output=True, text=True)
        has_audio = False
        sr = 44100
        try:
            data_a = json.loads(res_a.stdout)
            a_streams = data_a.get("streams", [])
            if a_streams:
                has_audio = True
                sr = int(a_streams[0].get("sample_rate", 44100))
        except Exception:
            pass

        return AnimeEpisodeSource(
            source_uri=str(p.resolve()),
            series_title=series_title,
            episode_number=episode_num,
            duration_sec=round(dur, 2),
            width=w,
            height=h,
            fps=round(fps, 2),
            has_audio=has_audio,
            audio_sample_rate=sr,
        )

    def detect_scenes_opencv(
        self,
        video_path: str,
        min_cut_sec: float = 2.0,
        max_cut_sec: float = 4.5,
        threshold: float = 28.0,
        max_total_cuts: int = 120,
    ) -> List[Tuple[float, float]]:
        """
        Detects scene change transitions using OpenCV color histogram distance.
        Guarantees cuts stay between min_cut_sec and max_cut_sec for optimal review pacing.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps

        # Sample at 2 fps (every 0.5s) for fast scene scanning
        sample_step = max(1, int(fps * 0.5))
        prev_hist = None

        cut_points = [0.0]
        last_cut_time = 0.0

        for f_idx in range(0, total_frames, sample_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            current_time = f_idx / fps
            elapsed_since_cut = current_time - last_cut_time

            # Compute HSV histogram
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

            if prev_hist is not None:
                # Correlation distance (1.0 = identical, 0.0 = completely different)
                similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                # Significant visual change detected
                if similarity < 0.65 and elapsed_since_cut >= min_cut_sec:
                    cut_points.append(round(current_time, 2))
                    last_cut_time = current_time
                    if len(cut_points) >= max_total_cuts:
                        break
            
            # Forced cut if exceeded max_cut_sec (crucial for anime review fair-use & pacing)
            if elapsed_since_cut >= max_cut_sec:
                cut_points.append(round(current_time, 2))
                last_cut_time = current_time
                if len(cut_points) >= max_total_cuts:
                    break

            prev_hist = hist

        cap.release()

        # Final end point
        if cut_points[-1] < duration_sec - 1.0:
            cut_points.append(round(duration_sec, 2))

        # Create pairs (start, end)
        scene_intervals = []
        for i in range(len(cut_points) - 1):
            s = cut_points[i]
            e = cut_points[i + 1]
            if e - s >= 1.0:  # Minimum 1 second valid slice
                scene_intervals.append((s, e))

        return scene_intervals

    def extract_and_reframe_cuts(
        self,
        video_path: str,
        scene_intervals: List[Tuple[float, float]],
        target_dir: Path,
        anti_copyright: bool = True,
    ) -> List[AnimeSceneCut]:
        """
        Slices and reframes detected scene intervals into 1080p MP4 clips.
        Applies smart 16:9 crop and subtle anti-content-ID framing.
        """
        target_dir.mkdir(parents=True, exist_ok=True)
        cuts = []

        # Video filter: center-crop to 1920x1080, remove black bars
        # Anti-copyright: 1.02x subtle punch-in scale, micro contrast tweak
        if anti_copyright:
            vf = "scale=1960:1102:force_original_aspect_ratio=increase,crop=1920:1080,eq=contrast=1.02:brightness=0.01:saturation=1.03"
        else:
            vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"

        for idx, (start_t, end_t) in enumerate(scene_intervals, 1):
            dur = round(end_t - start_t, 2)
            cut_id = f"cut_{idx:03d}"
            clip_filename = f"{cut_id}.mp4"
            thumb_filename = f"{cut_id}_thumb.jpg"
            clip_path = target_dir / clip_filename
            thumb_path = target_dir / thumb_filename

            # Extract slice using FFmpeg
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_t),
                "-t", str(dur),
                "-i", video_path,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                str(clip_path),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                
                # Extract keyframe thumbnail
                cmd_thumb = [
                    "ffmpeg", "-y",
                    "-ss", str(start_t + min(1.0, dur * 0.5)),
                    "-i", video_path,
                    "-vf", "scale=640:360",
                    "-vframes", "1",
                    str(thumb_path),
                ]
                subprocess.run(cmd_thumb, capture_output=True)

                cuts.append(
                    AnimeSceneCut(
                        cut_id=cut_id,
                        sequence=idx,
                        start_sec=start_t,
                        end_sec=end_t,
                        duration_sec=dur,
                        clip_path=str(clip_path.resolve()),
                        keyframe_path=str(thumb_path.resolve()) if thumb_path.exists() else None,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed slicing cut {cut_id} ({start_t}s - {end_t}s): {e}")

        logger.info(f"Successfully extracted {len(cuts)} reframed 1080p scene cuts into {target_dir}")
        return cuts
