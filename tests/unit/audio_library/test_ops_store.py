"""Sound edit operations measured on real tones, and the store's versions / undo / redo / trash / split / join."""
import shutil

import numpy as np
import pytest
import soundfile as sf

from engine.audio.library import ops
from engine.audio.library.store import SoundStore, decode
from engine.audio.studio.plan import Provenance

SR = 48000
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
PROV = Provenance(source="test", licence="CC0")


def tone(sec=2.0, f=440.0, amp=0.3):
    return (amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)).astype(np.float32)[:, None]


def rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def freq(x):
    m = x[:, 0] * np.hanning(len(x))
    spec = np.abs(np.fft.rfft(m))
    return float(np.fft.rfftfreq(len(m), 1 / SR)[spec.argmax()])


def max_step(x):
    return float(np.abs(np.diff(x[:, 0])).max())


def test_params_are_checked_clamped_and_unknown_ones_refused():
    assert ops.clean_params("gain", {"db": 99}) == {"db": 24.0}
    assert ops.clean_params("loop", {"times": 3.4}) == {"times": 3}
    with pytest.raises(ValueError):
        ops.clean_params("eq", {"preset": "loud; rm -rf"})
    with pytest.raises(ValueError):
        ops.clean_params("gain", {"db": "nan"})
    with pytest.raises(ValueError):
        ops.clean_params("gain", {"evil": 1})
    with pytest.raises(ValueError):
        ops.clean_params("nope", {})
    cat = {c["op"]: c for c in ops.ops_catalog()}
    assert cat["pitch"]["params"]["semitones"] == {"min": -12.0, "max": 12.0, "default": 2.0} and cat["eq"]["params"]["preset"]["choices"][0] == "custom"


def test_cutting_ops_change_the_length_exactly_and_join_without_clicks():
    x = tone(2.0)
    assert len(ops.apply("trim", x, a=0.5, b=1.25)) == int(0.75 * SR)
    d = ops.apply("delete", x, a=0.5, b=1.0)
    assert abs(len(d) / SR - 1.5) < 0.011 and max_step(d) < 0.05, "the join is cross-faded"
    s = ops.apply("silence", x, a=0.5, b=1.0)
    assert len(s) == len(x) and rms(s[int(0.52 * SR):int(0.98 * SR)]) == 0 and max_step(s) < 0.05
    i = ops.apply("insert_silence", x, params={"at": 1.0, "seconds": 0.5})
    assert abs(len(i) / SR - 2.5) < 0.011
    assert abs(len(ops.apply("loop", tone(1.0), params={"times": 3})) / SR - 3.0) < 0.03
    with pytest.raises(ValueError, match="select"):
        ops.apply("trim", x)


def test_volume_ops():
    x = tone(2.0)
    assert rms(ops.apply("gain", x, params={"db": -6})) == pytest.approx(rms(x) / 2, rel=0.01)
    g = ops.apply("gain", x, params={"db": 6}, a=0.5, b=1.0)
    assert len(g) == len(x) and rms(g[int(0.6 * SR):int(0.9 * SR)]) == pytest.approx(rms(x) * 2, rel=0.02) and rms(g[:int(0.4 * SR)]) == pytest.approx(rms(x), rel=0.01)
    p = ops.apply("normalize", x, params={"mode": "peak", "target": -1.0})
    assert float(np.abs(p).max()) == pytest.approx(10 ** (-1 / 20), rel=1e-3)
    f = ops.apply("fade_in", x, params={"seconds": 1.0})
    assert rms(f[:int(0.1 * SR)]) < rms(x) * 0.1 and rms(f[int(1.5 * SR):]) == pytest.approx(rms(x), rel=0.01)
    o = ops.apply("fade_out", x, params={"seconds": 0.5})
    assert float(np.abs(o[-50:]).max()) < 0.01
    r = ops.apply("reverse", np.linspace(0, 1, SR, dtype=np.float32)[:, None])
    assert r[0, 0] == pytest.approx(1.0) and r[-1, 0] == pytest.approx(0.0)


@needs_ffmpeg
def test_speed_and_pitch_measured():
    x = tone(2.0, 440)
    fast = ops.apply("speed", x, params={"factor": 2.0})
    assert abs(len(fast) / SR - 1.0) < 0.05 and abs(freq(fast) - 440) < 10, "speed keeps the pitch"
    up = ops.apply("pitch", x, params={"semitones": 12})
    assert abs(len(up) / SR - 2.0) < 0.05 and abs(freq(up[SR // 4: -SR // 4]) - 880) < 15, "an octave up keeps the length"


@needs_ffmpeg
def test_filters_do_what_they_say():
    x = tone(2.0, 60, 0.3) + tone(2.0, 1000, 0.3)
    cut = ops.apply("eq", x, params={"preset": "bass_cut"})
    lo = lambda y: np.abs(np.fft.rfft(y[:, 0]))[int(60 * len(y) / SR)]
    assert lo(cut) < lo(x) * 0.5
    hum = ops.apply("hum", tone(2.0, 50, 0.3) + tone(2.0, 1000, 0.1), params={"mains": "50"})
    assert abs(freq(hum[SR // 2:]) - 1000) < 5, "the 50 Hz hum is no longer the loudest thing"
    rng = np.random.default_rng(0)
    noisy = tone(2.0, 440, 0.3) + (0.03 * rng.standard_normal((2 * SR, 1))).astype(np.float32)
    clean = ops.apply("denoise", noisy, params={"amount": "strong"})
    ref = tone(2.0, 440, 0.3)[SR // 2:]
    gap = lambda y: rms(y[SR // 2:] - ref * (rms(y[SR // 2:]) / rms(ref)))
    assert len(clean) == len(noisy) and gap(clean) < gap(noisy) * 0.7
    loud = ops.apply("normalize", x * 0.1, params={"mode": "loudness", "target": -16})
    assert rms(loud) > rms(x * 0.1) * 2
    rev = ops.apply("reverb", tone(0.5), params={"room": "hall"})
    assert len(rev) > len(tone(0.5)) and rms(rev[int(0.6 * SR):int(0.9 * SR)]) > 0.005, "the reverb leaves a tail"
    gaps = np.concatenate([tone(0.5), np.zeros((2 * SR, 1), np.float32), tone(0.5)])
    assert len(ops.apply("remove_silence", gaps, params={"longer_than": 0.5, "keep": 0.25})) / SR < 1.8
    e = ops.apply("echo", x, a=0.5, b=1.5)
    assert len(e) == len(x)


@needs_ffmpeg
def test_store_versions_undo_redo_and_the_redo_branch(tmp_path):
    st = SoundStore(tmp_path)
    s = st.create(tone(2.0), "Beep", "effect", PROV)
    assert s.current == 1 and s.version().duration_s == 2.0
    s = st.edit(s.id, "trim", a=0.0, b=1.0)
    s = st.edit(s.id, "gain", {"db": -6})
    assert s.current == 3 and [v.op for v in s.versions] == ["created", "trim", "gain"] and s.duration_s == 1.0
    s = st.undo(s.id)
    s = st.undo(s.id)
    assert s.current == 1 and st.read(s.id).shape[0] == 2 * SR
    with pytest.raises(ValueError):
        st.undo(s.id)
    s = st.redo(s.id)
    assert s.current == 2
    s = st.edit(s.id, "reverse")
    assert [v.n for v in s.versions] == [1, 2, 3] and s.versions[-1].op == "reverse" and not (st.dir(s.id) / "v004.wav").exists()
    with pytest.raises(ValueError):
        st.redo(s.id)
    assert st.set_current(s.id, 1).current == 1
    pk = st.peaks(s.id, bins=100)
    assert len(pk["peaks"]) == 100 and max(pk["peaks"]) == pytest.approx(0.3, abs=0.01)


@needs_ffmpeg
def test_store_list_trash_split_join_and_import(tmp_path):
    st = SoundStore(tmp_path / "lib")
    a = st.create(tone(2.0), "Voice line", "voice", PROV)
    b = st.create(tone(1.0, 220), "Pad", "music", PROV)
    assert [s.name for s in st.list()] == ["Pad", "Voice line"] or {s.name for s in st.list()} == {"Pad", "Voice line"}
    assert [s.id for s in st.list(kind="music")] == [b.id] and [s.id for s in st.list(q="voice")] == [a.id]
    st.trash(b.id)
    assert [s.id for s in st.list()] == [a.id] and [s.id for s in st.list(trash=True)] == [b.id]
    st.trash(b.id, False)
    head, tail = st.split(a.id, 0.5)
    assert head.duration_s == 0.5 and tail.duration_s == 1.5 and tail.kind == "voice"
    j = st.join(head.id, b.id)
    assert abs(j.duration_s - 1.5) < 0.02
    st.trash(tail.id)
    assert st.empty_trash() == [tail.id] and not st.dir(tail.id).exists()
    mp3 = tmp_path / "in.wav"
    sf.write(str(mp3), np.hstack([tone(1.0), tone(1.0)]), 44100)
    imp = st.create_from_file(mp3, "Imported", "effect", Provenance(source="import", licence="owner"))
    assert imp.versions[0].channels == 2 and abs(imp.duration_s - SR / 44100) < 0.01, "imports are resampled to 48 kHz"
    with pytest.raises(FileNotFoundError):
        decode(tmp_path / "missing.wav")
    with pytest.raises(ValueError):
        st.load("../etc")


@needs_ffmpeg
def test_noise_reduction_lowers_the_noise_floor_and_keeps_the_sound_in_sync():
    rng = np.random.default_rng(0)
    speechy = tone(3.0, 300) * np.repeat((np.arange(30) % 3 == 0).astype(np.float32), SR // 10)[:, None]   # bursts with gaps, like speech
    noisy = speechy + (0.02 * rng.standard_normal(speechy.shape)).astype(np.float32)
    y = ops.apply("denoise", noisy, params={"amount": "strong"})
    assert len(y) == len(noisy) and ops.noise_floor_db(y) < ops.noise_floor_db(noisy) - 20
    xc = np.correlate(y[SR:2 * SR, 0], speechy[SR - 2000:2 * SR + 2000, 0], "valid")
    assert abs(int(np.argmax(xc)) - 2000) <= 2, "no delay"
