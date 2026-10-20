import asyncio
import json

import pytest

from engine.story.models import PanelObservationEntity
from engine.story.section_planner import SectionPlanner, ReconstructionError
from engine.llm.errors import GenerationLimitError


def observations(count=48):
    return [PanelObservationEntity(panel_id=f"actual-panel-uuid-{index}", sequence_global=index,
                                   visual_summary=f"The guard watches traveler {index} at the gate.") for index in range(1, count + 1)]


class Provider:
    provider_id = "fixture"

    def __init__(self):
        self.calls = []
        self.fail_at = None
        self.split = False
        self.omit_cast = False
        self.unknown_cast = False

    async def generate_structured(self, prompt, response_model, **kwargs):
        data = json.loads(prompt.split("SOURCE_DATA:\n", 1)[1])
        self.calls.append((data, kwargs))
        if self.fail_at == len(self.calls):
            raise TimeoutError("temporary network failure")
        if self.split and len(data["panels"]) > 6:
            raise GenerationLimitError("length", 3072, 3072)
        first, last = data["panels"][0]["panel"], data["panels"][-1]["panel"]
        return response_model.model_validate({
            "summary": "The guard watches a traveler approach.",
            "locations": [], "events": [], "relationships": [],
            "actors": [] if data["known_actors"] or self.omit_cast else [{"key": 1, "name": "Guard", "appearance": "ivory coat", "panels": [first]}],
            "scenes": [{"start": first, "end": last, "title": "At the gate", "summary": "The guard waits.", "characters": [999] if self.unknown_cast else [1]}],
            "beats": [{"scene": 1, "panels": list(dict.fromkeys([first, last])), "summary": "A traveler approaches."}],
        })


def test_48_panels_use_four_small_requests_and_real_reference_mapping(tmp_path):
    provider = Provider()
    progress = []
    chapter = asyncio.run(SectionPlanner().reconstruct(observations(), provider, tmp_path, progress=lambda *args: progress.append(args)))
    assert len(provider.calls) == 4
    assert all(len(data["panels"]) <= 12 and kwargs["max_tokens"] <= 3072 and kwargs["max_repair_retries"] == 0 for data, kwargs in provider.calls)
    assert all("actual-panel-uuid" not in json.dumps(data) for data, _ in provider.calls)
    assert len(chapter["characters"]) == 1
    assert chapter["scenes"][-1]["panel_end"] == "actual-panel-uuid-48"
    assert all(scene["character_ids"] == ["actor_1"] for scene in chapter["scenes"])
    assert progress[-1][0] > 0.9


def test_sections_resume_without_repeating_completed_model_calls(tmp_path):
    provider = Provider()
    provider.fail_at = 2
    with pytest.raises(TimeoutError):
        asyncio.run(SectionPlanner().reconstruct(observations(24), provider, tmp_path))
    provider.calls.clear()
    provider.fail_at = None
    asyncio.run(SectionPlanner().reconstruct(observations(24), provider, tmp_path))
    assert len(provider.calls) == 1
    assert provider.calls[0][0]["panels"][0]["panel"] == 13


def test_output_limit_shrinks_only_oversized_section_and_resumes_split_cache(tmp_path):
    provider = Provider()
    provider.split = True
    chapter = asyncio.run(SectionPlanner().reconstruct(observations(12), provider, tmp_path))
    assert [len(data["panels"]) for data, _ in provider.calls] == [12, 6, 6]
    assert len(chapter["scenes"]) == 2
    provider.calls.clear()
    asyncio.run(SectionPlanner().reconstruct(observations(12), provider, tmp_path))
    assert not provider.calls


def test_cancellation_before_request_does_not_call_model(tmp_path):
    provider = Provider()
    with pytest.raises(ValueError, match="cancelled"):
        asyncio.run(SectionPlanner().reconstruct(observations(), provider, tmp_path, cancelled=lambda: True))
    assert not provider.calls


def test_editing_late_source_panel_reuses_earlier_sections(tmp_path):
    provider = Provider()
    items = observations(24)
    asyncio.run(SectionPlanner().reconstruct(items, provider, tmp_path))
    provider.calls.clear()
    items[-1].visual_summary = "The traveler opens the gate."
    asyncio.run(SectionPlanner().reconstruct(items, provider, tmp_path))
    assert len(provider.calls) == 1
    assert provider.calls[0][0]["panels"][0]["panel"] == 13


def test_persistent_small_section_failure_is_non_retryable(tmp_path):
    class Limited(Provider):
        async def generate_structured(self, *args, **kwargs):
            self.calls.append(1)
            raise GenerationLimitError("length")
    provider = Limited()
    with pytest.raises(ReconstructionError) as error:
        asyncio.run(SectionPlanner().reconstruct(observations(12), provider, tmp_path))
    assert error.value.retryable is False
    assert len(provider.calls) == 3  # 12 -> 6 -> 3, without replaying the chapter


def test_worker_does_not_retry_deterministic_reconstruction_failure():
    import time
    import uuid
    from engine.database.models import Base, ProjectRecord
    from engine.database.session import SessionLocal, engine
    from engine.jobs.manager import JobManager
    Base.metadata.create_all(engine)
    project_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(ProjectRecord(id=project_id, title="Bounded retry test", source_type="LOCAL_FOLDER",
                             rights_status="PUBLIC_DOMAIN", workspace_path="/test"))
        db.commit()
    manager = JobManager()
    job = manager.create_job(project_id, "STORY_ANALYSIS", max_retries=3)
    calls = []
    async def operation(token, progress):
        calls.append(1)
        raise ReconstructionError("Small section still invalid")
    manager.enqueue_async(job.job_id, operation)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = manager.get_job(job.job_id)
        if state["status"] == "FAILED":
            break
        time.sleep(0.01)
    assert state["status"] == "FAILED"
    assert state["retry_count"] == 0
    assert calls == [1]


def test_visible_cast_cannot_be_silently_omitted_for_speed(tmp_path):
    provider = Provider()
    provider.omit_cast = True
    items = observations(3)
    items[0].visible_character_candidates = ["guard in an ivory coat"]
    with pytest.raises(ReconstructionError):
        asyncio.run(SectionPlanner().reconstruct(items, provider, tmp_path))


def test_unknown_cast_is_not_invented_and_requires_review(tmp_path):
    provider = Provider()
    provider.unknown_cast = True
    chapter = asyncio.run(SectionPlanner().reconstruct(observations(3), provider, tmp_path))
    assert chapter["scenes"][0]["character_ids"] == []
    assert chapter["reconstruction_metadata"]["review_notes"]
    assert all(actor["character_id"] != "actor_999" for actor in chapter["characters"])


def test_checkpoint_failure_does_not_repeat_generation_with_smaller_sections(tmp_path, monkeypatch):
    from engine.story import visual
    provider = Provider()
    def fail_write(*args):
        raise ValueError("checkpoint output path unavailable")
    monkeypatch.setattr(visual, "_write", fail_write)
    with pytest.raises(ValueError, match="output path unavailable"):
        asyncio.run(SectionPlanner().reconstruct(observations(12), provider, tmp_path))
    assert len(provider.calls) == 1
