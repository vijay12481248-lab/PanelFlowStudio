import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import time
from pathlib import Path
import soundfile as sf
from engine.audio.synthesis import local_synthesizer

ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\a4e8115d-1e24-4a23-88b5-ecc72941bc8f")
out_dir = ws / "audio" / "dialogue"
out_dir.mkdir(parents=True, exist_ok=True)

lines = [
    {
        "id": "narr_beat_1",
        "scene_id": "scene_1792725244459_2nws3",
        "start_time_sec": 0.0,
        "speaker": "The Narrator",
        "text": "In the shadow of the imperial court, a forbidden aura stirs. The air grows heavy with the scent of bloodshed.",
        "emotion": "Mysterious",
    },
    {
        "id": "narr_beat_2",
        "scene_id": "scene_1792725244459_ajki0",
        "start_time_sec": 20.0,
        "speaker": "The Narrator",
        "text": "Zhou Fan steps forward into the chamber. Every breath resonates with the terrifying aura of the Demonic Emperor.",
        "emotion": "Determined",
    },
    {
        "id": "narr_beat_3",
        "scene_id": "scene_1792725264163_8qsk2",
        "start_time_sec": 44.0,
        "speaker": "The Narrator",
        "text": "The surrounding guards tremble in dread. They realize too late what kind of monster has breached their gates.",
        "emotion": "Suspenseful",
    },
    {
        "id": "narr_beat_4",
        "scene_id": "scene_1792725264163_k9f12",
        "start_time_sec": 68.0,
        "speaker": "The Narrator",
        "text": "Without hesitation, the crimson energy ignites across his fingertips, tearing through ancient defensive wards.",
        "emotion": "Determined",
    },
    {
        "id": "narr_beat_5",
        "scene_id": "scene_1792725280915_m29a1",
        "start_time_sec": 92.0,
        "speaker": "The Narrator",
        "text": "A deafening shockwave shatters the courtyard as the true battle erupts across the grand pavilion.",
        "emotion": "Excited",
    },
    {
        "id": "narr_beat_6",
        "scene_id": "scene_1792725280915_y81nc",
        "start_time_sec": 116.0,
        "speaker": "The Narrator",
        "text": "Bloodlust fills the air. The power gap is absolute—none can withstand the wrath of the sovereign.",
        "emotion": "Serious",
    },
    {
        "id": "narr_beat_7",
        "scene_id": "scene_1792725301140_c82la",
        "start_time_sec": 140.0,
        "speaker": "The Narrator",
        "text": "As the dust settles over the fallen, Zhou Fan stands untouched, his crimson eyes gleaming in the dark.",
        "emotion": "Mysterious",
    },
    {
        "id": "narr_beat_8",
        "scene_id": "scene_1792725301140_p91fa",
        "start_time_sec": 156.0,
        "speaker": "The Narrator",
        "text": "The silence of the fallen marks a new dawn. The storm has only just begun.",
        "emotion": "Neutral",
    },
]

print(f"Synthesizing {len(lines)} narration lines for Magic Emperor...")
results = []
for idx, item in enumerate(lines, start=1):
    t0 = time.time()
    wav_path = local_synthesizer.synthesize(
        directory=out_dir,
        text=item["text"],
        voice="narrator",
        emotion=item["emotion"],
    )
    info = sf.info(wav_path)
    dur = round(info.duration, 2)
    elapsed = round(time.time() - t0, 2)
    print(f"[{idx}/{len(lines)}] Synthesized in {elapsed}s: duration={dur}s -> {wav_path.name}")
    results.append({
        **item,
        "wav_file": wav_path.name,
        "audio_url": f"/api/projects/a4e8115d-1e24-4a23-88b5-ecc72941bc8f/audio/dialogue/{wav_path.name}",
        "duration_sec": dur,
        "status": "APPROVED",
        "review_status": "APPROVED",
    })

print("\nAll 8 narration lines synthesized successfully!")
import json
with open("scratch/magic_emperor_synthesized_narration.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
