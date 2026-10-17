"""
Visual focus target selector for PanelFlow Motion Director.
Determines focal framing from upstream character bounding boxes, speech balloons, and narrative cues.
"""
from typing import Optional, List
from engine.motion.models.cues import FocusTarget
from engine.motion.models.enums import FocusType, SpeechBalloonPolicy
from engine.motion.models.camera import NormalizedRect
from engine.motion.models.input_contract import VisualSource
from engine.story.models import ScriptSegment, SegmentType


class FocusSelector:
    """
    Selects confident focal subjects from available visual metadata without hallucinating coordinates.
    """

    def select_focus_target(
        self,
        visual: VisualSource,
        segment: ScriptSegment,
        balloon_policy: SpeechBalloonPolicy = SpeechBalloonPolicy.BALANCED,
    ) -> FocusTarget:
        """
        Determines the primary focal subject for the given script segment and visual source.
        Rule: If location is unknown, do NOT invent exact coordinates.
        Conservative whole-panel framing is used; UNKNOWN remains UNKNOWN.
        """
        speaker_id = segment.speaker_character_id

        # 1. Check if speaker has an explicit character bounding box in this visual source
        if speaker_id and speaker_id in visual.character_bounding_boxes:
            box = visual.character_bounding_boxes[speaker_id]
            return FocusTarget(
                focus_type=FocusType.SPEAKER,
                character_id=speaker_id,
                speaker_id=speaker_id,
                bounding_box=box,
                confidence=0.95,
                description=f"Speaker '{speaker_id}' bounding box",
            )

        # 2. Check if any character bounding box exists (if single character visible)
        if len(visual.character_bounding_boxes) == 1:
            char_id, box = list(visual.character_bounding_boxes.items())[0]
            return FocusTarget(
                focus_type=FocusType.CHARACTER,
                character_id=char_id,
                speaker_id=speaker_id,
                bounding_box=box,
                confidence=0.85,
                description=f"Single visible character '{char_id}'",
            )

        # 3. Check speech balloon geometry if requested by policy
        if balloon_policy == SpeechBalloonPolicy.SHOW_BALLOONS and visual.speech_balloon_boxes:
            first_balloon = visual.speech_balloon_boxes[0]
            return FocusTarget(
                focus_type=FocusType.SPEECH_BALLOON,
                bounding_box=first_balloon,
                confidence=0.80,
                description="Speech balloon framing focus",
            )

        # 4. Action or Establishing beat -> Environmental wide
        if segment.type in (SegmentType.NARRATOR, SegmentType.TRANSITION):
            return FocusTarget.whole_panel("Narrator / establishing wide composition")

        # 5. Default conservative whole-panel framing
        return FocusTarget.whole_panel("Conservative whole-panel framing (unambiguous subject location unknown)")
