"""
Selective invalidation and dependency manager for PanelFlow Motion Director.
Enables fine-grained scene-level regeneration without destroying unrelated valid shots or overrides.
"""
from typing import Set, List, Dict
from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.overrides import MotionOverrides


class MotionInvalidationManager:
    """
    Tracks upstream dependencies and manages selective scene/shot invalidation.
    """

    def find_stale_scene_ids_from_script(
        self,
        timeline: VisualTimeline,
        modified_scene_ids: Set[str],
    ) -> Set[str]:
        """
        Returns scene IDs that must be replanned due to script or audio timing changes.
        """
        stale = set()
        for scene in timeline.scenes:
            if scene.scene_id in modified_scene_ids:
                stale.add(scene.scene_id)
        return stale

    def find_stale_scene_ids_from_visuals(
        self,
        timeline: VisualTimeline,
        modified_asset_ids: Set[str],
    ) -> Set[str]:
        """
        Returns scene IDs containing shots that reference modified visual assets.
        """
        stale = set()
        for scene in timeline.scenes:
            for shot in scene.shots:
                if shot.source_asset_id in modified_asset_ids:
                    stale.add(scene.scene_id)
                    break
        return stale

    def splice_regenerated_scenes(
        self,
        existing_timeline: VisualTimeline,
        new_scenes: List[MotionScene],
        overrides: MotionOverrides,
    ) -> VisualTimeline:
        """
        Splices newly regenerated scenes into the existing timeline while preserving
        locked manual overrides and valid sibling scenes.
        """
        new_scene_map = {sc.scene_id: sc for sc in new_scenes}
        final_scenes: List[MotionScene] = []

        current_clock = 0.0
        global_shot_seq = 1

        for old_scene in existing_timeline.scenes:
            if old_scene.scene_id in new_scene_map:
                # Use regenerated scene
                replacement = new_scene_map[old_scene.scene_id]
                dur = replacement.duration
                time_shift = current_clock - replacement.start_time
                updated_shots: List[Shot] = []
                for s in replacement.shots:
                    # Check if shot was locked by user
                    if overrides.is_shot_locked(s.shot_id):
                        locked_shot = existing_timeline.find_shot_by_id(s.shot_id)
                        if locked_shot:
                            updated_shots.append(locked_shot)
                            continue
                    s.sequence_global = global_shot_seq
                    global_shot_seq += 1
                    s.start_time = round(s.start_time + time_shift, 4)
                    s.end_time = round(s.end_time + time_shift, 4)
                    updated_shots.append(s)

                replacement.shots = updated_shots
                replacement.start_time = current_clock
                replacement.end_time = round(current_clock + dur, 4)
                current_clock = replacement.end_time
                final_scenes.append(replacement)
            else:
                # Retain existing valid scene
                dur = old_scene.duration
                time_shift = current_clock - old_scene.start_time
                if abs(time_shift) > 1e-4:
                    for s in old_scene.shots:
                        s.start_time = round(s.start_time + time_shift, 4)
                        s.end_time = round(s.end_time + time_shift, 4)
                old_scene.start_time = current_clock
                old_scene.end_time = round(current_clock + dur, 4)
                current_clock = old_scene.end_time
                final_scenes.append(old_scene)

        # Return updated copy
        return VisualTimeline(
            timeline_id=existing_timeline.timeline_id,
            project_id=existing_timeline.project_id,
            version=existing_timeline.version,
            timeline_source=existing_timeline.timeline_source,
            total_duration_sec=round(current_clock, 4),
            target_resolution=existing_timeline.target_resolution,
            style_profile=existing_timeline.style_profile,
            scenes=final_scenes,
            total_shots=sum(len(sc.shots) for sc in final_scenes),
            warnings=existing_timeline.warnings,
        )
