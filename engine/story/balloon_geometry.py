import math
from pathlib import Path
from typing import List, Optional
import cv2
import numpy as np

from engine.story.models import SpeakerAttributionEntity, SpeakerMethod, CharacterEntity


def detect_balloon_tail_vector(
    panel_image: np.ndarray,
    region_bbox: tuple[int, int, int, int],
) -> Optional[tuple[float, float]]:
    """
    Analyzes morphological contour protrusions around a speech balloon
    to estimate the directional vector (dx, dy) of the speech tail.
    """
    rx, ry, rw, rh = region_bbox
    h_img, w_img = panel_image.shape[:2]

    # Expand margin around balloon to find tail tip
    margin = 35
    x1 = max(0, rx - margin)
    y1 = max(0, ry - margin)
    x2 = min(w_img, rx + rw + margin)
    y2 = min(h_img, ry + rh + margin)

    crop = panel_image[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    if len(crop.shape) == 3:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        gray = crop

    # Whiteness mask for balloon interior + tail
    _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Find largest contour in crop
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 200:
        return None

    # Calculate center of balloon body
    M = cv2.moments(c)
    if M["m00"] == 0:
        return None
    cx = M["m10"] / M["m00"]
    cy = M["m01"] / M["m00"]

    # Find points farthest from center (candidate tail tips)
    pts = c.reshape(-1, 2)
    dists = np.sqrt((pts[:, 0] - cx) ** 2 + (pts[:, 1] - cy) ** 2)
    max_idx = np.argmax(dists)
    tip_x, tip_y = pts[max_idx]

    dx = float(tip_x - cx)
    dy = float(tip_y - cy)
    norm = math.sqrt(dx * dx + dy * dy)
    if norm > 10.0:
        return (dx / norm, dy / norm)

    return None


def resolve_speaker_by_geometry(
    panel_id: str,
    text_regions: list[dict],
    characters_in_panel: list[CharacterEntity],
    previous_speaker_id: Optional[str] = None,
    panel_image_path: Optional[Path | str] = None,
) -> list[SpeakerAttributionEntity]:
    """
    Applies deterministic geometric and heuristic rules to attribute dialogue
    before falling back to expensive LLM inferences.
    """
    attributions: list[SpeakerAttributionEntity] = []
    panel_img = None
    if panel_image_path and Path(panel_image_path).exists():
        panel_img = cv2.imread(str(panel_image_path))

    last_speaker = previous_speaker_id

    for reg in text_regions:
        reg_id = reg.get("id", "")
        reg_type = reg.get("region_type", reg.get("type", "SPEECH")).upper()
        reg_bbox = (reg.get("x", 0), reg.get("y", 0), reg.get("width", 100), reg.get("height", 60))

        # Rule 1: Narration / Caption boxes
        if reg_type in ("NARRATION", "CAPTION"):
            attributions.append(
                SpeakerAttributionEntity(
                    text_region_id=reg_id,
                    speaker_character_id="NARRATOR",
                    confidence=0.99,
                    method=SpeakerMethod.BALLOON_GEOMETRY,
                    evidence_panel_ids=[panel_id],
                    reason_code="NARRATION_BOX",
                )
            )
            continue

        # Rule 2: Sound Effects
        if reg_type in ("SFX", "ONOMATOPOEIA"):
            attributions.append(
                SpeakerAttributionEntity(
                    text_region_id=reg_id,
                    speaker_character_id="SFX",
                    confidence=0.98,
                    method=SpeakerMethod.BALLOON_GEOMETRY,
                    evidence_panel_ids=[panel_id],
                    reason_code="SOUND_EFFECT",
                )
            )
            continue

        # Rule 3: Single character present in panel
        if len(characters_in_panel) == 1:
            char = characters_in_panel[0]
            attributions.append(
                SpeakerAttributionEntity(
                    text_region_id=reg_id,
                    speaker_character_id=char.character_id,
                    confidence=0.95,
                    method=SpeakerMethod.BALLOON_GEOMETRY,
                    evidence_panel_ids=[panel_id],
                    reason_code="SOLITARY_CHARACTER",
                )
            )
            last_speaker = char.character_id
            continue

        # Rule 4: Balloon tail analysis if tail vector or panel image is available
        tail_resolved = False
        tail_vec = reg.get("tail_vector")
        if not tail_vec and panel_img is not None and len(characters_in_panel) >= 2:
            tail_vec = detect_balloon_tail_vector(panel_img, reg_bbox)

        if tail_vec and len(characters_in_panel) >= 2:
            dx, dy = tail_vec
            target_char = None
            if dx < -0.2 and len(characters_in_panel) >= 1:
                target_char = characters_in_panel[0]
            elif dx > 0.2 and len(characters_in_panel) >= 2:
                target_char = characters_in_panel[1]

            if target_char:
                attributions.append(
                    SpeakerAttributionEntity(
                        text_region_id=reg_id,
                        speaker_character_id=target_char.character_id,
                        confidence=0.92,
                        method=SpeakerMethod.BALLOON_GEOMETRY,
                        evidence_panel_ids=[panel_id],
                        reason_code="BALLOON_TAIL_TARGET",
                    )
                )
                last_speaker = target_char.character_id
                tail_resolved = True

        if tail_resolved:
            continue

        # Rule 5: Spatial left/right positioning heuristic for 2 characters when no prior speaker
        if len(characters_in_panel) == 2 and not last_speaker:
            x_pos = float(reg.get("x", 0.0))
            target_char = characters_in_panel[0] if x_pos < 0.5 else characters_in_panel[1]
            attributions.append(
                SpeakerAttributionEntity(
                    text_region_id=reg_id,
                    speaker_character_id=target_char.character_id,
                    confidence=0.85,
                    method=SpeakerMethod.BALLOON_GEOMETRY,
                    evidence_panel_ids=[panel_id],
                    reason_code="SPATIAL_PROXIMITY_LEFT_RIGHT",
                )
            )
            last_speaker = target_char.character_id
            continue

        # Rule 6: 2-character conversation alternation
        if len(characters_in_panel) == 2 and last_speaker:
            other_char = (
                characters_in_panel[1]
                if last_speaker == characters_in_panel[0].character_id
                else characters_in_panel[0]
            )
            attributions.append(
                SpeakerAttributionEntity(
                    text_region_id=reg_id,
                    speaker_character_id=other_char.character_id,
                    confidence=0.82,
                    method=SpeakerMethod.BALLOON_GEOMETRY,
                    evidence_panel_ids=[panel_id],
                    reason_code="SEQUENTIAL_CONTEXT",
                )
            )
            last_speaker = other_char.character_id
            continue

        # Rule 6: Ambiguous / Unknown fallback for LLM or human review
        attributions.append(
            SpeakerAttributionEntity(
                text_region_id=reg_id,
                speaker_character_id="UNKNOWN",
                confidence=0.40,
                method=SpeakerMethod.UNKNOWN,
                evidence_panel_ids=[panel_id],
                reason_code="AMBIGUOUS_MULTI_CHARACTER",
            )
        )

    return attributions
