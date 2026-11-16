"""Quick Audio page -> timeline: ready cues become library sounds (licence kept, reused when sent again) and items placed like the mixer places them."""
import shutil

import numpy as np
import pytest
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.api.routers import audio_library as mod
from engine.audio.library.store import SoundStore
from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import Candidate, Cue, PlanStore, Provenance
from engine.audio.studio.sources.base import Availability

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000


class Fake:
    name = "fake"

    def availability(self):
        return Availability(True, None)

    def find(self, cue, out_dir, plan, limit=3):
        x = np.zeros(SR, dtype=np.float32)
        x[int(0.25 * SR):int(0.3 * SR)] = 0.5   # the hit starts 0.25 s into the file
        p = out_dir / f"{cue.id}.wav"
        sf.write(str(p), x, SR)
        return [Candidate(id=f"{cue.id}_t", path=str(p), provider="fake", provenance=Provenance(source="openverse", licence="CC0", url="https://example.org/x"))]


def test_ready_cues_become_sounds_and_items_placed_like_the_mixer(tmp_path):
    plans = PlanStore(tmp_path / "plans")
    plan = plans.create("v.mp4", 24.0, 10.0)
    plan.cues = [Cue(id="hit", track="sfx", kind="impact", intent="door slam", hit_t=2.0, gain_db=-3.0, fade_out=0.2),
                 Cue(id="bed", track="music", kind="music", intent="pad", t_in=1.0, t_out=1.5),
                 Cue(id="todo", track="sfx", kind="whoosh", intent="not sourced")]
    plans.save(plan)
    eng = AudioEngine(plans, [Fake()])
    eng.source_cue(plan.id, "hit", mode="auto")
    eng.source_cue(plan.id, "bed", mode="auto")
    lib = SoundStore(tmp_path / "lib")
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_store] = lambda: lib
    app.dependency_overrides[mod.get_plans] = lambda: plans
    c = TestClient(app)
    items = c.post("/api/audio/library/from_plan", json={"plan_id": plan.id}).json()["items"]
    by = {i["cue_id"]: i for i in items}
    assert set(by) == {"hit", "bed"}, "only ready cues are sent"
    assert by["hit"]["start"] == pytest.approx(2.0 - 0.25, abs=0.006) and by["hit"]["kind"] == "effect" and by["hit"]["gain_db"] == -3.0 and by["hit"]["fade_out"] == 0.2
    assert by["bed"]["start"] == 1.0 and by["bed"]["out"] == pytest.approx(0.5) and by["bed"]["kind"] == "music"
    snd = lib.load(by["hit"]["sound"])
    assert snd.provenance.source == "openverse" and snd.provenance.url == "https://example.org/x" and snd.name == "door slam"
    again = c.post("/api/audio/library/from_plan", json={"plan_id": plan.id}).json()["items"]
    assert {i["sound"] for i in again} == {i["sound"] for i in items} and len(lib.list()) == 2, "sending again reuses the same sounds"
    empty = plans.create("w.mp4", 24.0, 5.0)
    plans.save(empty)
    assert c.post("/api/audio/library/from_plan", json={"plan_id": empty.id}).status_code == 400
    assert c.post("/api/audio/library/from_plan", json={"plan_id": "ap_nothere"}).status_code == 404
