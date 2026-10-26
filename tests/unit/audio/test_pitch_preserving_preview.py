import io
import numpy as np
import pytest
import soundfile as sf
from engine.audio.preview import tempo_preview


@pytest.mark.parametrize('tempo', [0.5, 1.5, 3])
def test_scheduled_preview_changes_duration_without_changing_voice_pitch(tempo):
    sr = 24000
    tone = 0.3 * np.sin(2 * np.pi * 440 * np.arange(sr * 2) / sr)
    raw = io.BytesIO(); sf.write(raw, tone, sr, format='WAV')
    pcm, rate = sf.read(io.BytesIO(tempo_preview(raw.getvalue(), tempo)))
    assert len(pcm) / rate == pytest.approx(2 / tempo, abs=1 / sr)
    spectrum = abs(np.fft.rfft(pcm[:int(rate * min(0.5, 1 / tempo))]))
    peak = np.argmax(spectrum) * rate / ((len(spectrum) - 1) * 2)
    assert peak == pytest.approx(440, abs=5)


@pytest.mark.parametrize('tempo', [0, -1, float('nan'), float('inf')])
def test_preview_rejects_invalid_tempo(tempo):
    with pytest.raises(ValueError): tempo_preview(b'', tempo)
