import uuid
from typing import List, Optional
from datetime import datetime, timezone

from engine.story.models import (
    NarrativeDocument,
    VideoScript,
    ScriptSegment,
    AdaptationProfile,
    SegmentType,
    MotionIntent,
    ProvenanceReference,
    EmotionType,
)
from engine.story.script.duration import estimate_segment_duration
from engine.story.script.validator import script_validator


class ScriptAdapter:
    """
    Transforms approved Narrative IR into an adapted VideoScript according to the selected AdaptationProfile.
    Strictly preserves provenance and never invents facts absent from Narrative IR.
    """

    def adapt(
        self,
        narrative: NarrativeDocument,
        profile: AdaptationProfile = AdaptationProfile.FAITHFUL,
    ) -> VideoScript:
        script_id = f"script_{uuid.uuid4().hex[:10]}"
        segments: List[ScriptSegment] = []

        char_map = {c.character_id: c for c in narrative.characters}
        char_map["NARRATOR"] = None

        current_time = 0.0
        seq = 1

        for scene in sorted(narrative.scenes, key=lambda s: s.sequence):
            # 1. Scene Introduction (Narrator)
            if profile in (AdaptationProfile.DRAMATIC_NARRATION, AdaptationProfile.ACCESSIBLE_RECAP) or (
                profile == AdaptationProfile.FAITHFUL and scene.summary and len(narrative.scenes) > 1
            ):
                import re
                candidate_text = scene.summary or scene.title or ""
                # Strip robotic scene/panel prefixes so narrator doesn't vocalize numbers
                cleaned_intro = re.sub(r"^(?:Scene|Panel|Shot)\s*#?\d+\s*[-:—–.]\s*", "", candidate_text, flags=re.IGNORECASE).strip()
                # If candidate is purely a dummy label like "Scene 1", discard it
                if re.match(r"^(?:Scene|Panel|Shot)\s*#?\d+$", cleaned_intro, flags=re.IGNORECASE):
                    cleaned_intro = ""
                intro_text = cleaned_intro

                if intro_text:
                    dur = estimate_segment_duration(intro_text, segment_type="NARRATOR")
                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        sequence=seq,
                        type=SegmentType.NARRATOR,
                        speaker_character_id="NARRATOR",
                        text=intro_text,
                        emotion=EmotionType.CALM,
                        intensity=0.5,
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=[scene.panel_start],
                            confidence=scene.confidence,
                        ),
                        production_intent="Scene establishing voiceover",
                        music_intent="MYSTERIOUS",
                        motion_intent=MotionIntent.ESTABLISHING,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

            # 2. Iterate beats and utterances in scene
            scene_beats = [b for b in narrative.beats if b.scene_id == scene.scene_id]
            scene_beats.sort(key=lambda b: b.sequence)

            for beat in scene_beats:
                # Atmospheric beat cue for dramatic profiles
                if profile == AdaptationProfile.DRAMATIC_NARRATION and beat.summary and beat.importance == "HIGH":
                    dur = estimate_segment_duration(beat.summary, segment_type="NARRATOR")
                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=SegmentType.NARRATOR,
                        speaker_character_id="NARRATOR",
                        text=beat.summary,
                        emotion=EmotionType.TENSE if beat.intensity > 0.6 else EmotionType.CALM,
                        intensity=beat.intensity,
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=beat.panel_ids,
                            confidence=beat.confidence,
                        ),
                        production_intent="Beat escalation cue",
                        music_intent=beat.music_intent or "TENSE",
                        sfx_intent=beat.sfx_intent,
                        motion_intent=MotionIntent.CHARACTER_FOCUS,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

                # Gather utterances linked to this beat's panels
                beat_panel_set = set(beat.panel_ids)
                beat_utterances = [u for u in narrative.utterances if u.panel_id in beat_panel_set]
                beat_utterances.sort(key=lambda u: u.sequence)

                for u in beat_utterances:
                    # In CONDENSED mode, skip purely redundant short utterances
                    if profile == AdaptationProfile.CONDENSED and len(u.corrected_text.strip()) < 3:
                        continue

                    speaker_id = u.speaker_character_id or "UNKNOWN"
                    seg_type = (
                        SegmentType.NARRATOR
                        if u.utterance_type.value in ("NARRATION", "CAPTION")
                        else SegmentType.CHARACTER_DIALOGUE
                    )

                    motion_hint = (
                        MotionIntent.REACTION_CLOSEUP
                        if u.emotion in (EmotionType.ANGRY, EmotionType.SURPRISED, EmotionType.AFRAID)
                        else MotionIntent.CHARACTER_FOCUS
                    )

                    dur = estimate_segment_duration(u.corrected_text, segment_type=seg_type.value)

                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=seg_type,
                        speaker_character_id=speaker_id,
                        text=u.corrected_text or u.source_text,
                        emotion=u.emotion,
                        intensity=u.intensity,
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=[u.panel_id],
                            text_region_ids=[u.text_region_id],
                            confidence=u.emotion_confidence,
                        ),
                        production_intent=f"Adapted from {u.utterance_type.value.lower()}",
                        music_intent=beat.music_intent,
                        sfx_intent=beat.sfx_intent,
                        motion_intent=motion_hint,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

            # Scene pause / transition hold
            pause_dur = 1.5
            pause_seg = ScriptSegment(
                segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                scene_id=scene.scene_id,
                sequence=seq,
                type=SegmentType.PAUSE,
                speaker_character_id=None,
                text="",
                estimated_duration=pause_dur,
                estimated_start=round(current_time, 2),
                estimated_end=round(current_time + pause_dur, 2),
                source_evidence=ProvenanceReference(panel_ids=[scene.panel_end]),
                production_intent="Scene transition pause",
                motion_intent=MotionIntent.STATIC,
            )
            segments.append(pause_seg)
            current_time += pause_dur
            seq += 1

        script = VideoScript(
            script_id=script_id,
            project_id=narrative.project_id,
            version="1.0",
            adaptation_profile=profile,
            segments=segments,
            estimated_duration=round(current_time, 2),
            language=narrative.language,
            status="DRAFT",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Run automatic faithfulness validation
        script_validator.validate(script, narrative)
        return script


script_adapter = ScriptAdapter()
