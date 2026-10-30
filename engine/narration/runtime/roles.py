"""Role-based model configuration (vision / planner / writer / judge)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from engine.config.settings import settings

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "narration_models.yaml"
REQUIRED_ROLES = ("vision", "planner", "writer", "judge")


class RoleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
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
            raw = {**raw, **{k: {**raw.get(k, {}), **v} for k, v in _read_roles(user).items()}}
    missing = [r for r in REQUIRED_ROLES if r not in raw]
    if missing:
        raise ValueError(f"narration models config missing roles: {', '.join(missing)}")
    return {name: RoleConfig(**cfg) for name, cfg in raw.items()}
