import json
import time
from pathlib import Path
import soundfile as sf
import numpy as np
import torch
from kokoro import KPipeline

AUDIO_DIR = Path("output/Regressed_Assassin_Duke/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
BEATS_DIR = AUDIO_DIR / "beats"
BEATS_DIR.mkdir(parents=True, exist_ok=True)

VOICE_NAME = "am_michael"
SAMPLE_RATE = 24000
PAUSE_SAMPLES = int(0.5 * SAMPLE_RATE)  # 0.5s pause between beats
SILENCE_GAP = np.zeros(PAUSE_SAMPLES, dtype=np.float32)

def main():
    t0 = time.time()
    beats_file = Path("output/Regressed_Assassin_Duke/parsed_beats.json")
    with open(beats_file, "r", encoding="utf-8") as f:
        beats = json.load(f)
    
    print(f"=== Initializing Kokoro TTS (Voice: {VOICE_NAME}) ===", flush=True)
    pipeline = KPipeline(lang_code="a")
    print("Kokoro pipeline ready!", flush=True)

    master_audio_list = []
    current_time_sec = 0.0
    timing_manifest = []

    total_beats = len(beats)
    for idx, beat in enumerate(beats, 1):
        b_id = beat["beat_id"]
        title = beat["title"]
        text = beat["text"]
        
        print(f"[{idx}/{total_beats}] Synthesizing {b_id}: {title} ({len(text.split())} words)...", flush=True)
        
        generator = pipeline(text, voice=VOICE_NAME, speed=1.0, split_pattern=r"\n+")
        beat_segments = []
        for _, _, audio in generator:
            beat_segments.append(audio)
        
        if not beat_segments:
            print(f"  Warning: No audio generated for {b_id}", flush=True)
            continue
            
        beat_audio = np.concatenate(beat_segments)
        beat_dur = len(beat_audio) / SAMPLE_RATE
        
        # Save individual beat audio
        beat_path = BEATS_DIR / f"{b_id}.wav"
        sf.write(str(beat_path), beat_audio, SAMPLE_RATE)
        
        start_sec = current_time_sec
        end_sec = current_time_sec + beat_dur
        
        timing_manifest.append({
            "beat_id": b_id,
            "act": beat["act"],
            "title": title,
            "start_sec": round(start_sec, 3),
            "end_sec": round(end_sec, 3),
            "duration_sec": round(beat_dur, 3),
            "word_count": len(text.split()),
            "wav_file": str(beat_path.name)
        })
        
        # Add to master
        master_audio_list.append(beat_audio)
        master_audio_list.append(SILENCE_GAP)
        
        current_time_sec = end_sec + 0.5  # include pause
        print(f"  Done in {beat_dur:.2f}s (Total timeline: {int(current_time_sec // 60)}m {int(current_time_sec % 60)}s)", flush=True)

    # Stitch master audio
    print("\nStitching full master narration audio...", flush=True)
    full_master = np.concatenate(master_audio_list)
    master_path = AUDIO_DIR / "master_narration.wav"
    sf.write(str(master_path), full_master, SAMPLE_RATE)
    
    total_dur_sec = len(full_master) / SAMPLE_RATE
    total_mins = int(total_dur_sec // 60)
    total_secs = int(total_dur_sec % 60)
    
    # Save timing manifest
    manifest_file = AUDIO_DIR / "timing_manifest.json"
    manifest_data = {
        "voice": VOICE_NAME,
        "sample_rate": SAMPLE_RATE,
        "total_duration_sec": round(total_dur_sec, 2),
        "total_duration_formatted": f"{total_mins:02d}:{total_secs:02d}",
        "total_beats": len(timing_manifest),
        "beats": timing_manifest
    }
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    elapsed = time.time() - t0
    print(f"\n[SUCCESS] Master Narration Audio Generated!")
    print(f"  File: {master_path}")
    print(f"  Duration: {total_mins} minutes {total_secs} seconds ({total_dur_sec:.2f}s)")
    print(f"  Size: {master_path.stat().st_size / (1024 * 1024):.2f} MB")
    print(f"  Total processing time: {elapsed:.1f}s")
    print(f"  Timing manifest: {manifest_file}")

if __name__ == "__main__":
    main()
