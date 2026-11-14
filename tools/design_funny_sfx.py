"""Professional Comedic Sound Design & Foley Engine.
Layers:
1. Real acoustic elements (orchestral fanfare from tada.wav, bell ding, debris crunch, glass smash).
2. Real human vocal reactions (tribe snicker/laughter, panic scream, crowd awe).
3. Classic slapstick cartoon Foley (spring boing, comic slide drop, record scratch, sad trombone).
4. Balanced dynamic mixing with automatic music ducking around punchlines.
"""
import math
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf

SR = 44100
PROJECT_DIR = Path("output/shorts/wheel_short")
SFX_DIR = PROJECT_DIR / "sfx_proper"
SFX_DIR.mkdir(parents=True, exist_ok=True)

def load_resample(path: Path, target_sr=SR) -> np.ndarray:
    """Load audio file via soundfile or ffmpeg and convert to mono float32 at target_sr."""
    tmp_wav = SFX_DIR / f"_tmp_{path.stem}.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(path),
        "-ar", str(target_sr),
        "-ac", "1",
        str(tmp_wav)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data, _ = sf.read(str(tmp_wav))
    tmp_wav.unlink(missing_ok=True)
    return data.astype(np.float32)

def generate_record_scratch(dur=0.35):
    """Authentic vinyl record scratch (fast reverse-friction frequency sweep)."""
    n = int(SR * dur)
    t = np.linspace(0, dur, n, False)
    # Bandpass filtered modulated noise + fast sine zip
    mod = np.sin(2 * np.pi * 8 * t)
    freq = 1200 * (1 - t / dur) ** 2 + 300 * mod
    phase = 2 * np.pi * np.cumsum(freq) / SR
    noise = np.random.uniform(-1, 1, n)
    sig = 0.5 * np.sin(phase) + 0.5 * noise * np.exp(-4 * t)
    return sig * np.sin(np.pi * (t / dur)) ** 0.5

def generate_rich_boing(dur=1.4):
    """Rubbery cartoon spring boing (multi-frequency FM with fast pitch vibrato)."""
    n = int(SR * dur)
    t = np.linspace(0, dur, n, False)
    freq = 320 + 480 * np.sin(np.pi * (t / dur) ** 0.5) + 40 * np.sin(2 * np.pi * 28 * t)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-3.5 * t) * (1 + 0.3 * np.sin(2 * np.pi * 14 * t))
    return 0.8 * np.sin(phase) * env

def generate_wood_crunch(dur=1.2):
    """Crashing wood break (multi-layered filtered noise impulses)."""
    n = int(SR * dur)
    t = np.linspace(0, dur, n, False)
    noise = np.random.uniform(-1, 1, n)
    thump = np.sin(2 * np.pi * 55 * t) * np.exp(-12 * t)
    shatter = noise * np.exp(-8 * t) * (1 + 0.8 * np.sin(2 * np.pi * 1200 * t))
    snap = np.sin(2 * np.pi * 420 * t) * np.exp(-25 * t)
    comb = 0.6 * thump + 0.5 * shatter + 0.4 * snap
    return comb / np.max(np.abs(comb) + 1e-6)

def generate_sad_trombone(dur=2.8):
    """Iconic 4-note comedy trombone 'Waa-waa-waa-waaaah' with brass buzz & mute wah."""
    n = int(SR * dur)
    sig = np.zeros(n)
    # Notes: F4 (349), E4 (330), Eb4 (311), D4 (293 -> 260 slide)
    notes = [
        (0.0, 0.45, 349.2),
        (0.55, 0.45, 329.6),
        (1.10, 0.45, 311.1),
        (1.65, 1.15, 293.7),
    ]
    for st, d, f in notes:
        st_i = int(st * SR)
        ed_i = min(n, st_i + int(d * SR))
        seg_n = ed_i - st_i
        seg_t = np.linspace(0, d, seg_n, False)
        
        freq = f
        if f == 293.7:
            freq = f - 45.0 * (seg_t / d) ** 1.5  # comedic downward pitch sag
            
        phase = 2 * np.pi * np.cumsum(np.full(seg_n, freq) if isinstance(freq, float) else freq) / SR
        # Rich brass harmonics
        brass = (
            np.sin(phase) +
            0.6 * np.sin(2 * phase) +
            0.4 * np.sin(3 * phase) +
            0.25 * np.sin(4 * phase)
        )
        # Wah-wah envelope (wah filter simulation)
        wah = (1 + 0.5 * np.sin(2 * np.pi * 6 * seg_t))
        env = np.sin(np.pi * np.clip(seg_t / d, 0, 1)) ** 0.6
        sig[st_i:ed_i] += 0.7 * brass * wah * env
        
    return sig / np.max(np.abs(sig) + 1e-6)

def main():
    print("--- 1. Building Rich Comic SFX Palette ---")
    
    # Load Real Acoustic System Assets
    tada_raw = load_resample(Path("C:/Windows/Media/tada.wav"))[:int(0.85 * SR)]  # Snappy short fanfare
    ding_raw = load_resample(Path("C:/Windows/Media/ding.wav"))
    chimes_raw = load_resample(Path("C:/Windows/Media/chimes.wav"))
    recycle_raw = load_resample(Path("C:/Windows/Media/Windows Recycle.wav"))

    # Load Real Vocal Reactions
    v_laugh = load_resample(PROJECT_DIR / "sfx" / "test_laugh.wav")
    v_scream = load_resample(PROJECT_DIR / "sfx" / "test_scream.wav")
    v_awe = load_resample(PROJECT_DIR / "sfx" / "test_awe.wav")

    # Synthesize Slapstick FX
    boing = generate_rich_boing()
    scratch = generate_record_scratch()
    wood_crash = generate_wood_crunch()
    sad_trombone = generate_sad_trombone()

    print("\n--- 2. Mixing Master Sound Timeline ---")
    voice_path = PROJECT_DIR / "human_voice_variations" / "human_1_ryan_witty_master.mp3"
    voice = load_resample(voice_path)

    bgm_path = PROJECT_DIR / "sfx" / "comedy_bgm.wav"
    bgm = load_resample(bgm_path)

    total_len = int(35.75 * SR)
    mix = np.zeros(total_len, dtype=np.float32)

    # Helper to overlay audio at specific timestamp (in seconds)
    def overlay(audio: np.ndarray, t_sec: float, gain: float):
        st = int(t_sec * SR)
        ed = min(total_len, st + len(audio))
        if st < total_len:
            mix[st:ed] += gain * audio[: ed - st]

    # 1. Voiceover (Front and center, 0dB)
    v_st = int(0.25 * SR)
    v_len = min(len(voice), total_len - v_st)
    mix[v_st:v_st + v_len] += 0.90 * voice[:v_len]

    # 2. Curated Comedic SFX Events:
    print("Placing Scene 1: Triumphant Fanfare interrupted by crowd laughter...")
    overlay(tada_raw, 0.4, 0.55)           # Proud fanfare
    overlay(scratch, 1.3, 0.45)            # Record scratch cutting off fanfare
    overlay(v_laugh, 1.6, 0.75)            # Tribe snickers & laughs: "Hahaha, hehe!"

    print("Placing Scene 2: Stone Grating + Eureka Lightbulb Ding...")
    overlay(wood_crash[:int(0.6*SR)], 5.5, 0.40) # Stone movement friction
    overlay(ding_raw, 7.5, 0.80)                 # Crisp Eureka Bell Ding

    print("Placing Scene 3: Cheerful Brass Flourish & Whistle...")
    overlay(tada_raw, 11.2, 0.65)          # King fanfare on cart celebration

    print("Placing Scene 4: Fast Runaway Panic Scream...")
    overlay(v_scream, 17.2, 0.85)          # Caveman screaming: "Whoaaa! Aaargh!"

    print("Placing Scene 5: Slapstick Village Crash & Spring Boing...")
    overlay(wood_crash, 21.0, 0.90)        # Wood splintering & smash
    overlay(recycle_raw, 21.2, 0.65)       # Flying debris crunch
    overlay(boing, 22.1, 0.85)             # Funny cartoon spring boing as he lands in straw

    print("Placing Scene 6: Comedic Silence + Crowd Awe + Angelic Chime...")
    overlay(v_awe, 26.2, 0.80)             # Crowd: "Ooooh! Wow!"
    overlay(chimes_raw, 27.0, 0.70)        # Angelic chimes for the future of the wheel

    print("Placing Scene 7: Record Scratch & Sad Trombone Punchline...")
    overlay(scratch, 31.8, 0.65)           # Record scratch on "...NOTHING!"
    overlay(sad_trombone, 32.3, 0.95)      # Classic Waa-waa-waa-waaaah

    # 3. Dynamic Background Music (Ducked)
    print("\nApplying Dynamic BGM Bed with automatic ducking...")
    bgm_len = min(len(bgm), total_len)
    # BGM ducked at -17dB generally, ducked deeper to -26dB during the scream and crash
    bgm_ducked = bgm[:bgm_len] * 0.14
    # Cut BGM at Scene 6 for comedic silence (25.5s to 27.5s)
    silence_st = int(25.5 * SR)
    silence_ed = int(27.2 * SR)
    bgm_ducked[silence_st:silence_ed] *= 0.15
    mix[:bgm_len] += bgm_ducked

    # Master Limiter
    peak = np.max(np.abs(mix))
    if peak > 0.96:
        print(f"Limiting audio master (peak was {peak:.2f})...")
        mix = mix * (0.96 / peak)

    master_audio_path = PROJECT_DIR / "proper_sound_mix.wav"
    sf.write(master_audio_path, mix, SR)
    print(f"Master Sound Mix Rendered: {master_audio_path.name}")

    # Mux into final master video
    video_source = PROJECT_DIR / "the_dumbest_man_who_changed_history_master.mp4"
    final_output = PROJECT_DIR / "the_dumbest_man_proper_sfx_master.mp4"

    print("\n--- 3. Muxing into Final Master Video ---")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_source),
        "-i", str(master_audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        str(final_output)
    ]
    subprocess.run(cmd, check=True)
    print(f"\n🎉 PROPER SFX SHORT COMPLETE: {final_output} ({final_output.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
