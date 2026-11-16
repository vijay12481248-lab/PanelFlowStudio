"""Narration: a line of text spoken by a local text-to-speech model, as a cue on the Voice lane.

Kokoro-82M (Apache-2.0, in-process, runs on the CPU by default so it never fights ComfyUI/Ollama for the GPU) and Qwen3-TTS 1.7B
(Apache-2.0, voice cloning from the reference recordings in the voice_references folder, through its own runner and virtualenv).
No cloud and no silent switch between them: a missing tool or voice is reported as the cue's reason.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from engine.audio.studio.plan import Candidate, Cue, Provenance, SoundPlan
from engine.audio.studio.sources.base import Availability
from engine.audio.studio.sources.music import _ONE_AT_A_TIME, ResourceSlot

PROVIDERS = ("kokoro", "qwen3_tts")
_MODEL = {"kokoro": ("Apache-2.0", "kokoro-82m"), "qwen3_tts": ("Apache-2.0", "qwen3-tts-12hz-1.7b-base")}
WORDS_PER_SECOND = 3.0   # measured 2026-11-16 on one 15-word line: Kokoro af_heart 4.97 s, Qwen3-TTS aria_female 5.68 s (n=2, re-measure with more lines)
_QWEN_PY = Path(os.environ.get("PANELFLOW_QWEN3_TTS_PYTHON", r"D:\Tools\Qwen3-TTS\.venv\Scripts\python.exe"))
_QWEN_RUNNER = Path(os.environ.get("PANELFLOW_QWEN3_TTS_RUNNER", r"D:\Tools\Qwen3-TTS\runner.py"))
_pipes: dict[str, Any] = {}


def estimate_seconds(text: str, speed: float = 1.0) -> float:
    """How long a line will take to speak: words at a narrator's pace plus a little for punctuation. A guide before the real length is known."""
    words = len(text.split())
    if not words:
        return 0.0
    pauses = sum(text.count(c) for c in ".!?") * 0.35 + sum(text.count(c) for c in ",;:") * 0.15
    return round((words / WORDS_PER_SECOND + pauses) / max(speed, 0.1), 2)


def kokoro_voices_on_disk(cache: Path | None = None) -> list[str]:
    """Kokoro voices whose weights are already in the Hugging Face cache (af_heart first): a voice not on disk would need a download."""
    if cache is None:
        try:
            from huggingface_hub import constants
            cache = Path(constants.HF_HUB_CACHE)
        except Exception:
            return []
    names = {p.stem for p in Path(cache).glob("models--hexgrad--Kokoro-82M/snapshots/*/voices/*.pt")}
    return sorted(names, key=lambda v: (v != "af_heart", v))


def list_voices() -> dict[str, list[str]]:
    """Kokoro voices on disk plus the reference recordings Qwen3-TTS can clone."""
    try:
        from engine.studio_audio import qwen3_voices
        ref = sorted(qwen3_voices())
    except Exception:
        ref = []
    return {"kokoro": kokoro_voices_on_disk(), "qwen3_tts": ref}


def _kokoro(text: str, voice: str, speed: float, out: Path) -> None:
    import numpy as np
    import soundfile as sf
    os.environ.setdefault("HF_HUB_OFFLINE", "1")   # a missing weight is an error, never a silent download
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from huggingface_hub import constants
    constants.HF_HUB_OFFLINE = True   # the env var is read at import; huggingface_hub may already be imported
    from kokoro import KPipeline
    lang = voice[0]
    if lang not in _pipes:
        _pipes[lang] = KPipeline(lang_code=lang, device=os.environ.get("PANELFLOW_KOKORO_DEVICE", "cpu"))
    chunks = [np.asarray(a.detach().cpu() if hasattr(a, "detach") else a) for _, _, a in _pipes[lang](text, voice=voice, speed=speed)]
    if not chunks:
        raise RuntimeError(f"Kokoro produced no audio for {text[:40]!r}")
    sf.write(str(out), np.concatenate(chunks), 24000, subtype="PCM_16")


def _qwen3(text: str, voice: str, speed: float, language: str, out: Path) -> None:
    from engine.studio_audio import qwen3_voices
    refs = qwen3_voices()
    if voice not in refs:
        raise RuntimeError(f"Qwen3-TTS has no voice {voice!r}; reference voices on disk: {', '.join(refs) or 'none'}")
    if not (_QWEN_PY.exists() and _QWEN_RUNNER.exists()):
        raise RuntimeError(f"Qwen3-TTS runner not found ({_QWEN_PY} / {_QWEN_RUNNER})")
    env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PYTHONIOENCODING": "utf-8"}
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "line.wav"
        p = subprocess.run([str(_QWEN_PY), str(_QWEN_RUNNER), "synth", "--text", text, "--output", str(raw), "--ref-audio", str(refs[voice]), "--language", language],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, env=env)
        if p.returncode != 0 or not raw.exists():
            raise RuntimeError(f"Qwen3-TTS: {(p.stderr or p.stdout)[-300:].strip()}")
        if abs(speed - 1.0) > 0.01:   # the runner has no speed control: change the tempo afterwards
            subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", str(raw), "-filter:a", f"atempo={min(max(speed, 0.5), 2.0):.3f}", str(out)], check=True, timeout=120)
        else:
            shutil.copyfile(raw, out)


def default_synth(text: str, voice: str, speed: float, provider: str, language: str, out: Path) -> None:
    if provider == "kokoro":
        _kokoro(text, voice, speed, out)
    elif provider == "qwen3_tts":
        _qwen3(text, voice, speed, language, out)
    else:
        raise RuntimeError(f"unknown speech provider {provider!r}")


class NarrationProvider:
    name = "narration"

    def __init__(self, synth: Callable[..., None] | None = None, slot: Any = None, voices: dict[str, list[str]] | None = None):
        self._synth, self._slot, self._voices = synth or default_synth, slot, voices
        self._errors: dict[str, str] = {}

    def _voice_list(self) -> dict[str, list[str]]:
        return self._voices if self._voices is not None else list_voices()

    def availability(self) -> Availability:
        have_kokoro = importlib.util.find_spec("kokoro") is not None
        have_qwen = _QWEN_PY.exists() and _QWEN_RUNNER.exists()
        if have_kokoro or have_qwen:
            return Availability(True, None)
        return Availability(False, "no speech model is installed (Kokoro is not importable and the Qwen3-TTS runner was not found)")

    def _problem(self, cue: Cue) -> str | None:
        if cue.kind != "narration":
            return None
        if not cue.text.strip():
            return "narration needs words: write the line first"
        provider = cue.provider or "kokoro"
        if provider not in PROVIDERS:
            return f"unknown speech provider {provider!r}; known: {', '.join(PROVIDERS)}"
        voices = self._voice_list().get(provider, [])
        if cue.voice and cue.voice not in voices:
            return f"{provider} has no voice {cue.voice!r}; available: {', '.join(voices) or 'none'}"
        if not cue.voice and not voices:
            return f"{provider} has no voices installed"
        return None

    def availability_for(self, cue: Cue) -> Availability:
        reason = self._problem(cue) or self._errors.get(cue.id)
        return Availability(reason is None, reason)

    def find(self, cue: Cue, out_dir: Path, plan: SoundPlan, limit: int = 1) -> list[Candidate]:
        if cue.kind != "narration" or self._problem(cue):
            return []
        provider = cue.provider or "kokoro"
        voice = cue.voice or self._voice_list()[provider][0]
        language = cue.hints.get("language", "English")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        gpu = provider == "qwen3_tts" and self._synth is default_synth
        if gpu:
            if not _ONE_AT_A_TIME.acquire(blocking=False):
                self._errors[cue.id] = "GPU busy: another audio job is running"
                return []
            slot, job = self._slot or ResourceSlot(), f"job_audiostudio_{cue.id}"
            try:
                got = slot.acquire(job)
            except Exception as e:
                got, why = False, f"GPU slot error: {e}"
            else:
                why = "GPU busy: the resource manager has no free slot"
            if not got:
                _ONE_AT_A_TIME.release()
                self._errors[cue.id] = why
                return []
        try:
            cands = []
            for i, factor in enumerate((1.0, 0.92, 1.08)[:max(1, limit)]):
                speed = round(max(0.5, min(2.0, cue.speed * factor)), 3)
                path = out_dir / f"{cue.id}_vo_{provider}_{i + 1}_{uuid.uuid4().hex[:6]}.wav"
                self._synth(cue.text.strip(), voice, speed, provider, language, path)
                if not path.is_file():
                    raise RuntimeError("the speech model wrote no file")
                lic, model = _MODEL[provider]
                cands.append(Candidate(id=path.stem[-14:], path=str(path), provider=self.name, label=f"{voice} at {speed:g}x",
                                       provenance=Provenance(source=f"tts/{provider}", licence=lic, model=model, author=voice)))
            self._errors.pop(cue.id, None)
            return cands
        except Exception as e:   # a failed line is reported, never replaced by another voice or a fake
            self._errors[cue.id] = f"{provider} failed: {e}"
            return []
        finally:
            if gpu:
                slot.release(job)
                _ONE_AT_A_TIME.release()
