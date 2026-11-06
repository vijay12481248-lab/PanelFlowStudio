import asyncio
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine.anime.review.channels import ChannelPreset, ChannelStore
from engine.database.models import Base
from engine.database.session import engine as db_engine
from engine.original import episode, queue
from engine.original import story as st
from engine.original.series import Episode, SeriesStore, episode_summary, publish_times
from tests.unit.test_original_story import BED, ScriptedLLM, full_bible


def test_series_store_roundtrip_ids_and_path_safety(tmp_path):
    store = SeriesStore(tmp_path)
    s = store.create("Mira's Moon Tales", "bedtime", full_bible(), "ch")
    s2 = store.create("Mira's Moon Tales", "bedtime", full_bible())
    assert s.id == "mira_s_moon_tales" and s2.id == "mira_s_moon_tales_2"
    assert store.get(s.id).bible.characters[0].name == "Mira" and len(store.list()) == 2
    assert store.dir("../../etc") == tmp_path / "etc"  # a caller-supplied id can never leave the root


def test_episode_numbers_and_continuity_summary(tmp_path):
    store = SeriesStore(tmp_path)
    s = store.create("S", "bedtime", full_bible())
    assert s.next_number() == 1
    store.update_episode(s.id, Episode(number=1, title="One", summary="Mira found the moon."))
    store.update_episode(s.id, Episode(number=2, title="Two", summary="Pip learned to hoot."))
    s = store.get(s.id)
    assert s.next_number() == 3 and "Episode 1 (One): Mira found the moon." in s.previous_summary() and "Episode 2" in s.previous_summary()


def test_portraits_are_shared_between_episodes(tmp_path):
    store = SeriesStore(tmp_path)
    s = store.create("S", "bedtime", full_bible())
    ep1, ep2 = store.episode_dir(s.id, 1), store.episode_dir(s.id, 2)
    (ep1 / "sheets").mkdir(parents=True)
    Image.new("RGB", (8, 8), "red").save(ep1 / "sheets" / "mira.png")
    assert store.push_sheets(s.id, ep1) == 1 and store.push_sheets(s.id, ep1) == 0
    assert store.pull_sheets(s.id, ep2) == 1 and (ep2 / "sheets" / "mira.png").exists()


def test_publish_times_one_per_day():
    t = publish_times(3, date(2026, 11, 3))
    assert t == ["2026-11-03T18:00:00", "2026-11-04T18:00:00", "2026-11-05T18:00:00"]


def test_next_episode_reuses_bible_and_gets_previous_summaries():
    llm = ScriptedLLM()
    bible = full_bible()
    s = asyncio.run(st.generate_story("bedtime", llm, series_bible=bible, previous="Episode 1 (One): Mira found the moon."))
    assert [c.id for c in s.bible.characters] == ["mira", "pip"] and s.bible.rules == bible.rules  # cast untouched
    assert "_Bible" not in llm.calls  # no new cast was invented
    assert any("Earlier episodes: Episode 1" in p for p in llm.prompts) and any("next episode of the bedtime series" in p for p in llm.prompts)


def test_episode_summary_is_short_and_ends_with_the_last_scene():
    s = asyncio.run(st.generate_story("bedtime", ScriptedLLM()))
    assert "It ends:" in episode_summary(s) and len(episode_summary(s)) <= 600


def test_wait_for_previous_blocks_until_done_and_honours_cancel(tmp_path):
    store = SeriesStore(tmp_path)
    s = store.create("S", "bedtime", full_bible())
    store.update_episode(s.id, Episode(number=1, status="running"))
    with pytest.raises(RuntimeError):
        episode.wait_for_previous(store, s.id, 2, lambda: True)
    with pytest.raises(TimeoutError):
        episode.wait_for_previous(store, s.id, 2, lambda: False, poll=0.01, limit=0.05)
    store.update_episode(s.id, Episode(number=1, status="done"))
    episode.wait_for_previous(store, s.id, 2, lambda: False)  # returns at once
    episode.wait_for_previous(store, s.id, 1, lambda: False)  # the first episode has nothing to wait for


@pytest.fixture
def client(tmp_path, monkeypatch):
    from engine.api.app import create_app
    import engine.api.routers.original as r

    Base.metadata.create_all(db_engine)
    monkeypatch.setattr(r, "SERIES_ROOT", tmp_path / "series")
    chans = ChannelStore(tmp_path / "c.json")
    chans.save(ChannelPreset(name="Main"))
    monkeypatch.setattr(queue, "channel_store", chans)
    return TestClient(create_app(allow_insecure=True), base_url="http://localhost"), r, tmp_path


def test_queue_runs_episodes_in_order_through_job_manager(client, monkeypatch):
    c, r, tmp = client
    store = SeriesStore(tmp / "series")
    s = store.create("Moon Tales", "bedtime", full_bible(), "main")
    order = []

    def fake_run(st_, sid, number, channel, provider, runner_factory, progress, is_cancelled, scenes, check, refine=False):
        order.append(number)
        progress(0.5, "half")
        st_.update_episode(sid, Episode(number=number, title=f"T{number}", summary=f"S{number}", status="done"))
        return {"episode": number, "video": f"v{number}.mp4"}

    class P:
        async def health_check(self):
            return True

    monkeypatch.setattr(queue, "run_episode", fake_run)
    from engine.llm.registry import llm_registry
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: P())
    q = c.post(f"/api/original/series/{s.id}/episodes", json={"count": 2, "start_date": "2026-11-03", "scenes": 3})
    assert q.status_code == 200, q.text
    assert [e["publish_at"] for e in q.json()] == ["2026-11-03T18:00:00", "2026-11-04T18:00:00"]
    for _ in range(100):
        jobs = c.get("/api/original/jobs").json()
        if len(jobs) == 2 and all(j["status"] in ("SUCCEEDED", "FAILED") for j in jobs):
            break
        time.sleep(0.1)
    assert sorted(order) == [1, 2] and all(j["status"] == "SUCCEEDED" for j in jobs), jobs
    assert [e.number for e in store.get(s.id).episodes] == [1, 2]


def test_unknown_series_and_channel_are_rejected(client):
    c, r, tmp = client
    assert c.post("/api/original/series/nope/episodes", json={"count": 1}).status_code == 404
    assert c.get("/api/original/series/nope").status_code == 404
    bad = c.post("/api/original/series", json={"name": "X Y", "genre": "bedtime", "channel_id": "missing"})
    assert bad.status_code == 422 and "missing" in bad.json()["detail"]


def test_concurrent_episode_updates_neither_crash_nor_lose_records(tmp_path):
    import threading

    store = SeriesStore(tmp_path)
    s = store.create("S", "bedtime", full_bible())
    errors = []

    def work(n):
        try:
            for _ in range(20):
                store.update_episode(s.id, Episode(number=n, title=f"T{n}"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(1, 6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [] and [e.number for e in store.get(s.id).episodes] == [1, 2, 3, 4, 5]


def test_refine_reaches_the_episode_run_only_when_asked_and_never_without_the_review(client, monkeypatch):
    c, r, tmp = client
    store = SeriesStore(tmp / "series")
    s = store.create("Moon Tales", "bedtime", full_bible(), "main")
    seen = []

    def fake_run(st_, sid, number, channel, provider, runner_factory, progress, is_cancelled, scenes, check, refine=False):
        seen.append((number, check, refine))
        st_.update_episode(sid, Episode(number=number, title="T", summary="S", status="done"))
        return {"episode": number}

    class P:
        async def health_check(self):
            return True

    monkeypatch.setattr(queue, "run_episode", fake_run)
    from engine.llm.registry import llm_registry
    monkeypatch.setattr(llm_registry, "get_ollama_provider", lambda: P())
    # refine without the picture review is refused before anything is queued
    before = len(c.get("/api/original/jobs").json())
    bad = c.post(f"/api/original/series/{s.id}/episodes", json={"count": 1, "check": False, "refine": True})
    assert bad.status_code == 422 and "refine needs the picture review" in bad.json()["detail"]
    assert len(c.get("/api/original/jobs").json()) == before
    assert c.post(f"/api/original/series/{s.id}/episodes", json={"count": 1}).status_code == 200  # default: off
    assert c.post(f"/api/original/series/{s.id}/episodes", json={"count": 1, "refine": True}).status_code == 200
    for _ in range(100):
        jobs = c.get("/api/original/jobs").json()
        if len(jobs) == before + 2 and all(j["status"] in ("SUCCEEDED", "FAILED") for j in jobs):
            break
        time.sleep(0.1)
    assert sorted(seen) == [(1, True, False), (2, True, True)], (seen, jobs)


def test_story_art_route_refuses_refine_without_the_review(client):
    c, r, tmp = client
    res = c.post("/api/original/story/whatever/art?refine=true&check=false")
    assert res.status_code == 422 and "refine needs the picture review" in res.json()["detail"]


def test_run_episode_hands_refine_to_generate_art_only_when_asked():
    import inspect

    assert inspect.signature(episode.run_episode).parameters["refine"].default is False
    # None (not False) keeps PANELFLOW_REFINE_LOOP honoured when the caller did not ask
    assert "refine=True if refine else None" in inspect.getsource(episode.run_episode)
