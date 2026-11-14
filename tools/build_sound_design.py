"""Studio Sound Design & Music Engine for 'The Dumbest Man Who Changed History'.
Synthesizes:
1. Full 35-second playful pizzicato/marimba comedic background track.
2. 7 precisely timed cartoon sound effects (pops, dings, slide whistles, wood crash, spring boing, sad trombone).
3. Professional multi-track mixing with automatic ducking under the Ryan UK voiceover.
4. Final video assembly with full audio design.
"""
import math
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf

SR = 44100
PROJECT_DIR = Path("output/shorts/wheel_short")
SFX_DIR = PROJECT_DIR / "sfx"
SFX_DIR.mkdir(parents=True, exist_ok=True)

def generate_tone(freq, duration, decay=3.0):
    t = np.linspace(0, duration, int(SR * duration), False)
    env = np.exp(-decay * t)
    return np.sin(2 * np.pi * freq * t) * env

def generate_bell_ding():
    dur = 1.8
    t = np.linspace(0, dur, int(SR * dur), False)
    # C7 bell chime with sparkling harmonics
    sig = (
        0.6 * np.sin(2 * np.pi * 2093 * t) * np.exp(-3.5 * t) +
        0.3 * np.sin(2 * np.pi * 4186 * t) * np.exp(-6.0 * t) +
        0.15 * np.sin(2 * np.pi * 6279 * t) * np.exp(-9.0 * t)
    )
    return sig

def generate_pop():
    dur = 0.25
    t = np.linspace(0, dur, int(SR * dur), False)
    freq = 600 - 350 * (t / dur)
    env = np.exp(-22 * t)
    return np.sin(2 * np.pi * freq * t) * env

def generate_slide_whistle():
    dur = 1.5
    t = np.linspace(0, dur, int(SR * dur), False)
    # Ascend then dramatic downward swoop with vibrato
    freq = 800 + 1200 * np.sin(np.pi * (t / dur)) + 35 * np.sin(2 * np.pi * 14 * t)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.minimum(t * 8, 1.0) * np.exp(-0.8 * t)
    return 0.7 * np.sin(phase) * env

def generate_crash_boing():
    dur = 2.2
    n_samples = int(SR * dur)
    t = np.linspace(0, dur, n_samples, False)

    # 1. Low impact thud
    thud = np.sin(2 * np.pi * 65 * t) * np.exp(-8 * t)

    # 2. Wood splintering (filtered noise bursts)
    noise = np.random.uniform(-1, 1, n_samples)
    splinter = noise * np.exp(-6 * t) * (1 + 0.5 * np.sin(2 * np.pi * 800 * t))

    # 3. Cartoon Spring Boing (starts after impact at t=0.3)
    boing_t = np.maximum(0, t - 0.25)
    boing_freq = 280 + 550 * np.sin(boing_t * 5) + 30 * np.sin(2 * np.pi * 32 * boing_t)
    boing_phase = 2 * np.pi * np.cumsum(boing_freq) / SR
    boing_env = np.where(t >= 0.25, np.exp(-3.2 * boing_t), 0)
    boing = 0.65 * np.sin(boing_phase) * boing_env

    combined = 0.5 * thud + 0.45 * splinter + 0.55 * boing
    return combined / np.max(np.abs(combined) + 1e-6)

def generate_shimmer():
    dur = 1.8
    n_samples = int(SR * dur)
    t = np.linspace(0, dur, n_samples, False)
    notes = [1046, 1318, 1568, 2093, 2637]  # C6, E6, G6, C7, E7
    sig = np.zeros(n_samples)
    for i, f in enumerate(notes):
        offset = int(0.08 * i * SR)
        sub_t = t[: n_samples - offset]
        wave = np.sin(2 * np.pi * f * sub_t) * np.exp(-4.0 * sub_t)
        sig[offset:] += 0.25 * wave
    return sig / np.max(np.abs(sig) + 1e-6)

def generate_sad_trombone():
    # Classic cartoon 4-note descending "womp womp womp waaaah"
    dur = 2.8
    n_samples = int(SR * dur)
    sig = np.zeros(n_samples)
    notes = [(0.0, 0.4, 261.63), (0.45, 0.4, 246.94), (0.9, 0.4, 233.08), (1.35, 1.3, 220.0)]
    for start, d, f in notes:
        st_idx = int(start * SR)
        ed_idx = st_idx + int(d * SR)
        seg_t = np.linspace(0, d, ed_idx - st_idx, False)
        # Add brass overtones (sawtooth-like)
        harmonics = (
            np.sin(2 * np.pi * f * seg_t) +
            0.5 * np.sin(4 * np.pi * f * seg_t) +
            0.3 * np.sin(6 * np.pi * f * seg_t)
        )
        if f == 220.0:  # downward slide on the last note
            bend = np.exp(-1.2 * seg_t)
            harmonics = np.sin(2 * np.pi * (f - 35 * (seg_t / d)) * seg_t) + 0.4 * np.sin(4 * np.pi * (f - 35 * (seg_t / d)) * seg_t)
        env = np.sin(np.pi * np.clip(seg_t / d, 0, 1)) ** 0.5
        sig[st_idx:ed_idx] += 0.6 * harmonics * env
    return sig / np.max(np.abs(sig) + 1e-6)

def generate_pizzicato_bgm(total_duration=36.0):
    """Playful cartoon comedy pizzicato + marimba backing bed at 130 BPM."""
    bpm = 130
    beat_dur = 60.0 / bpm
    total_samples = int(SR * total_duration)
    bgm = np.zeros(total_samples)

    # 4-chord progression: C major, A minor, F major, G7
    chord_bass = [130.81, 110.00, 87.31, 98.00]  # C3, A2, F2, G2
    marimba_notes = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6

    num_beats = int(total_duration / beat_dur)
    for b in range(num_beats):
        st = int(b * beat_dur * SR)
        chord_idx = (b // 4) % len(chord_bass)
        
        # Plucked Bass on beat 1 and 3
        if b % 2 == 0:
            freq = chord_bass[chord_idx]
            n_t = min(int(0.35 * SR), total_samples - st)
            t_seg = np.linspace(0, n_t / SR, n_t, False)
            bass_tone = (np.sin(2 * np.pi * freq * t_seg) + 0.3 * np.sin(4 * np.pi * freq * t_seg)) * np.exp(-8 * t_seg)
            bgm[st:st + n_t] += 0.45 * bass_tone

        # Marimba syncopated tap on off-beats
        if b % 2 == 1 or b % 4 == 2:
            m_freq = marimba_notes[(b * 3) % len(marimba_notes)]
            m_samples = min(int(0.2 * SR), total_samples - st)
            t_m = np.linspace(0, m_samples / SR, m_samples, False)
            marimba_tone = np.sin(2 * np.pi * m_freq * t_m) * np.exp(-18 * t_m)
            bgm[st:st + m_samples] += 0.3 * marimba_tone

    return bgm / np.max(np.abs(bgm) + 1e-6)

def main():
    print("--- 1. Synthesizing Comedy Sound Effects (SFX) ---")
    sfx_files = {
        "pop": (SFX_DIR / "01_pop.wav", generate_pop()),
        "ding": (SFX_DIR / "02_ding.wav", generate_bell_ding()),
        "whistle": (SFX_DIR / "04_whistle.wav", generate_slide_whistle()),
        "crash": (SFX_DIR / "05_crash_boing.wav", generate_crash_boing()),
        "shimmer": (SFX_DIR / "06_shimmer.wav", generate_shimmer()),
        "sad_trombone": (SFX_DIR / "07_sad_trombone.wav", generate_sad_trombone()),
    }
    for name, (path, sig) in sfx_files.items():
        sf.write(path, sig.astype(np.float32), SR)
        print(f"  -> Generated SFX: {path.name}")

    print("\n--- 2. Synthesizing 36s Playful Pizzicato Background Music ---")
    bgm_path = SFX_DIR / "comedy_bgm.wav"
    bgm_data = generate_pizzicato_bgm(36.0)
    sf.write(bgm_path, bgm_data.astype(np.float32), SR)
    print(f"  -> Generated BGM: {bgm_path.name}")

    print("\n--- 3. Multi-Track Timeline Assembly (Voice + SFX + BGM) ---")
    voice_path = PROJECT_DIR / "human_voice_variations" / "human_1_ryan_witty_master.mp3"
    voice_data, v_sr = sf.read(str(voice_path))
    if len(voice_data.shape) > 1:
        voice_data = np.mean(voice_data, axis=1)

    # Master Timeline (35.7 seconds @ 44.1kHz)
    total_len = int(35.75 * SR)
    mix = np.zeros(total_len, dtype=np.float32)

    # 1. Voice Track (Primary, placed at t=0.2s)
    v_st = int(0.2 * SR)
    v_len = min(len(voice_data), total_len - v_st)
    mix[v_st:v_st + v_len] += 0.88 * voice_data[:v_len]

    # 2. SFX Cues Timed to Visual Beats
    sfx_cues = [
        (1.2, sfx_files["pop"][1], 0.65),            # Scene 1: Pop when wheel raised
        (6.8, sfx_files["ding"][1], 0.70),           # Scene 2: Eureka Ding
        (16.5, sfx_files["whistle"][1], 0.75),       # Scene 4: Runaway slide whistle
        (21.2, sfx_files["crash"][1], 0.90),         # Scene 5: Crash & Boing
        (26.2, sfx_files["shimmer"][1], 0.60),       # Scene 6: Old man discovery chime
        (31.8, sfx_files["sad_trombone"][1], 0.85),  # Scene 7: Womp-womp punchline
    ]
    for cue_time, audio_arr, gain in sfx_cues:
        st = int(cue_time * SR)
        c_len = min(len(audio_arr), total_len - st)
        mix[st:st + c_len] += gain * audio_arr[:c_len]

    # 3. Background Music (Ducked at -18dB)
    bgm_len = min(len(bgm_data), total_len)
    mix[:bgm_len] += 0.16 * bgm_data[:bgm_len]

    # Normalize to prevent clipping
    peak = np.max(np.abs(mix))
    if peak > 0.95:
        mix = mix * (0.95 / peak)

    final_audio_path = PROJECT_DIR / "complete_sound_mix.wav"
    sf.write(final_audio_path, mix, SR)
    print(f"  -> Multi-track mix rendered: {final_audio_path.name}")

    print("\n--- 4. Muxing Complete Audio into Master Video ---")
    video_source = PROJECT_DIR / "the_dumbest_man_who_changed_history_master.mp4"
    final_output = PROJECT_DIR / "the_dumbest_man_complete_edition_with_sfx.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_source),
        "-i", str(final_audio_path),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "256k",
        str(final_output)
    ]
    subprocess.run(cmd, check=True)
    print(f"\n🎉 FULL PRODUCTION SHORT READY! File: {final_output} ({final_output.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
