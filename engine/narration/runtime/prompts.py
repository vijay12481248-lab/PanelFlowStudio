"""Versioned prompt assets stored as files under engine/narration/prompts/<step>/<version>.md."""
from __future__ import annotations

import hashlib
from pathlib import Path
from string import Template

from pydantic import BaseModel

PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"


class PromptAsset(BaseModel):
    step: str
    version: str
    text: str
    sha256: str

    def render(self, **values: str) -> str:
        return Template(self.text).substitute(**values)  # KeyError on missing variable


def load_prompt(step: str, version: str = "v1") -> PromptAsset:
    data = (PROMPTS_ROOT / step / f"{version}.md").read_bytes().replace(b"\r\n", b"\n")  # checkout-EOL proof
    return PromptAsset(
        step=step,
        version=version,
        text=data.decode("utf-8"),
        sha256=hashlib.sha256(data).hexdigest(),
    )
