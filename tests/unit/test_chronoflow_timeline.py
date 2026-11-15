"""Server-side ChronoFlow timeline: what agents (MCP) change is what the studio shows and the export renders."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import chronoflow_timeline as router_mod
from engine.chronoflow import timeline_ops as ops


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ops, "TIMELINE_DIR", tmp_path / "timelines")
    app = FastAPI()
    app.include_router(router_mod.router)
    return TestClient(app)


def _tl(n=2):
    return {"fps": 24, "clips": [{"id": f"c{i}", "label": f"Shot {i}", "src": f"s{i}.mp4", "in": 0, "out": 4, "speed": 1} for i in range(1, n + 1)]}


def test_the_ui_mirror_is_versioned_and_an_agent_edit_moves_the_version(client):
    assert client.get("/api/chronoflow/timeline/job1").json()["version"] == 0
    assert client.put("/api/chronoflow/timeline/job1", json={"timeline": _tl(), "source": "ui:abc"}).json()["version"] == 1
    r = client.post("/api/chronoflow/timeline/job1/op", json={"op": "color_set", "args": {"clip": 2, "controls": {"saturation": 0.4}}}).json()
    assert r["version"] == 2 and r["result"]["graded"][0]["clip"] == "c2"
    got = client.get("/api/chronoflow/timeline/job1").json()
    assert got["source"] == "agent", "the studio uses this to tell an agent edit from its own echo"
    assert got["timeline"]["clips"][1]["grade"]["nodes"][0]["saturation"] == 0.4 and "grade" not in got["timeline"]["clips"][0]
    assert got["clips"][1]["grade"] == [{"saturation": 0.4}], "the summary lists only what differs from neutral"


def test_grade_nodes_have_the_exact_shape_the_color_page_builds():
    tl = _tl(1)
    ops.color_set(tl, 1, {"gain": {"color": "orange", "amount": 0.5, "master": 0.1}, "temp": 20})
    node = tl["clips"][0]["grade"]["nodes"][0]
    assert set(node) == set(ops.new_node()), "same keys as grade.js newNode, so grade.js compiles it unchanged"
    assert node["gain"] == {"x": 0.433, "y": 0.25, "m": 0.1}, "orange = 30 degrees on the wheel ring (0 = red)"
    assert node["temp"] == 20 and tl["clips"][0]["grade"]["on"] is True


def test_a_look_goes_on_a_new_node_and_matches_the_color_page_numbers():
    tl = _tl(1)
    ops.color_set(tl, 1, {"contrast": 1.05})
    ops.color_set(tl, 1, {}, node=2, look="Teal & Orange")
    nodes = tl["clips"][0]["grade"]["nodes"]
    assert len(nodes) == 2 and nodes[0]["contrast"] == 1.05
    assert nodes[1]["label"] == "Teal & Orange" and nodes[1]["lift"] == {"x": -0.8, "y": -0.15, "m": 0} and nodes[1]["contrast"] == 1.12


def test_bad_requests_say_what_is_allowed(client):
    client.put("/api/chronoflow/timeline/j", json={"timeline": _tl()})
    cases = [
        ({"op": "color_set", "args": {"clip": 1, "controls": {"saturation": 5}}}, "0.0..2.0"),
        ({"op": "color_set", "args": {"clip": 9, "controls": {"saturation": 1}}}, "1..2"),
        ({"op": "color_set", "args": {"controls": {"sharpness": 1}}}, "unknown colour control"),
        ({"op": "color_set", "args": {"look": "Miami"}}, "Teal & Orange"),
        ({"op": "color_set", "args": {"controls": {"lift": {"color": "chartreuse"}}}}, "unknown colour"),
        ({"op": "fusion_add", "args": {"effect": "lens_flare"}}, "vignette"),
        ({"op": "explode", "args": {}}, "unknown op"),
    ]
    for body, hint in cases:
        r = client.post("/api/chronoflow/timeline/j/op", json=body)
        assert r.status_code == 400 and hint in r.json()["detail"], (body, r.json())
    assert client.get("/api/chronoflow/timeline/j").json()["version"] == 1, "a refused op changes nothing"


def test_an_op_before_the_job_was_opened_explains_what_to_do(client):
    r = client.post("/api/chronoflow/timeline/never/op", json={"op": "color_reset", "args": {}})
    assert r.status_code == 400 and "open the job once" in r.json()["detail"]


def test_job_ids_cannot_escape_the_timeline_folder(client):
    assert client.get("/api/chronoflow/timeline/..%5Cevil").status_code in (400, 404)
    with pytest.raises(ops.TimelineError):
        ops.load("../../evil")


def test_fusion_effects_chain_before_media_out_on_every_clip():
    tl = _tl(2)
    ops.fusion_add(tl, "all", "vignette", {"opacity": 0.5})
    ops.fusion_add(tl, 1, "text_plus", {"text": "Chapter 1"})
    g = tl["clips"][0]["fusion"]
    order, at = [], "media_out"
    while at != "media_in":
        conn = next(c for c in g["connections"] if c["to"]["nodeId"] == at)
        at = conn["from"]["nodeId"]
        order.append(next(n["type"] for n in g["nodes"] if n["id"] == at))
    assert order == ["text_plus", "vignette", "mediain"], "MediaIn -> vignette -> text -> MediaOut"
    assert [n["type"] for n in tl["clips"][1]["fusion"]["nodes"]][-1] == "vignette"
    assert ops.fusion_clear(tl, "all") and all("fusion" not in c for c in tl["clips"])


def test_copy_grade_to_all_and_reset():
    tl = _tl(3)
    ops.color_set(tl, 1, {}, look="Noir")
    ops.color_copy(tl, 1, "all")
    assert all(c["grade"]["nodes"][0]["saturation"] == 0 for c in tl["clips"])
    ops.color_reset(tl, 2)
    assert "grade" not in tl["clips"][1] and "grade" in tl["clips"][2]
