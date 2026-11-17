"""Text embedders for the guide model: what an action description becomes before it conditions the diffusion transformer.

Two named embedders; the one used for training is saved in the checkpoint and used again for generation (a checkpoint is never
asked for a different embedder than it learned):

- `hash`  the old bag-of-words hash. Offline and instant, but "kick" and "strike" are unrelated and so are all synonyms.
- `clip`  the CLIP-L text encoder that ComfyUI already has on disk for HiDream (`models/text_encoders/clip_l_hidream.safetensors`, 123 M
          parameters, runs on CPU in about 0.1 s per batch) with the tokenizer ComfyUI ships (`comfy/sd1_tokenizer`). Its 768-number text
          embedding is reduced to `dim` numbers by a fixed random projection (seeded, so the same text always gives the same vector).
          Nothing is downloaded. Missing files are an error, never a silent fallback to the hash.

Measured 2026-11-17 on 12 action phrases in 4 groups (kick, sword, walk, calm): the nearest other phrase belongs to the same group for 12/12
phrases with `clip` and 5/12 with `hash`. Small sample; see docs/MOTION_BANK.md. (Ollama's qwen3.5:9b was tried first: /api/embed answers 501.)
"""
from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from typing import Sequence

import numpy as np
import torch

EMBEDDERS = ("hash", "clip")
PROJECTION_SEED = 20261117
_COMFY = Path(os.environ.get("PANELFLOW_COMFYUI_DIR", r"E:\VIJAY SEKAR\ComfyUI"))
CLIP_WEIGHTS = Path(os.environ.get("PANELFLOW_CLIP_TEXT_ENCODER", str(_COMFY / "models" / "text_encoders" / "clip_l_hidream.safetensors")))
CLIP_TOKENIZER_DIR = Path(os.environ.get("PANELFLOW_CLIP_TOKENIZER_DIR", str(_COMFY / "comfy" / "sd1_tokenizer")))

_clip_lock = threading.Lock()
_clip_cache: dict = {}


class TextEmbedderError(RuntimeError):
    """The chosen embedder could not produce vectors (for example its model files are missing)."""


def embed_hash(text: str, dim: int = 256) -> torch.Tensor:
    """Deterministic bag-of-words hash embedding (unit length)."""
    words = text.lower().replace(",", " ").split()
    vec = torch.zeros(dim, dtype=torch.float32)
    for word in words:
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
        for i in range(8):
            idx = (h >> (i * 8)) % dim
            sign = 1.0 if ((h >> (i * 8 + 4)) & 1) else -1.0
            vec[idx] += sign
    norm = torch.norm(vec)
    return vec / max(1e-5, float(norm))


def _project(vectors: np.ndarray, dim: int) -> np.ndarray:
    """Fixed seeded Gaussian projection to `dim` numbers (keeps cosine similarity approximately), then unit length."""
    rng = np.random.default_rng(PROJECTION_SEED)
    matrix = rng.standard_normal((vectors.shape[1], dim)).astype(np.float32) / np.sqrt(dim)
    out = vectors.astype(np.float32) @ matrix
    return (out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-6)).astype(np.float32)


def _load_clip():
    """(tokenizer, model), loaded once. The weights are a long-CLIP-L text tower in Hugging Face key order."""
    with _clip_lock:
        key = (str(CLIP_WEIGHTS), str(CLIP_TOKENIZER_DIR))
        if key in _clip_cache:
            return _clip_cache[key]
        if not CLIP_WEIGHTS.is_file():
            raise TextEmbedderError(f"The text embedder 'clip' needs {CLIP_WEIGHTS} (the CLIP-L ComfyUI uses for HiDream); it is not there")
        if not (CLIP_TOKENIZER_DIR / "vocab.json").is_file():
            raise TextEmbedderError(f"The text embedder 'clip' needs the CLIP tokenizer files in {CLIP_TOKENIZER_DIR}; they are not there")
        try:
            from safetensors.torch import load_file
            from transformers import CLIPTextConfig, CLIPTextModelWithProjection, CLIPTokenizer

            config = CLIPTextConfig(
                vocab_size=49408, hidden_size=768, intermediate_size=3072, num_hidden_layers=12, num_attention_heads=12,
                max_position_embeddings=248, projection_dim=768, hidden_act="quick_gelu",
                bos_token_id=49406, eos_token_id=49407, pad_token_id=49407,
            )
            model = CLIPTextModelWithProjection(config)
            missing, unexpected = model.load_state_dict({k: v.float() for k, v in load_file(str(CLIP_WEIGHTS)).items()}, strict=False)
            missing = [m for m in missing if "position_ids" not in m]
            if missing or unexpected:
                raise TextEmbedderError(f"{CLIP_WEIGHTS.name} does not match a CLIP-L text encoder (missing {missing[:3]}, unexpected {unexpected[:3]})")
            _clip_cache[key] = (CLIPTokenizer.from_pretrained(str(CLIP_TOKENIZER_DIR)), model.eval())
        except TextEmbedderError:
            raise
        except Exception as exc:
            raise TextEmbedderError(f"Could not load the CLIP text encoder: {exc}") from exc
        return _clip_cache[key]


def embed_clip(texts: Sequence[str], dim: int = 256) -> torch.Tensor:
    """[N, dim] unit vectors from the local CLIP-L text encoder."""
    tokenizer, model = _load_clip()
    with torch.no_grad():
        batch = tokenizer(list(texts), padding=True, truncation=True, max_length=77, return_tensors="pt")
        raw = model(**batch).text_embeds.numpy()
    return torch.from_numpy(_project(raw, dim))


def embed_texts(texts: Sequence[str], embedder: str = "hash", dim: int = 256) -> torch.Tensor:
    """[N, dim] embeddings of `texts` with the named embedder."""
    if embedder == "hash":
        return torch.stack([embed_hash(t, dim) for t in texts]) if texts else torch.zeros((0, dim))
    if embedder == "clip":
        return embed_clip(texts, dim) if texts else torch.zeros((0, dim))
    raise ValueError(f"unknown text embedder '{embedder}'; choose one of {EMBEDDERS}")


def embed_one(text: str, embedder: str = "hash", dim: int = 256) -> torch.Tensor:
    return embed_texts([text], embedder, dim)[0]
