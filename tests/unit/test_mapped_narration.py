"""Measured narration must follow explicit semantic mappings, never panel counts."""
import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from engine.audio.service import AudioService


class SampleSynthesizer:
    def __init__(self, lengths=(137, 863), rates=(1000, 1000)):
        self.lengths = lengths
        self.rates = rates
        self.calls = []

    def synthesize(self, **kwargs):
        index = len(self.calls)
        self.calls.append(kwargs)
        path = Path(kwargs['directory']) / f'beat-{index}.wav'
        sf.write(path, np.full((self.lengths[index], 1), (index + 1) * 1024, dtype=np.int16), self.rates[index], subtype='PCM_16')
        return path


def service_with(synth):
    service = AudioService.__new__(AudioService)
    service.synthesizer = synth
    return service


def beats():
    return [
        {'id': 'reaction', 'text': 'He gasps.', 'panel_ids': ['a']},
        {'id': 'reveal', 'text': 'The gates open slowly.', 'panel_ids': ['b', 'c']},
    ]


def test_mapped_speech_cues_use_actual_pcm_lengths_and_keep_explicit_panels(tmp_path):
    synth = SampleSynthesizer()
    result = service_with(synth).synthesize_mapped_narration(
        tmp_path, 'segment/../../unsafe', beats(), {'a', 'b', 'c'},
        voice='Marcus', emotion='Suspenseful', intensity=0.0, speed=0.9, text_revision=4, force=True,
    )
    assert result['alignment_method'] == 'measured_beats'
    assert result['speech_cues'] == [
        {**beats()[0], 'start_sec': 0.0, 'end_sec': 0.137},
        {**beats()[1], 'start_sec': 0.137, 'end_sec': 1.0},
    ]
    assert result['measured_duration_sec'] == 1.0
    assert result['generated_audio_revision'] == 4
    path = Path(result['audio_path'])
    assert path.is_relative_to(tmp_path)
    data, rate = sf.read(path, dtype='int16')
    assert rate == 1000
    assert data.tolist() == [1024] * 137 + [2048] * 863
    assert [call['text'] for call in synth.calls] == [b['text'] for b in beats()]
    assert all(call['intensity'] == 0.0 and call['pace'] == 0.9 and call['force'] for call in synth.calls)


@pytest.mark.parametrize('mapping', [[], [{'id': 'x', 'text': ' ', 'panel_ids': ['a']}], [{'id': 'x', 'text': 'Speech', 'panel_ids': []}], [{'id': 'x', 'text': 'Speech', 'panel_ids': ['foreign']}], [beats()[0], beats()[0]]])
def test_invalid_mapping_fails_before_any_speech_is_generated(tmp_path, mapping):
    synth = SampleSynthesizer()
    with pytest.raises(ValueError):
        service_with(synth).synthesize_mapped_narration(tmp_path, 'segment', mapping, {'a', 'b', 'c'})
    assert synth.calls == []


def test_mixed_sample_rates_are_rejected_without_fabricating_cues(tmp_path):
    synth = SampleSynthesizer(rates=(1000, 2000))
    with pytest.raises(ValueError, match='sample rate|format'):
        service_with(synth).synthesize_mapped_narration(tmp_path, 'segment', beats(), {'a', 'b', 'c'})


def test_audio_returned_outside_workspace_is_rejected(tmp_path):
    class EscapingSynth:
        def synthesize(self, **kwargs):
            return tmp_path.parent / 'outside.wav'
    with pytest.raises(ValueError):
        service_with(EscapingSynth()).synthesize_mapped_narration(tmp_path, 'segment', beats(), {'a', 'b', 'c'})
