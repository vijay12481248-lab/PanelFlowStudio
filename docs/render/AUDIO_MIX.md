# PanelFlow Studio — Audio Mixdown & Ducking Architecture

## 1. Multi-Track Audio Architecture

PanelFlow mixes multi-track audio assets into a pristine 48 kHz stereo master stream using `numpy` and `soundfile`. The mix pipeline enforces broadcast loudness safety and clear dialogue intelligibility.

```
Dialogue Tracks (F5-TTS)   ───────────────────────────────┐
                                                         │
Music Track (ACE-Step)     ──────[ Ducking -8 dB ]───────┼──> [ Master Mix Buffer ] ──> [ Peak Soft Limiter ] ──> 48 kHz WAV
                                 ▲ (Attack 0.25s /       │                                 (-1.0 dBFS)
                                 │  Release 0.40s)       │
Sound Effects (SFX)        ──────────────────────────────┘
```

---

## 2. Dynamic Dialogue Ducking

To ensure speech remains articulate and unobstructed by background music, background music is automatically ducked by $-8\text{ dB}$ whenever speech intervals are active.

### Ducking Multiplier Formula
$$\text{gain\_factor} = 10^{\frac{-8.0}{20}} \approx 0.3981$$

### Continuous Envelope Calculation
Rather than abrupt rectangular attenuation (which causes audible volume pumping), `AudioMixer._build_ducking_envelope()` generates a smooth linear ramp:
- **Attack Phase** ($0.25\text{s}$ before speech starts): Linearly ramps music volume from $1.0$ down to $0.3981$.
- **Sustain Phase** (during dialogue): Holds music volume at $-8\text{ dB}$.
- **Release Phase** ($0.40\text{s}$ after speech ends): Linearly ramps music volume back up from $0.3981$ to $1.0$.
- **Interval Merging**: If two dialogue utterances occur within $0.65\text{s}$ of each other, the envelope remains ducked, preventing distracting fluctuation between adjacent sentences.

---

## 3. Broadcast Safety & Normalization

### A. NaN and Inf Sanitization
Audio arrays are scanned for non-finite floating point artifacts (`np.isnan`, `np.isinf`) caused by upstream synthesis glitches. Any detected `NaN` values are sanitized to $0.0$, and infinite peaks clamped to $\pm 0.95$.

### B. Peak Ceiling and Soft Limiting
Broadcast delivery guidelines require an audio ceiling of $-1.0\text{ dBFS}$ to prevent clipping distortion during lossy AAC encoding.
- If $\text{peak} > 0.99$, soft limiting normalizes the entire buffer:
  $$\text{scale} = \frac{0.891}{\text{peak}}$$
  where $0.891 \equiv -1.0\text{ dBFS}$.
- If no clipping is detected, natural headroom is preserved.
