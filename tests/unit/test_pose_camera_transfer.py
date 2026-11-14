"""Pose and camera transfer: the artwork keeps its characters and style, a second picture gives the poses and the camera."""
import base64
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.api.routers import comfyui
from engine.comfyui import edit_prompt, service
from engine.database.models import AssetRecord, Base, ProjectRecord
from engine.database.session import get_db


def _png(width: int, height: int, color=(10, 20, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture
def project(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pose.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    (tmp_path / "generated" / "comfyui").mkdir(parents=True)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p1", title="T", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        for asset_id, size in (("art", (1344, 768)), ("pose", (502, 664))):
            rel = f"generated/comfyui/{asset_id}.png"
            (tmp_path / rel).write_bytes(_png(*size))
            db.add(AssetRecord(id=asset_id, project_id="p1", asset_type="COMFYUI_GENERATED_IMAGE", filename=f"{asset_id}.png",
                               relative_path=rel, content_type="image/png", width=size[0], height=size[1],
                               byte_size=1, sha256=asset_id, status="READY", provenance={}))
        db.commit()
    return engine, tmp_path


@pytest.fixture
def client(project, monkeypatch):
    engine, _ = project

    class Registry:
        def metadata(self, wid):
            return {"requires_gpu": True, "gpu_vram_mb": 16000}

        def load(self, wid):
            return {}, "x"

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

    queued = {}
    monkeypatch.setattr(comfyui, "ComfyWorkflowRegistry", Registry)
    monkeypatch.setattr(comfyui, "enqueue_project_operation", lambda **kw: queued.update(kw) or "job-1")
    app = FastAPI()
    app.include_router(comfyui.project_router)
    app.dependency_overrides[get_db] = lambda: Session(engine)
    return TestClient(app), queued, engine


def test_a_pose_asset_is_queued_without_an_instruction(client):
    c, queued, _ = client
    res = c.post("/api/projects/p1/comfyui/edit", json={"asset_id": "art", "pose_asset_id": "pose"})
    assert res.status_code == 200
    assert queued["job_input"]["pose_asset_id"] == "pose"
    assert "pose_image_data" not in queued["job_input"]


def test_an_uploaded_pose_picture_becomes_a_project_asset(client, project):
    c, queued, engine = client
    data = "data:image/png;base64," + base64.b64encode(_png(502, 664)).decode()
    res = c.post("/api/projects/p1/comfyui/edit", json={"asset_id": "art", "pose_image_data": data, "prompt": "man in black leaps"})
    assert res.status_code == 200
    pose_id = res.json()["pose_asset_id"]
    assert queued["job_input"]["pose_asset_id"] == pose_id
    assert "pose_image_data" not in queued["job_input"]  # the job row must not carry the picture
    with Session(engine) as db:
        asset = db.query(AssetRecord).filter(AssetRecord.id == pose_id).one()
        assert asset.asset_type == "POSE_REFERENCE"
        assert (project[1] / asset.relative_path).is_file()


@pytest.mark.parametrize("body,code", [
    ({"asset_id": "art"}, 422),  # neither an instruction nor a pose picture
    ({"asset_id": "art", "pose_asset_id": "pose", "pose_image_data": "AAAA"}, 422),  # two pose pictures
    ({"asset_id": "art", "pose_asset_id": "nope"}, 400),  # not in this project
    ({"asset_id": "art", "pose_image_data": "not base64 at all!"}, 400),  # unusable upload
])
def test_bad_transfer_requests_are_refused(client, body, code):
    c, _, _ = client
    assert c.post("/api/projects/p1/comfyui/edit", json=body).status_code == code


def test_a_plain_edit_still_needs_its_instruction(client):
    c, _, _ = client
    assert c.post("/api/projects/p1/comfyui/edit", json={"asset_id": "art", "prompt": "make the sky stormy"}).status_code == 200


def test_the_caption_falls_back_to_a_plain_instruction_when_the_local_model_is_away(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "Client", boom)
    caption = edit_prompt.compose_transfer_prompt(_png(64, 64), _png(64, 64), "the man in black leaps")
    assert "<Picture 1>" in caption and "<Picture 2>" in caption and caption.endswith("the man in black leaps")


def test_the_caption_must_name_both_pictures(monkeypatch):
    import httpx

    class Reply:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

        def json(self):
            return {"response": self.text}

    class Fake:
        text = ""

        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return Reply(Fake.text)

    monkeypatch.setattr(httpx, "Client", Fake)
    good = ("Redraw <Picture 1> in exactly its own rendering, but follow <Picture 2>: on the left the man in a black coat leaps, "
            "clean-shaven, exactly two characters.")
    Fake.text = good
    assert edit_prompt.compose_transfer_prompt(_png(64, 64), _png(64, 64)) == good
    Fake.text = "A nice picture of two men fighting in a cave with ice and swords and glowing light everywhere you look."
    assert "<Picture 2>" in edit_prompt.compose_transfer_prompt(_png(64, 64), _png(64, 64))  # replaced by the plain instruction
    assert edit_prompt.compose_transfer_prompt(_png(64, 64), _png(64, 64)) != Fake.text


def test_the_transfer_edit_puts_the_artwork_first_and_takes_the_shape_of_the_pose_picture(project, monkeypatch):
    engine, tmp_path = project
    seen = {}

    class Art:
        def __init__(self, *a, **k):
            pass

        def edit(self, caption, references, *, width, height, **kw):
            seen.update(caption=caption, references=references, width=width, height=height)
            return type("A", (), {"png": _png(width, height), "width": width, "height": height, "prompt_id": "x", "workflow_id": "w",
                                  "workflow_sha256": "s", "model_files": [], "source_output": {"filename": "o.png"}})()

    class Reg:
        def __init__(self, *a, **k):
            pass

        def load(self, wid):
            return {}, "x"

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

    monkeypatch.setattr(service, "ArtEngine", Art)
    monkeypatch.setattr(service, "ComfyUIClient", lambda *a, **k: type("C", (), {"base_url": "http://x"})())
    monkeypatch.setattr(service, "ComfyWorkflowRegistry", Reg)
    monkeypatch.setattr(service, "release_local_model", lambda: None)
    monkeypatch.setattr(service, "compose_transfer_prompt", lambda art, pose, hint: f"TRANSFER:{hint}")
    with Session(engine) as db:
        out = service.edit_image_operation(db, lambda *a: None, lambda: False, project_id="p1", base_asset_id="art",
                                           pose_asset_id="pose", prompt="note")
        asset = db.query(AssetRecord).filter(AssetRecord.id == out["asset_id"]).one()
    expected = service.h3_edit_size(502, 664)
    assert (seen["width"], seen["height"]) == expected  # the pose picture sets the shape
    first, second = (Image.open(io.BytesIO(b)).size for b in seen["references"][:2])
    assert first == (1344, 768)  # <Picture 1> is the artwork, at its own size
    assert second == expected  # <Picture 2> is the pose picture at the working size
    assert seen["caption"] == "TRANSFER:note"
    assert asset.provenance["mode"] == "pose_camera_transfer" and asset.provenance["pose_asset_id"] == "pose"


def test_an_edit_job_is_rehydrated_as_an_edit(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "edit_image_operation", lambda *a, **k: seen.update(k))
    service.build_comfy_image_operation("p1", {"asset_id": "art", "prompt": "", "pose_asset_id": "pose", "seed": 7})(None, None, None)
    assert seen["base_asset_id"] == "art" and seen["pose_asset_id"] == "pose" and seen["seed"] == 7
