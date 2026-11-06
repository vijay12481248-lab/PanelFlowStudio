"""Phase 5b: `refine` is reachable from the Comfy image job, the ChronoFlow route and the MCP tool, off by default, and old persisted jobs still load."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from engine.api.routers import chronoflow, comfyui
from engine.comfyui import service
from engine.database.models import Base, ProjectRecord
from engine.database.session import get_db


@pytest.fixture
def comfy_client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="p1", title="t", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        db.commit()

    class Registry:
        def metadata(self, wid):
            return {"requires_gpu": True, "gpu_vram_mb": 1}

        def load(self, wid):
            return {}, "x"

        def preflight(self, wid):
            return {"ready": True, "missing_nodes": [], "missing_models": []}

    queued = {}

    def fake_enqueue(**kw):
        queued.update(kw)
        return "job-1"

    monkeypatch.setattr(comfyui, "ComfyWorkflowRegistry", Registry)
    monkeypatch.setattr(comfyui, "enqueue_project_operation", fake_enqueue)
    app = FastAPI()
    app.include_router(comfyui.project_router)
    app.dependency_overrides[get_db] = lambda: Session(engine)
    return TestClient(app), queued, monkeypatch


def test_comfy_image_job_defaults_to_no_refine_and_passes_it_through_when_asked(comfy_client):
    c, queued, mp = comfy_client
    body = {"prompt": "a lamp on a wooden table"}
    assert c.post("/api/projects/p1/comfyui/image", json=body).status_code == 200
    assert queued["job_input"]["refine"] is False
    assert c.post("/api/projects/p1/comfyui/image", json={**body, "refine": True}).json()["job_id"] == "job-1"
    assert queued["job_input"]["refine"] is True
    seen = {}
    mp.setattr(comfyui, "generate_image_operation", lambda *a, **kw: seen.update(kw))
    queued["operation"](None, lambda *_: None, lambda: False)
    assert seen["refine"] is True  # what the worker runs is what was asked for


def test_a_persisted_job_from_before_refine_existed_still_rehydrates_with_it_off(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "generate_image_operation", lambda *a, **kw: seen.update(kw))
    payload = {"workflow_id": "qwen_image_21", "prompt": "a lamp on a table", "negative_prompt": None, "width": 64, "height": 64, "seed": 1}
    service.build_comfy_image_operation("p1", payload)(None, lambda *_: None, lambda: False)
    assert seen["refine"] is False
    service.build_comfy_image_operation("p1", {**payload, "refine": True})(None, lambda *_: None, lambda: False)
    assert seen["refine"] is True


@pytest.fixture
def chrono_client():
    app = FastAPI()
    app.include_router(chronoflow.router)
    return TestClient(app)


def test_chronoflow_generate_image_reports_the_refinement_only_when_it_ran(chrono_client, monkeypatch):
    calls = []

    async def fake(prompt, negative, w, h, seed, refine=False):
        calls.append(refine)
        return "art_x.png", ({"status": "accept_low", "repaired": True, "iterations": []} if refine else None)

    monkeypatch.setattr(chronoflow.pipeline, "generate_art_image_ex", fake)
    plain = chrono_client.post("/api/chronoflow/generate_image", json={"prompt": "a lamp"}).json()
    assert plain["filename"] == "art_x.png" and "refine" not in plain  # the response shape is unchanged by default
    refined = chrono_client.post("/api/chronoflow/generate_image", json={"prompt": "a lamp", "refine": True}).json()
    assert refined["refine"]["status"] == "accept_low" and calls == [False, True]


def test_generate_art_image_keeps_its_old_return_type():
    from engine.chronoflow.pipeline import ChronoFlowPipeline

    p = ChronoFlowPipeline.__new__(ChronoFlowPipeline)

    async def ex(*a, **kw):
        return "f.png", None

    p.generate_art_image_ex = ex
    assert asyncio.run(ChronoFlowPipeline.generate_art_image(p, "a", "b")) == "f.png"


def test_the_mcp_tool_offers_refine_and_forwards_it(monkeypatch):
    from engine.mcp.tools import chronoflow_tools as t

    sent = {}

    async def fake_post(path, payload, **kw):
        sent.update(payload=payload, path=path)
        return {"success": True}

    monkeypatch.setattr(t.bridge, "post", fake_post)
    asyncio.run(t.panelflow_chronoflow_generate_image("a lamp"))
    assert sent["payload"]["refine"] is False
    asyncio.run(t.panelflow_chronoflow_generate_image("a lamp", refine=True))
    assert sent["payload"]["refine"] is True and sent["path"] == "/api/chronoflow/generate_image"


def test_refine_summary_has_what_a_ui_needs_and_no_image_bytes():
    from engine.original import refine as rf
    from engine.original.planner import CorrectionPlan

    res = rf.RefineResult(png=b"\x89PNG-bytes", selected=2, review=None, status="accept_low", repaired=True, generations=1,
                          plan=CorrectionPlan(action="accept", reason="the picture passes the review", final=True),
                          iterations=[{"n": 1, "kind": "generate", "file": "f", "png": b"x", "review": {"decision": "regenerate"}},
                                      {"n": 2, "kind": "repair", "parent": 1, "kept": True, "review": {"decision": "accept"}, "crop_check": [{"answer": "yes"}]}])
    out = rf.summary(res)
    assert out["status"] == "accept_low" and out["repaired"] and out["reason"] and [i["n"] for i in out["iterations"]] == [1, 2]
    assert "png" not in out["iterations"][0] and b"x" not in str(out).encode() and out["iterations"][1]["crop_check"][0]["answer"] == "yes"
