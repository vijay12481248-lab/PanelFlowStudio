import numpy as np
import soundfile as sf
import pytest

from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, PlanStore
from engine.audio.studio.sources.synth import SYNTH_KINDS, SynthProvider, render


@pytest.mark.parametrize("kind", sorted(SYNTH_KINDS))
def test_every_kind_renders_and_is_deterministic(kind):
    a, b, c = render(kind, 1.0, 7), render(kind, 1.0, 7), render(kind, 1.0, 8)
    assert a.dtype == np.float32 and len(a) == 48000 and np.abs(a).max() <= 0.9 + 1e-6
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)  # candidates must differ per seed


def _wav(tmp_path, kind, dur):
    p = tmp_path / f"{kind}.wav"
    sf.write(str(p), render(kind, dur, 1), 48000)
    return p


def test_impact_has_fast_attack(tmp_path):
    m = measure_take(_wav(tmp_path, "impact", 1.2))
    assert m.onset_s <= 0.01 and m.peak_db > -3


def test_whoosh_peak_is_late(tmp_path):
    m = measure_take(_wav(tmp_path, "whoosh", 1.0))
    assert m.peak_s > 0.4 * m.duration_s


def test_unknown_kind_returns_empty(tmp_path):
    plan = PlanStore(tmp_path).create("v.mp4", 24.0, 5.0)
    cue = Cue(id="c1", track="sfx", kind="dragon_roar")
    assert SynthProvider().find(cue, tmp_path, plan) == []


def test_find_writes_candidates_with_provenance(tmp_path):
    plan = PlanStore(tmp_path).create("v.mp4", 24.0, 5.0)
    cue = Cue(id="c1", track="sfx", kind="impact", hit_t=1.0)
    out = SynthProvider().find(cue, tmp_path, plan, limit=2)
    assert len(out) == 2 and all((tmp_path / c.path).is_file() or __import__("pathlib").Path(c.path).is_file() for c in out)
    assert out[0].provenance.licence == "CC0" and out[0].provenance.source == "synth"
    assert out[0].provenance.seed != out[1].provenance.seed


def test_availability_ok():
    assert SynthProvider().availability().ok is True
