import io
import numpy as np
import soundfile as sf
from engine.audio.alignment import OfflineHybridSpeechAligner


def audio_bytes():
    out = io.BytesIO()
    sf.write(out, np.sin(np.arange(32000) * 0.15).astype('float32') * 0.2, 16000, format='WAV')
    return out.getvalue()


def test_real_synthesis_byte_input_reaches_whisper(monkeypatch):
    calls = []
    def recognize(source):
        calls.append(source)
        return {'text': 'He raises the axe. She turns away.', 'chunks': [
            {'text': word, 'timestamp': (i * 0.2, (i + 1) * 0.2)}
            for i, word in enumerate('He raises the axe. She turns away.'.split())]}
    monkeypatch.setattr('engine.audio.alignment.get_offline_whisper_pipeline', lambda *_: recognize)
    result = OfflineHybridSpeechAligner().align(audio_bytes(), 'He raises the axe. She turns away.', panel_ids=['axe'])
    assert len(calls) == 1, 'Normal synthesis supplies bytes; this must not bypass the recognizer'
    assert calls[0]['sampling_rate'] == 16000
    assert len(calls[0]['raw']) == 32000
    assert result['alignment_tier'] == 'tier_1_whisper_vad'


def test_multiple_panel_ids_do_not_imply_one_sentence_per_panel(monkeypatch):
    monkeypatch.setattr('engine.audio.alignment.get_offline_whisper_pipeline', lambda *_: None)
    result = OfflineHybridSpeechAligner().align(audio_bytes(), 'He raises the axe. He swings it. She turns away.', panel_ids=['axe', 'face'])
    # Without explicit beats there is no evidence that sentence two belongs to
    # the second panel; all sentences still describe this declared panel group.
    assert all(cue['panel_ids'] == ['axe', 'face'] for cue in result['cues'])


def test_segment_endpoint_passes_panel_evidence_to_synthesis(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from engine.api.routers.audio import SynthesizeSegmentRequest, synthesize_narration_segment_endpoint
    class Query:
        def filter(self, *_): return self
        def first(self): return SimpleNamespace(workspace_path=str(tmp_path))
    db = SimpleNamespace(query=lambda *_: Query())
    received = {}
    def synthesize(**kwargs):
        received.update(kwargs)
        return {'audio_path': str(tmp_path / 'voice.wav'), 'speech_cues': []}
    monkeypatch.setattr('engine.api.routers.audio.audio_service.synthesize_narration_segment', synthesize)
    synthesize_narration_segment_endpoint('project', SynthesizeSegmentRequest(segment_id='voice', text='He raises the axe.', panel_ids=['axe']), db)
    assert received['panel_ids'] == ['axe']


def test_batch_generation_preserves_alignment_cues(tmp_path, monkeypatch):
    from engine.audio.service import AudioService
    service = AudioService()
    path = tmp_path / 'audio' / 'dialogue' / 'voice.wav'
    path.parent.mkdir(parents=True)
    path.write_bytes(audio_bytes())
    class Synth:
        def synthesize_batch(self, *_args, **_kwargs):
            return [{'id': 'voice', 'success': True, 'audio_path': str(path), 'duration': 2}]
    service.synthesizer = Synth()
    monkeypatch.setattr('engine.audio.alignment.get_offline_whisper_pipeline', lambda *_: None)
    result = service.synthesize_narration_batch(tmp_path, [{'segment_id': 'voice', 'text': 'He raises the axe.', 'panel_ids': ['axe']}])
    assert result[0]['speech_cues'][0]['panel_ids'] == ['axe']
    assert result[0]['speech_cues'][0]['end_sec'] == 2
