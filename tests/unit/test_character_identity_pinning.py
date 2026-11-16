"""Unit tests for FLUX.2 Character Identity Pinning, Model Sheet Generation & Face Verification."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine.api.app import app
from engine.characters.face_verify import FaceIdentityVerifier, FaceVerificationReport
from engine.characters.modelsheet import (
    VIEW_NAMES,
    build_model_sheet_prompt,
    generate_character_model_sheet,
    slice_model_sheet,
)
from engine.characters.pinning import (
    bind_character_references_for_shot,
    find_matching_characters,
    verify_shot_character_consistency,
)
from engine.comfyui.art import ArtImage
from engine.mcp.registry import registry
import engine.mcp.tools


@pytest.fixture
def client():
    return TestClient(app)


def _create_synthetic_model_sheet(w: int = 1536, h: int = 768) -> Image.Image:
    """Create a synthetic 4-view model sheet with distinct quadrants and simulated faces."""
    img = Image.new("RGB", (w, h), color=(220, 220, 220))
    step = w // 4
    colors = [(200, 100, 100), (100, 200, 100), (100, 100, 200), (200, 200, 100)]
    for i, col in enumerate(colors):
        # Draw a quadrant torso and face
        cx = i * step + step // 2
        cy = h // 3
        # Face box
        for x in range(cx - 40, cx + 40):
            for y in range(cy - 50, cy + 50):
                if (x - cx)**2 + (y - cy)**2 < 45**2:
                    img.putpixel((x, y), col)
    return img


def test_build_model_sheet_prompt():
    pos, neg = build_model_sheet_prompt(
        name="Vael Voss",
        look="silver armor, glowing amber visor, obsidian cape",
        role="Lead Operative",
    )
    assert "Vael Voss" in pos
    assert "Lead Operative" in pos
    assert "silver armor" in pos
    assert "4 distinct orthographic full-body views" in pos
    assert "front view" in pos
    assert "back view" in pos
    assert "solid light gray background" in pos

    assert "different characters" in neg
    assert "inconsistent clothing" in neg


def test_slice_model_sheet(tmp_path):
    sheet = _create_synthetic_model_sheet(1536, 768)
    sheet_file = tmp_path / "test_sheet.png"
    sheet.save(sheet_file)

    views = slice_model_sheet(sheet_file, out_dir=tmp_path, prefix="test_char")
    assert set(views.keys()) == set(VIEW_NAMES)

    for name in VIEW_NAMES:
        p = views[name]
        assert p.is_file()
        with Image.open(p) as crop:
            assert crop.size == (384, 768)


def test_face_identity_verifier_self_similarity():
    verifier = FaceIdentityVerifier()
    # Create test face image
    face = Image.new("RGB", (128, 128), color=(210, 180, 140))
    emb1 = verifier.extract_embedding(face)
    assert emb1 is not None
    assert emb1.shape == (512,)
    assert abs(np.linalg.norm(emb1) - 1.0) < 1e-4

    # Compare with identical image
    report = verifier.verify_face_match(face, face, threshold=0.72)
    assert report.matched is True
    assert report.status == "match"
    assert report.similarity >= 0.72
    assert report.reference_detected is True
    assert report.generated_detected is True


def test_face_identity_verifier_drift_detection(monkeypatch):
    verifier = FaceIdentityVerifier()
    
    # Deterministic test: orthogonal face embeddings simulate distinct character identities
    emb_a = np.zeros(512, dtype=np.float32)
    emb_a[0] = 1.0
    emb_b = np.zeros(512, dtype=np.float32)
    emb_b[1] = 1.0

    sim = verifier.compute_similarity(emb_a, emb_b)
    assert sim == 0.0

    # Mock extract_embedding to return orthogonal vectors
    side_effects = [emb_a, emb_b]
    monkeypatch.setattr(verifier, "extract_embedding", lambda src: side_effects.pop(0))

    face_a = Image.new("RGB", (128, 128), color=(255, 0, 0))
    face_b = Image.new("RGB", (128, 128), color=(0, 0, 255))
    report = verifier.verify_face_match(face_a, face_b, threshold=0.72)
    assert report.matched is False
    assert report.status == "drift"
    assert report.similarity < 0.60
    assert "drift detected" in report.message.lower()



def test_face_identity_verifier_no_face_detected():
    verifier = FaceIdentityVerifier()
    tiny_img = Image.new("RGB", (5, 5), color=(0, 0, 0))
    report = verifier.verify_face_match(tiny_img, tiny_img)
    assert report.matched is False
    assert report.status == "no_face_detected"


def test_find_matching_characters():
    vault = [
        {"id": "char_1", "name": "Vael", "role": "Protagonist"},
        {"id": "char_2", "name": "Maya", "role": "Operative"},
        {"id": "char_3", "name": "Shadow Beast", "role": "Antagonist"},
    ]

    # Explicit id
    match1 = find_matching_characters({"character_ids": ["char_2"]}, vault)
    assert len(match1) == 1
    assert match1[0]["id"] == "char_2"

    # Name in prompt
    match2 = find_matching_characters({"prompt": "A close up of Vael preparing to strike."}, vault)
    assert len(match2) == 1
    assert match2[0]["id"] == "char_1"

    # Multiple characters mentioned
    match3 = find_matching_characters({"prompt": "Vael confronts the dreaded Shadow Beast at the gates."}, vault)
    assert len(match3) == 2
    matched_ids = {c["id"] for c in match3}
    assert matched_ids == {"char_1", "char_3"}


def test_bind_character_references_for_shot(tmp_path, monkeypatch):
    from engine.chronoflow import pipeline
    monkeypatch.setattr(pipeline, "COMFY_INPUT_DIR", tmp_path)
    from engine.characters import pinning
    monkeypatch.setattr(pinning, "COMFY_INPUT_DIR", tmp_path)

    # Create dummy images in input dir
    (tmp_path / "char1_tq.png").write_bytes(b"png")
    (tmp_path / "char2_front.png").write_bytes(b"png")
    (tmp_path / "char3_main.png").write_bytes(b"png")

    vault = [
        {
            "id": "c1",
            "name": "Kael",
            "views": {"three_quarter": "char1_tq.png", "front": "char1_front.png"},
            "image": "char1_legacy.png",
        },
        {
            "id": "c2",
            "name": "Lyra",
            "views": {"front": "char2_front.png"},
            "image": "char2_legacy.png",
        },
        {
            "id": "c3",
            "name": "Titan",
            "views": {},
            "image": "char3_main.png",
        },
    ]

    shot = {"character_ids": ["c1", "c2", "c3"]}
    refs = bind_character_references_for_shot(shot, vault, max_references=4)
    assert len(refs) == 3
    assert refs[0] == "char1_tq.png"
    assert refs[1] == "char2_front.png"
    assert refs[2] == "char3_main.png"


def test_generate_character_model_sheet_mocked_engine(tmp_path):
    sheet = _create_synthetic_model_sheet(1536, 768)
    sheet_bytes = io.BytesIO()
    sheet.save(sheet_bytes, format="PNG")
    raw_png = sheet_bytes.getvalue()

    mock_art = MagicMock()
    mock_art.generate.return_value = ArtImage(
        png=raw_png,
        width=1536,
        height=768,
        prompt_id="test_prompt_id",
        workflow_id="flux2_klein_4b",
        workflow_sha256="sha256",
        model_files=[],
        source_output={},
        seed=42,
    )

    result = generate_character_model_sheet(
        character_id="char_test_01",
        name="Aria",
        look="emerald cloak, golden hair",
        role="Mage",
        art_engine=mock_art,
        out_dir=tmp_path,
        seed=42,
        extract_face_embedding=True,
    )

    assert result["success"] is True
    assert result["character_id"] == "char_test_01"
    assert (tmp_path / result["model_sheet_filename"]).is_file()
    assert len(result["views"]) == 4
    for view_name in VIEW_NAMES:
        assert (tmp_path / result["views"][view_name]).is_file()
    assert result["face_embedding"] is not None
    assert len(result["face_embedding"]) == 512


def test_character_endpoints(client, tmp_path, monkeypatch):
    from engine.chronoflow import pipeline
    monkeypatch.setattr(pipeline, "COMFY_INPUT_DIR", tmp_path)

    # 1. Save character
    payload = {
        "name": "Test Hero",
        "role": "Leader",
        "description": "Armor with crimson cloak",
        "image": "hero.png",
    }
    resp = client.post("/api/chronoflow/characters", json=payload)
    assert resp.status_code == 200
    char_data = resp.json()["character"]
    char_id = char_data["id"]

    # 2. Pin references endpoint
    pin_resp = client.post("/api/chronoflow/characters/pin_references", json={
        "scene": {"character_ids": [char_id]},
        "max_references": 4,
    })
    assert pin_resp.status_code == 200
    assert "references" in pin_resp.json()

    # 3. Verify face endpoint
    face1 = tmp_path / "face1.png"
    face2 = tmp_path / "face2.png"
    Image.new("RGB", (128, 128), (200, 180, 160)).save(face1)
    Image.new("RGB", (128, 128), (200, 180, 160)).save(face2)

    vf_resp = client.post("/api/chronoflow/characters/verify_face", json={
        "query_image": str(face1),
        "reference_image": str(face2),
        "threshold": 0.72,
    })
    assert vf_resp.status_code == 200
    res_data = vf_resp.json()
    assert res_data["success"] is True
    assert res_data["matched"] is True
    assert res_data["status"] == "match"


@pytest.mark.asyncio
async def test_character_mcp_tools():
    t_sheet = registry.get_tool("panelflow_chronoflow_generate_model_sheet")
    assert t_sheet is not None
    assert "character_id" in t_sheet.input_schema["properties"]

    t_verify = registry.get_tool("panelflow_chronoflow_verify_face")
    assert t_verify is not None
    assert "query_image" in t_verify.input_schema["properties"]
    assert "reference_image" in t_verify.input_schema["properties"]

    t_pin = registry.get_tool("panelflow_chronoflow_pin_references")
    assert t_pin is not None
    assert "scene" in t_pin.input_schema["properties"]
