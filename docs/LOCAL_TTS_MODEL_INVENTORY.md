# PanelFlow Studio — Local Neural TTS Model Inventory

**Audit Date**: October 18, 2026  
**Auditor**: Antigravity AI Engineering & Audio Directorate  
**Environment**: Windows 11 Pro, NVIDIA GeForce RTX 5060 Ti (16 GB VRAM, Driver 610.88, CUDA 12.9)  
**Tools Root**: `C:\Tools`

---

## 1. Executive Summary

This inventory documents all local neural Text-to-Speech (TTS) models discovered in `C:\Tools` and surrounding developer toolchains. Each model was evaluated against strict production criteria:
1. **Local Availability**: Fully installed offline without on-the-fly network downloads.
2. **Hardware Compatibility**: Functional on Windows x64 with PyTorch CUDA 12.9 on RTX 5060 Ti.
3. **Commercial Licensing**: Permissive licensing (MIT, Apache-2.0) without non-commercial (NC) encumbrances.
4. **Voice Cloning & Storytelling Utility**: Zero-shot reference voice cloning, emotional adaptability, and dramatic suitability for manga/manhua motion comic narration.

```
┌─────────────────┬───────────────────┬──────────────┬───────────────┬───────────────────────────────┐
│ Model           │ Checkpoint / Repo │ License      │ Commercial    │ Production Operational Status │
├─────────────────┼───────────────────┼──────────────┼───────────────┼───────────────────────────────┤
│ Chatterbox      │ chatterbox-turbo  │ MIT          │ YES           │ VERIFIED & OPERATIONAL (GPU)  │
│ Dia 1.6B        │ Dia-1.6B-0626     │ Apache-2.0   │ YES           │ VERIFIED & OPERATIONAL (GPU)  │
│ Qwen3-TTS 1.7B  │ 12Hz-1.7B-Base    │ Apache-2.0   │ YES           │ INSTALLED (Weights uncached)  │
│ LuxTTS          │ YatharthS/LuxTTS  │ Apache-2.0   │ YES           │ BLOCKED (Win symlink error)   │
│ TADA 1B/3B      │ Hume AI TADA      │ Llama / MIT  │ CONDITIONAL   │ BLOCKED (CPU-only PyTorch)    │
│ F5-TTS          │ F5-TTS Base       │ CC-BY-NC-4.0 │ NO            │ EXCLUDED (Non-commercial)     │
│ CosyVoice 3     │ CosyVoice-330M    │ Apache-2.0   │ YES           │ NOT INSTALLED                 │
│ ACE-Step 1.5    │ ACE-Step-1.5      │ Apache-2.0   │ YES           │ RESERVED (Music synthesis)    │
└─────────────────┴───────────────────┴──────────────┴───────────────┴───────────────────────────────┘
```

> [!IMPORTANT]
> **ACE-Step 1.5 Classification**: In accordance with system instructions, ACE-Step 1.5 is classified strictly as an algorithmic/neural music and dynamic BGM synthesis foundation. It is **not** a speech narration engine and is reserved for future music-generation milestones.

---

## 2. In-Depth Model Audits

### 2.1 Chatterbox Turbo (Resemble AI) — PRIMARY CANDIDATE

- **Repository**: `C:\Tools\Chatterbox`
- **Cached Weights**: `C:\Users\Vijaya sekhar\.cache\huggingface\hub\models--ResembleAI--chatterbox-turbo`
- **Python Environment**: `C:\Tools\Chatterbox\.venv\Scripts\python.exe`
- **PyTorch / CUDA**: PyTorch `2.8.0+cu129`, CUDA 12.9
- **Code License**: MIT (Permissive)
- **Weight License**: MIT (Permissive)
- **Commercial Use**: **Fully Eligible**
- **Output Sample Rate**: 24,000 Hz (24 kHz PCM_16)
- **Architecture**: Latent diffusion transformer + S3 token representation + Vocos/HiFi-GAN vocoder + Perth perceptual watermark.
- **Reference Audio Requirements**:
  - Accepts 3 to 10-second reference audio clips (`.wav`, `.mp3`).
  - Conditionals cached into model memory via `model.prepare_conditionals(ref_path)`.
  - Default voice conditioning (Leon) available when no reference audio is provided.
- **Hardware Performance**:
  - **Cold Load Time**: 1.05s
  - **VRAM Consumption**: ~2.5 GB allocated (15% of 16 GB RTX 5060 Ti)
  - **Average Real-Time Factor (RTF)**: **0.3035** (~3.3x faster than real-time)
  - **Latency**: 1.8s to 3.2s per narrative paragraph
- **Emotional & Dramatic Control**:
  - Steered via decoding hyperparameters (`temperature` 0.65–0.82, `top_p` 0.85–0.95, `repetition_penalty` 1.15–1.25).
  - Paralinguistic prefix tags (`[whisper]`, `[sigh]`, `[gasp]`, `[chuckle]`).
- **Known Restrictions**:
  - Single-speaker per synthesis call.
  - Requires clean reference audio; background noise in reference audio will bleed into generation.

---

### 2.2 Dia 1.6B (Nari Labs) — SECONDARY / DIALOGUE SPECIALIST

- **Repository**: `C:\Tools\dia`
- **Cached Weights**: `C:\Users\Vijaya sekhar\.cache\huggingface\hub\models--nari-labs--Dia-1.6B-0626`
- **Python Environment**: `C:\Tools\dia\.venv\Scripts\python.exe`
- **PyTorch / CUDA**: PyTorch `2.8.0+cu129`, CUDA 12.9
- **Code License**: Apache-2.0
- **Weight License**: Apache-2.0
- **Commercial Use**: **Fully Eligible**
- **Output Sample Rate**: 44,100 Hz (44.1 kHz Studio Fidelity PCM_16)
- **Architecture**: 1.6-Billion parameter autoregressive dialogue transformer with discrete acoustic tokens.
- **Model Capabilities**:
  - Native multi-speaker dialogue sequencing in a single generation call (`[S1]`, `[S2]`).
  - Rich paralinguistic token support embedded in text: `(laughs)`, `(sighs)`, `(whispers)`, `(gasp)`, `(groans)`, `(coughs)`.
  - Reference audio voice prompting supported via `--audio-prompt`.
- **Hardware Performance**:
  - **Cold Load Time**: 8.67s
  - **VRAM Consumption**: ~3.8 GB allocated (23% of 16 GB RTX 5060 Ti)
  - **Average Real-Time Factor (RTF)**: **2.5427** (~2.5x audio duration)
  - **Latency**: 12.5s to 19.8s per narrative paragraph
- **Known Restrictions**:
  - Significantly higher inference latency than Chatterbox Turbo (~8.4x slower).
  - Fixed output token sequence requires silence trimming for variable-length lines.
  - Autoregressive generation requires explicit `max_tokens` argument (omitting triggers `TypeError`).

---

### 2.3 Qwen3-TTS 1.7B (Alibaba Qwen Team)

- **Repository**: `C:\Tools\Qwen3-TTS`
- **Python Environment**: `C:\Tools\Qwen3-TTS\.venv\Scripts\python.exe`
- **PyTorch / CUDA**: PyTorch `2.8.0+cu129`, CUDA 12.9
- **Code License**: Apache-2.0
- **Weight License**: Apache-2.0
- **Commercial Use**: **Fully Eligible**
- **Architecture**: 1.7B LLM-based TTS with 12Hz acoustic tokenization. Variants: `Base` (voice cloning), `CustomVoice` (preset characters), `VoiceDesign` (natural language voice prompts).
- **Current Operational Status**: **INSTALLED BUT UNINITIALIZED**
  - Checkpoint weights (`Qwen/Qwen3-TTS-12Hz-1.7B-Base`) are **not pre-cached** in local disk cache.
  - Runtime dependency warnings: `sox` executable missing from system PATH; `flash-attn` not compiled for Windows CUDA 12.9.
  - In accordance with audit constraints, model download was deferred to prevent unsolicited bandwidth/disk writes.

---

### 2.4 LuxTTS (YatharthS / ZipVoice)

- **Repository**: `C:\Tools\LuxTTS`
- **Python Environment**: `C:\Tools\LuxTTS\.venv\Scripts\python.exe`
- **PyTorch / CUDA**: PyTorch `2.8.0+cu129`, CUDA 12.9
- **Code License**: Apache-2.0
- **Weight License**: Apache-2.0
- **Current Operational Status**: **BLOCKED BY OS PRIVILEGE RESTRICTION**
  - Instantiation failed with: `OSError: [WinError 1314] A required privilege is not held by the client: os.symlink`.
  - HuggingFace Hub's cache mechanism requires Windows Developer Mode or Administrator privileges to create NTFS symbolic links.
  - Python package `k2` is missing from the environment, forcing fallback to unoptimized PyTorch routines.

---

### 2.5 TADA 1B/3B (Hume AI)

- **Repository**: `C:\Tools\TADA`
- **Python Environment**: `C:\Tools\TADA\.venv\Scripts\python.exe`
- **PyTorch / CUDA**: PyTorch `2.7.1+cpu` (**CPU Only**)
- **Code License**: MIT / Llama 3.2 Community License
- **Commercial Use**: **Conditional** (Subject to Llama 3.2 monthly user threshold)
- **Current Operational Status**: **BLOCKED (CPU-ONLY & MISSING WEIGHTS)**
  - TADA environment lacks CUDA support (`cuda_available=False`).
  - Running a 1B–3B parameter transformer on CPU is unviable for interactive video editing.

---

### 2.6 F5-TTS & CosyVoice (Evaluated External Candidates)

- **F5-TTS**:
  - Official model checkpoint license: **CC-BY-NC-4.0 (Non-Commercial)**.
  - **Verdict**: Strictly excluded from PanelFlow Studio distribution due to commercial license infringement risks.
  - Not installed in `C:\Tools`.
- **CosyVoice 3**:
  - Apache-2.0 license reported for code and weights.
  - **Verdict**: Not installed or cached in `C:\Tools`.

---

## 3. Local Voice Reference Assets

The following verified voice reference samples are present in `C:\Tools\voice_references\` and ready for zero-shot cloning:

| Voice ID | File Name | Format | Duration | Pitch / Tone | Canonical Story Role |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `marcus_male` | `marcus_male.wav` | 16-bit PCM WAV | 5.8s | Deep, resonant, authoritative | Zhuo Fan / Antiheroes / Male Lead |
| `aria_female` | `aria_female.wav` | 16-bit PCM WAV | 7.6s | Articulate, warm, balanced | Lead Narrator / Female Lead |
| `aria_narrator` | `aria_female_narrator.wav` | 16-bit PCM WAV | 7.6s | Grounded, calm, documentary | Documentary Storyteller |
| `seraphina_female` | `seraphina_female_cinematic.mp3` | True ID3 MP3 | 4.2s | Soft, breathy, elegant | Heroine / High Priestess |
| `leon_male` | *(Default Chatterbox Turbo)* | Latent Embed | — | Crisp, modern, energetic | Luo Yunhai / Young Master / Devlog |

---

## 4. Hardware Resource Budget (RTX 5060 Ti)

```
Total Physical VRAM: 16,311 MiB (16.0 GB)
Current System & Ollama Allocation: 9,290 MiB (~9.1 GB)
Available Headroom: 7,021 MiB (~6.9 GB)

Model Footprint Comparison:
├── Chatterbox Turbo:  2,540 MiB (Headroom remaining: 4,481 MiB) -> SAFE COEXISTENCE
└── Dia 1.6B:          3,820 MiB (Headroom remaining: 3,201 MiB) -> SAFE COEXISTENCE
```

Both **Chatterbox Turbo** and **Dia 1.6B** easily fit within the available 6.9 GB VRAM headroom without competing with Ollama background workers.
