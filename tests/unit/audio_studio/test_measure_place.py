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


def _two_lobes(path, sr=SR, a1=0.5, a2=0.499, lead=0.0):
    t = np.arange(int(sr * 1.5)) / sr
    env = a1 * np.exp(-((t - 0.45) / 0.08) ** 2) + a2 * np.exp(-((t - 0.85) / 0.08) ** 2)
    x = (env * np.sin(2 * np.pi * 700 * t)).astype(np.float32)
    x = np.concatenate([np.zeros(int(sr * lead), dtype=np.float32), x])
    sf.write(str(path), x, sr)
    return path


def test_peak_is_stable_when_two_lobes_are_nearly_equal(tmp_path):
    a = measure_take(_two_lobes(tmp_path / "a.wav"))
    b = measure_take(_two_lobes(tmp_path / "b.wav", lead=0.003))
    assert abs((b.peak_s - a.peak_s) - 0.003) < 0.002  # a tiny shift must move the peak by the same tiny amount
    assert 0.5 < a.peak_s < 0.8  # between the lobes, not on one of them


def test_measurement_is_made_at_the_mixers_48k(tmp_path):
    import shutil
    import subprocess
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    src = _two_lobes(tmp_path / "s44.wav", sr=44100)
    ref = tmp_path / "s48.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "48000", str(ref)], check=True)  # what the mixer does
    a, b = measure_take(src), measure_take(ref)
    assert abs(a.peak_s - b.peak_s) < 0.002 and abs(a.onset_s - b.onset_s) < 0.002
