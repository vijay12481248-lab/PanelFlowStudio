from engine.comfyui.service import _history_images, _patch_workflow, _validate_output_dimensions
from engine.comfyui import service
from engine.comfyui.registry import ComfyWorkflowRegistry, WorkflowRegistryError
from engine.comfyui.client import ComfyUIClient
from unittest.mock import patch
import hashlib
import json
import pytest
import os
import subprocess
import asyncio
import io
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from engine.database.models import Base, ProjectRecord, AssetRecord
from engine.api.routers.comfyui import get_project_asset_file


def test_patch_image_workflow_parameters():
    workflow = {
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "old-positive"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "old-negative"}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 768, "height": 1024}},
        "7": {"class_type": "KSampler", "inputs": {"seed": ["14", 0]}},
        "13": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
        "14": {"class_type": "PrimitiveInt", "inputs": {"value": 1}},
    }
    slots = {
        "prompt": {"node_id": "4", "input": "text", "class_type": "CLIPTextEncode"},
        "negative_prompt": {"node_id": "5", "input": "text", "class_type": "CLIPTextEncode"},
        "width": {"node_id": "6", "input": "width", "class_type": "EmptySD3LatentImage"},
        "height": {"node_id": "6", "input": "height", "class_type": "EmptySD3LatentImage"},
        "seed": {"node_id": "14", "input": "value", "class_type": "PrimitiveInt"},
        "filename_prefix": {"node_id": "13", "input": "filename_prefix", "class_type": "SaveImage"},
    }
    patched = _patch_workflow(workflow, slots, "new prompt", "new negative", 640, 960, 42, "panelflow/test")
    assert patched["4"]["inputs"]["text"] == "new prompt"
    assert patched["5"]["inputs"]["text"] == "new negative"
    assert patched["6"]["inputs"]["width"] == 640
    assert patched["6"]["inputs"]["height"] == 960
    assert patched["14"]["inputs"]["value"] == 42
    assert patched["13"]["inputs"]["filename_prefix"] == "panelflow/test"
    assert workflow["4"]["inputs"]["text"] == "old-positive"


def test_patch_rejects_unsupported_latent_node_and_unpatchable_dimension_slot():
    workflow = {
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "old-positive"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "old-negative"}},
        "6": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 1024}},
        "7": {"class_type": "KSampler", "inputs": {"seed": 1}},
        "13": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
    }
    slots = {
        "prompt": {"node_id": "4", "input": "text", "class_type": "CLIPTextEncode"},
        "negative_prompt": {"node_id": "5", "input": "text", "class_type": "CLIPTextEncode"},
        "width": {"node_id": "6", "input": "width", "class_type": "EmptySD3LatentImage"},
        "height": {"node_id": "6", "input": "height", "class_type": "EmptySD3LatentImage"},
        "seed": {"node_id": "7", "input": "seed", "class_type": "KSampler"},
        "filename_prefix": {"node_id": "13", "input": "filename_prefix", "class_type": "SaveImage"},
    }
    with pytest.raises(service.ComfyImageGenerationError, match="width.*class_type"):
        _patch_workflow(workflow, slots, "prompt", "negative", 640, 960, 42, "panelflow/test")


def test_registry_rejects_workflow_without_exact_patch_slot_contract():
    workflow = {"6": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 1024}}}
    with pytest.raises(WorkflowRegistryError, match="exact patch slots"):
        ComfyWorkflowRegistry._validate_patch_slots("unsupported", workflow, {"patch_slots": {}})


def test_output_dimensions_must_match_requested_dimensions_before_persistence():
    with pytest.raises(service.ComfyImageGenerationError, match="dimensions"):
        _validate_output_dimensions(
            actual_width=512,
            actual_height=512,
            requested_width=640,
            requested_height=960,
            dimension_policy={"mode": "exact", "min": 256, "max": 2048, "multiple_of": 8},
        )


def test_mismatched_output_is_rejected_before_asset_file_or_database_persistence(tmp_path, monkeypatch):
    workflow = {
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "old-positive"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "old-negative"}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 768, "height": 1024}},
        "13": {"class_type": "SaveImage", "inputs": {"filename_prefix": "old"}},
        "14": {"class_type": "PrimitiveInt", "inputs": {"value": 1}},
    }
    slots = {
        "prompt": {"node_id": "4", "input": "text", "class_type": "CLIPTextEncode"},
        "negative_prompt": {"node_id": "5", "input": "text", "class_type": "CLIPTextEncode"},
        "width": {"node_id": "6", "input": "width", "class_type": "EmptySD3LatentImage"},
        "height": {"node_id": "6", "input": "height", "class_type": "EmptySD3LatentImage"},
        "seed": {"node_id": "14", "input": "value", "class_type": "PrimitiveInt"},
        "filename_prefix": {"node_id": "13", "input": "filename_prefix", "class_type": "SaveImage"},
    }
    image_buffer = io.BytesIO()
    Image.new("RGB", (512, 512), "blue").save(image_buffer, format="PNG")

    class FakeClient:
        base_url = "http://127.0.0.1:8188"

        def submit_prompt(self, *args, **kwargs):
            return "prompt-1"

        def history(self, prompt_id):
            return {prompt_id: {"outputs": {"13": {"images": [{"filename": "bad.png", "type": "output"}]}}}}

        def download_output(self, *args, **kwargs):
            return image_buffer.getvalue()

    class FakeRegistry:
        def __init__(self, client):
            pass

        def load(self, workflow_id):
            return workflow, "a" * 64

        def metadata(self, workflow_id):
            return {
                "patch_slots": slots,
                "dimension_policy": {"mode": "exact", "min": 256, "max": 2048, "multiple_of": 8},
            }

        def preflight(self, workflow_id):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(ProjectRecord(id="project", title="test", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
            db.commit()
            monkeypatch.setattr(service, "ComfyUIClient", FakeClient)
            monkeypatch.setattr(service, "ComfyWorkflowRegistry", FakeRegistry)
            writes = []
            monkeypatch.setattr(service, "_write_project_image", lambda *args: writes.append(args))
            with pytest.raises(service.ComfyImageGenerationError, match="dimensions"):
                service.generate_image_operation(
                    db,
                    lambda *_: None,
                    lambda: False,
                    project_id="project",
                    workflow_id="approved",
                    prompt="valid prompt text",
                    negative_prompt="negative",
                    width=640,
                    height=960,
                    seed=42,
                    timeout_s=30,
                )
            assert writes == []
            assert db.query(AssetRecord).count() == 0
    finally:
        engine.dispose()


def test_history_images_extracts_save_image_outputs():
    history = {"prompt-1": {"outputs": {"13": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]}}}}
    assert _history_images(history, "prompt-1") == [{"filename": "a.png", "subfolder": "", "type": "output"}]

def test_registry_rejects_symlinked_workflow_even_with_matching_checksum(tmp_path):
    root = tmp_path / "api"
    root.mkdir()
    raw = json.dumps({"1": {"class_type": "SaveImage"}}).encode()
    filename = root / "approved.json"
    filename.write_bytes(raw)
    client = ComfyUIClient()
    client.api_workflow_root = lambda: root
    registry = ComfyWorkflowRegistry(client)
    registry._entries = {"approved": {"id": "approved", "filename": filename.name, "sha256": hashlib.sha256(raw).hexdigest()}}
    original = type(filename).is_symlink
    with patch.object(type(filename), "is_symlink", lambda self: self == filename or original(self)):
        try:
            registry.load("approved")
        except WorkflowRegistryError:
            pass
        else:
            raise AssertionError("Registry read a symlinked workflow")

def test_generated_asset_exclusive_creation_does_not_overwrite(tmp_path):
    directory = tmp_path / "generated" / "comfyui"
    directory.mkdir(parents=True)
    existing = directory / "image.png"
    existing.write_bytes(b"original")
    import pytest
    with pytest.raises(service.ComfyImageGenerationError, match="already exists"):
        service._write_project_image(tmp_path, "generated/comfyui/image.png", b"replacement")
    assert existing.read_bytes() == b"original"

def test_registry_rejects_workflow_swapped_to_outside_before_open(tmp_path, monkeypatch):
    from engine.comfyui import registry as registry_module
    root = tmp_path / "api"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    approved = {"1": {"class_type": "SaveImage"}}
    raw = json.dumps(approved).encode()
    parent = root / "nested"
    parent.mkdir()
    (parent / "approved.json").write_bytes(raw)
    (outside / "approved.json").write_bytes(raw)
    client = ComfyUIClient()
    client.api_workflow_root = lambda: root
    registry = ComfyWorkflowRegistry(client)
    registry._entries = {"approved": {"id": "approved", "filename": "nested/approved.json", "sha256": hashlib.sha256(raw).hexdigest()}}
    original = registry_module.resolve_contained_path
    checks = 0

    def swap_after_check(*args, **kwargs):
        nonlocal checks
        checks += 1
        if checks == 2:
            # Restore the path just before the old post-read validation.
            if os.name == "nt":
                (root / "nested").rmdir()
            else:
                (root / "nested").unlink()
            (root / "previous").rename(parent)
        path = original(*args, **kwargs)
        if checks == 1:
            parent.rename(root / "previous")
            if os.name == "nt":
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(parent), str(outside)], capture_output=True)
                if result.returncode:
                    pytest.skip(f"junctions unavailable: {result.stderr!r}")
            else:
                parent.symlink_to(outside, target_is_directory=True)
        return path

    monkeypatch.setattr(registry_module, "resolve_contained_path", swap_after_check)
    with pytest.raises(WorkflowRegistryError, match="unsafe"):
        registry.load("approved")

def test_registry_rejects_oversize_workflow_even_with_approved_digest(tmp_path):
    from engine.comfyui.registry import _MAX_WORKFLOW_BYTES
    root = tmp_path / "api"
    root.mkdir()
    raw = json.dumps({"1": {"class_type": "SaveImage", "inputs": {"text": "x" * _MAX_WORKFLOW_BYTES}}}).encode()
    (root / "approved.json").write_bytes(raw)
    client = ComfyUIClient()
    client.api_workflow_root = lambda: root
    registry = ComfyWorkflowRegistry(client)
    registry._entries = {"approved": {"id": "approved", "filename": "approved.json", "sha256": hashlib.sha256(raw).hexdigest()}}
    with pytest.raises(WorkflowRegistryError, match="size limit"):
        registry.load("approved")

def test_asset_response_does_not_open_swapped_junction_at_delivery(tmp_path):
    root = tmp_path / "project"
    generated = root / "generated"
    generated.mkdir(parents=True)
    (generated / "image.png").write_bytes(b"approved")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "image.png").write_bytes(b"secret")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(ProjectRecord(id="project", title="test", source_type="LOCAL_FOLDER", workspace_path=str(root)))
            db.add(AssetRecord(id="asset", project_id="project", asset_type="IMAGE", filename="image.png", relative_path="generated/image.png", sha256="0" * 64))
            db.commit()
            response = get_project_asset_file("project", "asset", db)

            async def body():
                return b"".join([chunk async for chunk in response.body_iterator])

            try:
                generated.rename(root / "original")
            except PermissionError:
                # Windows pins the opened file's parent against rename. That is
                # the strongest valid outcome: the swap cannot be performed.
                assert asyncio.run(body()) == b"approved"
                return
            if os.name == "nt":
                result = subprocess.run(["cmd", "/c", "mklink", "/J", str(generated), str(outside)], capture_output=True)
                if result.returncode:
                    pytest.skip(f"junctions unavailable: {result.stderr!r}")
            else:
                generated.symlink_to(outside, target_is_directory=True)

            assert asyncio.run(body()) == b"approved"
    finally:
        engine.dispose()
