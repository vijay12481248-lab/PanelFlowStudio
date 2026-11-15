"""Generate truly human-sounding voice variations with acting punctuation, dynamic pacing, and broadcast mastering."""
import os
import sys
import asyncio
import subprocess
from pathlib import Path
import edge_tts

OUT_DIR = Path("output/shorts/wheel_short/human_voice_variations")
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR = OUT_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)

# Directed acting script with human comedic pauses and emphasis
SCRIPT_ACTING = (
    "Thousands of years ago... one absolute idiot had an idea that changed the world. "
    "He discovered that putting a round thing under a heavy thing... makes the heavy thing move! "
    "Suddenly, he was the smartest man in the entire tribe! "
    "Except... he forgot ONE tiny detail. Brakes! "
    "He wiped out the village! His house! And PROBABLY his marriage! "
    "But the old man saw something else. He saw the future! "
    "And that's how humanity got the wheel... and the inventor? Got absolutely NOTHING!"
)

# Broadcast Vocal Chain (Shure SM7B Style EQ + Dynamics)
AUDIO_FILTER = (
    "highpass=f=80,"
    "equalizer=f=220:t=q:w=1.2:g=2.5,"
    "equalizer=f=3500:t=q:w=1.5:g=3.0,"
    "equalizer=f=11000:t=q:w=1.2:g=1.5,"
    "acompressor=threshold=-18dB:ratio=3:attack=15:release=120:makeup=2dB,"
    "loudnorm=I=-16:TP=-1.5:LRA=10"
)

CONFIGS = [
    {
        "id": "human_1_ryan_witty_master",
        "name": "Ryan UK (Human-Tuned Comedic Master)",
        "voice": "en-GB-RyanNeural",
        "rate": "+9%",
        "pitch": "+0Hz",
        "desc": "Your preferred British satirist voice, directed with comedic timing, dramatic pauses, and studio microphone mastering.",
    },
    {
        "id": "human_2_william_organic",
        "name": "William (Ultra-Natural Storyteller)",
        "voice": "en-AU-WilliamMultilingualNeural",
        "rate": "+10%",
        "pitch": "+0Hz",
        "desc": "Microsoft's latest multilingual foundation voice with natural vocal cord texture and human inflection.",
    },
    {
        "id": "human_3_ryan_high_energy",
        "name": "Ryan UK (Fast-Paced TikTok Edit)",
        "voice": "en-GB-RyanNeural",
        "rate": "+16%",
        "pitch": "+2Hz",
        "desc": "Faster, punchier British delivery designed for instant dopamine and viral short retention.",
    },
]

async def synth_take(text: str, voice: str, rate: str, pitch: str, raw_path: Path):
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(str(raw_path))

def master_audio(raw_path: Path, master_path: Path):
    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_path),
        "-af", AUDIO_FILTER,
        "-c:a", "libmp3lame",
        "-b:a", "256k",
        str(master_path)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    print("--- Generating Human-Calibrated Voice Takes with Studio Mastering ---")
    results = []

    for cfg in CONFIGS:
        raw_file = RAW_DIR / f"{cfg['id']}_raw.mp3"
        master_file = OUT_DIR / f"{cfg['id']}.mp3"
        print(f"\nProcessing {cfg['name']} ({cfg['voice']})...")

        asyncio.run(synth_take(SCRIPT_ACTING, cfg["voice"], cfg["rate"], cfg["pitch"], raw_file))
        print(f"  -> Synthesized {raw_file.name}")

        master_audio(raw_file, master_file)
        print(f"  -> Applied Broadcast Mastering: {master_file.name}")

        # Probe duration
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(master_file)]
        dur = float(subprocess.check_output(cmd).decode().strip())
        print(f"  -> Verified Duration: {dur:.2f}s")

        results.append({
            "name": cfg["name"],
            "file": str(master_file),
            "duration": round(dur, 2),
            "description": cfg["desc"]
        })

    import json
    summary_file = OUT_DIR / "takes.json"
    summary_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nAll human-level takes ready! Summary saved to {summary_file}")

if __name__ == "__main__":
    main()
