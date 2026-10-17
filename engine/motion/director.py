"""
Motion Director primary public facade for PanelFlow Studio.
Coordinates shot planning, camera bounds validation, effect budgeting, and timeline caching.
"""
from typing import Optional, Dict, Any, List, Set
from pathlib import Path
import json

from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.input_contract import MotionDirectorInput, MotionOverrides
from engine.motion.models.overrides import ShotOverride
from engine.motion.models.warnings import MotionWarning
from engine.motion.models.enums import WarningType, WarningSeverity
from engine.motion.planning.shot_planner import ShotPlanner
from engine.motion.planning.invalidation import MotionInvalidationManager
from engine.motion.validation.composition_validator import CompositionValidator
from engine.motion.hashing import MotionHasher


class MotionDirector:
    """
    Primary interface for transforming approved narrative scripts and source artwork
    into professional, synchronized motion-comic visual timelines.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.planner = ShotPlanner()
        self.validator = CompositionValidator()
        self.invalidation_manager = MotionInvalidationManager()
        self.hasher = MotionHasher()
        self.cache_dir = cache_dir

        # In-memory plan cache
        self._plan_cache: Dict[str, VisualTimeline] = {}

    def plan_visual_timeline(
        self,
        input_data: MotionDirectorInput,
        force_regenerate: bool = False,
    ) -> VisualTimeline:
        """
        Generates a complete, render-ready VisualTimeline locked to the MasterAudioTimeline.
        """
        input_hash = self.hasher.compute_input_hash(input_data)

        # Check cache if not forcing regeneration
        if not force_regenerate and input_hash in self._plan_cache:
            return self._plan_cache[input_hash]

        # 1. Execute Shot Planner
        timeline = self.planner.plan_timeline(input_data)

        # 2. Audit Timeline Composition
        known_assets = [v.asset_id for v in input_data.visual_sources]
        is_valid, comp_warnings = self.validator.validate_timeline(
            timeline=timeline,
            known_visual_asset_ids=known_assets,
        )
        timeline.warnings.extend(comp_warnings)

        # 3. Compute reproducible timeline hash
        timeline.hash = self.hasher.compute_timeline_hash(timeline)

        # Cache plan
        self._plan_cache[input_hash] = timeline

        if self.cache_dir:
            self._persist_to_cache(input_hash, timeline)

        return timeline

    def regenerate_scenes(
        self,
        input_data: MotionDirectorInput,
        existing_timeline: VisualTimeline,
        scene_ids_to_regenerate: Set[str],
    ) -> VisualTimeline:
        """
        Selectively regenerates specified scenes while preserving sibling scenes and locked overrides.
        """
        # Filter input data to only target scenes
        filtered_segments = [
            seg for seg in input_data.script.segments
            if seg.scene_id in scene_ids_to_regenerate
        ]
        if not filtered_segments:
            return existing_timeline

        # Create temporary input for the subset
        subset_script = input_data.script.model_copy(deep=True)
        subset_script.segments = filtered_segments

        subset_input = input_data.model_copy(deep=True)
        subset_input.script = subset_script

        # Plan the new subset scenes
        regenerated_subset = self.planner.plan_timeline(subset_input)

        # Splice into existing timeline
        overrides = input_data.manual_overrides or MotionOverrides()
        spliced = self.invalidation_manager.splice_regenerated_scenes(
            existing_timeline=existing_timeline,
            new_scenes=regenerated_subset.scenes,
            overrides=overrides,
        )

        # Re-validate spliced timeline
        known_assets = [v.asset_id for v in input_data.visual_sources]
        _, comp_warnings = self.validator.validate_timeline(spliced, known_visual_asset_ids=known_assets)
        spliced.warnings.extend(comp_warnings)
        spliced.hash = self.hasher.compute_timeline_hash(spliced)

        return spliced

    def apply_override_to_timeline(
        self,
        timeline: VisualTimeline,
        override: ShotOverride,
    ) -> VisualTimeline:
        """
        Applies a user-directed manual override to an individual shot in the timeline.
        """
        updated_scenes: List[MotionScene] = []
        applied = False

        for sc in timeline.scenes:
            updated_shots: List[Shot] = []
            for s in sc.shots:
                if s.shot_id == override.shot_id:
                    s = self.planner._apply_override(s, override)
                    applied = True
                updated_shots.append(s)
            sc.shots = updated_shots
            updated_scenes.append(sc)

        if not applied:
            timeline.warnings.append(
                MotionWarning(
                    warning_type=WarningType.MOTION_PLAN_STALE,
                    severity=WarningSeverity.WARNING,
                    message=f"Override targeted shot '{override.shot_id}' which was not found in timeline.",
                )
            )

        timeline.scenes = updated_scenes
        timeline.hash = self.hasher.compute_timeline_hash(timeline)
        return timeline

    def _persist_to_cache(self, input_hash: str, timeline: VisualTimeline):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self.cache_dir / f"motion_plan_{input_hash[:16]}.json"
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(timeline.model_dump_json(indent=2))
        except Exception:
            pass
