"""Role-based model configuration (vision / planner / writer / judge)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from engine.config.settings import settings

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "narration_models.yaml"
REQUIRED_ROLES = ("vision", "planner", "writer", "judge")


class RoleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    provider: Literal["ollama", "gemini"] = "ollama"  # gemini: Google's API with GEMINI_API_KEY, opt-in per role
    temperature: float
    top_p: float | None = None
    max_tokens: int
    num_ctx: int = 8192
    concurrency: int = Field(default=1, ge=1)
    timeout_s: float = 120.0


def _read_roles(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("roles") or {}


def load_roles(path: Path | None = None) -> dict[str, RoleConfig]:
    raw = _read_roles(path or DEFAULT_PATH)
    if path is None:
        user = settings.app_data_dir / "config" / "narration_models.yaml"
        if user.exists():
            raw = {**raw, **{k: {**raw.get(k, {}), **(v or {})} for k, v in _read_roles(user).items()}}
    missing = [r for r in REQUIRED_ROLES if r not in raw]
    if missing:
        raise ValueError(f"narration models config missing roles: {', '.join(missing)}")
    return {name: RoleConfig(**cfg) for name, cfg in raw.items()}


class TtsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    voice: str


class SttConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    device: str = "cpu"
    compute_type: str = "int8"


def _read_section(name: str, path: Path | None) -> dict:
    data = yaml.safe_load((path or DEFAULT_PATH).read_text(encoding="utf-8")) or {}
    raw = data.get(name) or {}
    if path is None:
        user = settings.app_data_dir / "config" / "narration_models.yaml"
        if user.exists():
            raw = {**raw, **((yaml.safe_load(user.read_text(encoding="utf-8")) or {}).get(name) or {})}
    return raw


def load_tts_config(path: Path | None = None) -> TtsConfig:
    return TtsConfig(**_read_section("tts", path))


def load_stt_config(path: Path | None = None) -> SttConfig:
    return SttConfig(**_read_section("stt", path))
