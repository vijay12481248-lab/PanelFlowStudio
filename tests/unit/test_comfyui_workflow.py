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
                    workflow_id=service.ART_WORKFLOW_ID,
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


def test_refine_is_off_by_default_and_when_asked_stores_the_selected_image_with_its_iterations(tmp_path, monkeypatch):
    import io
    import types

    from PIL import Image

    from engine.comfyui.art import ArtImage
    from engine.original import refine as refine_mod

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(buf, "PNG")
    raw = buf.getvalue()
    art = ArtImage(png=raw, width=64, height=64, prompt_id="p1", workflow_id=service.ART_WORKFLOW_ID, workflow_sha256="a" * 64, model_files=["m"],
                   source_output={"filename": "k.png", "subfolder": "", "type": "output"}, seed=5)
    res = types.SimpleNamespace(status="accept", selected=2, generations=2, repaired=False, plan=None, iterations=[
        {"n": 1, "kind": "generate", "file": "f1", "sha256": "s1", "seed": 5, "review": {"decision": "regenerate"}},
        {"n": 2, "kind": "generate", "file": "f2", "sha256": "s2", "seed": 7919 + 5, "review": {"decision": "accept"}}])
    seen = {}

    def fake_refine(prompt, negative, width, height, seed, **kw):
        seen.update(kw, prompt=prompt)
        return art, res

    monkeypatch.setattr(refine_mod, "refine_art_image", fake_refine)
    monkeypatch.setattr(service, "ComfyUIClient", lambda: types.SimpleNamespace(base_url="http://x/"))
    monkeypatch.setattr(service, "ArtEngine", lambda *a, **k: (_ for _ in ()).throw(AssertionError("plain ArtEngine must not run when refine=True")))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(ProjectRecord(id="project", title="t", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
            db.commit()
            out = service.generate_image_operation(db, lambda *_: None, lambda: False, project_id="project", workflow_id=service.ART_WORKFLOW_ID,
                                                   prompt="a lamp", negative_prompt="", width=64, height=64, seed=1, refine=True)
            asset = db.query(AssetRecord).one()
            assert out["sha256"] == asset.sha256 and (tmp_path / asset.relative_path).read_bytes() == raw
            assert asset.provenance["refine"]["selected"] == 2 and [i["n"] for i in asset.provenance["refine"]["iterations"]] == [1, 2]
            assert seen["ws"] == tmp_path / "generated" / "comfyui_candidates"
    finally:
        engine.dispose()


def test_submit_comfyui_inpaint_job(tmp_path, monkeypatch):
    from engine.api.routers.comfyui import submit_comfyui_inpaint_job, ComfyInpaintRequest
    from engine.comfyui.service import INPAINT_WORKFLOW_ID
    from engine.database.models import Base
    from engine.database.session import engine as db_engine, SessionLocal

    Base.metadata.create_all(bind=db_engine)
    with SessionLocal() as db:
        db.add(ProjectRecord(id='proj1', title='test', source_type='LOCAL_FOLDER', workspace_path=str(tmp_path)))
        db.commit()

        class FakeRegistry:
            def metadata(self, wf_id):
                return {'requires_gpu': True, 'gpu_vram_mb': 10000}
            def load(self, wf_id):
                return ({}, 'a' * 64)
            def preflight(self, wf_id):
                return {'ready': True, 'missing_nodes': [], 'missing_models': []}

        monkeypatch.setattr('engine.api.routers.comfyui.ComfyWorkflowRegistry', lambda *a, **k: FakeRegistry())

        req = ComfyInpaintRequest(
            asset_id='asset1',
            mask_data='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
            prompt='test inpaint prompt',
        )
        result = submit_comfyui_inpaint_job('proj1', req, db=db)
        assert result['status'] == 'QUEUED'
        assert result['workflow_id'] == INPAINT_WORKFLOW_ID
        assert 'job_id' in result


def _png(colour="red"):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(buf, "PNG")
    return buf.getvalue()


def _reference_fixture(tmp_path):
    """A project with one stored asset on disk that can serve as a character reference."""
    (tmp_path / "generated" / "comfyui").mkdir(parents=True)
    (tmp_path / "generated" / "comfyui" / "hero.png").write_bytes(_png("teal"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(ProjectRecord(id="project", title="t", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
    db.add(ProjectRecord(id="other", title="o", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path / "other")))
    db.add(AssetRecord(id="hero", project_id="project", asset_type="COMFYUI_GENERATED_IMAGE", filename="hero.png",
                       relative_path="generated/comfyui/hero.png", content_type="image/png", width=64, height=64,
                       byte_size=1, sha256="0" * 64, status="READY", provenance={}))
    db.commit()
    return engine, db


def test_reference_assets_reach_the_art_engine_and_are_recorded(tmp_path, monkeypatch):
    import types

    from engine.comfyui.art import ArtImage

    seen = {}

    class FakeArt:
        def __init__(self, *a, **k):
            pass

        def generate(self, *a, **k):
            seen.update(k)
            return ArtImage(png=_png(), width=64, height=64, prompt_id="p1", workflow_id=service.ART_WORKFLOW_ID,
                            workflow_sha256="a" * 64, model_files=["m"],
                            source_output={"filename": "k.png", "subfolder": "", "type": "output"}, seed=1)

    monkeypatch.setattr(service, "ArtEngine", FakeArt)
    monkeypatch.setattr(service, "ComfyUIClient", lambda: types.SimpleNamespace(base_url="http://x/"))
    monkeypatch.setattr(service, "ComfyWorkflowRegistry", lambda *a, **k: None)
    engine, db = _reference_fixture(tmp_path)
    try:
        service.generate_image_operation(db, lambda *_: None, lambda: False, project_id="project", workflow_id=service.ART_WORKFLOW_ID,
                                         prompt="same hero, running", negative_prompt="", width=64, height=64, seed=1,
                                         reference_asset_ids=["hero"])
        assert seen["reference_images"] == [tmp_path / "generated" / "comfyui" / "hero.png"]
        new = db.query(AssetRecord).filter(AssetRecord.id != "hero").one()
        assert new.provenance["reference_asset_ids"] == ["hero"]

        seen.clear()  # no references: the engine call must not change for existing callers
        service.generate_image_operation(db, lambda *_: None, lambda: False, project_id="project", workflow_id=service.ART_WORKFLOW_ID,
                                         prompt="a lamp", negative_prompt="", width=64, height=64, seed=2)
        assert seen["reference_images"] is None
    finally:
        db.close()
        engine.dispose()


def test_an_h3_image_job_draws_at_the_working_size_and_stores_the_size_that_was_asked_for(tmp_path, monkeypatch):
    import types

    from engine.comfyui.art import ArtImage

    seen, released = {}, []

    class FakeArt:
        def __init__(self, *a, **k):
            pass

        def generate(self, prompt, negative, width, height, *a, **k):
            seen.update(k, size=(width, height))
            buf = io.BytesIO()
            Image.new("RGB", (width, height), "red").save(buf, "PNG")
            return ArtImage(png=buf.getvalue(), width=width, height=height, prompt_id="p1", workflow_id=k["workflow_id"],
                            workflow_sha256="a" * 64, model_files=["m"],
                            source_output={"filename": "k.png", "subfolder": "", "type": "output"}, seed=1)

    monkeypatch.setattr(service, "ArtEngine", FakeArt)
    monkeypatch.setattr(service, "release_local_model", lambda: released.append(True))
    monkeypatch.setattr(service, "ComfyUIClient", lambda: types.SimpleNamespace(base_url="http://x/"))
    monkeypatch.setattr(service, "ComfyWorkflowRegistry", lambda *a, **k: None)
    engine, db = _reference_fixture(tmp_path)
    kw = dict(project_id="project", workflow_id=service.EDIT_WORKFLOW_ID, prompt="a lamp on a table", negative_prompt="", seed=1)
    try:
        out = service.generate_image_operation(db, lambda *_: None, lambda: False, width=1344, height=768, **kw)
        assert seen["size"] == service.h3_edit_size(1344, 768) == (2720, 1536) and seen["workflow_id"] == service.EDIT_WORKFLOW_ID
        assert released == [True]  # the local model leaves the VRAM first
        new = db.query(AssetRecord).filter(AssetRecord.id == out["asset_id"]).one()
        with Image.open(tmp_path / new.relative_path) as stored:
            assert stored.size == (new.width, new.height) == (out["width"], out["height"]) == (1344, 768)
        assert (new.provenance["drawn_width"], new.provenance["drawn_height"]) == (2720, 1536)
        assert new.provenance["workflow_id"] == service.EDIT_WORKFLOW_ID
        with pytest.raises(service.ComfyImageGenerationError, match="refine only runs"):
            service.generate_image_operation(db, lambda *_: None, lambda: False, width=1344, height=768, refine=True, **kw)
        with pytest.raises(service.ComfyImageGenerationError, match="Image workflows"):
            service.generate_image_operation(db, lambda *_: None, lambda: False, width=1344, height=768, **{**kw, "workflow_id": "anime_sdxl"})
    finally:
        db.close()
        engine.dispose()


def test_bad_references_fail_before_any_gpu_work(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "ArtEngine", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not generate")))
    engine, db = _reference_fixture(tmp_path)
    kw = dict(project_id="project", workflow_id=service.ART_WORKFLOW_ID, prompt="a lamp", negative_prompt="", width=64, height=64, seed=1)
    try:
        with pytest.raises(service.ComfyImageGenerationError, match="not found in this project"):
            service.generate_image_operation(db, lambda *_: None, lambda: False, reference_asset_ids=["nope"], **kw)
        with pytest.raises(service.ComfyImageGenerationError, match="refine does not support"):
            service.generate_image_operation(db, lambda *_: None, lambda: False, reference_asset_ids=["hero"], refine=True, **kw)
        (tmp_path / "generated" / "comfyui" / "hero.png").unlink()
        with pytest.raises(service.ComfyImageGenerationError, match="no file on disk"):
            service.generate_image_operation(db, lambda *_: None, lambda: False, reference_asset_ids=["hero"], **kw)
    finally:
        db.close()
        engine.dispose()


def test_route_rejects_unknown_or_foreign_references_and_refine_combination(tmp_path):
    from fastapi import HTTPException

    from engine.api.routers.comfyui import ComfyImageRequest, submit_comfyui_image_job

    engine, db = _reference_fixture(tmp_path)
    try:
        with pytest.raises(HTTPException) as e:
            submit_comfyui_image_job("other", ComfyImageRequest(prompt="same hero, running", reference_asset_ids=["hero"]), db=db)
        assert e.value.status_code == 400 and "not found in this project" in e.value.detail  # an asset of another project
        with pytest.raises(HTTPException) as e:
            submit_comfyui_image_job("project", ComfyImageRequest(prompt="same hero, running", reference_asset_ids=["hero"], refine=True), db=db)
        assert e.value.status_code == 400 and "refine" in e.value.detail
        with pytest.raises(ValueError):
            ComfyImageRequest(prompt="same hero, running", reference_asset_ids=["a", "b", "c", "d", "e"])  # the workflow has four slots
    finally:
        db.close()
        engine.dispose()


def test_recovered_job_keeps_its_references(monkeypatch):
    captured = {}
    monkeypatch.setattr(service, "generate_image_operation", lambda *a, **k: captured.update(k))
    payload = {"workflow_id": service.ART_WORKFLOW_ID, "prompt": "p" * 12, "width": 64, "height": 64, "seed": 1,
               "reference_asset_ids": ["hero"]}
    service.build_comfy_image_operation("project", payload)(None, None, None)
    assert captured["reference_asset_ids"] == ["hero"]
    captured.clear()
    service.build_comfy_image_operation("project", {k: v for k, v in payload.items() if k != "reference_asset_ids"})(None, None, None)
    assert captured["reference_asset_ids"] is None  # jobs queued before this change still rehydrate


def _mp4(tmp_path, frames=6, size=(64, 48)):
    import cv2
    import numpy as np

    path = tmp_path / "fake_clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 24.0, size)
    for i in range(frames):
        writer.write(np.full((size[1], size[0], 3), i * 30, dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def _clip_fixture(tmp_path, monkeypatch, video=None):
    """A project with a stored picture, the GPU render faked (it records how it was called), everything else real."""
    import types

    from engine.original import animate, h3_modes

    calls = {}

    def fake_make_clip(mode, prompt, **kw):
        calls.update(mode=mode, prompt=prompt, **kw)
        return video if video is not None else _mp4(tmp_path)

    monkeypatch.setattr(h3_modes, "make_clip", fake_make_clip)
    monkeypatch.setattr(animate, "release_ollama", lambda: calls.update(ollama_released=True))
    monkeypatch.setattr(service, "ComfyUIClient", lambda: types.SimpleNamespace(base_url="http://x/"))
    monkeypatch.setattr(service, "ComfyWorkflowRegistry", lambda *a, **k: types.SimpleNamespace(load=lambda wid: ({}, "b" * 64)))
    engine, db = _reference_fixture(tmp_path)
    return calls, engine, db


def _run_clip(db, **kw):
    args = dict(project_id="project", action="The hero runs in place", seconds=2.3, seed=7, first_asset_id="hero")
    return service.generate_clip_operation(db, lambda *_: None, kw.pop("is_cancelled", lambda: False), **{**args, **kw})


def test_one_picture_makes_an_image_to_video_clip_that_is_stored_as_an_asset(tmp_path, monkeypatch):
    calls, engine, db = _clip_fixture(tmp_path, monkeypatch)
    try:
        out = _run_clip(db)
        assert calls["mode"] == "i2va" and calls["first"] == tmp_path / "generated" / "comfyui" / "hero.png" and calls["last"] is None
        assert "<Picture 1>" in calls["prompt"] and "The hero runs in place" in calls["prompt"] and calls["ollama_released"]
        asset = db.query(AssetRecord).filter(AssetRecord.id == out["asset_id"]).one()
        assert asset.asset_type == "COMFYUI_GENERATED_VIDEO" and asset.content_type == "video/mp4"
        assert (asset.width, asset.height, out["frames"]) == (64, 48, 6)
        assert (tmp_path / asset.relative_path).stat().st_size == asset.byte_size == out["byte_size"]
        assert asset.provenance["workflow_id"] == "fastvideo_h3_film_free" and asset.provenance["workflow_sha256"] == "b" * 64
        assert asset.provenance["seed"] == 7 and asset.provenance["first_asset_id"] == "hero"
    finally:
        db.close()
        engine.dispose()


def test_the_same_picture_as_first_and_last_frame_makes_a_loop(tmp_path, monkeypatch):
    calls, engine, db = _clip_fixture(tmp_path, monkeypatch)
    try:
        out = _run_clip(db, last_asset_id="hero")
        hero = tmp_path / "generated" / "comfyui" / "hero.png"
        assert calls["mode"] == "fl2va" and calls["first"] == hero and calls["last"] == hero and out["mode"] == "fl2va"
        assert "2.33-second mark" in calls["prompt"]  # the alignment line uses the length H3 really renders, not the 2.3 asked for
    finally:
        db.close()
        engine.dispose()


def test_clip_failures_leave_no_asset_and_no_file(tmp_path, monkeypatch):
    calls, engine, db = _clip_fixture(tmp_path, monkeypatch, video=b"this is not a video")
    try:
        with pytest.raises(service.H3ClipGenerationError, match="cannot be decoded"):
            _run_clip(db)
        assert db.query(AssetRecord).filter(AssetRecord.asset_type == "COMFYUI_GENERATED_VIDEO").count() == 0
        assert [p.name for p in (tmp_path / "generated" / "comfyui").iterdir()] == ["hero.png"]  # the unreadable file was removed
        calls.clear()
        with pytest.raises(service.H3ClipGenerationError, match="not found in this project"):
            _run_clip(db, first_asset_id="nope")
        with pytest.raises(service.H3ClipGenerationError, match="Last-frame asset"):
            _run_clip(db, last_asset_id="nope")
        with pytest.raises(service.H3ClipGenerationError, match="cancelled"):
            _run_clip(db, is_cancelled=lambda: True)
        assert "mode" not in calls  # none of those reached the GPU
    finally:
        db.close()
        engine.dispose()


def test_clip_route_refuses_assets_of_another_project(tmp_path):
    from fastapi import HTTPException

    from engine.api.routers.comfyui import ComfyClipRequest, submit_comfyui_clip_job

    engine, db = _reference_fixture(tmp_path)
    try:
        for kw in ({}, {"last_asset_id": "hero"}):  # "hero" belongs to "project", not "other"
            with pytest.raises(HTTPException) as e:
                submit_comfyui_clip_job("other", ComfyClipRequest(action="The hero runs in place", first_asset_id="hero", **kw), db=db)
            assert e.value.status_code == 400 and "not found in this project" in e.value.detail
        with pytest.raises(HTTPException) as e:
            submit_comfyui_clip_job("missing", ComfyClipRequest(action="The hero runs in place", first_asset_id="hero"), db=db)
        assert e.value.status_code == 404
    finally:
        db.close()
        engine.dispose()


def test_clip_job_survives_a_restart_and_is_gated_as_a_comfyui_job(monkeypatch):
    from engine.jobs.manager import COMFYUI_JOB_TYPES

    assert service.H3_CLIP_JOB_TYPE in COMFYUI_JOB_TYPES  # else the GPU gate would refuse it whenever ComfyUI holds its weights
    captured = {}
    monkeypatch.setattr(service, "generate_clip_operation", lambda *a, **k: captured.update(k))
    payload = {"action": "The hero runs in place", "first_asset_id": "hero", "last_asset_id": "hero", "seconds": 2.3, "seed": 7, "timeout_s": 900.0}
    service.build_h3_clip_operation("project", payload)(None, None, None)
    assert captured == {"project_id": "project", "action": "The hero runs in place", "seconds": 2.3, "seed": 7, "first_asset_id": "hero",
                        "last_asset_id": "hero", "timeout_s": 900.0}
