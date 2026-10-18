import urllib.request
import json

project_id = '68711176-90f5-4a68-8520-78d6e183bf65'

# Test 1: Draft Narration
print('--- Testing /narration/draft ---')
draft_payload = json.dumps({
    'scenes': [
        {
            'id': 'scene_01',
            'sequence': 1,
            'visual_description': 'Wide establishing shot of an ancient mountain citadel draped in violet mist.',
            'ocr_text': '',
            'characters': ['Narrator'],
        },
        {
            'id': 'scene_02',
            'sequence': 2,
            'visual_description': 'A young disciple stands before the monolithic temple gates.',
            'ocr_text': 'I have finally arrived at the Dragon Sect...',
            'characters': ['Marcus'],
            'speaker': 'Marcus',
        }
    ]
}).encode('utf-8')

req = urllib.request.Request(
    f'http://localhost:8765/api/projects/{project_id}/narration/draft',
    data=draft_payload,
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req, timeout=30) as r:
    plan = json.loads(r.read().decode())
    print('Draft Plan received with', len(plan['beats']), 'beats:')
    for b in plan['beats']:
        print(f"  Beat {b['sequence']} [{b['speaker']} - {b['inferred_emotional_context']}]: {b['proposed_narration_text']}")

# Test 2: Synthesize Segment
print('\n--- Testing /narration/synthesize-segment ---')
synth_payload = json.dumps({
    'segment_id': 'test_seg_01',
    'text': '[whisper] The ancient mechanism stirs beneath the obsidian floor.',
    'voice': 'The Narrator',
    'emotion': 'Whispering',
    'intensity': 0.7,
    'speed': 1.0,
    'text_revision': 1,
    'content_hash': 'test_hash_123',
    'force': True
}).encode('utf-8')

req2 = urllib.request.Request(
    f'http://localhost:8765/api/projects/{project_id}/narration/synthesize-segment',
    data=synth_payload,
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req2, timeout=45) as r:
    result = json.loads(r.read().decode())
    print('Synthesized successfully!')
    print('  Audio URL:', result['audio_url'])
    print('  Measured duration:', result['measured_duration_sec'], 'seconds')
    print('  Revision:', result['generated_audio_revision'])

# Test 3: Audio File Streaming Verification
print('\n--- Testing Audio File Streaming ---')
stream_url = f"http://localhost:8765{result['audio_url']}"
req3 = urllib.request.Request(stream_url)
with urllib.request.urlopen(req3, timeout=10) as r:
    audio_bytes = r.read()
    print(f'Audio streaming endpoint returned {len(audio_bytes)} bytes with Content-Type: {r.headers.get("Content-Type")}')
