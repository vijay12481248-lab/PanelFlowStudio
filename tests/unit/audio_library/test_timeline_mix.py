"""Timeline sounds mixed onto a rendered picture: placement, trim, ducking under the voice, loudness, bad items refused."""
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from engine.audio.library.store import SoundStore
from engine.audio.library.timeline_mix import check_items, mix_onto_video
from engine.audio.studio.plan import Provenance

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
P = Provenance(source="test", licence="CC0")


def tone(sec, f, amp=0.3):
    return (amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)).astype(np.float32)[:, None]


def band(x, f, a, b):
    seg = x[int(a * SR):int(b * SR), 0]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    k = int(round(f * len(seg) / SR))
    return float(spec[k - 3:k + 4].max())


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "pic.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x120:d=8:r=24", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


def _audio(video, tmp_path):
    w = tmp_path / "out.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_f32le", str(w)], check=True)
    x, _ = sf.read(str(w), dtype="float32", always_2d=True)
    return x


def test_voice_music_effect_are_placed_trimmed_and_music_ducks_under_voice(tmp_path, video):
    st = SoundStore(tmp_path / "lib")
    voice = st.create(tone(2.0, 300), "line", "voice", P)
    music = st.create(tone(8.0, 1000, 0.2), "bed", "music", P)
    fx = st.create(tone(3.0, 2500), "hit", "effect", P)
    loud = mix_onto_video(video, [
        {"sound": music.id, "track": "music", "start": 0.0},
        {"sound": voice.id, "track": "voice", "start": 4.0},
        {"sound": fx.id, "track": "effect", "start": 1.0, "in": 1.0, "out": 1.5},   # half a second from the middle of the sound
    ], st)
    x = _audio(video, tmp_path)
    assert abs(len(x) / SR - 8.0) < 0.1
    assert band(x, 300, 4.2, 5.8) > 10 * band(x, 300, 1.5, 3.5), "the voice is at 4-6 s"
    assert band(x, 2500, 1.05, 1.45) > 10 * band(x, 2500, 2.0, 3.0), "the effect plays 1.0-1.5 s only"
    assert band(x, 1000, 4.3, 5.7) < band(x, 1000, 2.0, 3.4) * 0.5, "music ducks while the voice speaks"
    assert abs(loud["integrated_lufs"] + 14) < 1.5


def test_no_items_leaves_the_video_alone_and_bad_items_are_refused(tmp_path, video):
    st = SoundStore(tmp_path / "lib")
    before = video.read_bytes()
    assert mix_onto_video(video, [], st) == {} and video.read_bytes() == before
    s = st.create(tone(1.0, 440), "x", "effect", P)
    with pytest.raises(ValueError, match="not in the library"):
        check_items([{"sound": "snd_missing00", "track": "voice"}], st)
    with pytest.raises(ValueError, match="track"):
        check_items([{"sound": s.id, "track": "drums"}], st)
    with pytest.raises(ValueError, match="empty"):
        check_items([{"sound": s.id, "in": 0.5, "out": 0.5}], st)
    with pytest.raises(ValueError):
        check_items([{"sound": "../../etc"}], st)
    assert check_items([{"sound": s.id, "gain_db": 99, "start": -3}], st)[0]["gain_db"] == 24.0
