"""Endpoints the Audio page needs: plan list, stored picture cuts, video with Range, take peaks."""
import shutil
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import audio_studio as mod
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import PlanStore
from engine.audio.studio.sources.synth import SynthProvider

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
B = "/api/audio/studio"


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "cuts.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for colour in ("black", "white", "black"):
        cmd += ["-f", "lavfi", "-i", f"color=c={colour}:s=160x120:d=2:r=24"]
    cmd += ["-f", "lavfi", "-i", "sine=frequency=300:duration=6", "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)]
    subprocess.run(cmd, check=True)
    return p


@pytest.fixture
def client(tmp_path):
    engine = AudioEngine(PlanStore(tmp_path / "store"), [SynthProvider()])
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_engine] = lambda: engine
    return TestClient(app)


def _create(client, video):
    return client.post(f"{B}/plans", json={"video_path": str(video)}).json()


def test_list_returns_plans_newest_first_with_a_summary(client, video, tmp_path):
    a = _create(client, video)
    other = tmp_path / "second.mp4"
    shutil.copy(video, other)
    b = _create(client, other)
    rows = client.get(f"{B}/plans").json()
    assert [r["id"] for r in rows] == [b["id"], a["id"]]
    assert rows[0]["video_name"] == "second.mp4" and rows[0]["cues"] == 0 and rows[0]["fps"] == 24.0 and rows[0]["duration"] == pytest.approx(6.0, abs=0.2)


def test_spot_stores_the_picture_cuts_on_the_plan(client, video):
    pid = _create(client, video)["id"]
    plan = client.post(f"{B}/plans/{pid}/spot").json()
    assert len(plan["cuts"]) == 2 and plan["cuts"][0] == pytest.approx(2.0, abs=0.05)
    assert client.get(f"{B}/plans/{pid}").json()["cuts"] == plan["cuts"]


def test_video_is_served_with_range_support(client, video):
    pid = _create(client, video)["id"]
    r = client.get(f"{B}/plans/{pid}/video", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100 and r.headers["content-range"].startswith("bytes 0-99/")
    assert client.get(f"{B}/plans/{pid}/video").status_code == 200


def test_video_404_when_the_file_is_gone(client, video):
    pid = _create(client, video)["id"]
    video.unlink()
    assert client.get(f"{B}/plans/{pid}/video").status_code == 404


def _sourced(client, video):
    pid = _create(client, video)["id"]
    client.put(f"{B}/plans/{pid}", json={"cues": [{"id": "c1", "track": "sfx", "kind": "impact", "hit_t": 1.0}]})
    plan = client.post(f"{B}/plans/{pid}/cues/c1/source", json={"mode": "ask"}).json()
    return pid, plan["cues"][0]["candidates"][0]["id"]


def test_take_peaks_for_a_candidate_are_bins_in_0_to_1_and_cached(client, video, tmp_path):
    pid, tid = _sourced(client, video)
    r = client.get(f"{B}/plans/{pid}/takes/{tid}/peaks", params={"bins": 200}).json()
    assert len(r["peaks"]) == 200 and all(0 <= p <= 1 for p in r["peaks"]) and max(r["peaks"]) > 0.3 and r["duration"] > 0.5
    assert client.get(f"{B}/plans/{pid}/takes/{tid}/peaks", params={"bins": 200}).json() == r


def test_take_peaks_rejects_unknown_and_path_like_ids(client, video):
    pid, _ = _sourced(client, video)
    assert client.get(f"{B}/plans/{pid}/takes/nope/peaks").status_code == 404
    assert client.get(f"{B}/plans/{pid}/takes/..%5Cx/peaks").status_code in (400, 404)
    assert client.get(f"{B}/plans/{pid}/takes/a.b/peaks").status_code == 400


def test_put_tracks_upserts_by_id_and_keeps_the_others(client, video):
    """Found by the Audio page: saving one fader used to delete the other four tracks."""
    pid = _create(client, video)["id"]
    got = client.put(f"{B}/plans/{pid}", json={"tracks": [{"id": "music", "gain_db": -6.0}]}).json()
    assert [t["id"] for t in got["tracks"]] == ["dialogue", "music", "sfx", "ambience", "foley"]
    assert {t["id"]: t["gain_db"] for t in got["tracks"]}["music"] == -6.0 and got["tracks"][1]["duck_under"] == "dialogue"
    assert client.put(f"{B}/plans/{pid}", json={"tracks": [{"id": "nope", "gain_db": 1}]}).status_code == 400
