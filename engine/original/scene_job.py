"""The durable job behind POST /api/original/scene/generate: one scene plan -> one checked picture (engine/original/scene_run.py)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from engine.comfyui.art import ArtEngine
from engine.config.settings import settings
from engine.creative.mistakes import MistakeLedger
from engine.jobs.workflow import register_operation_factory
from engine.llm.registry import llm_registry
from engine.original.scene_plan import ScenePlan
from engine.original.scene_run import generate_scene

JOB_TYPE = "SCENE_GENERATION"
SCENE_ROOT = Path(__file__).resolve().parents[2] / "output" / "Original_Scenes"


def lessons_path() -> Path:
    return settings.app_data_dir / "config" / "scene_lessons.json"  # never the repo's vault ledger


def build_scene_operation(project_id: str, payload: dict):
    plan = ScenePlan(**payload["plan"])
    seed = payload.get("seed")

    def operation(db, progress, is_cancelled):
        provider = llm_registry.get_ollama_provider()  # local first, no cloud or mock fallback
        if not asyncio.run(provider.health_check()):
            raise RuntimeError("Ollama is not reachable")
        key, ws = uuid.uuid4().hex[:8], SCENE_ROOT / project_id
        progress(0.05, "drawing and checking the scene")
        result = generate_scene(ArtEngine(), provider, plan, ws=ws, key=key, seed=seed, ledger=MistakeLedger(file_path=lessons_path()), is_cancelled=is_cancelled)
        out = result.model_dump(mode="json")
        out["image_file"] = str(ws / out["image_path"])
        return out

    return operation


register_operation_factory(JOB_TYPE, build_scene_operation)
