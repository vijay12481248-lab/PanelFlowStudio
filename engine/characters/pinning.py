"""Character Identity Pinning & Multi-Shot Consistency for FLUX.2 Klein (`flux2_klein_4b_ref`).

Automatically extracts and binds character turnaround views to generation requests,
preventing face drift across camera angles and scene cuts.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from engine.characters.face_verify import FaceIdentityVerifier, FaceVerificationReport
MAX_REFERENCES = 4  # a reference-capable image model takes up to four pictures (HiDream and Z-Image take none; the H3 edit graph takes four)
from engine.chronoflow.pipeline import COMFY_INPUT_DIR

logger = logging.getLogger(__name__)


def find_matching_characters(
    scene_or_shot: dict[str, Any],
    characters_vault: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify which characters from the vault appear in a given shot or scene."""
    found: list[dict[str, Any]] = []
    seen_ids = set()

    # 1. Explicit character IDs
    char_ids = scene_or_shot.get("character_ids") or []
    if isinstance(char_ids, str):
        char_ids = [char_ids]
    for cid in char_ids:
        for c in characters_vault:
            if c.get("id") == cid and cid not in seen_ids:
                found.append(c)
                seen_ids.add(cid)

    # 2. Protagonist field
    protagonist = scene_or_shot.get("protagonist")
    if isinstance(protagonist, dict) and protagonist.get("id") and protagonist.get("id") not in seen_ids:
        found.append(protagonist)
        seen_ids.add(protagonist["id"])

    # 3. Mention by name in shot prompt or title
    prompt = (scene_or_shot.get("prompt") or "") + " " + (scene_or_shot.get("title") or "")
    prompt_lower = prompt.lower()
    for c in characters_vault:
        cid = c.get("id")
        if cid in seen_ids:
            continue
        cname = (c.get("name") or "").strip().lower()
        if cname and len(cname) >= 3 and cname in prompt_lower:
            found.append(c)
            seen_ids.add(cid)

    return found


def bind_character_references_for_shot(
    scene_or_shot: dict[str, Any],
    characters_vault: list[dict[str, Any]],
    max_references: int = MAX_REFERENCES,
) -> list[str]:
    """Retrieve up to `max_references` reference image names for a shot.
    
    Priority per character:
    1. Sliced 'three_quarter' or 'front' turnaround view (best for FLUX.2 Klein reference conditioning)
    2. Character reference 'image'
    3. Full 'model_sheet' image
    
    Returns a list of image filenames present in ComfyUI input directory.
    """
    matched_chars = find_matching_characters(scene_or_shot, characters_vault)
    references: list[str] = []

    for char in matched_chars:
        if len(references) >= max_references:
            break

        views = char.get("views") or char.get("turnaround_views") or {}
        # 1. Prefer three_quarter view (rich angle for 3D depth), then front view
        view_cand = views.get("three_quarter") or views.get("front") or views.get("profile")
        if view_cand:
            name = Path(view_cand).name
            if (COMFY_INPUT_DIR / name).is_file():
                references.append(name)
                continue

        # 2. Main character portrait image
        img = char.get("image")
        if img:
            name = Path(img).name
            if (COMFY_INPUT_DIR / name).is_file():
                references.append(name)
                continue

        # 3. Full model sheet
        sheet = char.get("model_sheet") or char.get("model_sheet_filename")
        if sheet:
            name = Path(sheet).name
            if (COMFY_INPUT_DIR / name).is_file():
                references.append(name)
                continue

    return references[:max_references]


def verify_shot_character_consistency(
    shot_image: Path | str | bytes,
    character_ids: list[str],
    characters_vault: list[dict[str, Any]],
    verifier: FaceIdentityVerifier | None = None,
    threshold: float = 0.72,
) -> list[FaceVerificationReport]:
    """Verify facial consistency of all assigned characters against their canonical references."""
    v = verifier or FaceIdentityVerifier()
    reports: list[FaceVerificationReport] = []

    for cid in character_ids:
        char = next((c for c in characters_vault if c.get("id") == cid), None)
        if not char:
            continue

        # Find best reference image
        views = char.get("views") or char.get("turnaround_views") or {}
        ref_cand = views.get("front") or views.get("three_quarter") or char.get("image") or char.get("model_sheet")
        if not ref_cand:
            continue

        ref_path = COMFY_INPUT_DIR / Path(ref_cand).name
        if not ref_path.is_file():
            ref_path = Path(ref_cand)
            if not ref_path.is_file():
                continue

        report = v.verify_face_match(shot_image, ref_path, threshold=threshold)
        reports.append(report)

    return reports
