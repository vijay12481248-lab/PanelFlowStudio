import uuid
from typing import List
from engine.story.models import (
    NarrativeDocument,
    ContinuityWarningEntity,
    CharacterEntity,
    SceneEntity,
    EventEntity,
    UtteranceEntity,
)


class ContinuityAuditor:
    """
    Audits Narrative IR for logical, temporal, and character continuity violations.
    Produces non-destructive warning flags for review.
    """

    def audit(self, doc: NarrativeDocument) -> List[ContinuityWarningEntity]:
        warnings: List[ContinuityWarningEntity] = []

        char_map = {c.character_id: c for c in doc.characters}
        loc_map = {loc.location_id: loc for loc in doc.locations}
        char_first_panel: dict[str, int] = {}

        # 1. Check Character Name Duplications (e.g. two different IDs sharing identical canonical names)
        names_seen: dict[str, str] = {}
        for c in doc.characters:
            norm_name = c.display_name.strip().lower()
            if norm_name and norm_name not in ("unknown", "narrator", "sfx"):
                if norm_name in names_seen:
                    warnings.append(
                        ContinuityWarningEntity(
                            warning_id=f"warn_{uuid.uuid4().hex[:8]}",
                            warning_type="DUPLICATE_CHARACTER_NAME",
                            severity="WARNING",
                            description=(
                                f"Multiple characters share the name '{c.display_name}' "
                                f"({c.character_id} and {names_seen[norm_name]}). Consider merging."
                            ),
                            affected_character_ids=[c.character_id, names_seen[norm_name]],
                        )
                    )
                else:
                    names_seen[norm_name] = c.character_id

        # 2. Check Utterance Speakers Exist
        for u in doc.utterances:
            if u.speaker_character_id and u.speaker_character_id not in ("NARRATOR", "SFX", "UNKNOWN"):
                if u.speaker_character_id not in char_map:
                    warnings.append(
                        ContinuityWarningEntity(
                            warning_id=f"warn_{uuid.uuid4().hex[:8]}",
                            warning_type="UNKNOWN_SPEAKER_REFERENCE",
                            severity="ERROR",
                            description=(
                                f"Utterance '{u.utterance_id}' references non-existent character ID "
                                f"'{u.speaker_character_id}'."
                            ),
                            affected_panel_ids=[u.panel_id],
                            affected_character_ids=[u.speaker_character_id],
                        )
                    )

        # 3. Check Event Target & Actor Validity
        for evt in doc.events:
            if evt.actor_character_id and evt.actor_character_id not in char_map:
                warnings.append(
                    ContinuityWarningEntity(
                        warning_id=f"warn_{uuid.uuid4().hex[:8]}",
                        warning_type="INVALID_EVENT_ACTOR",
                        severity="ERROR",
                        description=f"Event '{evt.event_id}' has non-existent actor '{evt.actor_character_id}'.",
                        affected_panel_ids=evt.panel_ids,
                    )
                )
            if evt.target_character_id and evt.target_character_id not in char_map:
                warnings.append(
                    ContinuityWarningEntity(
                        warning_id=f"warn_{uuid.uuid4().hex[:8]}",
                        warning_type="INVALID_EVENT_TARGET",
                        severity="ERROR",
                        description=f"Event '{evt.event_id}' has non-existent target '{evt.target_character_id}'.",
                        affected_panel_ids=evt.panel_ids,
                    )
                )

        # 4. Check Scene Sequence Continuity
        for i in range(len(doc.scenes) - 1):
            s1 = doc.scenes[i]
            s2 = doc.scenes[i + 1]
            if s1.sequence >= s2.sequence:
                warnings.append(
                    ContinuityWarningEntity(
                        warning_id=f"warn_{uuid.uuid4().hex[:8]}",
                        warning_type="SCENE_SEQUENCE_MISORDER",
                        severity="WARNING",
                        description=f"Scene '{s1.scene_id}' sequence ({s1.sequence}) >= next scene ({s2.sequence}).",
                        affected_panel_ids=[s1.panel_end, s2.panel_start],
                    )
                )

        # 5. Check Beat Sequence within Scenes
        for sc in doc.scenes:
            scene_beats = [b for b in doc.beats if b.scene_id == sc.scene_id]
            scene_beats.sort(key=lambda b: b.sequence)
            for j in range(len(scene_beats) - 1):
                b1 = scene_beats[j]
                b2 = scene_beats[j + 1]
                if b1.sequence >= b2.sequence:
                    warnings.append(
                        ContinuityWarningEntity(
                            warning_id=f"warn_{uuid.uuid4().hex[:8]}",
                            warning_type="BEAT_SEQUENCE_MISORDER",
                            severity="WARNING",
                            description=f"Story beats in scene '{sc.scene_id}' have non-increasing sequences.",
                            affected_panel_ids=b1.panel_ids + b2.panel_ids,
                        )
                    )

        return warnings
