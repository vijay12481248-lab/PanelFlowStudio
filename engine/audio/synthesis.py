"""
Enhanced Local Speech Synthesizer for PanelFlow Studio.
Provides emotion-aware, story-aligned TTS via Chatterbox Turbo (MIT).
Avoids unnecessary model reloads between segments, supports batch synthesis,
and performs speech cleanup and verification.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
import numpy as np
import soundfile as sf
from types import SimpleNamespace

logger = logging.getLogger("panelflow.audio.synthesis")

TOOLS_ROOT = Path(os.environ.get("PANELFLOW_LOCAL_TOOLS_ROOT", r"C:\Tools"))
VOICE_REF_DIR = TOOLS_ROOT / "voice_references"
CHATTERBOX_PYTHON = TOOLS_ROOT / "Chatterbox" / ".venv" / "Scripts" / "python.exe"

# Voice identity mapping to authorized local reference files
VOICE_MAP: Dict[str, Path] = {
    "aria_female": VOICE_REF_DIR / "aria_female_narrator.wav",
    "the narrator": VOICE_REF_DIR / "aria_female_narrator.wav",
    "narrator": VOICE_REF_DIR / "aria_female_narrator.wav",
    "aria": VOICE_REF_DIR / "aria_female.wav",
    "marcus_male": VOICE_REF_DIR / "marcus_male.wav",
    "marcus": VOICE_REF_DIR / "marcus_male.wav",
    "char_marcus": VOICE_REF_DIR / "marcus_male.wav",
    "seraphina_female": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "seraphina": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "char_seraphina": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
}

# Emotion delivery mapping for Chatterbox Turbo
EMOTION_SETTINGS: Dict[str, Dict[str, Any]] = {
    "neutral": {"tag": "", "temperature": 0.70, "top_p": 0.90, "repetition_penalty": 1.15},
    "happy": {"tag": "[chuckle] ", "temperature": 0.78, "top_p": 0.92, "repetition_penalty": 1.15},
    "excited": {"tag": "[chuckle] ", "temperature": 0.82, "top_p": 0.95, "repetition_penalty": 1.15},
    "sad": {"tag": "[sigh] ", "temperature": 0.65, "top_p": 0.88, "repetition_penalty": 1.20},
    "fearful": {"tag": "[gasp] ", "temperature": 0.75, "top_p": 0.90, "repetition_penalty": 1.20},
    "suspenseful": {"tag": "", "temperature": 0.70, "top_p": 0.90, "repetition_penalty": 1.18},
    "mysterious": {"tag": "", "temperature": 0.68, "top_p": 0.88, "repetition_penalty": 1.18},
    "whispering": {"tag": "[whisper] ", "temperature": 0.65, "top_p": 0.85, "repetition_penalty": 1.20},
    "serious": {"tag": "", "temperature": 0.68, "top_p": 0.90, "repetition_penalty": 1.22},
    "angry": {"tag": "", "temperature": 0.65, "top_p": 0.92, "repetition_penalty": 1.25},
    "determined": {"tag": "", "temperature": 0.66, "top_p": 0.90, "repetition_penalty": 1.20},
}


def resolve_voice_reference(voice_identifier: str) -> Optional[str]:
    key = voice_identifier.strip().lower()
    if key in VOICE_MAP and VOICE_MAP[key].exists():
        return str(VOICE_MAP[key])
    # Check if voice_identifier is an absolute file path
    p = Path(voice_identifier)
    if p.exists() and p.is_file():
        return str(p)
    # Check default narrator
    default_ref = VOICE_MAP.get("aria_female")
    if default_ref and default_ref.exists():
        return str(default_ref)
    return None


def postprocess_speech_audio(wav_path: Path, target_peak: float = 0.95) -> Dict[str, Any]:
    """
    Validates and cleans speech audio:
    - Normalizes peak amplitude to prevent clipping
    - Trims excess leading/trailing silence (>300ms) with clean fade in/out
    - Measures exact duration and sample rate
    """
    data, sr = sf.read(str(wav_path))
    if len(data.shape) > 1:
        data = data[:, 0]  # Mono
    data = data.astype(np.float32)

    # Detect non-silent regions
    threshold = 0.005
    abs_d = np.abs(data)
    non_silent = np.where(abs_d > threshold)[0]
    if len(non_silent) > 0:
        pad_samples = int(sr * 0.15)  # 150ms padding
        start_idx = max(0, non_silent[0] - pad_samples)
        end_idx = min(len(data), non_silent[-1] + pad_samples)
        data = data[start_idx:end_idx]

    # Peak normalization to target_peak (-0.5 dB)
    peak = np.max(np.abs(data))
    if peak > 0.0001:
        data = (data / peak) * target_peak

    sf.write(str(wav_path), data, sr, subtype="PCM_16")
    duration = len(data) / float(sr)
    return {
        "duration": round(duration, 3),
        "sample_rate": sr,
        "channels": 1,
        "peak_amplitude": float(np.max(np.abs(data))),
    }


class LocalSpeechSynthesizer:
    def __init__(self, adapter_factory=None, python_exe: Optional[Path] = None):
        self.adapter_factory = adapter_factory
        self.python_exe = python_exe or CHATTERBOX_PYTHON

    def synthesize(
        self,
        directory: Path | str,
        text: str,
        voice: str,
        provider_id: str = "chatterbox_turbo",
        emotion: str = "Neutral",
        intensity: float = 0.5,
        pace: float = 1.0,
        delivery_style: str = "CALM_NARRATION",
        vocal_energy: str = "medium",
        force: bool = False,
        text_revision: int = 1,
    ) -> Path:
        """
        Synthesizes a single narration line with emotion conditioning and content addressing.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        if self.adapter_factory:
            key = hashlib.sha256(json.dumps([
                "speech-v2", provider_id, text, voice, emotion, round(intensity, 2), round(pace, 2), delivery_style
            ], ensure_ascii=False).encode()).hexdigest()
            if force:
                key += "_" + uuid.uuid4().hex[:12]
            target = directory / f"speech_{key}.wav"
            if target.exists() and not force:
                if sf.info(str(target)).duration > 0:
                    return target
            brief = SimpleNamespace(
                scene=text, audio_type="voice",
                voice_params=SimpleNamespace(dialogue_text=text, speaker=voice, pace=pace,
                                             emotion_primary=emotion, intensity=intensity,
                                             energy=vocal_energy, delivery_style=delivery_style,
                                             paralinguistic_tags=[]),
            )
            temporary = directory / f"speech_{key}_{uuid.uuid4().hex}.tmp.wav"
            try:
                result = self.adapter_factory(provider_id).generate(brief, output_path=temporary)
                if not result.success:
                    raise ValueError(getattr(result, "error_message", "Local speech model failed"))
                if not temporary.exists() or sf.info(str(temporary)).duration <= 0:
                    raise ValueError("Local speech model returned no valid audio")
                temporary.replace(target)
                target.with_suffix(".json").write_text(json.dumps({
                    "text": text, "voice": voice, "provider": provider_id,
                    "emotion": emotion, "intensity": intensity, "pace": pace,
                    "duration": sf.info(str(target)).duration, "audio_path": str(target),
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                return target
            finally:
                temporary.unlink(missing_ok=True)

        results = self.synthesize_batch(
            tasks=[{
                "id": uuid.uuid4().hex[:8],
                "directory": str(directory),
                "text": text,
                "voice": voice,
                "emotion": emotion,
                "intensity": intensity,
                "pace": pace,
                "force": force,
                "text_revision": text_revision,
            }],
            provider_id=provider_id,
        )
        if not results or not results[0].get("success"):
            err = results[0].get("error", "Speech synthesis failed") if results else "Synthesis error"
            raise ValueError(f"TTS failed: {err}")
        return Path(results[0]["audio_path"])

    def synthesize_batch(
        self,
        tasks: List[Dict[str, Any]],
        provider_id: str = "chatterbox_turbo",
        progress_cb=None,
        cancelled_cb=None,
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes multiple narration segments in a SINGLE model session.
        Avoids reloading weights between segments, providing sub-second generation per line.
        """
        if not tasks:
            return []

        if provider_id not in ("chatterbox_turbo", "chatterbox"):
            raise ValueError(f"Unsupported speech provider: {provider_id}. Use 'chatterbox_turbo' (MIT).")

        if not self.python_exe.exists():
            raise ValueError(f"Chatterbox virtual environment not found at {self.python_exe}")

        prepared_tasks = []
        results = []

        for t in tasks:
            text = t["text"].strip()
            if not text:
                continue
            directory = Path(t["directory"])
            directory.mkdir(parents=True, exist_ok=True)
            voice = t.get("voice", "Narrator")
            emotion_raw = t.get("emotion", "Neutral").strip().lower()
            emo_cfg = EMOTION_SETTINGS.get(emotion_raw, EMOTION_SETTINGS["neutral"])

            # Formulate text with paralinguistic tag if not already present
            formatted_text = text
            if emo_cfg["tag"] and not text.startswith("["):
                formatted_text = f"{emo_cfg['tag']}{text}"

            ref_path = resolve_voice_reference(voice)
            content_key = hashlib.sha256(json.dumps([
                "speech-v3", provider_id, formatted_text, voice, emo_cfg["temperature"], emo_cfg["top_p"],
            ], ensure_ascii=False).encode()).hexdigest()

            if t.get("force"):
                content_key += f"_{uuid.uuid4().hex[:8]}"

            target_wav = directory / f"speech_{content_key}.wav"
            meta_path = target_wav.with_suffix(".json")

            # Content-addressed cache hit check
            if target_wav.exists() and not t.get("force") and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if meta.get("duration", 0) > 0.2:
                        results.append({
                            "id": t["id"],
                            "success": True,
                            "audio_path": str(target_wav),
                            "duration": meta["duration"],
                            "cached": True,
                            "emotion": emotion_raw,
                        })
                        continue
                except Exception:
                    pass

            prepared_tasks.append({
                "id": t["id"],
                "target_path": str(target_wav),
                "meta_path": str(meta_path),
                "text": formatted_text,
                "raw_text": text,
                "voice": voice,
                "ref_audio": ref_path,
                "temperature": emo_cfg["temperature"],
                "top_p": emo_cfg["top_p"],
                "repetition_penalty": emo_cfg["repetition_penalty"],
                "emotion": emotion_raw,
                "text_revision": t.get("text_revision", 1),
            })

        if not prepared_tasks:
            return results

        # Run batch synthesis script via Chatterbox virtual environment
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f_in:
            json.dump(prepared_tasks, f_in, ensure_ascii=False)
            batch_input_path = f_in.name

        batch_output_path = batch_input_path.replace(".json", "_out.json")

        runner_code = f"""
import sys, os, json, torch, soundfile as sf, numpy as np
from pathlib import Path
from chatterbox.tts_turbo import ChatterboxTurboTTS

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

with open({repr(batch_input_path)}, 'r', encoding='utf-8') as f:
    tasks = json.load(f)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = ChatterboxTurboTTS.from_pretrained(device=device)

outputs = []
current_ref = None

for task in tasks:
    try:
        ref_audio = task.get('ref_audio')
        if ref_audio and ref_audio != current_ref and Path(ref_audio).exists():
            model.prepare_conditionals(ref_audio)
            current_ref = ref_audio
        wav = model.generate(
            task['text'],
            temperature=task.get('temperature', 0.70),
            top_p=task.get('top_p', 0.90),
            repetition_penalty=task.get('repetition_penalty', 1.15)
        )
        audio_np = wav.squeeze().cpu().numpy().astype(np.float32)
        peak = np.max(np.abs(audio_np))
        if peak > 0.001:
            audio_np = (audio_np / peak) * 0.95
        target_path = task['target_path']
        sf.write(target_path, audio_np, model.sr, subtype='PCM_16')
        dur = float(len(audio_np)) / float(model.sr)
        outputs.append({{'id': task['id'], 'success': True, 'audio_path': target_path, 'duration': dur}})
    except Exception as e:
        outputs.append({{'id': task['id'], 'success': False, 'error': str(e)}})

with open({repr(batch_output_path)}, 'w', encoding='utf-8') as f:
    json.dump(outputs, f)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f_py:
            f_py.write(runner_code)
            runner_py_path = f_py.name

        try:
            if progress_cb:
                progress_cb(0.15, "Loading Chatterbox Turbo on GPU...")
            res = subprocess.run(
                [str(self.python_exe), runner_py_path],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if res.returncode != 0:
                logger.error(f"Chatterbox batch error: {res.stderr}")
                raise ValueError(f"Chatterbox inference failed: {res.stderr.strip()[:300]}")

            if not Path(batch_output_path).exists():
                raise ValueError("Chatterbox produced no output payload")

            batch_results = json.loads(Path(batch_output_path).read_text(encoding="utf-8"))
            for br in batch_results:
                matched_task = next((pt for pt in prepared_tasks if pt["id"] == br["id"]), None)
                if br.get("success") and matched_task:
                    # Apply conservative postprocessing & cleanup
                    clean_info = postprocess_speech_audio(Path(br["audio_path"]))
                    br["duration"] = clean_info["duration"]
                    # Write metadata sidecar
                    Path(matched_task["meta_path"]).write_text(json.dumps({
                        "text": matched_task["raw_text"],
                        "formatted_text": matched_task["text"],
                        "voice": matched_task["voice"],
                        "emotion": matched_task["emotion"],
                        "duration": clean_info["duration"],
                        "sample_rate": clean_info["sample_rate"],
                        "channels": clean_info["channels"],
                        "provider": provider_id,
                        "text_revision": matched_task["text_revision"],
                        "created_at": time.time(),
                    }, indent=2), encoding="utf-8")
                results.append(br)

        finally:
            Path(batch_input_path).unlink(missing_ok=True)
            Path(batch_output_path).unlink(missing_ok=True)
            Path(runner_py_path).unlink(missing_ok=True)

        return results


local_synthesizer = LocalSpeechSynthesizer()
