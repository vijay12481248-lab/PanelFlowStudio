"""
Production RenderEngine for PanelFlow Studio.
Orchestrates RenderPlan compilation, preflight validation, frame composition,
audio mixdown, FFmpeg encoding, and post-render audit.
"""
from typing import Dict, Any, List, Optional, Tuple, Callable
from pathlib import Path
import json
import hashlib

from engine.motion.models.timeline import VisualTimeline, Shot
from engine.motion.models.input_contract import MasterAudioTimeline, AudioInterval
from engine.render.models.render_plan import RenderPlan, RenderShotPlan, RenderAudioTrack
from engine.render.models.profiles import RenderProfile
from engine.render.models.enums import (
    RenderStage,
    RenderStatus,
    ScalePolicy,
    BackgroundFillPolicy,
    MusicDurationPolicy,
    RenderQuality,
)
from engine.render.models.audit import RenderAuditReport
from engine.render.clock import RenderFrameClock
from engine.render.composer import FrameComposer
from engine.render.audio import AudioMixer
from engine.render.encoder import FFmpegEncoder
from engine.render.validator import RenderValidator


class RenderEngine:
    """
    Primary interface for transforming deterministic VisualTimelines into professional MP4 videos.
    """

    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
    ):
        self.encoder = FFmpegEncoder(ffmpeg_path, ffprobe_path)
        self.validator = RenderValidator(self.encoder.ffprobe_path, self.encoder.ffmpeg_path)
        self.mixer = AudioMixer(sample_rate=48000, channels=2)
        self.composer = FrameComposer()

    def compile_render_plan(
        self,
        timeline: VisualTimeline,
        master_audio: MasterAudioTimeline,
        source_assets_map: Dict[str, str],
        bgm_path: Optional[str] = None,
        sfx_tracks: Optional[List[RenderAudioTrack]] = None,
        profile: Optional[RenderProfile] = None,
        music_policy: MusicDurationPolicy = MusicDurationPolicy.LOOP,
    ) -> RenderPlan:
        """
        Translates a VisualTimeline and MasterAudioTimeline into an inspectable, frame-accurate RenderPlan.
        """
        prof = profile or RenderProfile.standard_1080p()
        clock = RenderFrameClock(fps=prof.fps)

        total_duration = max(timeline.total_duration_sec, master_audio.total_duration_sec)
        total_frames = clock.time_to_frame(total_duration)

        all_shots = timeline.all_shots()
        shot_plans: List[RenderShotPlan] = []

        for idx, shot in enumerate(all_shots):
            s_frame, e_frame, n_frames = clock.time_range_to_frame_range(shot.start_time, shot.end_time)

            # Resolve asset path on disk
            asset_path = source_assets_map.get(shot.source_asset_id, shot.source_asset_id)

            shot_plans.append(
                RenderShotPlan(
                    shot_id=shot.shot_id,
                    scene_id=shot.scene_id,
                    sequence_global=shot.sequence_global,
                    source_asset_path=str(asset_path),
                    start_frame=s_frame,
                    end_frame=e_frame,
                    total_frames=n_frames,
                    start_time=shot.start_time,
                    end_time=shot.end_time,
                    duration=shot.duration,
                    camera_start=shot.camera_start,
                    camera_end=shot.camera_end,
                    easing=shot.easing,
                    motion_type=shot.motion_type,
                    frame_region=shot.frame_region,
                    scale_policy=ScalePolicy.COVER,
                    fill_policy=BackgroundFillPolicy.BLACK,
                    layers=shot.layer_instructions,
                    effects=shot.effect_instructions,
                    transition_in=shot.transition_in,
                    transition_out=shot.transition_out,
                    captions=shot.caption_cues,
                )
            )

        # 2. Build Audio Tracks
        audio_tracks: List[RenderAudioTrack] = []
        speech_intervals: List[Tuple[float, float, float]] = []

        for iv in master_audio.intervals:
            if iv.is_speech and iv.audio_file_uri:
                speech_intervals.append((iv.start_time, iv.end_time, -8.0))
                audio_tracks.append(
                    RenderAudioTrack(
                        track_type="dialogue",
                        file_path=iv.audio_file_uri,
                        start_time=iv.start_time,
                        end_time=iv.end_time,
                        gain_db=0.0,
                    )
                )

        # 3. Add BGM Track if provided
        if bgm_path and Path(bgm_path).exists():
            audio_tracks.append(
                RenderAudioTrack(
                    track_type="music",
                    file_path=str(bgm_path),
                    start_time=0.0,
                    end_time=total_duration,
                    gain_db=-10.0,  # Balanced music volume
                    ducking_intervals=speech_intervals,
                )
            )

        # 4. Add additional SFX if provided
        if sfx_tracks:
            audio_tracks.extend(sfx_tracks)

        # Compute deterministic plan hash
        hash_blob = json.dumps(
            {
                "project_id": timeline.project_id,
                "duration": total_duration,
                "frames": total_frames,
                "shots": [s.shot_id for s in shot_plans],
                "audio": [a.file_path for a in audio_tracks],
                "profile": prof.model_dump(),
            },
            sort_keys=True,
        )
        plan_hash = hashlib.sha256(hash_blob.encode("utf-8")).hexdigest()

        return RenderPlan(
            project_id=timeline.project_id,
            total_duration_sec=total_duration,
            total_frames=total_frames,
            profile=prof,
            shots=shot_plans,
            audio_tracks=audio_tracks,
            music_policy=music_policy,
            hash=plan_hash,
        )

    def preflight_check(self, plan: RenderPlan) -> Tuple[bool, List[str]]:
        """
        Validates all prerequisites before committing compute to expensive frame generation.
        """
        issues: List[str] = []

        # 1. Check FFmpeg runtime
        rt = self.encoder.check_runtime()
        if not rt["available"]:
            issues.append(f"FFmpeg missing or inoperable: {rt.get('error')}")

        # 2. Check source visual assets exist
        for s in plan.shots:
            p = Path(s.source_asset_path)
            if not p.exists() or not p.is_file():
                issues.append(f"Source asset for shot '{s.shot_id}' not found: {s.source_asset_path}")

        # 3. Check audio files exist
        for a in plan.audio_tracks:
            p = Path(a.file_path)
            if not p.exists() or not p.is_file():
                issues.append(f"Audio asset for track '{a.track_id}' not found: {a.file_path}")

        # 4. Check timeline continuity
        if plan.total_frames <= 0:
            issues.append(f"Invalid plan total_frames: {plan.total_frames}")

        return (len(issues) == 0), issues

    def execute_render(
        self,
        plan: RenderPlan,
        output_mp4_path: Path,
        workspace_dir: Optional[Path] = None,
        progress_cb: Optional[Callable[[RenderStage, int, int, float], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> RenderAuditReport:
        """
        Executes preflight, audio mixdown, video frame piping, and post-render validation.
        """
        # 1. Preflight
        passed, issues = self.preflight_check(plan)
        if not passed:
            return RenderAuditReport(
                is_valid=False,
                output_mp4_path=str(output_mp4_path),
                warnings=[f"Preflight validation failed: {'; '.join(issues)}"],
            )

        # 2. Setup deterministic workspace
        work_dir = workspace_dir or (output_mp4_path.parent / "workspace" / f"render_{plan.hash[:12]}")
        work_dir.mkdir(parents=True, exist_ok=True)

        # Save RenderPlan JSON
        plan_json_path = work_dir / "render_plan.json"
        with open(plan_json_path, "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))

        # 3. Audio Mixdown
        if progress_cb:
            progress_cb(RenderStage.PREPARING, 0, plan.total_frames, 0.0)

        mixed_audio_wav = work_dir / "mixed_master_audio.wav"
        mix_ok, mix_metrics = self.mixer.mix_timeline_audio(plan, mixed_audio_wav)
        if not mix_ok:
            return RenderAuditReport(
                is_valid=False,
                output_mp4_path=str(output_mp4_path),
                warnings=["Audio mixdown failed."],
            )

        # 4. Encode Video & Mux
        output_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        encode_success = self.encoder.encode_video_with_audio(
            plan=plan,
            composer=self.composer,
            audio_wav_path=mixed_audio_wav,
            output_mp4_path=output_mp4_path,
            progress_cb=progress_cb,
            cancel_token=cancel_token,
        )

        if not encode_success:
            return RenderAuditReport(
                is_valid=False,
                output_mp4_path=str(output_mp4_path),
                warnings=["Encoding was cancelled or interrupted."],
            )

        # 5. Post-Render Validation & Frame Sampling Audit
        if progress_cb:
            progress_cb(RenderStage.VALIDATING, plan.total_frames, plan.total_frames, 100.0)

        audit_report = self.validator.validate_mp4_output(
            output_mp4_path=output_mp4_path,
            plan=plan,
            sample_work_dir=work_dir / "audit_samples",
        )

        # Save validation JSON
        validation_json_path = work_dir / "validation_report.json"
        with open(validation_json_path, "w", encoding="utf-8") as f:
            f.write(audit_report.model_dump_json(indent=2))

        if progress_cb:
            progress_cb(RenderStage.COMPLETE, plan.total_frames, plan.total_frames, 100.0)

        return audit_report
