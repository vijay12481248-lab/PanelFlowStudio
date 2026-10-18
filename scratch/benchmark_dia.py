import os
import time
import json
import shutil
from pathlib import Path
import torch
import numpy as np
import soundfile as sf
from dia.model import Dia

OUT_DIR_REPO = Path(r"C:\Users\Vijaya sekhar\Tools\PanelFlow Studio\scratch\tts_benchmark\dia")
OUT_DIR_ARTIFACT = Path(r"C:\Users\Vijaya sekhar\.gemini\antigravity-cli\brain\dc7f0225-3893-4147-9f2e-47bed84d1129\scratch\tts_benchmark\dia")
OUT_DIR_REPO.mkdir(parents=True, exist_ok=True)
OUT_DIR_ARTIFACT.mkdir(parents=True, exist_ok=True)

TEST_PROMPTS = [
    {
        "id": "01_calm_narration",
        "style": "Calm Narration",
        "text": "[S1] The ancient library stood in complete silence as dust drifted through the moonlight, waiting for the chosen one to turn the first page.",
        "max_tokens": 512,
        "temperature": 0.65,
        "top_p": 0.85
    },
    {
        "id": "02_fearful_suspense",
        "style": "Fearful Suspense",
        "text": "[S1] (whispers) Wait... do you hear that? Something is moving in the shadows beneath us. Don't make a sound.",
        "max_tokens": 512,
        "temperature": 0.70,
        "top_p": 0.85
    },
    {
        "id": "03_angry_dialogue",
        "style": "Angry Character Dialogue",
        "text": "[S1] (groans) You dare challenge me after everything I sacrificed? I will tear down this entire kingdom with my own bare hands!",
        "max_tokens": 512,
        "temperature": 0.80,
        "top_p": 0.90
    },
    {
        "id": "04_sad_emotional",
        "style": "Sad Emotional Delivery",
        "text": "[S1] (sighs) I tried so hard to protect them... but in the end, I was too weak. Now they are gone forever.",
        "max_tokens": 512,
        "temperature": 0.65,
        "top_p": 0.85
    },
    {
        "id": "05_mysterious_storytelling",
        "style": "Mysterious Storytelling",
        "text": "[S1] Legends speak of a shattered mirror hidden deep within the abyss, reflecting not the past, but the fate of worlds yet unborn.",
        "max_tokens": 512,
        "temperature": 0.70,
        "top_p": 0.85
    },
    {
        "id": "06_natural_dialogue",
        "style": "Natural Conversational Dialogue",
        "text": "[S1] Honestly, I didn't think the plan would work either, (laughs) but look at us now. We actually pulled it off!",
        "max_tokens": 512,
        "temperature": 0.75,
        "top_p": 0.90
    }
]

def run_dia_benchmark():
    print("=" * 60)
    print("DIA 1.6B BENCHMARK (6 Canonical Narrative Prompts)")
    print("=" * 60)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        start_vram_mb = torch.cuda.memory_allocated() / (1024 * 1024)
        print(f"Initial allocated VRAM: {start_vram_mb:.1f} MB")

    t_load_0 = time.time()
    model = Dia.from_pretrained("nari-labs/Dia-1.6B-0626", compute_dtype="bfloat16", device=device)
    t_load_1 = time.time()
    load_time = t_load_1 - t_load_0
    sample_rate = 44100
    print(f"Model Load Time: {load_time:.2f}s, Sample Rate: {sample_rate}")

    results = []

    for idx, prompt in enumerate(TEST_PROMPTS, 1):
        p_id = prompt["id"]
        text = prompt["text"]
        style = prompt["style"]
        print(f"\n[{idx}/6] Generating {p_id} ({style})...")

        torch.manual_seed(42 + idx)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(42 + idx)
            torch.cuda.synchronize()

        t0 = time.time()
        output_audio = model.generate(
            text=text,
            max_tokens=prompt["max_tokens"],
            temperature=prompt["temperature"],
            top_p=prompt["top_p"]
        )
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        t1 = time.time()
        latency_sec = t1 - t0

        audio_np = np.asarray(output_audio, dtype=np.float32)
        if audio_np.ndim > 1:
            audio_np = audio_np.squeeze()

        peak = float(np.max(np.abs(audio_np)))
        if peak > 0.001:
            audio_np = (audio_np / peak) * 0.95
        rms = float(np.sqrt(np.mean(audio_np ** 2)))
        duration_sec = float(len(audio_np) / sample_rate)
        rtf = latency_sec / duration_sec if duration_sec > 0 else 0.0

        repo_wav = OUT_DIR_REPO / f"{p_id}.wav"
        artifact_wav = OUT_DIR_ARTIFACT / f"{p_id}.wav"
        sf.write(str(repo_wav), audio_np, sample_rate, subtype="PCM_16")
        shutil.copy2(str(repo_wav), str(artifact_wav))

        rec = {
            "id": p_id,
            "style": style,
            "text": text,
            "latency_sec": round(latency_sec, 3),
            "duration_sec": round(duration_sec, 2),
            "rtf": round(rtf, 4),
            "sample_rate": sample_rate,
            "channels": 1,
            "peak": round(peak, 4),
            "rms": round(rms, 4),
            "vram_allocated_mb": round(torch.cuda.memory_allocated() / (1024 * 1024), 1) if torch.cuda.is_available() else 0,
            "wav_path": str(repo_wav)
        }
        results.append(rec)
        print(f"  -> Generated {duration_sec:.2f}s in {latency_sec:.3f}s (RTF: {rtf:.4f})")
        print(f"  -> Saved: {repo_wav.name}")

    summary = {
        "engine": "Dia 1.6B (Nari Labs)",
        "license": "Apache-2.0",
        "commercial_eligible": True,
        "device": device,
        "load_time_sec": round(load_time, 2),
        "sample_rate": sample_rate,
        "results": results,
        "avg_rtf": round(float(np.mean([r["rtf"] for r in results])), 4),
        "avg_latency_sec": round(float(np.mean([r["latency_sec"] for r in results])), 3)
    }

    json_repo = OUT_DIR_REPO / "dia_benchmark_results.json"
    json_art = OUT_DIR_ARTIFACT / "dia_benchmark_results.json"
    with open(json_repo, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    shutil.copy2(str(json_repo), str(json_art))
    print(f"\n[OK] Dia benchmark completed! Average RTF: {summary['avg_rtf']}")

if __name__ == "__main__":
    run_dia_benchmark()
