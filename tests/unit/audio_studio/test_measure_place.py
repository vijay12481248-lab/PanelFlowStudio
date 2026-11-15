import numpy as np
import pytest
import soundfile as sf

from engine.audio.studio.measure import measure_take
from engine.audio.studio.place import placement_for

SR = 48000


def _burst(path, at=0.5, amp=0.5, dur=0.05, total=1.0):
    x = np.zeros(int(SR * total), dtype=np.float32)
    n = int(SR * dur)
    i = int(SR * at)
    x[i:i + n] = amp * np.sin(2 * np.pi * 1000 * np.arange(n) / SR)
    sf.write(str(path), x, SR)
    return path


def test_onset_within_5ms(tmp_path):
    m = measure_take(_burst(tmp_path / "a.wav"))
    assert abs(m.onset_s - 0.5) < 0.005
    assert 0.5 <= m.peak_s <= 0.56
    assert m.duration_s == pytest.approx(1.0, abs=0.01)
    assert m.peak_db == pytest.approx(-6.0, abs=0.3)


def test_clipping_counted(tmp_path):
    assert measure_take(_burst(tmp_path / "c.wav", amp=1.0)).clipped_samples > 0
    assert measure_take(_burst(tmp_path / "d.wav", amp=0.5)).clipped_samples == 0


def test_silent_file_is_reported(tmp_path):
    sf.write(str(tmp_path / "s.wav"), np.zeros(SR, dtype=np.float32), SR)
    m = measure_take(tmp_path / "s.wav")
    assert m.peak_db <= -90 and m.onset_s == 0.0


def test_placement_positive():
    p = placement_for(hit_t=2.0, anchor_s=0.3)
    assert p.start_s == pytest.approx(1.7) and p.trim_s == 0.0


def test_placement_negative_trims():
    p = placement_for(hit_t=0.1, anchor_s=0.3)
    assert p.start_s == 0.0 and p.trim_s == pytest.approx(0.2)
