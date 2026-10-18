"""
FFmpeg discovery, process orchestration, and frame pipe encoder for PanelFlow Production Renderer.
"""
from typing import Optional, Dict, Any, Callable
from pathlib import Path
import subprocess
import shutil
import os
import sys

from engine.render.models.render_plan import RenderPlan
from engine.render.models.enums import RenderStage
from engine.render.composer import FrameComposer


class FFmpegEncoder:
    """
    Orchestrates FFmpeg subprocess execution and streams raw RGB video frames directly to stdin.
    """

    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
    ):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or self._find_fallback_ffmpeg()
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe") or self._find_fallback_ffprobe()

    def _find_fallback_ffmpeg(self) -> Optional[str]:
        # Check standard winget location on Windows
        winget_pattern = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_pattern.exists():
            for p in winget_pattern.rglob("ffmpeg.exe"):
                return str(p)
        return None

    def _find_fallback_ffprobe(self) -> Optional[str]:
        winget_pattern = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        if winget_pattern.exists():
            for p in winget_pattern.rglob("ffprobe.exe"):
                return str(p)
        return None

    def check_runtime(self) -> Dict[str, Any]:
        """
        Inspects local system for FFmpeg and ffprobe binary availability and codec support.
        """
        if not self.ffmpeg_path or not Path(self.ffmpeg_path).exists():
            return {
                "available": False,
                "error": "FFMPEG_RUNTIME_MISSING",
                "ffmpeg_path": None,
                "ffprobe_path": None,
            }

        try:
            res = subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True, timeout=5)
            version_line = res.stdout.splitlines()[0] if res.stdout else "unknown"

            # Check for hardware nvenc support
            nvenc_supported = "enable-nvenc" in res.stdout or "h264_nvenc" in res.stdout
            x264_supported = "enable-libx264" in res.stdout

            return {
                "available": True,
                "version": version_line,
                "ffmpeg_path": str(self.ffmpeg_path),
                "ffprobe_path": str(self.ffprobe_path) if self.ffprobe_path else None,
                "h264_software": x264_supported,
                "h264_hardware_nvenc": nvenc_supported,
                "aac_audio": True,
            }
        except Exception as e:
            return {
                "available": False,
                "error": f"FFMPEG_EXEC_ERROR: {str(e)}",
                "ffmpeg_path": str(self.ffmpeg_path),
            }

    def encode_video_with_audio(
        self,
        plan: RenderPlan,
        composer: FrameComposer,
        audio_wav_path: Path,
        output_mp4_path: Path,
        progress_cb: Optional[Callable[[RenderStage, int, int, float], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Streams composited RGB frames to FFmpeg stdin and muxes the mixed audio WAV track.
        """
        runtime = self.check_runtime()
        if not runtime["available"]:
            raise RuntimeError(f"FFmpeg runtime check failed: {runtime.get('error')}")

        output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        w = plan.profile.width
        h = plan.profile.height
        fps = plan.profile.fps
        total_frames = plan.total_frames

        # FFmpeg command line
        cmd = [
            self.ffmpeg_path,
            "-y",  # Overwrite output
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{w}x{h}",
            "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "-",  # Video frames from stdin
            "-i", str(audio_wav_path),  # Audio from WAV
            "-c:v", plan.profile.video_codec,
            "-pix_fmt", plan.profile.pixel_format,
            "-crf", str(plan.profile.crf),
            "-preset", plan.profile.preset,
            "-c:a", plan.profile.audio_codec,
            "-b:a", f"{plan.profile.audio_bitrate_kbps}k",
            "-shortest",
            "-movflags", "+faststart",
            str(output_mp4_path),
        ]

        if progress_cb:
            progress_cb(RenderStage.ENCODING, 0, total_frames, 0.0)

        log_path = output_mp4_path.parent / "ffmpeg_encode.log"
        with open(log_path, "wb") as log_f:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=log_f,
            )

            try:
                for frame_idx in range(total_frames):
                    if cancel_token and cancel_token():
                        try:
                            proc.kill()
                            proc.wait(timeout=5)
                        except Exception:
                            pass
                        try:
                            if output_mp4_path.exists():
                                output_mp4_path.unlink()
                        except Exception:
                            pass
                        if progress_cb:
                            progress_cb(RenderStage.CANCELLED, frame_idx, total_frames, 0.0)
                        return False

                    # 1. Compose frame
                    frame_img = composer.compose_frame(frame_idx, plan)
                    if frame_img.mode != "RGB":
                        frame_img = frame_img.convert("RGB")
                    if frame_img.size != (w, h):
                        frame_img = frame_img.resize((w, h), Image.Resampling.LANCZOS)

                    # 2. Write raw RGB bytes to FFmpeg stdin
                    try:
                        raw_bytes = frame_img.tobytes()
                        proc.stdin.write(raw_bytes)
                    except (BrokenPipeError, OSError):
                        break

                    # 3. Report progress periodically
                    if progress_cb and (frame_idx % 15 == 0 or frame_idx == total_frames - 1):
                        pct = round((frame_idx + 1) / total_frames * 100.0, 1)
                        progress_cb(RenderStage.ENCODING, frame_idx + 1, total_frames, pct)

                # Close stdin to signal end of stream
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                proc.wait(timeout=300)

                if proc.returncode != 0:
                    err_msg = ""
                    if log_path.exists():
                        err_msg = log_path.read_text(encoding="utf-8", errors="ignore")[-800:]
                    raise RuntimeError(f"FFmpeg encoding failed (code {proc.returncode}): {err_msg}")

                if progress_cb:
                    progress_cb(RenderStage.MUXING, total_frames, total_frames, 100.0)

                return True

            except Exception as e:
                err_msg = ""
                if log_path.exists():
                    try:
                        err_msg = log_path.read_text(encoding="utf-8", errors="ignore")[-1200:]
                    except Exception:
                        pass
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
                try:
                    if output_mp4_path.exists():
                        output_mp4_path.unlink()
                except Exception:
                    pass
                raise RuntimeError(f"FFmpeg encoding exception: {e} | Stderr: {err_msg}") from e
