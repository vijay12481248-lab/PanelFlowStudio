import os
import sys
import json
import math
from pathlib import Path
import numpy as np
import soundfile as sf

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_PATH = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\68711176-90f5-4a68-8520-78d6e183bf65")
RENDERS_DIR = PROJECT_PATH / "renders"
MIXED_WAV = RENDERS_DIR / "chapter9_60s_mixed_master.wav"

def analyze_audio():
    print("=================================================================")
    print(" CHAPTER 9.1: AUDIO CONTINUITY, DUCKING & SPECTRAL ANALYSIS")
    print("=================================================================")

    if not MIXED_WAV.exists():
        print(f"Error: {MIXED_WAV} does not exist!")
        return

    data, sr = sf.read(str(MIXED_WAV))
    print(f"Loaded master WAV: {MIXED_WAV.name} | Samples: {len(data)} | SR: {sr} Hz | Channels: {data.shape[1]}")
    mono = np.mean(data, axis=1)

    # 1. Boundary click & continuity analysis at 18.0s and 46.0s
    print("\n--- 1. Boundary Click & Discontinuity Analysis ---")
    boundaries = [18.0, 46.0]
    for b_sec in boundaries:
        center_idx = int(round(b_sec * sr))
        # Look at window of 100ms around boundary
        window_samples = int(sr * 0.1)
        start_idx = max(0, center_idx - window_samples)
        end_idx = min(len(mono), center_idx + window_samples)
        sub_seg = mono[start_idx:end_idx]

        # Calculate maximum sample-to-sample difference (derivative)
        diffs = np.abs(np.diff(sub_seg))
        max_diff = float(np.max(diffs))
        rms_boundary = float(np.sqrt(np.mean(sub_seg ** 2)))
        rms_dbfs = 20.0 * math.log10(max(rms_boundary, 1e-6))

        # Check for silence gap (>50ms of near zero amplitude)
        energy_50ms = [np.mean(sub_seg[i:i+int(sr*0.05)]**2) for i in range(0, len(sub_seg) - int(sr*0.05), int(sr*0.01))]
        min_energy = min(energy_50ms) if energy_50ms else 0.0
        has_dropout = min_energy < 1e-8

        print(f"Boundary @ {b_sec:.1f}s:")
        print(f"  - Max sample step (click indicator): {max_diff:.5f} (threshold: >0.15 indicates click)")
        print(f"  - RMS across boundary: {rms_dbfs:.2f} dBFS")
        print(f"  - Has silence dropout: {has_dropout}")
        assert max_diff < 0.15, f"Audible click detected at {b_sec}s boundary!"

    # 2. Dialogue Ducking & Attenuation Measurement
    print("\n--- 2. Dialogue Ducking & Intelligibility Measurement ---")
    # Dialogue intervals from Chapter 9 timeline:
    # narr_01: 1.0s - 3.78s
    # narr_02: 7.5s - 12.35s
    # narr_03: 19.0s - 21.63s
    # narr_04: 25.5s - 29.00s
    # narr_05: 37.0s - 39.88s
    # narr_06: 49.0s - 56.21s
    speech_intervals = [
        ("narr_01 (Citadel)", 1.0, 3.78),
        ("narr_02 (Marcus Sword)", 7.5, 12.35),
        ("narr_03 (Seraphina Silence)", 19.0, 21.63),
        ("narr_04 (Ancestral Matrix)", 25.5, 29.0),
        ("narr_05 (Forbidden Valley)", 37.0, 39.88),
        ("narr_06 (Nine Nether Domain)", 49.0, 56.21),
    ]

    for name, s_t, e_t in speech_intervals:
        # Pre-speech background level (0.8s before speech)
        pre_s = max(0, int(round((s_t - 0.9) * sr)))
        pre_e = max(0, int(round((s_t - 0.1) * sr)))
        if pre_e > pre_s:
            rms_pre = float(np.sqrt(np.mean(mono[pre_s:pre_e] ** 2)))
            db_pre = 20.0 * math.log10(max(rms_pre, 1e-6))
        else:
            db_pre = -30.0

        # During speech
        dur_s = int(round(s_t * sr))
        dur_e = int(round(e_t * sr))
        rms_speech = float(np.sqrt(np.mean(mono[dur_s:dur_e] ** 2)))
        db_speech = 20.0 * math.log10(max(rms_speech, 1e-6))

        # Post-speech recovery (0.8s after speech)
        post_s = min(len(mono), int(round((e_t + 0.3) * sr)))
        post_e = min(len(mono), int(round((e_t + 1.1) * sr)))
        if post_e > post_s:
            rms_post = float(np.sqrt(np.mean(mono[post_s:post_e] ** 2)))
            db_post = 20.0 * math.log10(max(rms_post, 1e-6))
        else:
            db_post = -30.0

        print(f"Interval {name} [{s_t:.1f}s - {e_t:.1f}s]:")
        print(f"  - Pre-speech bed: {db_pre:.2f} dBFS")
        print(f"  - Speech interval: {db_speech:.2f} dBFS (Dialogue active)")
        print(f"  - Post-speech bed: {db_post:.2f} dBFS (Recovery)")

    # 3. Frequency Band Energy & Headroom Analysis
    print("\n--- 3. Frequency Spectrum & Dialogue Headroom Allocation ---")
    # Take an FFT of the music cues vs dialogue clips
    # Bands: Low (<250Hz), Low-Mid (250-2000Hz), Dialogue Core (2000-5000Hz), High (>5000Hz)
    fft_vals = np.abs(np.fft.rfft(mono))
    fft_freqs = np.fft.rfftfreq(len(mono), 1.0 / sr)

    def band_energy(f_min, f_max):
        idx = np.where((fft_freqs >= f_min) & (fft_freqs < f_max))[0]
        return float(np.sum(fft_vals[idx] ** 2))

    total_e = float(np.sum(fft_vals ** 2))
    e_low = band_energy(20, 250) / total_e * 100.0
    e_mid = band_energy(250, 2000) / total_e * 100.0
    e_core = band_energy(2000, 5000) / total_e * 100.0
    e_high = band_energy(5000, 20000) / total_e * 100.0

    print(f"Full Master Spectral Distribution:")
    print(f"  - Bass (< 250 Hz): {e_low:.1f}%")
    print(f"  - Mid / Harmonic (250 - 2,000 Hz): {e_mid:.1f}%")
    print(f"  - Dialogue Core Headroom (2,000 - 5,000 Hz): {e_core:.1f}% (Speech clarity zone)")
    print(f"  - Air / Presence (> 5,000 Hz): {e_high:.1f}%")

    out_metrics = {
        "sample_rate": sr,
        "duration_sec": len(mono) / sr,
        "peak_dbfs": round(20.0 * math.log10(float(np.max(np.abs(mono)))), 2),
        "rms_dbfs": round(20.0 * math.log10(float(np.sqrt(np.mean(mono**2)))), 2),
        "boundary_18s_max_step": round(max_diff, 5),
        "spectral_distribution": {
            "low_pct": round(e_low, 1),
            "mid_pct": round(e_mid, 1),
            "dialogue_core_pct": round(e_core, 1),
            "air_pct": round(e_high, 1),
        }
    }

    out_json = RENDERS_DIR / "chapter9_1_dsp_metrics.json"
    out_json.write_text(json.dumps(out_metrics, indent=2), encoding="utf-8")
    print(f"\nSaved DSP metrics to: {out_json}")

if __name__ == "__main__":
    analyze_audio()
