import shutil
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import audio_studio as mod
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import PlanStore, snap
from engine.audio.studio.sources.synth import SynthProvider

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=3:r=24",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)], check=True)
    return p


@pytest.fixture
def client(tmp_path):
    store = PlanStore(tmp_path / "store")
    engine = AudioEngine(store, [SynthProvider()])
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_engine] = lambda: engine
    return TestClient(app)


def _create(client, video, **kw):
    r = client.post("/api/audio/studio/plans", json={"video_path": str(video), **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_plan_probes_video(client, video):
    plan = _create(client, video)
    assert plan["fps"] == 24.0 and plan["duration"] == pytest.approx(3.0, abs=0.1) and plan["dialogue_path"] == str(video) and plan["version"] == 1


def test_create_plan_rejects_missing_video(client, tmp_path):
    assert client.post("/api/audio/studio/plans", json={"video_path": str(tmp_path / "nope.mp4")}).status_code == 400


def test_get_unknown_plan_404(client):
    assert client.get("/api/audio/studio/plans/ap_nope").status_code == 404


def test_put_snaps_hit_t_and_bumps_version(client, video):
    plan = _create(client, video)
    cues = [{"id": "c1", "track": "sfx", "kind": "impact", "hit_t": 1.013}]
    got = client.put(f"/api/audio/studio/plans/{plan['id']}", json={"cues": cues}).json()
    assert got["version"] == 2 and got["cues"][0]["hit_t"] == snap(1.013, 24.0) and got["cues"][0]["status"] == "draft"


def test_put_merges_existing_cue_state_and_rejects_bad_cues(client, video):
    plan = _create(client, video)
    pid = plan["id"]
    client.put(f"/api/audio/studio/plans/{pid}", json={"cues": [{"id": "c1", "track": "sfx", "kind": "impact", "hit_t": 1.0}]})
    client.post(f"/api/audio/studio/plans/{pid}/cues/c1/source", json={})
    got = client.put(f"/api/audio/studio/plans/{pid}", json={"cues": [{"id": "c1", "intent": "new words"}]}).json()
    assert got["cues"][0]["intent"] == "new words" and got["cues"][0]["chosen_take"] and got["cues"][0]["kind"] == "impact"
    for bad in ([{"id": "../x", "track": "sfx", "kind": "impact"}], [{"id": "a", "track": "sfx", "kind": "x", "hit_t": -1}],
                [{"id": "a", "track": "sfx", "kind": "x"}, {"id": "a", "track": "sfx", "kind": "y"}]):
        assert client.put(f"/api/audio/studio/plans/{pid}", json={"cues": bad}).status_code == 400


def test_bad_ids_400(client, video):
    assert client.get("/api/audio/studio/plans/..%5Cx").status_code in (400, 404)
    assert client.get("/api/audio/studio/plans/a.b").status_code == 400
    pid = _create(client, video)["id"]
    assert client.get(f"/api/audio/studio/plans/{pid}/files/..%2F..%2Fx").status_code in (400, 404)
    assert client.get(f"/api/audio/studio/plans/{pid}/files/..\\plan.json").status_code in (400, 404)


def test_source_ask_mode_returns_needs_pick_then_pick(client, video):
    pid = _create(client, video, mode="ask")["id"]
    client.put(f"/api/audio/studio/plans/{pid}", json={"cues": [{"id": "c1", "track": "sfx", "kind": "impact", "hit_t": 1.0}]})
    cue = client.post(f"/api/audio/studio/plans/{pid}/cues/c1/source", json={}).json()["cues"][0]
    assert cue["status"] == "needs_pick" and len(cue["candidates"]) == 3
    done = client.post(f"/api/audio/studio/plans/{pid}/cues/c1/pick", json={"candidate_id": cue["candidates"][1]["id"]}).json()
    assert done["cues"][0]["status"] == "ready"
    assert client.post(f"/api/audio/studio/plans/{pid}/cues/c1/pick", json={"candidate_id": "nope"}).status_code == 404
    assert client.post(f"/api/audio/studio/plans/{pid}/cues/zzz/source", json={}).status_code == 404


def test_providers_report_shape(client):
    r = client.get("/api/audio/studio/providers").json()
    assert r["synth"] == {"ok": True, "reason": None}


def test_spot_qa_mix_export_files(client, video):
    pid = _create(client, video)["id"]
    plan = client.post(f"/api/audio/studio/plans/{pid}/spot").json()
    assert [c["track"] for c in plan["cues"]] == ["music"]  # a flat black video has no cuts
    client.put(f"/api/audio/studio/plans/{pid}", json={"cues": [{"id": "c1", "track": "sfx", "kind": "impact", "hit_t": 1.0}], "remove_cues": ["music_1"]})
    client.post(f"/api/audio/studio/plans/{pid}/cues/c1/source", json={})
    qa = client.post(f"/api/audio/studio/plans/{pid}/qa").json()
    assert qa["errors"] == 0
    assert next(c for c in client.get(f"/api/audio/studio/plans/{pid}").json()["cues"] if c["id"] == "c1")["placement_error_ms"] is not None
    mix = client.post(f"/api/audio/studio/plans/{pid}/mix", json={"target_lufs": -14}).json()
    assert mix["file"] == "renders/master.wav" and "integrated_lufs" in mix["loudness"]
    assert client.get(f"/api/audio/studio/plans/{pid}/files/{mix['file']}").status_code == 200
    exp = client.post(f"/api/audio/studio/plans/{pid}/export", json={"mux": True}).json()
    assert "master.mp4" in exp["files"] and "me.wav" in exp["files"]


def test_put_cues_upserts_and_keeps_unlisted_cues_until_removed(client, video):
    pid = _create(client, video)["id"]
    put = lambda **b: client.put(f"/api/audio/studio/plans/{pid}", json=b)  # noqa: E731
    put(cues=[{"id": "a", "track": "sfx", "kind": "click"}, {"id": "b", "track": "sfx", "kind": "pop"}])
    got = put(cues=[{"id": "b", "intent": "changed"}, {"id": "c", "track": "sfx", "kind": "ding"}]).json()
    assert [c["id"] for c in got["cues"]] == ["a", "b", "c"] and got["cues"][1]["intent"] == "changed"
    got = put(remove_cues=["a", "c"]).json()
    assert [c["id"] for c in got["cues"]] == ["b"]
    assert put(remove_cues=["nope"]).status_code == 400


def test_long_qa_does_not_wipe_an_edit_made_while_it_ran(client, video):
    """Review #1: qa/export saved the plan loaded before they started."""
    import threading
    pid = _create(client, video)["id"]
    base = f"/api/audio/studio/plans/{pid}"
    client.put(base, json={"cues": [{"id": "c1", "track": "sfx", "kind": "impact", "hit_t": 1.0, "intent": "first"}]})
    client.post(f"{base}/cues/c1/source", json={})
    started, release = threading.Event(), threading.Event()
    real = mod.mixer.render_cue

    def slow(plan, cue, out):
        started.set()
        release.wait(10)
        return real(plan, cue, out)
    mod.mixer.render_cue = slow
    try:
        t = threading.Thread(target=lambda: client.post(f"{base}/qa"))
        t.start()
        assert started.wait(10)
        client.put(base, json={"cues": [{"id": "c1", "intent": "edited during qa"}]})
        release.set()
        t.join(30)
    finally:
        mod.mixer.render_cue = real
    cue = client.get(base).json()["cues"][0]
    assert cue["intent"] == "edited during qa" and cue["placement_error_ms"] is not None


def test_put_plan_refuses_server_owned_cue_fields(client, video):
    """Review #4: a caller could set takes with any path and any licence, skipping the licence gate."""
    pid = _create(client, video)["id"]
    forged = {"id": "c1", "track": "sfx", "kind": "x", "chosen_take": "t", "status": "ready",
              "takes": [{"id": "t", "path": "C:/secret.wav", "provenance": {"source": "x", "licence": "CC0"}}]}
    r = client.put(f"/api/audio/studio/plans/{pid}", json={"cues": [forged]})
    assert r.status_code == 400 and "source_cue" in r.json()["detail"]
