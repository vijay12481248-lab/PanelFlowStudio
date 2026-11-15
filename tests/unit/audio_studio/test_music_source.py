from types import SimpleNamespace

from engine.audio.studio.plan import Cue, PlanStore
from engine.audio.studio.sources.music import MusicProvider


class Slot:
    def __init__(self, ok=True):
        self.ok, self.acquired, self.released = ok, [], []

    def acquire(self, job_id):
        self.acquired.append(job_id)
        return self.ok

    def release(self, job_id):
        self.released.append(job_id)


def _gen(calls):
    def gen(**kw):
        calls.append(kw)
        i = kw["take_index"]
        return SimpleNamespace(take_id=f"t{i}", audio_file_path=str(kw["workspace_music_dir"] / f"t{i}.wav"),
                               model_id="acestep-v15-turbo", seed=100 + i)
    return gen


def _ctx(tmp_path, kind="music", t_out=12.0):
    plan = PlanStore(tmp_path).create("v.mp4", 24.0, 20.0)
    return plan, Cue(id="m1", track="music", kind=kind, intent="calm piano underscore", t_in=2.0, t_out=t_out)


def test_music_cue_calls_generator_with_cue_length(tmp_path):
    plan, cue = _ctx(tmp_path)
    calls, slot = [], Slot()
    out = MusicProvider(generator=_gen(calls), slot=slot, health=lambda: {"available": True}).find(cue, tmp_path, plan, limit=2)
    assert [c.id for c in out] == ["t1", "t2"]
    assert calls[0]["audio_duration"] == 10.0 and calls[0]["prompt"] == "calm piano underscore"
    assert out[0].provenance.source == "ace-step" and out[0].provenance.licence == "MIT" and out[0].provenance.seed == 101


def test_open_ended_cue_runs_to_video_end(tmp_path):
    plan, cue = _ctx(tmp_path, t_out=None)
    calls = []
    MusicProvider(generator=_gen(calls), slot=Slot(), health=lambda: {"available": True}).find(cue, tmp_path, plan, limit=1)
    assert calls[0]["audio_duration"] == 18.0


def test_non_music_cue_returns_empty(tmp_path):
    plan, cue = _ctx(tmp_path, kind="whoosh")
    assert MusicProvider(generator=_gen([]), slot=Slot(), health=lambda: {"available": True}).find(cue, tmp_path, plan) == []


def test_gpu_slot_released_on_error(tmp_path):
    plan, cue = _ctx(tmp_path)
    slot = Slot()

    def boom(**kw):
        raise RuntimeError("ACE-Step died")
    p = MusicProvider(generator=boom, slot=slot, health=lambda: {"available": True})
    assert p.find(cue, tmp_path, plan) == []
    assert slot.released == slot.acquired and len(slot.released) == 1
    assert "ACE-Step died" in p.availability().reason


def test_health_down_reports_reason(tmp_path):
    plan, cue = _ctx(tmp_path)
    p = MusicProvider(generator=_gen([]), slot=Slot(), health=lambda: {"available": False, "error": "connection refused"})
    assert p.find(cue, tmp_path, plan) == []
    a = p.availability()
    assert a.ok is False and "connection refused" in a.reason


def test_gpu_busy_returns_empty_with_reason(tmp_path):
    plan, cue = _ctx(tmp_path)
    p = MusicProvider(generator=_gen([]), slot=Slot(ok=False), health=lambda: {"available": True})
    assert p.find(cue, tmp_path, plan) == []
    assert "GPU busy" in p.availability().reason
