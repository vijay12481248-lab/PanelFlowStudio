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


def _mp3_and_reference(tmp_path):
    import shutil
    import subprocess
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    src = _burst(tmp_path / "src.wav", at=0.5, amp=0.5, dur=0.4, total=1.5)
    mp3, ref = tmp_path / "x.mp3", tmp_path / "ref.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), str(ref)], check=True)  # the decoder the mixer uses
    return mp3, ref


def test_mp3_is_measured_the_way_the_mixer_decodes_it(tmp_path):
    mp3, ref = _mp3_and_reference(tmp_path)
    a, b = measure_take(mp3), measure_take(ref)
    assert abs(a.onset_s - b.onset_s) < 0.002 and abs(a.peak_s - b.peak_s) < 0.002 and abs(a.duration_s - b.duration_s) < 0.002
