"""
Shot duration heuristics and pacing rules for PanelFlow Motion Director.
"""
from engine.motion.models.input_contract import MotionStyleProfile
from engine.story.models import ScriptSegment, SegmentType


class TimingDirector:
    """
    Enforces professional motion-comic pacing heuristics without robotic cutting.
    """

    def calculate_ideal_duration(
        self,
        audio_duration: float,
        segment: ScriptSegment,
        is_establishing: bool = False,
        is_reaction: bool = False,
        style_profile: MotionStyleProfile = MotionStyleProfile.subtle(),
    ) -> float:
        """
        Calculates recommended duration for a shot based on audio, narrative context, and style profile.
        """
        if is_establishing:
            return max(style_profile.establishing_shot_duration, audio_duration)

        if is_reaction:
            return max(style_profile.reaction_hold_duration, audio_duration)

        # Dialogue or narration
        if audio_duration > 0.0:
            # Respect the audio duration, bounded by minimum shot duration
            return max(style_profile.min_shot_duration, audio_duration)

        return style_profile.min_shot_duration

    def should_merge_adjacent_shots(
        self,
        seg_a: ScriptSegment,
        seg_b: ScriptSegment,
        source_id_a: str,
        source_id_b: str,
        dur_a: float,
        dur_b: float,
        style_profile: MotionStyleProfile,
    ) -> bool:
        """
        Determines whether two adjacent script segments sharing the same visual source
        should be planned as a continuous camera sequence instead of a hard cut.
        """
        # Must share the exact same source asset/panel
        if source_id_a != source_id_b:
            return False

        # If combined duration is comfortably within dialogue limits
        combined = dur_a + dur_b
        if combined <= style_profile.comfortable_dialogue_max:
            # If one of the lines is brief (< 2.0s), merging preserves continuity
            if dur_a < style_profile.min_shot_duration or dur_b < style_profile.min_shot_duration:
                return True

        return False
