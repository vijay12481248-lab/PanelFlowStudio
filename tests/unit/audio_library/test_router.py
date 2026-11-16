"""REST for the sound library with fake sources: make, keep effects, import, upload, edit, preview, undo, split, trash."""
import shutil

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import audio_library as mod
from engine.audio.library.store import SoundStore
from engine.audio.studio.plan import Candidate, Provenance
from engine.audio.studio.sources.base import Availability
from engine.audio.studio.sources.narration import NarrationProvider
from engine.audio.studio.sources.synth import SynthProvider

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
B = "/api/audio/library"
SR = 48000


def _tone(sec, f=300):
    return (0.3 * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)).astype(np.float32)


def _speak(text, voice, speed, provider, language, out):
    sf.write(str(out), _tone(1.5 / speed), SR)


class FakeMusic:
    name = "ace-step"

    def __init__(self, ok=True):
        self.ok = ok

    def availability(self):
        return Availability(self.ok, None if self.ok else "ACE-Step is not reachable")

    def find(self, cue, out_dir, plan, limit=1):
        if not self.ok:
            return []
        p = out_dir / "m.wav"
        sf.write(str(p), _tone(cue.t_out - cue.t_in, 110), SR)
        return [Candidate(id="m1", path=str(p), provider=self.name, provenance=Provenance(source="ace-step", licence="MIT", model="ace"))]


@pytest.fixture
def store(tmp_path):
    return SoundStore(tmp_path / "lib")


def _client(store, music_ok=True):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_store] = lambda: store
    app.dependency_overrides[mod.get_makers] = lambda: {"narration": NarrationProvider(synth=_speak, voices={"kokoro": ["af_heart"], "qwen3_tts": []}),
                                                        "music": FakeMusic(music_ok), "effects": [SynthProvider()]}
    return TestClient(app)


@pytest.fixture
def client(store):
    return _client(store)


def test_make_voice_and_music_and_the_reasons_when_they_fail(client, store):
    v = client.post(f"{B}/sounds/voice", json={"text": "Hello from the narrator.", "voice": "af_heart"}).json()
    assert v["kind"] == "voice" and v["provenance"]["source"] == "tts/kokoro" and v["duration_s"] == pytest.approx(1.5, abs=0.02) and v["info"]["text"].startswith("Hello")
    assert client.post(f"{B}/sounds/voice", json={"text": "  "}).status_code == 400
    bad = client.post(f"{B}/sounds/voice", json={"text": "Hi", "voice": "nobody"})
    assert bad.status_code == 503 and "no voice" in bad.json()["detail"]
    m = client.post(f"{B}/sounds/music", json={"description": "soft piano", "seconds": 8}).json()
    assert m["kind"] == "music" and m["duration_s"] == pytest.approx(8, abs=0.02) and m["provenance"]["licence"] == "MIT"
    down = _client(store, music_ok=False).post(f"{B}/sounds/music", json={"description": "x"})
    assert down.status_code == 503


def test_script_becomes_one_voice_sound_per_paragraph_in_order(client):
    r = client.post(f"{B}/sounds/script", json={"text": "First line here.\n\nSecond line here.\n\nThird.", "voice": "af_heart"})
    assert r.status_code == 200
    s = r.json()["sounds"]
    assert [x["info"]["line"] for x in s] == [1, 2, 3] and len({x["info"]["script"] for x in s}) == 1
    assert s[0]["name"].startswith("Line 01: First") and all(x["kind"] == "voice" for x in s)
    assert client.post(f"{B}/sounds/script", json={"text": "  "}).status_code == 400
    bad = client.post(f"{B}/sounds/script", json={"text": "One.\n\nTwo.", "voice": "nobody"})
    assert bad.status_code == 503 and "line 1 of 2" in bad.json()["detail"]


def test_effects_are_heard_first_then_kept(client):
    cands = client.post(f"{B}/effects/find", json={"kind": "whoosh", "description": "fast whoosh", "limit": 2}).json()["candidates"]
    assert len(cands) == 2 and client.get(f"{B}/effects/candidates/{cands[0]['id']}/file").status_code == 200
    s = client.post(f"{B}/effects/keep", json={"candidate_id": cands[1]["id"], "name": "Whoosh"}).json()
    assert s["kind"] == "effect" and s["name"] == "Whoosh" and s["provenance"]["licence"] == "CC0"
    assert client.post(f"{B}/effects/keep", json={"candidate_id": "../x"}).status_code == 400
    assert client.post(f"{B}/effects/keep", json={"candidate_id": "cand_00000"}).status_code == 404


def test_import_upload_record(client, tmp_path):
    f = tmp_path / "rain.wav"
    sf.write(str(f), _tone(2.0), 44100)
    s = client.post(f"{B}/sounds/import", json={"path": str(f), "kind": "effect"}).json()
    assert s["name"] == "rain" and s["provenance"] == {"source": "import", "licence": "owner", "url": str(f), "model": None, "seed": None, "author": None}
    assert client.post(f"{B}/sounds/import", json={"path": str(tmp_path / "none.wav")}).status_code == 404
    r = client.post(f"{B}/sounds/upload", files={"file": ("mic.wav", f.read_bytes(), "audio/wav")}, data={"source": "recording", "kind": "voice"}).json()
    assert r["provenance"]["source"] == "recording" and r["kind"] == "voice" and r["name"].startswith("Recording")
    junk = client.post(f"{B}/sounds/upload", files={"file": ("x.wav", b"not audio", "audio/wav")})
    assert junk.status_code == 400


def test_edit_preview_undo_split_trash_over_rest(client, store):
    sid = client.post(f"{B}/sounds/voice", json={"text": "One two three.", "voice": "af_heart"}).json()["id"]
    pv = client.post(f"{B}/sounds/{sid}/preview", json={"op": "trim", "a": 0.0, "b": 0.5})
    assert pv.status_code == 200 and pv.headers["content-type"] == "audio/wav" and store.load(sid).current == 1, "a preview changes nothing"
    s = client.post(f"{B}/sounds/{sid}/edit", json={"op": "trim", "a": 0.0, "b": 1.0}).json()
    assert s["current"] == 2 and s["duration_s"] == pytest.approx(1.0)
    assert client.post(f"{B}/sounds/{sid}/edit", json={"op": "trim"}).status_code == 400
    assert client.post(f"{B}/sounds/{sid}/edit", json={"op": "eq", "params": {"preset": "x"}}).status_code == 400
    assert client.post(f"{B}/sounds/{sid}/undo").json()["current"] == 1
    assert client.post(f"{B}/sounds/{sid}/redo").json()["current"] == 2
    assert client.post(f"{B}/sounds/{sid}/versions/1/current").json()["current"] == 1
    assert client.get(f"{B}/sounds/{sid}/file", params={"v": 2}).status_code == 200
    assert len(client.get(f"{B}/sounds/{sid}/peaks", params={"bins": 100}).json()["peaks"]) == 100
    sp = client.post(f"{B}/sounds/{sid}/split", json={"at": 0.5}).json()
    assert sp["sound"]["duration_s"] == pytest.approx(0.5) and sp["new"]["duration_s"] == pytest.approx(1.0)
    assert client.patch(f"{B}/sounds/{sid}", json={"name": "Line one", "kind": "effect"}).json()["name"] == "Line one"
    client.delete(f"{B}/sounds/{sid}")
    assert sid not in [x["id"] for x in client.get(f"{B}/sounds").json()] and sid in [x["id"] for x in client.get(f"{B}/sounds", params={"trash": True}).json()]
    client.post(f"{B}/sounds/{sid}/restore")
    assert sid in [x["id"] for x in client.get(f"{B}/sounds", params={"kind": "effect"}).json()]
    assert {o["op"] for o in client.get(f"{B}/ops").json()} >= {"trim", "pitch", "denoise", "reverb"}
    assert client.get(f"{B}/sounds/nope_1").status_code == 404
