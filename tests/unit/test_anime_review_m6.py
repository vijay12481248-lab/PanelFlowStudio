import time

import pytest
from fastapi.testclient import TestClient

from engine.acquisition.rights.models import RightsDeclaration, RightsStatus
from engine.anime.review import channels, pipeline, queue
from engine.anime.review.channels import ChannelPreset, ChannelStore
from engine.database.models import Base
from engine.database.session import engine as db_engine

OK = {"status": "COMMENTARY_REVIEW", "permission_notes": "review with commentary"}


def test_channel_store_roundtrip(tmp_path):
    st = ChannelStore(tmp_path / "c.json")
    saved = st.save(ChannelPreset(name="Otaku Daily", voice="af_heart", extra_tags=["otaku"]))
    assert saved.id == "otaku_daily" and st.get("otaku_daily").voice == "af_heart"
    st.delete("otaku_daily")
    with pytest.raises(KeyError):
        st.get("otaku_daily")


def test_voice_rate_is_bounded():
    with pytest.raises(ValueError):
        ChannelPreset(name="x", voice_rate=3.0)


def test_pipeline_rechecks_rights(tmp_path):
    spec = pipeline.ReviewJobSpec(source="x.mp4", title="t", rights=RightsDeclaration(), channel_id="c", workspace=str(tmp_path))
    with pytest.raises(ValueError, match="UNKNOWN"):
        pipeline.run_review(spec, ChannelPreset(name="c"), None, lambda *_: None, lambda: False)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from engine.api.app import create_app
    import engine.api.routers.anime_review as r

    Base.metadata.create_all(db_engine)
    monkeypatch.setattr(r, "WORKSPACE_ROOT", tmp_path / "ws")
    monkeypatch.setattr(r, "channel_store", ChannelStore(tmp_path / "c.json"))
    monkeypatch.setattr(queue, "channel_store", r.channel_store)
    r.channel_store.save(ChannelPreset(name="Main"))
    return TestClient(create_app(allow_insecure=True), base_url="http://localhost")


def test_queue_refuses_unknown_rights_and_queues_nothing(client):
    bad = [{"source": "a.mp4", "title": "A", "rights": OK, "channel_id": "main"},
           {"source": "b.mp4", "title": "B", "rights": {"status": "UNKNOWN"}, "channel_id": "main"}]
    r = client.post("/api/anime/review/queue", json=bad)
    assert r.status_code == 422 and "B" in r.json()["detail"]
    assert client.get("/api/anime/review/jobs").json() == []


def test_queue_runs_job_through_job_manager(client, monkeypatch):
    seen = {}

    def fake_run(spec, channel, provider, progress, is_cancelled):
        seen["channel"], seen["rights"] = channel.name, spec.rights.status
        progress(0.5, "half")
        return {"video": "v.mp4"}

    class P:
        async def health_check(self):
            return True

    monkeypatch.setattr(queue, "run_review", fake_run)
    from engine.llm.registry import llm_registry
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: P())
    q = client.post("/api/anime/review/queue", json=[{"source": "a.mp4", "title": "A", "rights": OK, "channel_id": "main"}])
    assert q.status_code == 200, q.text
    for _ in range(100):
        job = client.get("/api/anime/review/jobs").json()[0]
        if job["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.1)
    assert job["status"] == "SUCCEEDED", job
    assert job["output"].get("video") == "v.mp4" or job["progress"] == 1.0
    assert seen == {"channel": "Main", "rights": RightsStatus.COMMENTARY_REVIEW}
