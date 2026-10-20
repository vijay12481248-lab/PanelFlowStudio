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
import io
from pathlib import Path
import numpy as np
import soundfile as sf
from types import SimpleNamespace

logger = logging.getLogger("panelflow.audio.synthesis")

from engine.system.setup import get_voice_reference_dir
from engine.security.paths import (
    promote_contained_file,
    read_contained_bytes,
    resolve_contained_path,
    unlink_contained_file,
    write_contained_bytes,
    write_contained_json,
)

TOOLS_ROOT = Path(os.environ.get("PANELFLOW_LOCAL_TOOLS_ROOT", r"C:\Tools"))
VOICE_REF_DIR = get_voice_reference_dir()
CHATTERBOX_PYTHON = TOOLS_ROOT / "Chatterbox" / ".venv" / "Scripts" / "python.exe"

# Voice identity mapping to authorized local reference files
VOICE_MAP: Dict[str, Path] = {
    # Aria (Female Narrator / Elegant Host)
    "aria_female": VOICE_REF_DIR / "aria_female_narrator.wav",
    "aria_female_narrator": VOICE_REF_DIR / "aria_female_narrator.wav",
    "voice_aria_female_narrator": VOICE_REF_DIR / "aria_female_narrator.wav",
    "the narrator": VOICE_REF_DIR / "aria_female_narrator.wav",
    "narrator": VOICE_REF_DIR / "aria_female_narrator.wav",
    "narrator (local f5-tts)": VOICE_REF_DIR / "aria_female_narrator.wav",
    "aria (the narrator)": VOICE_REF_DIR / "aria_female_narrator.wav",
    "aria": VOICE_REF_DIR / "aria_female.wav",
    "aria (pepper female)": VOICE_REF_DIR / "aria_female.wav",
    "char_aria": VOICE_REF_DIR / "aria_female.wav",

    # Marcus (Male Deep Storyteller / Protagonist / Warrior)
    "marcus_male": VOICE_REF_DIR / "marcus_male.wav",
    "voice_marcus_male": VOICE_REF_DIR / "marcus_male.wav",
    "marcus": VOICE_REF_DIR / "marcus_male.wav",
    "char_marcus": VOICE_REF_DIR / "marcus_male.wav",
    "marcus (male deep f5-tts)": VOICE_REF_DIR / "marcus_male.wav",
    "marcus (male deep)": VOICE_REF_DIR / "marcus_male.wav",
    "marcus (male warrior)": VOICE_REF_DIR / "marcus_male.wav",
    "marcus_male_deep": VOICE_REF_DIR / "marcus_male.wav",
    "char_zhuo_fan": VOICE_REF_DIR / "marcus_male.wav",
    "zhuo fan": VOICE_REF_DIR / "marcus_male.wav",
    "danqing shen": VOICE_REF_DIR / "marcus_male.wav",
    "valerian": VOICE_REF_DIR / "marcus_male.wav",

    # Leon (Youthful Male)
    "voice_leon_male": VOICE_REF_DIR / "marcus_male.wav",
    "leon_male": VOICE_REF_DIR / "marcus_male.wav",
    "leon": VOICE_REF_DIR / "marcus_male.wav",
    "luo yunhai": VOICE_REF_DIR / "marcus_male.wav",

    # Seraphina (Female Cinematic / Ethereal)
    "seraphina_female": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "voice_seraphina_female": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "seraphina": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "char_seraphina": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "seraphina (cinematic)": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
    "high priestess": VOICE_REF_DIR / "seraphina_female_cinematic.mp3",
}

# Emotion delivery mapping for Chatterbox Turbo
# Controls acoustic style through decoder sampling parameters, avoiding literal vocalization of bracketed tags
EMOTION_SETTINGS: Dict[str, Dict[str, Any]] = {
    "neutral": {"tag": "", "temperature": 0.76, "top_p": 0.92, "repetition_penalty": 1.18, "top_k": 50},
    "calm": {"tag": "", "temperature": 0.74, "top_p": 0.90, "repetition_penalty": 1.18, "top_k": 50},
    "happy": {"tag": "", "temperature": 0.80, "top_p": 0.94, "repetition_penalty": 1.16, "top_k": 60},
    "excited": {"tag": "", "temperature": 0.82, "top_p": 0.95, "repetition_penalty": 1.16, "top_k": 60},
    "sad": {"tag": "", "temperature": 0.74, "top_p": 0.90, "repetition_penalty": 1.20, "top_k": 40},
    "fearful": {"tag": "", "temperature": 0.75, "top_p": 0.92, "repetition_penalty": 1.20, "top_k": 50},
    "suspenseful": {"tag": "", "temperature": 0.74, "top_p": 0.92, "repetition_penalty": 1.20, "top_k": 50},
    "mysterious": {"tag": "", "temperature": 0.74, "top_p": 0.90, "repetition_penalty": 1.18, "top_k": 50},
    "whispering": {"tag": "", "temperature": 0.73, "top_p": 0.90, "repetition_penalty": 1.20, "top_k": 40},
    "serious": {"tag": "", "temperature": 0.74, "top_p": 0.92, "repetition_penalty": 1.20, "top_k": 50},
    "angry": {"tag": "", "temperature": 0.76, "top_p": 0.92, "repetition_penalty": 1.22, "top_k": 50},
    "determined": {"tag": "", "temperature": 0.75, "top_p": 0.92, "repetition_penalty": 1.20, "top_k": 50},
}


def sanitize_tts_text(text: str) -> str:
    """
    Cleans text for neural TTS generation.
    - Strips bracketed stage directions ([whisper], [sigh], [gasp], etc.)
    - Strips parenthetical acting cues ((whispering), (sighs))
    - Strips Japanese brackets (「, 」, 『, 』)
    - Strips leading speaker labels (Narrator:, Marcus:, etc.)
    - Strips robotic scene/panel prefixes (Scene 1:, Panel 2 —, etc.)
    - Prevents vocalizing dummy scene/panel labels
    """
    import re
    if not text:
        return ""

    # Remove bracketed directions like [whisper], [sigh], [gasp], [pause]
    cleaned = re.sub(r"\[[^\]]*\]", " ", text)
    # Remove parenthetical cues like (whispering), (sighs)
    cleaned = re.sub(r"\([^\)]*\)", " ", cleaned)

    # Normalize Japanese brackets & quotation marks
    cleaned = cleaned.replace("「", '"').replace("」", '"')
    cleaned = cleaned.replace("『", '"').replace("』", '"')
    cleaned = cleaned.replace("【", "").replace("】", "")

    # Replace smart quotes and dashes
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u2014", " - ").replace("\u2013", " - ")
    cleaned = cleaned.replace("\u2026", "...")

    # Normalize whitespace first
    cleaned = " ".join(cleaned.split()).strip()

    # Strip leading speaker tags like "The Narrator:", "Narrator:", "Marcus:", "Aria:", "Seraphina:"
    cleaned = re.sub(
        r"^(?:The\s+)?(?:Narrator|Marcus|Aria|Seraphina|Leon|Zhuo\s+Fan|Protagonist|Speaker|[A-Z][a-zA-Z0-9_]{1,24})\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Strip leading scene/panel prefixes like "Scene 1 — Panel #1:", "Scene 1:", "Panel #2 —"
    cleaned = re.sub(
        r"^(?:Scene|Panel|Shot)\s*#?\d+\s*(?:[—–\-:]|\s*(?:—|–|-)\s*Panel\s*#?\d+)?\s*[:—–\-.]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # If the remaining text is purely a dummy label like "Scene 1 — Panel #1." or "Scene 2."
    if re.match(r"^(?:Scene|Panel|Shot)\s*#?\d+(?:\s*[-—–.]\s*(?:Panel\s*#?\d+)?)?\.?$", cleaned, flags=re.IGNORECASE):
        return ""

    # Strip accidental dangling leading or trailing colons/dashes
    cleaned = re.sub(r"^[:—–\-\s]+", "", cleaned)
    cleaned = re.sub(r"[:—–\-]+$", "", cleaned)

    return cleaned.strip()


def _check_voice_file(target: Optional[Path]) -> Optional[str]:
    if not target:
        return None
    if target.exists():
        return str(target)
    # Check current dynamic voice reference dir
    active_dir = get_voice_reference_dir()
    alt = active_dir / target.name
    if alt.exists():
        return str(alt)
    # Check bundled package directory
    bundled = Path(__file__).resolve().parent / "voice_references" / target.name
    if bundled.exists():
        return str(bundled)
    return None


def resolve_voice_reference(voice_identifier: str) -> Optional[str]:
    if not voice_identifier:
        return _check_voice_file(VOICE_MAP.get("marcus_male")) or _check_voice_file(VOICE_MAP.get("aria_female"))

    # Check direct path
    p = Path(voice_identifier)
    if p.exists() and p.is_file():
        return str(p)

    key = voice_identifier.strip().lower()
    if key in VOICE_MAP:
        found = _check_voice_file(VOICE_MAP[key])
        if found:
            return found

    # Fuzzy heuristic matching on key tokens
    if any(k in key for k in ("marcus", "male", "warrior", "zhuo", "danqing", "valerian", "leon", "boy")):
        found = _check_voice_file(VOICE_MAP.get("marcus_male"))
        if found:
            return found

    if any(k in key for k in ("seraphina", "priestess", "ethereal", "queen")):
        found = _check_voice_file(VOICE_MAP.get("seraphina_female"))
        if found:
            return found

    if any(k in key for k in ("aria", "female", "girl", "woman")):
        found = _check_voice_file(VOICE_MAP.get("aria_female"))
        if found:
            return found

    if "narrator" in key:
        found = _check_voice_file(VOICE_MAP.get("the narrator"))
        if found:
            return found

    return _check_voice_file(VOICE_MAP.get("marcus_male")) or _check_voice_file(VOICE_MAP.get("aria_female"))


def postprocess_speech_audio(wav_path: Path, target_peak: float = 0.95) -> Dict[str, Any]:
    """
    Validates and cleans speech audio:
    - Normalizes peak amplitude to prevent clipping
    - Trims excess leading/trailing silence (>300ms) with clean fade in/out
    - Measures exact duration and sample rate
    """
    root = wav_path.parents[2]
    data, sr = sf.read(io.BytesIO(read_contained_bytes(root, wav_path)))
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

    encoded = io.BytesIO()
    sf.write(encoded, data, sr, format="WAV", subtype="PCM_16")
    write_contained_bytes(root, wav_path, encoded.getvalue())
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
        root = directory.parents[1]
        resolve_contained_path(root, directory)

        if self.adapter_factory:
            key = hashlib.sha256(json.dumps([
                "speech-v2", provider_id, text, voice, emotion, round(intensity, 2), round(pace, 2), delivery_style
            ], ensure_ascii=False).encode()).hexdigest()
            if force:
                key += "_" + uuid.uuid4().hex[:12]
            target = directory / f"speech_{key}.wav"
            if target.exists() and not force:
                if sf.info(io.BytesIO(read_contained_bytes(root, target))).duration > 0:
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
                if not temporary.exists() or sf.info(io.BytesIO(read_contained_bytes(root, temporary))).duration <= 0:
                    raise ValueError("Local speech model returned no valid audio")
                promote_contained_file(root, temporary, target)
                duration = sf.info(io.BytesIO(read_contained_bytes(root, target))).duration
                write_contained_json(root, target.with_suffix(".json"), {
                    "text": text, "voice": voice, "provider": provider_id,
                    "emotion": emotion, "intensity": intensity, "pace": pace,
                    "duration": duration, "audio_path": str(target),
                }, ensure_ascii=False)
                return target
            finally:
                try:
                    unlink_contained_file(root, temporary)
                except FileNotFoundError:
                    pass

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
        if provider_id not in ("chatterbox_turbo", "chatterbox"):
            logger.info(f"Mapping requested speech provider '{provider_id}' to verified local 'chatterbox_turbo'")
            provider_id = "chatterbox_turbo"

        if not self.python_exe.exists():
            raise ValueError(f"Chatterbox virtual environment not found at {self.python_exe}")

        prepared_tasks = []
        results = []

        for t in tasks:
            raw_text = t["text"].strip()
            if not raw_text:
                continue
            cleaned_text = sanitize_tts_text(raw_text)
            if not cleaned_text:
                continue
            directory = Path(t["directory"])
            root = directory.parents[1]
            resolve_contained_path(root, directory)
            voice = t.get("voice", "Narrator")
            emotion_raw = t.get("emotion", "Neutral").strip().lower()
            emo_cfg = EMOTION_SETTINGS.get(emotion_raw, EMOTION_SETTINGS["neutral"])

            ref_path = resolve_voice_reference(voice)
            content_key = hashlib.sha256(json.dumps([
                "speech-v4", provider_id, cleaned_text, voice, emo_cfg["temperature"], emo_cfg["top_p"], emo_cfg.get("top_k", 50),
            ], ensure_ascii=False).encode()).hexdigest()

            if t.get("force"):
                content_key += f"_{uuid.uuid4().hex[:8]}"

            target_wav = directory / f"speech_{content_key}.wav"
            meta_path = target_wav.with_suffix(".json")

            # Content-addressed cache hit check
            if target_wav.exists() and not t.get("force") and meta_path.exists():
                try:
                    meta = json.loads(read_contained_bytes(root, meta_path).decode("utf-8"))
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

            temporary_wav = directory / f"speech_{content_key}_{uuid.uuid4().hex}.tmp.wav"
            prepared_tasks.append({
                "id": t["id"],
                "target_path": str(temporary_wav),
                "authoritative_path": str(target_wav),
                "meta_path": str(meta_path),
                "text": cleaned_text,
                "raw_text": raw_text,
                "voice": voice,
                "ref_audio": ref_path,
                "temperature": emo_cfg["temperature"],
                "top_p": emo_cfg["top_p"],
                "repetition_penalty": emo_cfg["repetition_penalty"],
                "top_k": emo_cfg.get("top_k", 50),
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
            temperature=task.get('temperature', 0.76),
            top_p=task.get('top_p', 0.92),
            repetition_penalty=task.get('repetition_penalty', 1.18),
            top_k=task.get('top_k', 50)
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
                    temporary_wav = Path(br["audio_path"])
                    target_wav = Path(matched_task["authoritative_path"])
                    clean_info = postprocess_speech_audio(temporary_wav)
                    root = target_wav.parents[2]
                    promote_contained_file(root, temporary_wav, target_wav)
                    br["audio_path"] = str(target_wav)
                    br["duration"] = clean_info["duration"]
                    # Write metadata sidecar
                    write_contained_json(root, Path(matched_task["meta_path"]), {
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
                    })
                results.append(br)

        finally:
            Path(batch_input_path).unlink(missing_ok=True)
            Path(batch_output_path).unlink(missing_ok=True)
            Path(runner_py_path).unlink(missing_ok=True)

        return results


local_synthesizer = LocalSpeechSynthesizer()
