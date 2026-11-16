"""REST for the Audio Studio screen: voices, narration sample, add sound, script, fix, plan from a timeline, narration edits."""
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import audio_studio as mod
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import PlanStore
from engine.audio.studio.sources.narration import NarrationProvider
from engine.audio.studio.sources.synth import SynthProvider

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
B = "/api/audio/studio"
SR = 48000


def _speak(text, voice, speed, provider, language, out):
    sf.write(str(out), (0.3 * np.sin(2 * np.pi * 200 * np.arange(int(SR * 1.5 / speed)) / SR)).astype(np.float32), SR)


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=20:r=24", "-f", "lavfi", "-i", "sine=frequency=300:duration=20",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(p)], check=True)
    return p


@pytest.fixture
def client(tmp_path, video):
    engine = AudioEngine(PlanStore(tmp_path / "store"), [SynthProvider(), NarrationProvider(synth=_speak)])
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_engine] = lambda: engine

    def renderer(clips, overlays, luts, out_dir):
        return video   # a stand-in for the timeline renderer
    app.dependency_overrides[mod.get_timeline_renderer] = lambda: renderer
    return TestClient(app)


def _plan(client, video):
    return client.post(f"{B}/plans", json={"video_path": str(video)}).json()


def test_voices_lists_both_engines_and_the_tool_status(client):
    r = client.get(f"{B}/voices").json()
    assert "af_heart" in r["voices"]["kokoro"] and "qwen3_tts" in r["voices"] and set(r["providers"]) == {"kokoro", "qwen3_tts"}


def test_narration_sample_speaks_a_line_without_adding_a_cue(client, video):
    pid = _plan(client, video)["id"]
    r = client.post(f"{B}/plans/{pid}/narration/sample", json={"text": "Hello there.", "voice": "af_heart", "provider": "kokoro", "speed": 1.0}).json()
    assert r["seconds"] == pytest.approx(1.5, abs=0.1) and r["file"].startswith("samples/")
    assert client.get(f"{B}/plans/{pid}/files/{r['file']}").status_code == 200
    assert client.get(f"{B}/plans/{pid}").json()["cues"] == []
    bad = client.post(f"{B}/plans/{pid}/narration/sample", json={"text": "", "voice": "af_heart", "provider": "kokoro"})
    assert bad.status_code == 400


def test_script_makes_draft_narration_cues_and_sourcing_speaks_them(client, video):
    pid = _plan(client, video)["id"]
    plan = client.post(f"{B}/plans/{pid}/script", json={"text": "First line of the story.\n\nSecond line of the story.", "mode": "sequential", "start": 1.0,
                                                         "voice": "af_heart", "provider": "kokoro"}).json()
    ids = [c["id"] for c in plan["cues"]]
    assert ids == ["vo_01", "vo_02"] and all(c["status"] == "draft" and c["kind"] == "narration" for c in plan["cues"])
    done = client.post(f"{B}/plans/{pid}/cues/vo_01/source", json={}).json()
    assert done["cues"][0]["status"] == "ready" and done["cues"][0]["takes"][0]["provenance"]["source"] == "tts/kokoro"


def test_editing_the_words_of_a_spoken_line_makes_it_draft_again(client, video):
    pid = _plan(client, video)["id"]
    client.post(f"{B}/plans/{pid}/script", json={"text": "Original words here.", "voice": "af_heart", "provider": "kokoro"})
    client.post(f"{B}/plans/{pid}/cues/vo_01/source", json={})
    same = client.put(f"{B}/plans/{pid}", json={"cues": [{"id": "vo_01", "gain_db": -2.0}]}).json()["cues"][0]
    assert same["status"] == "ready" and same["chosen_take"], "a gain change keeps the speech"
    changed = client.put(f"{B}/plans/{pid}", json={"cues": [{"id": "vo_01", "text": "New words instead."}]}).json()["cues"][0]
    assert changed["status"] == "draft" and changed["chosen_take"] is None, "new words need new speech"


def test_add_sound_creates_a_cue_at_a_time_and_sources_it(client, video):
    pid = _plan(client, video)["id"]
    r = client.post(f"{B}/plans/{pid}/add_sound", json={"intent": "a short click", "kind": "click", "hit_t": 2.0, "mode": "ask"}).json()
    c = r["cues"][0]
    assert c["id"] == "snd_01" and c["status"] == "needs_pick" and len(c["candidates"]) >= 1 and abs(c["hit_t"] - 2.0) < 1 / 24 + 1e-6 and c["track"] == "sfx"


def test_original_audio_switch_and_fix_endpoint(client, video):
    pid = _plan(client, video)["id"]
    got = client.put(f"{B}/plans/{pid}", json={"keep_original_audio": False}).json()
    assert got["keep_original_audio"] is False
    r = client.post(f"{B}/plans/{pid}/fix").json()
    assert r["fixed"] == [] and r["remaining"] == []


def test_a_plan_from_the_video_studio_timeline_keeps_its_cuts_and_job(client, video):
    r = client.post(f"{B}/plans/from_timeline", json={"clips": [{"src": "a.mp4"}], "overlays": [], "luts": {}, "cuts": [4.0, 9.01, 99.0, -1.0], "job_id": "job123"}).json()
    assert r["source"] == {"kind": "timeline", "job_id": "job123"} and r["fps"] == 24.0
    assert r["cuts"] == [4.0, pytest.approx(9.0, abs=1 / 24)], "cuts are snapped to frames and the ones outside the picture are dropped"
    assert client.post(f"{B}/plans/from_timeline", json={"clips": [], "overlays": [], "luts": {}, "cuts": [], "job_id": "j"}).status_code == 400
