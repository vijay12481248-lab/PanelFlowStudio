"""Assembly script for C006 Empty Seat stickman short.

Combines the 6 ChronoFlow video clips according to the 40-second timeline,
generates a custom warm emotional score with foley accents, and produces
the final master 1080x1920 9:16 video.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "c006_empty_seat"
CLIP_DIR = OUT_DIR / "clips"
SEG_DIR = OUT_DIR / "seg"
AUDIO_DIR = OUT_DIR / "audio"
FINAL_DIR = OUT_DIR / "final"

for d in (SEG_DIR, AUDIO_DIR, FINAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

SR = 48000
W, H = 1080, 1920

SHOT_TIMINGS = [
    {"id": "s1", "dur": 3.0, "beat": "Hook"},
    {"id": "s2", "dur": 6.0, "beat": "Goal"},
    {"id": "s3", "dur": 7.0, "beat": "Escalation"},
    {"id": "s4", "dur": 7.0, "beat": "Pattern interrupt"},
    {"id": "s5", "dur": 11.0, "beat": "Payoff"},
    {"id": "s6", "dur": 6.0, "beat": "Aftertaste"},
]

def probe_duration(p: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True
    ).stdout
    return float(out.strip())

# ---------------------------------------------------------------------- Audio synthesis
def synth_foley_and_music(total_dur: float = 40.0) -> np.ndarray:
    n_samples = int(total_dur * SR)
    audio = np.zeros((n_samples, 2), dtype=np.float32)
    t = np.arange(n_samples) / SR

    # 1. Subtle warm ambient room tone (cafe background air)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n_samples).astype(np.float32)
    sos_amb = butter(2, [80, 800], "band", fs=SR, output="sos")
    room = sosfilt(sos_amb, noise) * 0.015
    audio[:, 0] += room
    audio[:, 1] += room

    # 2. Gentle piano chords (C major - G - Am - F progression, bittersweet tender)
    # Chord schedule (starts quietly in s1/s2, develops in s3/s4, blooms warmly at s5 payoff)
    chords = [
        # (start_s, dur_s, [freqs], base_vol)
        (0.5, 3.0, [261.63, 329.63, 392.00], 0.05),     # C maj
        (3.5, 3.0, [196.00, 246.94, 293.66], 0.06),     # G maj
        (6.5, 3.0, [220.00, 261.63, 329.63], 0.06),     # A min
        (9.5, 3.5, [174.61, 220.00, 261.63], 0.07),     # F maj
        (13.0, 3.5, [196.00, 246.94, 293.66], 0.07),    # G maj
        (16.5, 3.5, [220.00, 261.63, 329.63], 0.06),    # A min (melancholic realization)
        (20.0, 3.0, [174.61, 220.00, 261.63], 0.06),    # F maj
        (23.0, 4.0, [261.63, 329.63, 392.00, 523.25], 0.11),  # C maj (warm payoff bloom!)
        (27.0, 3.5, [196.00, 246.94, 293.66, 392.00], 0.10),  # G maj
        (30.5, 3.5, [220.00, 261.63, 329.63, 440.00], 0.09),  # A min
        (34.0, 5.5, [261.63, 329.63, 392.00, 523.25], 0.08),  # C maj resolution
    ]

    for start_t, dur, freqs, vol in chords:
        i0 = int(start_t * SR)
        i1 = min(n_samples, i0 + int(dur * SR))
        chord_len = i1 - i0
        ct = np.arange(chord_len) / SR
        env = np.sin(np.pi * np.clip(ct / dur, 0, 1) ** 0.5) * np.exp(-ct / (dur * 0.7))
        for f in freqs:
            tone = np.sin(2 * np.pi * f * ct) + 0.3 * np.sin(4 * np.pi * f * ct)
            audio[i0:i1, 0] += (tone * env * vol).astype(np.float32)
            audio[i0:i1, 1] += (tone * env * vol).astype(np.float32)

    # 3. Foley events per timeline beat:
    def add_tap(at_sec: float, pitch: float = 600.0, vol: float = 0.12):
        i0 = int(at_sec * SR)
        i1 = min(n_samples, i0 + int(0.2 * SR))
        tt = np.arange(i1 - i0) / SR
        tap = np.sin(2 * np.pi * pitch * tt) * np.exp(-tt * 35.0) * vol
        audio[i0:i1, 0] += tap
        audio[i0:i1, 1] += tap

    def add_rustle(at_sec: float, dur_sec: float = 0.5, vol: float = 0.06):
        i0 = int(at_sec * SR)
        i1 = min(n_samples, i0 + int(dur_sec * SR))
        tt = np.arange(i1 - i0) / SR
        r_noise = rng.standard_normal(i1 - i0).astype(np.float32)
        sos_r = butter(2, [1200, 5000], "band", fs=SR, output="sos")
        r_filtered = sosfilt(sos_r, r_noise) * np.sin(np.pi * tt / dur_sec) * vol
        audio[i0:i1, 0] += r_filtered
        audio[i0:i1, 1] += r_filtered

    # Beat 1: place card placement tap
    add_tap(0.8, pitch=450.0, vol=0.08)
    # Beat 2: cloth shift / waiting chair creak
    add_rustle(3.8, dur_sec=0.4, vol=0.05)
    # Beat 3: sudden slide / catch rustle (comic tension)
    add_rustle(9.6, dur_sec=0.6, vol=0.09)
    add_tap(10.2, pitch=520.0, vol=0.10)
    # Beat 4: soft sigh / cloth rustle
    add_rustle(17.0, dur_sec=0.7, vol=0.04)
    # Beat 5: stranger footsteps & chair pull
    add_rustle(23.4, dur_sec=0.8, vol=0.07)
    add_tap(24.2, pitch=320.0, vol=0.09)
    # Beat 6: soft cup clink on table
    add_tap(35.2, pitch=1800.0, vol=0.07)

    # Master gentle fade-out at end (last 2 seconds)
    fade_len = int(2.0 * SR)
    fade_curve = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    audio[-fade_len:, 0] *= fade_curve
    audio[-fade_len:, 1] *= fade_curve

    # Normalize to -1.5 dB peak
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (10 ** (-1.5 / 20) / peak)
    return audio


def assemble():
    print("=== STAGE 3: SEGMENT CONFORMING & TIMELINE ASSEMBLY ===")
    seg_list_file = OUT_DIR / "segments.txt"
    seg_lines = []

    for item in SHOT_TIMINGS:
        sid = item["id"]
        target_dur = item["dur"]
        raw_clip = CLIP_DIR / f"{sid}.mp4"
        seg_clip = SEG_DIR / f"{sid}.mp4"

        if not raw_clip.exists():
            print(f"Error: raw clip {raw_clip} does not exist!")
            sys.exit(1)

        cdur = probe_duration(raw_clip)
        print(f"Conforming {sid}: raw {cdur:.2f}s -> target {target_dur:.2f}s...")

        # Video filter: Lanczos upscale to 1080x1920, unsharp, 30fps
        vf = f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.6,fps=30,setsar=1"
        if target_dur > cdur:
            vf += f",tpad=stop_mode=clone:stop_duration={target_dur - cdur + 0.1:.2f}"

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(raw_clip),
            "-vf", vf,
            "-t", f"{target_dur:.3f}",
            "-an",
            "-c:v", "libx264",
            "-crf", "16",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(seg_clip),
        ]
        subprocess.run(cmd, check=True)
        seg_lines.append(f"file '{seg_clip.as_posix()}'")

    seg_list_file.write_text("\n".join(seg_lines), encoding="utf-8")

    # Generate audio
    print("\nSynthesizing custom 40s emotional soundtrack + foley...")
    audio_data = synth_foley_and_music(40.0)
    audio_path = AUDIO_DIR / "c006_master_audio.wav"
    sf.write(str(audio_path), audio_data, SR)
    print(f"Saved audio bed to {audio_path} ({audio_path.stat().st_size} bytes)")

    # Concatenate video segments
    concat_video = OUT_DIR / "concat_temp.mp4"
    print("\nConcatenating video segments...")
    cmd_cat = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(seg_list_file),
        "-c", "copy",
        str(concat_video),
    ]
    subprocess.run(cmd_cat, check=True)

    # Final Mux with Audio
    final_video = FINAL_DIR / "C006_Empty_Seat_Final_40s.mp4"
    print("\nMuxing final master video with audio bed...")
    cmd_mux = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(concat_video),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(final_video),
    ]
    subprocess.run(cmd_mux, check=True)

    final_dur = probe_duration(final_video)
    final_size = final_video.stat().st_size
    print(f"\n=======================================================")
    print(f"SUCCESS! Final master video created:")
    print(f"Path: {final_video}")
    print(f"Duration: {final_dur:.2f} seconds")
    print(f"Size: {final_size / (1024*1024):.2f} MB")
    print(f"Resolution: {W}x{H} (Vertical 9:16)")
    print(f"=======================================================")


if __name__ == "__main__":
    assemble()
