import uuid
from typing import List, Optional
from datetime import datetime, timezone

from engine.story.models import (
    NarrativeDocument,
    StoryBeatEntity,
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
        seen_utterances = set()

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

            # 2. Sequential Scene Panels & Utterance Stitching
            from engine.imaging.panels.classification import PROMO_PATTERNS

            # Determine all panels in this scene from observations
            all_pids = [o.panel_id for o in narrative.observations]
            s_idx = all_pids.index(scene.panel_start) if scene.panel_start in all_pids else 0
            e_idx = all_pids.index(scene.panel_end) if scene.panel_end in all_pids else len(all_pids) - 1
            if s_idx > e_idx: s_idx, e_idx = e_idx, s_idx
            scene_pids = all_pids[s_idx : e_idx + 1] if all_pids else [scene.panel_start]
            scene_pids_set = set(scene_pids)

            scene_beats = [b for b in narrative.beats if b.scene_id == scene.scene_id]
            scene_beats.sort(key=lambda b: b.sequence)

            # If no beats assigned to this scene, create a fallback beat covering scene panels
            if not scene_beats and scene.summary:
                dummy_beat = StoryBeatEntity(
                    beat_id=f"beat_{uuid.uuid4().hex[:8]}",
                    scene_id=scene.scene_id,
                    sequence=1,
                    panel_ids=scene_pids,
                    summary=scene.summary,
                    confidence=scene.confidence,
                )
                scene_beats = [dummy_beat]

            # Collect all valid utterances in this scene
            scene_utterances = [u for u in narrative.utterances if u.panel_id in scene_pids_set]
            scene_utterances.sort(key=lambda u: u.sequence)

            def _is_valid_u(u):
                t = (u.corrected_text or u.source_text or "").strip()
                alnums = [c for c in t if c.isalnum()]
                if len(alnums) < 2 or (len(t.split()) == 1 and len(alnums) < 4):
                    return False
                if "[BLURRED" in t or "REDACTED" in t:
                    return False
                if any(p.search(t) for p in PROMO_PATTERNS):
                    return False
                return True

            valid_scene_u = [u for u in scene_utterances if _is_valid_u(u)]

            # Iterate through beats to maintain dramatic narrative recap flow
            for beat in scene_beats:
                beat_panel_set = set(beat.panel_ids) if beat.panel_ids else scene_pids_set
                beat_u = [u for u in valid_scene_u if u.panel_id in beat_panel_set and u.utterance_id not in seen_utterances]

                # CONTINUOUS RECAP VOICE:
                # If dramatic recap profile OR if beat has no character dialogue, emit narrator recap line!
                should_narrate_beat = (
                    (profile in (AdaptationProfile.DRAMATIC_NARRATION, AdaptationProfile.ACCESSIBLE_RECAP) and beat.summary)
                    or (not beat_u and beat.summary)
                )
                if should_narrate_beat:
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
                            panel_ids=beat.panel_ids if beat.panel_ids else [scene.panel_start],
                            confidence=beat.confidence,
                        ),
                        production_intent="Continuous narrative recap cue",
                        music_intent=beat.music_intent or "TENSE",
                        sfx_intent=beat.sfx_intent,
                        motion_intent=MotionIntent.CHARACTER_FOCUS,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

                # SPEECH BUBBLE STITCHING:
                # Group adjacent dialogue bubbles in the same panel for the same speaker into complete sentences
                stitched_groups = []
                curr_group = []
                for u in beat_u:
                    seen_utterances.add(u.utterance_id)
                    if not curr_group:
                        curr_group.append(u)
                    else:
                        prev = curr_group[-1]
                        if prev.panel_id == u.panel_id and prev.speaker_character_id == u.speaker_character_id:
                            curr_group.append(u)
                        else:
                            stitched_groups.append(curr_group)
                            curr_group = [u]
                if curr_group:
                    stitched_groups.append(curr_group)

                for group in stitched_groups:
                    lead_u = group[0]
                    speaker_id = lead_u.speaker_character_id or "UNKNOWN"
                    seg_type = (
                        SegmentType.NARRATOR
                        if lead_u.utterance_type.value in ("NARRATION", "CAPTION")
                        else SegmentType.CHARACTER_DIALOGUE
                    )
                    # Stitch text
                    combined_texts = [(u.corrected_text or u.source_text).strip() for u in group]
                    stitched_text = " ".join(t for t in combined_texts if t)
                    all_region_ids = [u.text_region_id for u in group if u.text_region_id]
                    panel_ids = list(dict.fromkeys(u.panel_id for u in group))

                    dur = estimate_segment_duration(stitched_text, segment_type=seg_type.value)
                    motion_hint = (
                        MotionIntent.REACTION_CLOSEUP
                        if lead_u.emotion in (EmotionType.ANGRY, EmotionType.SURPRISED, EmotionType.AFRAID)
                        else MotionIntent.CHARACTER_FOCUS
                    )

                    seg = ScriptSegment(
                        segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                        scene_id=scene.scene_id,
                        beat_id=beat.beat_id,
                        sequence=seq,
                        type=seg_type,
                        speaker_character_id=speaker_id,
                        text=stitched_text,
                        emotion=lead_u.emotion,
                        intensity=max(u.intensity for u in group),
                        estimated_duration=dur,
                        estimated_start=round(current_time, 2),
                        estimated_end=round(current_time + dur, 2),
                        source_evidence=ProvenanceReference(
                            panel_ids=panel_ids,
                            text_region_ids=all_region_ids,
                            confidence=lead_u.emotion_confidence,
                        ),
                        production_intent=f"Adapted from stitched {lead_u.utterance_type.value.lower()}",
                        music_intent=beat.music_intent,
                        sfx_intent=beat.sfx_intent,
                        motion_intent=motion_hint,
                    )
                    segments.append(seg)
                    current_time += dur
                    seq += 1

            # Any remaining unvoiced utterances in scene
            remaining_u = [u for u in valid_scene_u if u.utterance_id not in seen_utterances]
            for u in remaining_u:
                seen_utterances.add(u.utterance_id)
                speaker_id = u.speaker_character_id or "UNKNOWN"
                seg_type = SegmentType.NARRATOR if u.utterance_type.value in ("NARRATION", "CAPTION") else SegmentType.CHARACTER_DIALOGUE
                text_u = (u.corrected_text or u.source_text).strip()
                dur = estimate_segment_duration(text_u, segment_type=seg_type.value)
                seg = ScriptSegment(
                    segment_id=f"seg_{uuid.uuid4().hex[:8]}",
                    scene_id=scene.scene_id,
                    sequence=seq,
                    type=seg_type,
                    speaker_character_id=speaker_id,
                    text=text_u,
                    emotion=u.emotion,
                    intensity=u.intensity,
                    estimated_duration=dur,
                    estimated_start=round(current_time, 2),
                    estimated_end=round(current_time + dur, 2),
                    source_evidence=ProvenanceReference(
                        panel_ids=[u.panel_id],
                        text_region_ids=[u.text_region_id] if u.text_region_id else [],
                        confidence=u.emotion_confidence,
                    ),
                    production_intent=f"Adapted from {u.utterance_type.value.lower()}",
                    motion_intent=MotionIntent.CHARACTER_FOCUS,
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
