"""The durable job behind POST /api/original/scene/generate: one scene plan -> one checked picture (engine/original/scene_run.py)."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from engine.comfyui.art import ArtEngine
from engine.comfyui.edit_prompt import release_local_model
from engine.config.settings import settings
from engine.creative.mistakes import MistakeLedger
from engine.jobs.workflow import register_operation_factory
from engine.llm.registry import llm_registry
from engine.original import scene_store
from engine.original.crosscheck import cross_check
from engine.original.judges import default_judges
from engine.original.scene_plan import ScenePlan, load_playbook
from engine.original.scene_run import generate_scene

JOB_TYPE = "SCENE_GENERATION"
SCENE_ROOT = Path(__file__).resolve().parents[2] / "output" / "Original_Scenes"


def lessons_path() -> Path:
    return settings.app_data_dir / "config" / "scene_lessons.json"  # never the repo's vault ledger


def analyse(db, run_id: str, provider, plan: ScenePlan, image: Path) -> None:
    """The two judges look at the delivered picture one after the other and cross-check each other; whatever happens is stored, nothing is raised."""
    try:
        playbook = load_playbook(plan.scene_type)
        groups = playbook.state_groups
        same = lambda a, b: a == b or any(a in g and b in g for g in groups)
        cc = asyncio.run(cross_check(default_judges(provider), image.read_bytes(), [*playbook.action_states, "other"], same_state=same, between=release_local_model))
        scene_store.save_analysis(db, run_id, cc.model_dump(mode="json"))
    except Exception as exc:
        try:
            scene_store.save_analysis(db, run_id, None, error=f"{type(exc).__name__}: {exc}"[:300])
        except Exception:
            pass


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
        try:  # saving the run must never lose the picture
            run = scene_store.create_run(db, project_id=project_id, job_id=None, brief=plan.brief, plan=plan.model_dump(mode="json"), image_path=out["image_path"], result=out)
            out["run_id"] = run["id"]
        except Exception as exc:
            out["run_error"] = f"{type(exc).__name__}: {exc}"[:300]
            return out
        progress(0.8, "two vision models are reviewing the picture")
        analyse(db, run["id"], provider, plan, ws / out["image_path"])
        return out

    return operation


register_operation_factory(JOB_TYPE, build_scene_operation)
