"""
Deterministic motion plan cache hashing for PanelFlow Motion Director.
"""
import hashlib
import json
from typing import Any, Dict
from engine.motion.models.input_contract import MotionDirectorInput
from engine.motion.models.timeline import VisualTimeline

PLANNER_VERSION = "motion_v1.0"


class MotionHasher:
    """
    Computes reproducible cryptographic hashes of motion inputs and outputs.
    Guarantees that identical inputs yield identical plan hashes.
    """

    @staticmethod
    def compute_input_hash(input_data: MotionDirectorInput) -> str:
        """
        Produces a stable hash representing all semantic inputs to the motion director.
        """
        components: Dict[str, Any] = {
            "version": PLANNER_VERSION,
            "project_id": input_data.project_id,
            "seed": input_data.seed,
            "resolution": {
                "w": input_data.target_resolution.width,
                "h": input_data.target_resolution.height,
                "fps": input_data.target_resolution.fps,
                "aspect": input_data.target_resolution.aspect_ratio,
            },
            "profile": {
                "preset": input_data.style_profile.preset.value,
                "max_zoom": input_data.style_profile.max_zoom,
                "max_pan": input_data.style_profile.max_pan_distance,
                "speed": input_data.style_profile.movement_speed,
                "easing": input_data.style_profile.camera_easing.value,
                "balloon_policy": input_data.style_profile.speech_balloon_policy.value,
            },
            "visuals": [
                {
                    "asset_id": v.asset_id,
                    "w": v.width,
                    "h": v.height,
                    "boxes": {k: b.model_dump() for k, b in sorted(v.character_bounding_boxes.items())},
                }
                for v in sorted(input_data.visual_sources, key=lambda x: x.asset_id)
            ],
            "script_segments": [
                {
                    "id": seg.segment_id,
                    "scene": seg.scene_id,
                    "speaker": seg.speaker_character_id,
                    "text": seg.text.strip(),
                    "intent": seg.motion_intent.value if seg.motion_intent else None,
                }
                for seg in input_data.script.segments
            ],
            "audio_intervals": [
                {
                    "id": iv.interval_id,
                    "seg_id": iv.script_segment_id,
                    "start": round(iv.start_time, 3),
                    "end": round(iv.end_time, 3),
                }
                for iv in input_data.master_audio_timeline.intervals
            ],
            "overrides": (
                {k: v.model_dump() for k, v in sorted(input_data.manual_overrides.shot_overrides.items())}
                if input_data.manual_overrides else {}
            ),
        }

        blob = json.dumps(components, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_timeline_hash(timeline: VisualTimeline) -> str:
        """
        Produces a stable hash representing the planned shots and camera states.
        """
        shot_data = [
            {
                "id": s.shot_id,
                "asset": s.source_asset_id,
                "start": s.start_time,
                "end": s.end_time,
                "motion": s.motion_type.value,
                "cam_start": s.camera_start.model_dump(),
                "cam_end": s.camera_end.model_dump(),
            }
            for s in timeline.all_shots()
        ]
        blob = json.dumps(shot_data, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
