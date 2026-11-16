"""Character Turnaround Model Sheet Generator and Slicer for FLUX.2 Klein (`flux2_klein_4b`).

Generates canonical 4-view turnaround sheets (front, 3/4 angle, side profile, and back),
slices them into individual reference views, and registers them for character identity pinning.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

from engine.characters.face_verify import FaceIdentityVerifier
from engine.comfyui.art import ART_WORKFLOW_ID, ArtEngine
from engine.chronoflow.pipeline import COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR

logger = logging.getLogger(__name__)

VIEW_NAMES = ("front", "three_quarter", "profile", "back")


def build_model_sheet_prompt(
    name: str,
    look: str,
    role: str = "Protagonist",
    style_tags: str = "clean anime film style, crisp linework",
) -> tuple[str, str]:
    """Compiles positive and negative prompts for generating a canonical 4-view model sheet.
    
    Returns (positive_prompt, negative_prompt).
    """
    positive = (
        f"Professional character turnaround model sheet of {name}, {role}. "
        f"4 distinct orthographic full-body views arranged horizontally from left to right on one sheet: "
        f"front view, three-quarter angle view, profile side view, and back view. "
        f"Clean uniform neutral lighting, plain solid light gray background, neutral relaxed facial expression, "
        f"exact same outfit, facial features, hair style, proportions and color palette across all views: {look}. "
        f"{style_tags}, 2D animation character design sheet, concept art model sheet."
    )
    negative = (
        "different characters, inconsistent clothing, dynamic perspective, heavy shadows, "
        "dutch angle, cropped head, missing limbs, background objects, furniture, text, watermark"
    )
    return positive, negative


def slice_model_sheet(
    image_source: Path | str | bytes | Image.Image,
    out_dir: Path | None = None,
    prefix: str = "modelsheet_view",
) -> dict[str, Path]:
    """Slice a 4-view horizontal character sheet into individual view crops:
    `front`, `three_quarter`, `profile`, `back`.
    
    Returns dict mapping view name to saved Path on disk.
    """
    if isinstance(image_source, Image.Image):
        img = image_source.convert("RGB")
    elif isinstance(image_source, bytes):
        img = Image.open(io.BytesIO(image_source)).convert("RGB")
    else:
        p = Path(image_source)
        if not p.is_file():
            raise FileNotFoundError(f"Model sheet file not found: {image_source}")
        img = Image.open(p).convert("RGB")

    w, h = img.size
    step = w // 4
    save_dir = out_dir or COMFY_INPUT_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    result_paths: dict[str, Path] = {}

    for idx, view_name in enumerate(VIEW_NAMES):
        crop_box = (idx * step, 0, (idx + 1) * step, h)
        slice_img = img.crop(crop_box)
        filename = f"{prefix}_{view_name}.png"
        out_path = save_dir / filename
        slice_img.save(out_path, format="PNG")
        result_paths[view_name] = out_path.resolve()

    return result_paths


def generate_character_model_sheet(
    character_id: str,
    name: str,
    look: str,
    role: str = "Protagonist",
    art_engine: ArtEngine | None = None,
    out_dir: Path | None = None,
    seed: int | None = None,
    extract_face_embedding: bool = True,
) -> dict[str, Any]:
    """Generate a canonical 4-view character turnaround sheet using ArtEngine (flux2_klein_4b).
    
    - Generates 1536x768 turnaround sheet.
    - Slices sheet into 4 canonical views ('front', 'three_quarter', 'profile', 'back').
    - Extracts 512-dimensional face embedding from front view.
    - Returns metadata dictionary with filenames, view slices, and embedding vector.
    """
    engine = art_engine or ArtEngine()
    target_dir = out_dir or COMFY_INPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    pos_prompt, neg_prompt = build_model_sheet_prompt(name=name, look=look, role=role)

    sheet_filename = f"modelsheet_{character_id}.png"
    sheet_path = target_dir / sheet_filename

    art_image = engine.generate(
        prompt=pos_prompt,
        negative_prompt=neg_prompt,
        width=1536,
        height=768,
        seed=seed,
        prefix=f"modelsheet_{character_id}",
        workflow_id=ART_WORKFLOW_ID,
    )
    sheet_path.write_bytes(art_image.png)

    # Slice into 4 views
    views = slice_model_sheet(
        sheet_path,
        out_dir=target_dir,
        prefix=f"modelsheet_{character_id}",
    )

    # Extract facial embedding from front or three_quarter view
    face_embedding: list[float] | None = None
    if extract_face_embedding:
        verifier = FaceIdentityVerifier()
        # Prefer front view, fallback to three_quarter
        emb = verifier.extract_embedding(views.get("front") or sheet_path)
        if emb is None:
            emb = verifier.extract_embedding(views.get("three_quarter") or sheet_path)
        if emb is not None:
            face_embedding = [round(float(x), 6) for x in emb]

    return {
        "success": True,
        "character_id": character_id,
        "model_sheet_path": str(sheet_path),
        "model_sheet_filename": sheet_filename,
        "views": {k: str(v.name) for k, v in views.items()},
        "face_embedding": face_embedding,
        "prompt": pos_prompt,
        "seed": art_image.seed,
    }
