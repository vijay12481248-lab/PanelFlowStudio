"""Generate multiple high-quality continuous voice variations for the 35s Short."""
import os
import sys
import asyncio
from pathlib import Path
import edge_tts
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.narration.runtime.audio import KokoroTts

OUT_DIR = Path("output/shorts/wheel_short/voice_variations")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FULL_SCRIPT = (
    "Thousands of years ago, one idiot had an idea that changed the world! "
    "He discovered that putting a round thing under a heavy thing... makes the heavy thing move! "
    "Suddenly, he became the smartest man in the entire tribe! "
    "But he forgot ONE tiny detail... brakes! "
    "He destroyed the village... his house... and probably his marriage! "
    "But the old man saw something different. He saw the future! "
    "And that's how humanity got the wheel... and the inventor got absolutely NOTHING!"
)

VARIATIONS = [
    {
        "id": "variation_1_christopher",
        "name": "Viral YouTube Storyteller (Christopher)",
        "provider": "edge",
        "voice": "en-US-ChristopherNeural",
        "rate": "+10%",
        "pitch": "+2Hz",
        "desc": "High energy, punchy, engaging YouTube documentary-comedy narrator.",
    },
    {
        "id": "variation_2_ryan_uk",
        "name": "Witty British Satirist (Ryan)",
        "provider": "edge",
        "voice": "en-GB-RyanNeural",
        "rate": "+8%",
        "pitch": "+0Hz",
        "desc": "OverSimplified / History Matters comedic, dry, sarcastic delivery.",
    },
    {
        "id": "variation_3_andrew",
        "name": "Casual Energetic Buddy (Andrew)",
        "provider": "edge",
        "voice": "en-US-AndrewMultilingualNeural",
        "rate": "+12%",
        "pitch": "+1Hz",
        "desc": "Natural, upbeat, conversational, storytelling style.",
    },
    {
        "id": "variation_4_kokoro_george",
        "name": "Theatrical Storybook (Kokoro George)",
        "provider": "kokoro",
        "voice": "bm_george",
        "rate": 1.15,
        "pitch": None,
        "desc": "Deep, theatrical, classic storybook orator with natural pauses.",
    },
]

async def synth_edge(text: str, voice: str, rate: str, pitch: str, out_path: Path):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))

def main():
    print("--- Generating 4 High-Quality Continuous Voice Variations ---")
    results = []

    # 1. Edge-TTS variations
    for v in VARIATIONS:
        out_file = OUT_DIR / f"{v['id']}.wav" if v["provider"] == "kokoro" else OUT_DIR / f"{v['id']}.mp3"
        print(f"\nSynthesizing {v['name']} ({v['voice']})...")
        
        if v["provider"] == "edge":
            asyncio.run(synth_edge(FULL_SCRIPT, v["voice"], v["rate"], v["pitch"], out_file))
        elif v["provider"] == "kokoro":
            tts = KokoroTts()
            samples = tts.synth(FULL_SCRIPT, voice=v["voice"], rate=v["rate"])
            sf.write(out_file, samples, 24000)

        # Probe duration using ffprobe
        import subprocess, json
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(out_file)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        dur = float(json.loads(res.stdout)["format"]["duration"])
        print(f"  -> Generated {out_file.name} ({dur:.2f}s)")
        
        results.append({
            "name": v["name"],
            "file": str(out_file),
            "duration": round(dur, 2),
            "description": v["desc"]
        })

    summary_file = OUT_DIR / "variations.json"
    summary_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nAll variations complete! Saved summary to {summary_file}")

if __name__ == "__main__":
    main()
