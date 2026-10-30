"""Content-addressed artifact cache: root/<step>/<key>.json, written atomically."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def cache_key(step: str, inputs: Any, prompt_sha: str, model: str, params: dict) -> str:
    blob = json.dumps(
        {"step": step, "inputs": inputs, "prompt_sha": prompt_sha, "model": model, "params": params},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ArtifactCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, step: str, key: str) -> Path:
        return self.root / step / f"{key}.json"

    def get(self, step: str, key: str, model_cls: type[T]) -> T | list[T] | None:
        path = self._path(step, key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [model_cls.model_validate(d) for d in data]
        return model_cls.model_validate(data)

    def put(self, step: str, key: str, artifact: BaseModel | list[BaseModel]) -> Path:
        path = self._path(step, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            [a.model_dump(mode="json") for a in artifact]
            if isinstance(artifact, list)
            else artifact.model_dump(mode="json")
        )
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return path
