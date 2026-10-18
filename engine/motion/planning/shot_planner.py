"""
Core ShotPlanner for PanelFlow Motion Director.
Transforms approved script segments, source visuals, and master audio intervals into
a deterministic, render-ready VisualTimeline.
"""
import re
import uuid
from typing import List, Dict, Optional, Tuple, Set

from engine.motion.models.timeline import VisualTimeline, MotionScene, Shot
from engine.motion.models.camera import CameraState, NormalizedRect, TargetResolution
from engine.motion.models.cues import FocusTarget, CaptionCue
from engine.motion.models.enums import (
    MotionType,
    EasingFunction,
    TransitionType,
    EffectType,
    TimelineSourceType,
    WarningType,
)
from engine.motion.models.effects import EffectInstruction, EffectBudget
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.layers import ParallaxPlan
from engine.motion.models.warnings import MotionWarning
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    AudioInterval,
    MotionStyleProfile,
)
from engine.motion.timing.audio_clock import AudioClockResolver
from engine.motion.timing.duration_rules import TimingDirector
from engine.motion.planning.focus_selector import FocusSelector
from engine.motion.planning.dialogue_framer import DialogueFramer
from engine.motion.planning.repetition_detector import RepetitionDetector
from engine.motion.camera.bounds_validator import CameraBoundsValidator
from engine.story.models import ScriptSegment, SegmentType, MotionIntent, SceneEntity


class ShotPlanner:
    """
    Translates approved script segments, story beats, and authoritative audio clock intervals
    into cinematic camera shots, transitions, and framing.
    """

    def __init__(self):
        self.audio_resolver = AudioClockResolver()
        self.timing_director = TimingDirector()
        self.focus_selector = FocusSelector()
        self.dialogue_framer = DialogueFramer()
        self.bounds_validator = CameraBoundsValidator()
        self.repetition_detector = RepetitionDetector()

    def plan_timeline(self, input_data: MotionDirectorInput) -> VisualTimeline:
        """
        Executes deterministic shot planning across all narrative scenes and audio intervals.
        """
        profile = input_data.style_profile
        target_res = input_data.target_resolution
        target_aspect = target_res.numeric_aspect
        overrides = input_data.manual_overrides

        # 1. Map script segments to authoritative master audio timeline intervals
        pairs = self.audio_resolver.resolve_timeline_intervals(
            input_data.script, input_data.master_audio_timeline
        )
        # A story beat can span several panels while remaining one continuous
        # narration clip. Subdivide its visual clock and assign proportional
        # subtitle text to each shot so that captions match spoken timing
        # and do not duplicate entire paragraphs across consecutive frames.
        storyboard_pairs = []
        for segment, interval in pairs:
            panel_ids = list(dict.fromkeys(segment.source_evidence.panel_ids))
            if len(panel_ids) <= 1:
                storyboard_pairs.append((segment, interval))
                continue

            raw_text = segment.text.strip()
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", raw_text) if s.strip()]
            words = raw_text.split()
            n_panels = len(panel_ids)

            for index, panel_id in enumerate(panel_ids):
                part = segment.model_copy(deep=True)
                part.source_evidence.panel_ids = [panel_id]

                # Proportionally assign spoken text slice to this panel shot
                if len(sentences) == n_panels:
                    part.text = sentences[index]
                elif len(words) > 0:
                    w_start = int(len(words) * index / n_panels)
                    w_end = int(len(words) * (index + 1) / n_panels) if index < n_panels - 1 else len(words)
                    part.text = " ".join(words[w_start:w_end]).strip()
                else:
                    part.text = ""

                timing = interval.model_copy(deep=True)
                timing.start_time = interval.start_time + interval.duration * index / n_panels
                timing.end_time = interval.start_time + interval.duration * (index + 1) / n_panels
                storyboard_pairs.append((part, timing))
        pairs = storyboard_pairs

        # 2. Build index of available visual sources
        visual_by_panel_id: Dict[str, VisualSource] = {}
        visual_by_asset_id: Dict[str, VisualSource] = {}
        for vs in input_data.visual_sources:
            visual_by_asset_id[vs.asset_id] = vs
            if vs.panel_id:
                visual_by_panel_id[vs.panel_id] = vs

        # 3. Group segment-audio pairs by scene_id
        scene_segments: Dict[str, List[Tuple[ScriptSegment, AudioInterval]]] = {}
        for seg, a_iv in pairs:
            sc_id = seg.scene_id or "scene_default"
            scene_segments.setdefault(sc_id, []).append((seg, a_iv))

        # Scene entities index
        scene_entity_map: Dict[str, SceneEntity] = {sc.scene_id: sc for sc in input_data.scenes}

        planned_scenes: List[MotionScene] = []
        global_shot_idx = 1
        active_visual_idx = 0
        all_warnings: List[MotionWarning] = []
        effect_budget = EffectBudget()

        # Previous camera state for continuity
        last_camera_end: Optional[CameraState] = None
        last_asset_id: Optional[str] = None

        # 4. Process each scene
        for scene_seq, (sc_id, seg_pairs) in enumerate(scene_segments.items(), start=1):
            sc_entity = scene_entity_map.get(sc_id)
            sc_title = sc_entity.title if sc_entity else f"Scene {scene_seq}"
            sc_start = seg_pairs[0][1].start_time if seg_pairs else 0.0
            sc_end = seg_pairs[-1][1].end_time if seg_pairs else sc_start

            effect_budget.reset_scene(sc_id)
            scene_shots: List[Shot] = []

            for shot_in_sc_idx, (seg, a_iv) in enumerate(seg_pairs, start=1):
                shot_id = f"shot_{sc_id}_{shot_in_sc_idx:02d}"

                # A. Select visual source
                visual = self._resolve_visual_source(
                    seg, input_data.visual_sources, visual_by_panel_id, visual_by_asset_id, active_visual_idx
                )
                if visual:
                    # Update active visual tracker if matched
                    try:
                        active_visual_idx = input_data.visual_sources.index(visual)
                    except ValueError:
                        pass
                else:
                    # Fallback visual source if none available
                    visual = VisualSource(
                        asset_id="asset_missing_fallback",
                        width=target_res.width,
                        height=target_res.height,
                    )
                    all_warnings.append(
                        MotionWarning(
                            warning_type=WarningType.SOURCE_VISUAL_MISSING,
                            message=f"No visual source mapped for segment '{seg.segment_id}'. Using fallback frame.",
                            shot_id=shot_id,
                            scene_id=sc_id,
                            timestamp_sec=a_iv.start_time,
                        )
                    )

                is_new_visual = (visual.asset_id != last_asset_id)
                is_first_in_scene = (shot_in_sc_idx == 1)

                # B. Determine focus target
                focus = self.focus_selector.select_focus_target(
                    visual=visual,
                    segment=seg,
                    balloon_policy=profile.speech_balloon_policy,
                )

                # C. Determine camera motion and framing
                c_start, c_end, m_type, easing = self._plan_camera_motion(
                    seg=seg,
                    visual=visual,
                    focus=focus,
                    profile=profile,
                    is_first_in_scene=is_first_in_scene,
                    is_new_visual=is_new_visual,
                    previous_camera_end=last_camera_end,
                    target_aspect=target_aspect,
                )

                # Pacing & static-hold guard: long static holds (> 5.0s) cause viewer fatigue.
                # Convert long holds to subtle breathing zoom (1.0 -> 1.05)
                if m_type == MotionType.STATIC_HOLD and a_iv.duration > 5.0:
                    c_start = CameraState(center_x=0.5, center_y=0.5, zoom=1.0)
                    c_end = CameraState(center_x=0.5, center_y=0.5, zoom=min(profile.max_zoom, 1.05))
                    m_type = MotionType.SLOW_ZOOM_IN
                    easing = EasingFunction.SMOOTHSTEP

                # D. Transitions
                trans_in, trans_out = self._plan_transitions(
                    is_first_in_scene=is_first_in_scene,
                    is_last_in_scene=(shot_in_sc_idx == len(seg_pairs)),
                    is_new_visual=is_new_visual,
                    profile=profile,
                )

                # E. Effects (governed by EffectBudget)
                effects = self._plan_effects(seg, sc_id, a_iv, effect_budget) if profile.effect_intensity > 0 else []

                # F. Caption cue with human readability limits
                captions = []
                cap_text = seg.text.strip()
                if cap_text:
                    words = cap_text.split()
                    max_readable_words = max(8, int(a_iv.duration * 3.6))
                    if len(words) > max_readable_words:
                        cap_text = " ".join(words[:max_readable_words]) + "..."
                    captions.append(
                        CaptionCue(
                            cue_id=f"cap_{shot_id}",
                            text=cap_text,
                            speaker=seg.speaker_character_id,
                            speaker_character_id=seg.speaker_character_id,
                            start_time=a_iv.start_time,
                            end_time=a_iv.end_time,
                            script_segment_id=seg.segment_id,
                        )
                    )

                # G. Build Shot
                shot = Shot(
                    shot_id=shot_id,
                    scene_id=sc_id,
                    beat_id=seg.beat_id,
                    sequence_in_scene=shot_in_sc_idx,
                    sequence_global=global_shot_idx,
                    source_asset_id=visual.asset_id,
                    source_panel_id=visual.panel_id,
                    start_time=a_iv.start_time,
                    end_time=a_iv.end_time,
                    frame_region=visual.panel_bounds or NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0),
                    camera_start=c_start,
                    camera_end=c_end,
                    easing=easing,
                    motion_type=m_type,
                    focus_targets=[focus],
                    layer_instructions=ParallaxPlan.flat_fallback(visual.file_path).layers,
                    effect_instructions=effects,
                    transition_in=trans_in,
                    transition_out=trans_out,
                    caption_cues=captions,
                    planning_metadata={
                        "script_segment_id": seg.segment_id,
                        "script_segment_type": seg.type.value,
                        "audio_interval_id": a_iv.interval_id,
                        "is_establishing": is_first_in_scene,
                    },
                    provenance={
                        "panel_ids": seg.source_evidence.panel_ids if seg.source_evidence else [],
                        "script_segment_id": seg.segment_id,
                    },
                )

                # H. Apply manual overrides if present
                if overrides:
                    ov = overrides.get_shot_override(shot_id)
                    if ov:
                        shot = self._apply_override(shot, ov)

                scene_shots.append(shot)
                global_shot_idx += 1
                last_camera_end = shot.camera_end
                last_asset_id = shot.source_asset_id

            # Create MotionScene
            sc_dur = max(0.0, sc_end - sc_start)
            motion_scene = MotionScene(
                scene_id=sc_id,
                sequence=scene_seq,
                title=sc_title,
                start_time=sc_start,
                end_time=sc_end,
                shots=scene_shots,
                location_id=sc_entity.location_id if sc_entity else None,
                character_ids=sc_entity.character_ids if sc_entity else [],
            )
            planned_scenes.append(motion_scene)

        # 5. Check visual repetition across the timeline
        all_shots = []
        for sc in planned_scenes:
            all_shots.extend(sc.shots)
        rep_warnings = self.repetition_detector.detect_repetition(all_shots)
        all_warnings.extend(rep_warnings)

        total_dur = input_data.master_audio_timeline.total_duration_sec
        if all_shots:
            total_dur = max(total_dur, all_shots[-1].end_time)

        return VisualTimeline(
            project_id=input_data.project_id,
            timeline_source=input_data.master_audio_timeline.timeline_source,
            total_duration_sec=round(total_dur, 3),
            target_resolution=target_res,
            style_profile=profile,
            scenes=planned_scenes,
            total_shots=len(all_shots),
            warnings=all_warnings,
        )

    # -----------------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------------

    def _resolve_visual_source(
        self,
        seg: ScriptSegment,
        all_visuals: List[VisualSource],
        by_panel_id: Dict[str, VisualSource],
        by_asset_id: Dict[str, VisualSource],
        current_idx: int,
    ) -> Optional[VisualSource]:
        """
        Resolves the appropriate visual source for a script segment from evidence provenance.
        """
        # 1. Try segment's direct panel evidence
        if seg.source_evidence and seg.source_evidence.panel_ids:
            for pid in seg.source_evidence.panel_ids:
                if pid in by_panel_id:
                    return by_panel_id[pid]
                if pid in by_asset_id:
                    return by_asset_id[pid]

        # 2. Try current sequential visual
        if 0 <= current_idx < len(all_visuals):
            return all_visuals[current_idx]

        # 3. Fallback to first available visual
        return all_visuals[0] if all_visuals else None

    def _plan_camera_motion(
        self,
        seg: ScriptSegment,
        visual: VisualSource,
        focus: FocusTarget,
        profile: MotionStyleProfile,
        is_first_in_scene: bool,
        is_new_visual: bool,
        previous_camera_end: Optional[CameraState],
        target_aspect: float,
    ) -> Tuple[CameraState, CameraState, MotionType, EasingFunction]:
        """
        Determines start and end camera state, motion type, and easing curve.
        """
        src_aspect = visual.aspect_ratio
        easing = profile.camera_easing

        # A. Explicit motion intent from ScriptSegment or StoryBeat
        if seg.motion_intent == MotionIntent.STATIC or seg.type == SegmentType.PAUSE:
            c_start = CameraState(center_x=0.5, center_y=0.5, zoom=1.0)
            c_end = c_start.model_copy(deep=True)
            m_type = MotionType.STATIC_HOLD
        elif seg.motion_intent == MotionIntent.ESTABLISHING or is_first_in_scene:
            # Wide establishing move: start full wide, gentle push
            c_start = CameraState(center_x=0.5, center_y=0.5, zoom=1.00)
            c_end = CameraState(center_x=0.5, center_y=0.5, zoom=min(profile.max_zoom, 1.08))
            m_type = MotionType.ESTABLISHING_MOVE
            easing = EasingFunction.SMOOTHSTEP

        elif seg.motion_intent == MotionIntent.REACTION_CLOSEUP:
            # Reaction hold: close crop on character/face, static hold
            tx = focus.bounding_box.center_x if focus.bounding_box else 0.5
            ty = focus.bounding_box.center_y if focus.bounding_box else 0.5
            c_start = CameraState(center_x=tx, center_y=ty, zoom=min(profile.max_zoom, 1.22))
            c_end = CameraState(center_x=tx, center_y=ty, zoom=min(profile.max_zoom, 1.22))
            m_type = MotionType.REACTION_HOLD

        elif seg.motion_intent == MotionIntent.IMPACT:
            # Impact hold: immediate punch with static hold
            c_start = CameraState(center_x=0.5, center_y=0.5, zoom=min(profile.max_zoom, 1.15))
            c_end = CameraState(center_x=0.5, center_y=0.5, zoom=min(profile.max_zoom, 1.15))
            m_type = MotionType.STATIC_HOLD

        elif seg.motion_intent == MotionIntent.SLOW_PUSH:
            tx = focus.bounding_box.center_x if focus.bounding_box else 0.5
            ty = focus.bounding_box.center_y if focus.bounding_box else 0.5
            c_start = CameraState(center_x=0.5, center_y=0.5, zoom=1.02)
            c_end = CameraState(center_x=tx, center_y=ty, zoom=profile.max_zoom)
            m_type = MotionType.SLOW_ZOOM_IN

        elif seg.motion_intent == MotionIntent.PAN:
            half_pan = min(0.15, profile.max_pan_distance / 2)
            c_start = CameraState(center_x=0.5 - half_pan, center_y=0.5, zoom=min(profile.max_zoom, 1.12))
            c_end = CameraState(center_x=0.5 + half_pan, center_y=0.5, zoom=min(profile.max_zoom, 1.12))
            m_type = MotionType.PAN_RIGHT

        elif seg.type == SegmentType.CHARACTER_DIALOGUE:
            # Use DialogueFramer for dialogue
            c_start, c_end, m_type = self.dialogue_framer.frame_dialogue_shot(
                visual=visual,
                focus_target=focus,
                style_profile=profile,
                is_first_line_in_panel=is_new_visual,
                previous_camera_end=previous_camera_end,
                target_aspect=target_aspect,
            )

        else:
            # Default narration / calm hold: gentle slow push
            c_start = CameraState(center_x=0.5, center_y=0.5, zoom=1.00)
            c_end = CameraState(center_x=0.5, center_y=0.5, zoom=min(profile.max_zoom, 1.06))
            m_type = MotionType.SLOW_ZOOM_IN

        # Validate bounds
        c_start, c_end, _, _ = self.bounds_validator.validate_trajectory(
            c_start, c_end, source_aspect=src_aspect, target_aspect=target_aspect
        )

        return c_start, c_end, m_type, easing

    def _plan_transitions(
        self,
        is_first_in_scene: bool,
        is_last_in_scene: bool,
        is_new_visual: bool,
        profile: MotionStyleProfile,
    ) -> Tuple[TransitionInstruction, TransitionInstruction]:
        # Scene entrance
        if is_first_in_scene:
            trans_in = TransitionInstruction.dissolve(profile.transition_duration)
        elif is_new_visual:
            trans_in = TransitionInstruction.hard_cut()
        else:
            trans_in = TransitionInstruction.match_hold()

        # Scene exit
        if is_last_in_scene:
            trans_out = TransitionInstruction.dissolve(profile.transition_duration)
        else:
            trans_out = TransitionInstruction.hard_cut()

        return trans_in, trans_out

    def _plan_effects(
        self,
        seg: ScriptSegment,
        sc_id: str,
        a_iv: AudioInterval,
        effect_budget: EffectBudget,
    ) -> List[EffectInstruction]:
        effects: List[EffectInstruction] = []

        if seg.motion_intent == MotionIntent.IMPACT or seg.emotion.value == "ANGRY" and seg.intensity >= 0.8:
            if effect_budget.can_apply(EffectType.IMPACT_SHAKE, sc_id, a_iv.start_time, 0.4):
                effects.append(
                    EffectInstruction(
                        effect_type=EffectType.IMPACT_SHAKE,
                        start_time=a_iv.start_time,
                        end_time=a_iv.start_time + 0.35,
                        intensity=0.6,
                        parameters={"amplitude": 8.0, "frequency": 24.0},
                    )
                )
                effect_budget.record_usage(EffectType.IMPACT_SHAKE, sc_id, a_iv.start_time)

        return effects

    def _apply_override(self, shot: Shot, ov) -> Shot:
        if ov.override_source_asset_id:
            shot.source_asset_id = ov.override_source_asset_id
        if ov.override_crop:
            shot.frame_region = ov.override_crop
        if ov.override_camera_start:
            shot.camera_start = ov.override_camera_start
        if ov.override_camera_end:
            shot.camera_end = ov.override_camera_end
        if ov.override_motion_type:
            shot.motion_type = ov.override_motion_type
        if ov.override_focus_target:
            shot.focus_targets = [ov.override_focus_target]
        if ov.override_transition_in:
            shot.transition_in = ov.override_transition_in
        if ov.override_transition_out:
            shot.transition_out = ov.override_transition_out
        shot.locked = ov.locked
        shot.planning_metadata["manual_override"] = True
        return shot
