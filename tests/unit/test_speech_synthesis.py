from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from engine.audio.synthesis import LocalSpeechSynthesizer


class Adapter:
    def __init__(self):
        self.texts = []

    def generate(self, brief, output_path):
        self.texts.append(brief.voice_params.dialogue_text)
        sf.write(str(output_path), np.zeros(2400), 24000)
        return SimpleNamespace(success=True)


def test_cache_uses_actual_script_and_invalidates_only_changed_text(tmp_path):
    adapter = Adapter()
    synth = LocalSpeechSynthesizer(adapter_factory=lambda _: adapter)
    first = synth.synthesize(tmp_path, "The gate opens.", "Narrator")
    assert synth.synthesize(tmp_path, "The gate opens.", "Narrator") == first
    other = synth.synthesize(tmp_path, "Someone arrives.", "Narrator")
    assert other != first
    assert first.exists()
    assert adapter.texts == ["The gate opens.", "Someone arrives."]


def test_failure_does_not_become_fake_voice(tmp_path):
    adapter = SimpleNamespace(generate=lambda *a, **k: SimpleNamespace(success=False, error_message="weights unavailable"))
    synth = LocalSpeechSynthesizer(adapter_factory=lambda _: adapter)
    with pytest.raises(ValueError, match="weights unavailable"):
        synth.synthesize(tmp_path, "Real text", "Narrator")
    assert not list(tmp_path.glob("*.wav"))


def test_selective_regeneration_does_not_overwrite_shared_cached_voice(tmp_path):
    adapter = Adapter()
    synth = LocalSpeechSynthesizer(adapter_factory=lambda _: adapter)
    original = synth.synthesize(tmp_path, "Same text", "Narrator")
    regenerated = synth.synthesize(tmp_path, "Same text", "Narrator", force=True)
    assert regenerated != original
    assert original.exists() and regenerated.exists()
