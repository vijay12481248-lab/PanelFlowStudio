"""
Audio Director Service for PanelFlow Studio.
Coordinates speech synthesis, MasterAudioTimeline assembly, selective regeneration,
and audio approval gates.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import copy
import logging
import soundfile as sf
import io
from datetime import datetime, timezone
from sqlalchemy.orm import Session

logger = logging.getLogger("panelflow.audio.service")

from engine.database.models import ProjectRecord, VideoScriptRecord, ScriptSegmentRecord, AudioTimelineRecord, VisualTimelineRecord, RenderJobRecord
from engine.acquisition.models.models import PipelineStage
from engine.motion.models.input_contract import MasterAudioTimeline, AudioInterval, TimelineSourceType
from engine.security.paths import ensure_contained_directory, read_contained_bytes, write_contained_json


def _contained_audio_info(workspace: Path | str, path: Path | str):
    return sf.info(io.BytesIO(read_contained_bytes(workspace, path)))


def utc_now():
    return datetime.now(timezone.utc)


class AudioService:
    """
    Manages speech audio synthesis, music track binding, and MasterAudioTimeline synchronization.
    """

    def __init__(self):
        from engine.audio.synthesis import local_synthesizer
        self.synthesizer = local_synthesizer

    def synthesize_narration_segment(
        self,
        workspace_path: Path,
        segment_id: str,
        text: str,
        voice: str,
        emotion: str = "Neutral",
        intensity: float = 0.5,
        speed: float = 1.0,
        text_revision: int = 1,
        force: bool = False,
    ) -> Dict[str, Any]:
        dialogue_dir = Path(workspace_path) / "audio" / "dialogue"
        ensure_contained_directory(workspace_path, Path("audio") / "dialogue")
        wav_path = self.synthesizer.synthesize(
            directory=dialogue_dir,
            text=text,
            voice=voice,
            emotion=emotion,
            intensity=intensity,
            pace=speed,
            text_revision=text_revision,
            force=force,
        )
        info = _contained_audio_info(workspace_path, wav_path)
        return {
            "success": True,
            "segment_id": segment_id,
            "audio_path": str(wav_path),
            "measured_duration_sec": round(info.duration, 3),
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "generated_audio_revision": text_revision,
        }

    def synthesize_narration_batch(
        self,
        workspace_path: Path,
        tasks: List[Dict[str, Any]],
        progress=lambda *args: None,
        cancelled=lambda: False,
    ) -> List[Dict[str, Any]]:
        dialogue_dir = Path(workspace_path) / "audio" / "dialogue"
        ensure_contained_directory(workspace_path, Path("audio") / "dialogue")
        batch_tasks = []
        for t in tasks:
            batch_tasks.append({
                "id": t["segment_id"],
                "directory": str(dialogue_dir),
                "text": t["text"],
                "voice": t.get("voice", "Narrator"),
                "emotion": t.get("emotion", "Neutral"),
                "intensity": t.get("intensity", 0.5),
                "pace": t.get("speed", 1.0),
                "text_revision": t.get("text_revision", 1),
                "force": t.get("force", False),
            })
        return self.synthesizer.synthesize_batch(batch_tasks, progress_cb=progress, cancelled_cb=cancelled)

    def get_audio_timeline(self, db: Session, project_id: str) -> Optional[Dict[str, Any]]:
        record = (
            db.query(AudioTimelineRecord)
            .filter(AudioTimelineRecord.project_id == project_id)
            .order_by(AudioTimelineRecord.created_at.desc())
            .first()
        )
        if not record:
            return None

        warnings = []
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        plan_path = Path(project.workspace_path) / "audio" / "chapter_audio_plan.json" if project else None
        if plan_path:
            try:
                warnings = json.loads(read_contained_bytes(str(project.workspace_path), Path("audio") / "chapter_audio_plan.json").decode("utf-8")).get("warnings", [])
            except FileNotFoundError:
                pass
        return {
            "id": record.id,
            "project_id": record.project_id,
            "status": record.status,
            "total_duration": record.total_duration,
            "voice_casting": record.voice_casting,
            "warnings": warnings,
            "timeline": record.timeline_json,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    _DEFAULT_VOICE_CASTING = {
        "char_marcus": "Marcus (Male Deep F5-TTS)",
        "char_narrator": "Narrator",
        "NARRATOR": "Narrator",
        "narrator": "Narrator",
        "The Narrator": "Narrator",
        "char_seraphina": "Seraphina (Cinematic)",
        "char_aria": "Aria (The Narrator)",
        "char_leon": "Leon",
    }
    _TTS_MODELS = {"chatterbox_turbo": "ChatterboxTurboTTS"}

    def resolve_voice_casting(self, voice_casting: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Freeze the complete voice map so recovery does not inherit new defaults."""
        return {**self._DEFAULT_VOICE_CASTING, **(voice_casting or {})}

    def resolve_tts_provider_identity(self, db: Session, project_id: str) -> tuple[str, str]:
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        provider_id = (project.settings or {}).get("tts_provider", "chatterbox_turbo")
        model_name = (project.settings or {}).get("tts_model") or self._TTS_MODELS.get(provider_id)
        if not isinstance(provider_id, str) or not isinstance(model_name, str):
            raise ValueError("Configured TTS provider/model identity is incomplete")
        self.validate_pinned_tts_provider(provider_id, model_name, require_available=False)
        return provider_id, model_name

    def validate_pinned_tts_provider(
        self,
        provider_id: str,
        model_name: str,
        *,
        require_available: bool = True,
    ) -> None:
        """Reject unavailable or drifted persisted TTS identities without fallback."""
        expected_model = self._TTS_MODELS.get(provider_id)
        if expected_model is None or expected_model != model_name:
            raise RuntimeError(f"Persisted TTS provider/model is unavailable: {provider_id}/{model_name}")
        if require_available and not getattr(self.synthesizer, "adapter_factory", None):
            python_exe = getattr(self.synthesizer, "python_exe", None)
            if python_exe is not None and not python_exe.exists():
                raise RuntimeError(f"Persisted TTS provider is unavailable: {provider_id}")

    def generate_audio_timeline(
        self,
        db: Session,
        project_id: str,
        voice_casting: Optional[Dict[str, str]] = None,
        progress=lambda *args: None,
        cancelled=lambda: False,
        tts_provider_id: str | None = None,
        tts_model_name: str | None = None,
        voice_casting_is_resolved: bool = False,
    ) -> Dict[str, Any]:
        """
        Synthesizes / aligns all dialogue segments from the approved script into a MasterAudioTimeline.
        """
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        script = (
            db.query(VideoScriptRecord)
            .filter(VideoScriptRecord.project_id == project_id)
            .order_by(VideoScriptRecord.created_at.desc())
            .first()
        )
        if not script or not script.segments:
            raise ValueError("No script segments found for audio generation. Complete script adaptation first.")

        if script.status != "APPROVED":
            raise ValueError("Approve the script before generating narration audio.")

        workspace = Path(proj.workspace_path)
        audio_dir = workspace / "audio"
        dialogue_dir = audio_dir / "dialogue"
        ensure_contained_directory(workspace, Path("audio") / "dialogue")

        if tts_provider_id is None and tts_model_name is None:
            tts_provider_id, tts_model_name = self.resolve_tts_provider_identity(db, project_id)
        else:
            self.validate_pinned_tts_provider(tts_provider_id or "", tts_model_name or "")
        voice_map = dict(voice_casting or {}) if voice_casting_is_resolved else self.resolve_voice_casting(voice_casting)

        intervals: List[AudioInterval] = []
        current_time = 0.5  # 0.5s pre-speech establishing pause

        ordered_segments = sorted(script.segments, key=lambda item: item.sequence)

        # Batch synthesize all dialogue speech segments in a single model load session
        speech_tasks = []
        for seg in ordered_segments:
            if not seg.text.strip() or seg.type in ("PAUSE", "TRANSITION", "SFX_CUE"):
                continue
            speaker_key = seg.speaker_character_id or "NARRATOR"
            voice = voice_map.get(speaker_key) or voice_map.get(speaker_key.lower()) or "Narrator"
            speech_tasks.append({
                "id": seg.id,
                "directory": str(dialogue_dir),
                "text": seg.text,
                "voice": voice,
                "emotion": seg.emotion or "Neutral",
                "intensity": seg.intensity if seg.intensity is not None else 0.5,
                "pace": 1.0,
                "text_revision": 1,
                "force": False,
            })

        batch_results_map: Dict[str, Any] = {}
        if speech_tasks and hasattr(self.synthesizer, "synthesize_batch"):
            progress(0.1, f"Synthesizing {len(speech_tasks)} dialogue segments with local TTS...")
            try:
                batch_res = self.synthesizer.synthesize_batch(
                    speech_tasks,
                    provider_id=tts_provider_id,
                    progress_cb=progress,
                    cancelled_cb=cancelled,
                )
                for br in batch_res:
                    if br.get("success"):
                        batch_results_map[br["id"]] = br
                    else:
                        logger.warning(f"Batch TTS failed for segment {br.get('id')}: {br.get('error')}")
            except Exception as e:
                logger.warning(f"Batch synthesis exception: {e}, falling back to per-segment synthesis")

        for index, seg in enumerate(ordered_segments):
            if cancelled():
                raise ValueError("TTS cancelled; approved script and completed speech clips were preserved.")
            progress(0.7 + 0.2 * index / max(1, len(ordered_segments)), f"Assembling audio timeline: segment {index + 1}/{len(ordered_segments)}")
            if not seg.text.strip() or seg.type in ("PAUSE", "TRANSITION", "SFX_CUE"):
                end_time = current_time + max(0.0, seg.estimated_duration)
                intervals.append(AudioInterval(
                    script_segment_id=seg.id, start_time=current_time, end_time=end_time,
                    is_speech=False, text="",
                ))
                current_time = end_time
                continue

            br = batch_results_map.get(seg.id)
            if br and br.get("audio_path"):
                seg_audio_file = Path(br["audio_path"])
                dur = round(br.get("duration", 3.0), 3)
            else:
                speaker_key = seg.speaker_character_id or "NARRATOR"
                voice = voice_map.get(speaker_key) or voice_map.get(speaker_key.lower()) or "Narrator"
                seg_audio_file = self.synthesizer.synthesize(
                    dialogue_dir, seg.text, voice,
                    provider_id=tts_provider_id,
                    emotion=seg.emotion, intensity=seg.intensity,
                )
                info = _contained_audio_info(workspace, seg_audio_file)
                dur = round(info.duration, 3)

            start_t = round(current_time, 3)
            end_t = round(start_t + dur, 3)

            intervals.append(
                AudioInterval(
                    interval_id=f"iv_{seg.id[:8]}",
                    script_segment_id=seg.id,
                    speaker_character_id=seg.speaker_character_id or "char_marcus",
                    start_time=start_t,
                    end_time=end_t,
                    audio_file_uri=str(seg_audio_file),
                    text=seg.text,
                    is_speech=True,
                )
            )

            # 0.5s natural pause between dialogue sentences
            current_time = end_t + 0.5

        total_duration = round(current_time + 1.0, 3)  # 1.0s tail padding

        mat = MasterAudioTimeline(
            project_id=project_id,
            total_duration_sec=total_duration,
            timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
            intervals=intervals,
            sample_rate=48000,
            channels=2,
        )
        chapter_plan = {"warnings": []}
        if (proj.settings or {}).get("visual_storytelling"):
            progress(0.9, "Planning chapter music and sparse sound effects...")
            from engine.audio.chapter_plan import plan_chapter_audio
            chapter_plan = plan_chapter_audio(workspace, proj.settings or {}, ordered_segments, mat.model_dump())
        if cancelled():
            raise ValueError("Audio generation cancelled; generated assets were preserved.")

        # Save JSON sidecar
        write_contained_json(workspace, Path("audio") / "master_audio_timeline.json", mat.model_dump())

        # Persist record in SQLite
        rec = AudioTimelineRecord(
            project_id=project_id,
            status="DRAFT",
            total_duration=total_duration,
            timeline_json=mat.model_dump(),
            voice_casting=voice_map,
        )
        db.add(rec)
        from engine.story.dependency import mark_media_stale
        mark_media_stale(db, project_id, include_audio=False)

        # Update project stage to VOICE_GENERATED
        proj.current_stage = PipelineStage.VOICE_GENERATED.value
        proj.updated_at = utc_now()
        db.commit()
        db.refresh(rec)

        return {
            "id": rec.id,
            "project_id": rec.project_id,
            "status": rec.status,
            "total_duration": total_duration,
            "intervals_count": len(intervals),
            "timeline": mat.model_dump(),
            "warnings": chapter_plan["warnings"],
        }

    def regenerate_segment_audio(
        self,
        db: Session,
        project_id: str,
        segment_id: str,
    ) -> Dict[str, Any]:
        """
        Selective regeneration: Re-synthesizes ONLY the specified segment.
        Recalculates subsequent start/end timestamps while keeping all other WAV files intact.
        """
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        record = (
            db.query(AudioTimelineRecord)
            .filter(AudioTimelineRecord.project_id == project_id)
            .order_by(AudioTimelineRecord.created_at.desc())
            .first()
        )
        if not record:
            raise ValueError("No existing audio timeline found to regenerate.")

        mat_dict = copy.deepcopy(record.timeline_json)
        intervals = mat_dict.get("intervals", [])

        # Find target interval
        target_idx = -1
        for idx, iv in enumerate(intervals):
            if iv.get("script_segment_id") == segment_id:
                target_idx = idx
                break

        if target_idx == -1:
            raise ValueError(f"Segment {segment_id} not found in audio timeline.")

        target_iv = intervals[target_idx]
        wav_path = Path(target_iv["audio_file_uri"])

        segment = db.query(ScriptSegmentRecord).filter(
            ScriptSegmentRecord.id == segment_id,
            ScriptSegmentRecord.project_id == project_id,
        ).first()
        if not segment or not segment.text.strip():
            raise ValueError("Narration segment not found or empty.")
        script = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == segment.script_id).first()
        if not script or script.status != "APPROVED":
            raise ValueError("Approve the edited script before regenerating speech.")
        voice = (record.voice_casting or {}).get(segment.speaker_character_id or "NARRATOR", "Narrator")
        wav_path = self.synthesizer.synthesize(
            Path(proj.workspace_path) / "audio" / "dialogue", segment.text, voice,
            provider_id=(proj.settings or {}).get("tts_provider", "chatterbox_turbo"),
            emotion=segment.emotion, intensity=segment.intensity, force=True,
        )
        target_iv["audio_file_uri"] = str(wav_path)
        target_iv["text"] = segment.text

        # Preserve explicit pauses and original inter-clip gaps when speech changes.
        previous_intervals = copy.deepcopy(intervals)
        tail_padding = max(0.0, mat_dict["total_duration_sec"] - previous_intervals[-1]["end_time"])
        current_time = float(target_iv["start_time"])
        for idx in range(target_idx, len(intervals)):
            iv = intervals[idx]
            previous = previous_intervals[idx]
            if idx > target_idx:
                current_time += max(0.0, previous["start_time"] - previous_intervals[idx - 1]["end_time"])
            file_dur = (round(_contained_audio_info(str(proj.workspace_path), iv["audio_file_uri"]).duration, 3) if iv.get("audio_file_uri")
                        else previous["end_time"] - previous["start_time"])
            iv["start_time"] = round(current_time, 3)
            iv["end_time"] = round(current_time + file_dur, 3)
            current_time = iv["end_time"]

        total_duration = round(current_time + tail_padding, 3)
        mat_dict["total_duration_sec"] = total_duration
        mat_dict["intervals"] = intervals

        write_contained_json(str(proj.workspace_path), Path("audio") / "master_audio_timeline.json", mat_dict)

        # Mark as DRAFT and invalidate downstream motion & render
        record.timeline_json = mat_dict
        record.total_duration = total_duration
        record.status = "DRAFT"
        record.updated_at = utc_now()
        proj.updated_at = utc_now()
        for motion in db.query(VisualTimelineRecord).filter(VisualTimelineRecord.project_id == project_id).all():
            motion.status = "STALE"
        for render in db.query(RenderJobRecord).filter(RenderJobRecord.project_id == project_id, RenderJobRecord.status == "COMPLETE").all():
            render.status = "STALE"
        if (proj.settings or {}).get("visual_storytelling"):
            from engine.audio.chapter_plan import plan_chapter_audio
            plan_settings = dict(proj.settings or {})
            plan_settings["auto_music"] = False
            try:
                prior = json.loads(read_contained_bytes(str(proj.workspace_path), Path("audio") / "chapter_audio_plan.json").decode("utf-8"))
                plan_settings["chapter_music_path"] = prior.get("music", {}).get("path")
            except FileNotFoundError:
                pass
            plan_chapter_audio(Path(proj.workspace_path), plan_settings, sorted(script.segments, key=lambda s: s.sequence), mat_dict)
        db.commit()

        return {
            "status": "REGENERATED",
            "segment_id": segment_id,
            "total_duration": total_duration,
            "timeline": mat_dict,
        }

    def approve_audio(self, db: Session, project_id: str) -> bool:
        record = (
            db.query(AudioTimelineRecord)
            .filter(AudioTimelineRecord.project_id == project_id)
            .order_by(AudioTimelineRecord.created_at.desc())
            .first()
        )
        if not record:
            raise ValueError("No audio timeline found to approve.")
        if record.status == "STALE":
            raise ValueError("Audio is stale; regenerate the edited narration before approving.")
        script = db.query(VideoScriptRecord).filter(VideoScriptRecord.project_id == project_id).order_by(VideoScriptRecord.created_at.desc()).first()
        if not script or script.status != "APPROVED":
            raise ValueError("Approve the current script before approving audio.")
        current_segments = {s.id: s for s in script.segments}
        speech_segment_ids = set()
        for interval in record.timeline_json.get("intervals", []):
            segment = current_segments.get(interval.get("script_segment_id"))
            if interval.get("is_speech"):
                if segment is None or interval.get("text") != segment.text:
                    raise ValueError("Audio does not match the approved script; regenerate changed segments.")
                speech_segment_ids.add(segment.id)
        expected_speech_ids = {s.id for s in script.segments if getattr(s, "segment_type", None) != "PAUSE"}
        if speech_segment_ids != expected_speech_ids:
            raise ValueError("Audio does not cover every approved narration segment; regenerate audio.")

        record.status = "APPROVED"
        record.updated_at = utc_now()

        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if proj:
            proj.current_stage = PipelineStage.AUDIO_APPROVED.value
            proj.updated_at = utc_now()

        db.commit()
        return True


audio_service = AudioService()
