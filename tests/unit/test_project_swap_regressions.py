"""Deterministic check/use swaps at destructive and PIL output boundaries."""
import os
import shutil
import asyncio
import builtins
import hashlib
import io
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from engine.acquisition.downloader.pipeline import DownloadPipeline
from engine.acquisition.models import DownloadedPageResult, PageCandidate
from engine.audio.chapter_plan import plan_chapter_audio
from engine.audio.music_director import StoryAwareMusicDirector
from engine.audio.service import AudioService
from engine.api.routers.audio import analyze_panel_vision_endpoint
from engine.database.models import (
    AudioTimelineRecord,
    Base,
    NarrativeRecord,
    PageRecord,
    PanelRecord,
    ProjectRecord,
    ScriptSegmentRecord,
    TextRegionRecord,
    VideoScriptRecord,
)
from engine.projects.service import ProjectService
from engine.imaging.panels.detector import PanelBox, panel_detector
from engine.imaging.normalization.normalizer import page_normalizer
from engine.imaging.redaction import blur_entire_image
from engine.story.models import NarrativeDocument
from engine.story.service import StoryService
from engine.story.visual import _write
from engine.acquisition.downloader.validation import rotate_image_file


def _swap(directory: Path, outside: Path):
    from test_project_filesystem_boundary import _link
    directory.rename(directory.with_name(directory.name + "-previous"))
    _link(directory, outside)


def test_delete_project_swap_at_recursive_traversal_does_not_delete_outside(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        service = ProjectService(tmp_path / "default")
        project = service.create_project(db, "Book", "LOCAL_FOLDER", "PUBLIC_DOMAIN",
                                         project_settings={"project_path": str(tmp_path / "chosen" / "book")})
        workspace = Path(project.workspace_path)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "preserve.txt").write_text("keep")
        original = shutil.rmtree

        def swap_at_use(path, *args, **kwargs):
            workspace.rename(workspace.with_name("book-previous"))
            outside.rename(workspace)  # a real directory, not a symlink, now occupies the checked name
            return original(path, *args, **kwargs)

        monkeypatch.setattr("engine.projects.service.shutil.rmtree", swap_at_use)
        with pytest.raises((OSError, ValueError, NotImplementedError)):
            service.delete_project(db, project.id)
        assert (outside / "preserve.txt").read_text() == "keep"
        assert db.get(ProjectRecord, project.id) is not None
    engine.dispose()


def test_panel_crop_swap_at_pil_save_does_not_write_outside(tmp_path, monkeypatch):
    source = tmp_path / "page.jpg"
    Image.new("RGB", (20, 20), "red").save(source)
    project = tmp_path / "book"
    panels = project / "panels"
    panels.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    original = Image.Image.save
    swapped = False

    def swap_before_save(image, fp, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            _swap(panels, outside)
        return original(image, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", swap_before_save)
    box = PanelBox(id="p", page_id="page", sequence=1, x=0, y=0, width=10, height=10)
    with pytest.raises((OSError, ValueError)):
        panel_detector.extract_crop(source, box, panels / "crop.jpg")
    assert not (outside / "crop.jpg").exists()


@pytest.mark.parametrize("operation,folder,name", [
    (lambda source, output: page_normalizer.normalize_page(source, output), "normalized", "output.jpg"),
    (lambda source, output: blur_entire_image(output, backup=False), "panels", "output.jpg"),
    (lambda source, output: rotate_image_file(output, 90), "source", "output.jpg"),
])
def test_image_output_swap_at_pil_save_preserves_outside(tmp_path, monkeypatch, operation, folder, name):
    project = tmp_path / "book"
    directory = project / folder
    directory.mkdir(parents=True)
    source = project / "source.jpg"
    Image.new("RGB", (20, 20), "red").save(source)
    output = directory / name
    if folder in ("panels", "source"):
        shutil.copyfile(source, output)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / name).write_bytes(b"keep")
    original = Image.Image.save
    swapped = False

    def swap_before_save(image, fp, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            _swap(directory, outside)
        return original(image, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", swap_before_save)
    with pytest.raises((OSError, ValueError)):
        operation(source, output)
    assert (outside / name).read_bytes() == b"keep"


def test_story_checkpoint_swap_before_temp_write_preserves_outside(tmp_path, monkeypatch):
    cache = tmp_path / "book" / "story" / "vision_cache"
    cache.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    from engine.security import paths as security_paths
    original = security_paths.open_contained_output
    swapped = False

    def swap_before_write(root, candidate, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            _swap(cache, outside)
        return original(root, candidate, **kwargs)

    monkeypatch.setattr(security_paths, "open_contained_output", swap_before_write)
    with pytest.raises((OSError, ValueError)):
        _write(cache / "checkpoint.json", {"value": 1})
    assert not (outside / "checkpoint.json").exists()


def _db_with_project(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    workspace = tmp_path / "chosen" / "book"
    for directory in ("source", "normalized", "panels", "text_regions", "story", "script", "audio", "audio/dialogue", "audio/music"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    project = ProjectRecord(id="project", title="Book", source_type="LOCAL_FOLDER", workspace_path=str(workspace))
    page = PageRecord(id="page", project_id="project", sequence=1, filename="page.jpg", width=40, height=40)
    panel = PanelRecord(id="panel", project_id="project", page_id="page", sequence=1, page_sequence=1,
                        x=0, y=0, width=20, height=20, crop_filename="panel.jpg")
    db.add_all((project, page, panel))
    db.commit()
    return engine, db, workspace, project, page, panel


def test_acquisition_cached_asset_parent_swap_fails_closed(tmp_path, monkeypatch):
    class Adapter:
        calls = 0

        async def download_page(self, page, target, cancel):
            self.calls += 1
            data = b"verified image bytes"
            target.write_bytes(data)
            return DownloadedPageResult(sequence=page.sequence, source_uri=page.source_uri,
                                        target_path=target, filename=target.name, width=10, height=10,
                                        byte_size=len(data), sha256=hashlib.sha256(data).hexdigest())

    workspace = tmp_path / "book"
    adapter = Adapter()
    kwargs = dict(project_id="project", workspace_path=workspace, adapter=adapter,
                  candidates=[PageCandidate(sequence=1, source_uri="https://example.test/page.jpg")],
                  source_meta={}, rights_meta={}, chapter_meta={})
    _, manifest = asyncio.run(DownloadPipeline().execute(**kwargs))
    source = workspace / "source"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "page_0001.jpg").write_bytes(b"verified image bytes")
    original_is_file = Path.is_file
    swapped = False

    def swap_after_cached_check(path):
        nonlocal swapped
        result = original_is_file(path)
        if path == source / "page_0001.jpg" and result and not swapped:
            swapped = True
            _swap(source, outside)
        return result

    monkeypatch.setattr(Path, "is_file", swap_after_cached_check)
    with pytest.raises((OSError, ValueError)):
        asyncio.run(DownloadPipeline().execute(**kwargs, existing_manifest=manifest))
    assert (outside / "page_0001.jpg").read_bytes() == b"verified image bytes"


def test_acquisition_manifest_publication_does_not_replace_swapped_outside_file(tmp_path, monkeypatch):
    class Adapter:
        async def download_page(self, page, target, cancel):
            data = b"new image"
            target.write_bytes(data)
            return DownloadedPageResult(sequence=page.sequence, source_uri=page.source_uri,
                                        target_path=target, filename=target.name, width=10, height=10,
                                        byte_size=len(data), sha256=hashlib.sha256(data).hexdigest())

    workspace = tmp_path / "book"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "manifest.json").write_text("preserve", encoding="utf-8")
    original_replace = Path.replace
    swapped = False

    def swap_before_manifest_replace(path, target):
        nonlocal swapped
        if path.name.startswith("manifest.json.") and not swapped:
            swapped = True
            (outside / path.name).write_text("attacker temp", encoding="utf-8")
            workspace.rename(workspace.with_name("book-previous"))
            _link = __import__("test_project_filesystem_boundary")._link
            _link(workspace, outside)
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", swap_before_manifest_replace)
    asyncio.run(DownloadPipeline().execute(
        project_id="project", workspace_path=workspace, adapter=Adapter(),
        candidates=[PageCandidate(sequence=1, source_uri="https://example.test/page.jpg")],
        source_meta={}, rights_meta={}, chapter_meta={},
    ))
    assert (outside / "manifest.json").read_text(encoding="utf-8") == "preserve"
    assert json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))["project_id"] == "project"


def test_panel_cv2_decode_uses_bytes_captured_before_parent_swap(tmp_path, monkeypatch):
    workspace = tmp_path / "book"
    source = workspace / "source"
    source.mkdir(parents=True)
    image_path = source / "page.jpg"
    Image.new("RGB", (120, 100), "black").save(image_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    Image.new("RGB", (12, 10), "black").save(outside / "page.jpg")
    original_imread = cv2.imread

    def swapping_imread(path, *args, **kwargs):
        _swap(source, outside)
        return original_imread(path, *args, **kwargs)

    monkeypatch.setattr(cv2, "imread", swapping_imread)
    monkeypatch.setattr(panel_detector, "_detect_page_contours", lambda *args, **kwargs: [])
    boxes = panel_detector.detect_panels(image_path)
    assert max(box.width for box in boxes) > 50


def test_project_text_region_crop_uses_held_panel_bytes(tmp_path, monkeypatch):
    engine, db, workspace, project, page, panel = _db_with_project(tmp_path)
    try:
        Image.new("RGB", (20, 20), "red").save(workspace / "panels" / "panel.jpg")
        outside = tmp_path / "outside"
        outside.mkdir()
        Image.new("RGB", (20, 20), "blue").save(outside / "panel.jpg")
        from engine.imaging.text_regions import TextRegionBox
        import engine.imaging.text_regions as text_regions

        class Detector:
            def detect(self, **kwargs):
                return [TextRegionBox(id="region", project_id="project", page_id="page", panel_id="panel",
                                      x=0, y=0, width=10, height=10)]

        monkeypatch.setattr(text_regions, "ClassicalTextRegionDetector", Detector)
        original_open = Image.open
        swapped = False

        def swap_before_path_open(fp, *args, **kwargs):
            nonlocal swapped
            if isinstance(fp, (str, Path)) and Path(fp).name == "panel.jpg" and not swapped:
                swapped = True
                _swap(workspace / "panels", outside)
            return original_open(fp, *args, **kwargs)

        monkeypatch.setattr(Image, "open", swap_before_path_open)
        records = ProjectService(tmp_path / "default").detect_text_regions_project(db, "project")
        crop = workspace / "text_regions" / records[0].crop_filename
        with original_open(crop) as image:
            assert image.convert("RGB").getpixel((2, 2))[0] > image.convert("RGB").getpixel((2, 2))[2]
    finally:
        db.close()
        engine.dispose()


def test_story_sidecar_read_rejects_parent_swap(tmp_path, monkeypatch):
    engine, db, workspace, project, *_ = _db_with_project(tmp_path)
    try:
        original_doc = NarrativeDocument(project_id="project")
        (workspace / "story" / "narrative.json").write_text(original_doc.model_dump_json(), encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "narrative.json").write_text(NarrativeDocument(project_id="outside").model_dump_json(), encoding="utf-8")
        original_read_text = Path.read_text
        swapped = False

        def swap_before_read(path, *args, **kwargs):
            nonlocal swapped
            if path.name == "narrative.json" and not swapped:
                swapped = True
                _swap(workspace / "story", outside)
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", swap_before_read)
        assert StoryService().get_narrative(db, "project").project_id == "project"
    finally:
        db.close()
        engine.dispose()


def test_audio_timeline_write_does_not_follow_swapped_audio_directory(tmp_path, monkeypatch):
    engine, db, workspace, project, *_ = _db_with_project(tmp_path)
    try:
        script = VideoScriptRecord(id="script", project_id="project", status="APPROVED")
        segment = ScriptSegmentRecord(id="segment", script_id="script", project_id="project", scene_id="scene",
                                      sequence=1, type="NARRATOR", text="Hello", estimated_duration=1,
                                      source_evidence={"panel_ids": ["panel"]})
        db.add_all((script, segment))
        db.commit()
        audio = workspace / "audio"
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "master_audio_timeline.json").write_text("preserve", encoding="utf-8")
        wav = audio / "dialogue" / "speech.wav"
        import soundfile as sf
        sf.write(str(wav), np.zeros(8000), 8000)

        service = AudioService()
        service.synthesizer = SimpleNamespace(
            adapter_factory=True,
            synthesize_batch=lambda *args, **kwargs: [{"id": "segment", "success": True, "audio_path": str(wav), "duration": 1.0}],
        )
        original_open = builtins.open
        swapped = False

        def swap_before_timeline_open(file, *args, **kwargs):
            nonlocal swapped
            if Path(file).name == "master_audio_timeline.json" and not swapped:
                swapped = True
                _swap(audio, outside)
            return original_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", swap_before_timeline_open)
        service.generate_audio_timeline(db, "project", tts_provider_id="chatterbox_turbo",
                                        tts_model_name="ChatterboxTurboTTS")
        assert (outside / "master_audio_timeline.json").read_text(encoding="utf-8") == "preserve"
        assert json.loads((audio / "master_audio_timeline.json").read_text(encoding="utf-8"))["total_duration_sec"] > 0
    finally:
        db.close()
        engine.dispose()


def test_audio_plan_and_music_metadata_writes_avoid_pathname_swap(tmp_path, monkeypatch):
    workspace = tmp_path / "book"
    (workspace / "audio" / "music").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    original_write_text = Path.write_text
    swapped = False

    def swap_before_sidecar_write(path, data, *args, **kwargs):
        nonlocal swapped
        if path.name in {"chapter_audio_plan.json", "music_direction_plan.json"} and not swapped:
            swapped = True
            _swap(workspace / "audio", outside)
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", swap_before_sidecar_write)
    plan_chapter_audio(workspace, {}, [], {"total_duration_sec": 1, "intervals": []})
    assert not (outside / "chapter_audio_plan.json").exists()
    assert (workspace / "audio" / "chapter_audio_plan.json").is_file()


@pytest.mark.asyncio
async def test_on_demand_vision_crop_uses_held_source_bytes(tmp_path, monkeypatch):
    engine, db, workspace, project, page, panel = _db_with_project(tmp_path)
    try:
        Image.new("RGB", (40, 40), "red").save(workspace / "source" / "page.jpg")
        outside = tmp_path / "outside"
        outside.mkdir()
        Image.new("RGB", (40, 40), "blue").save(outside / "page.jpg")
        original_open = Image.open
        swapped = False

        def swap_before_path_open(fp, *args, **kwargs):
            nonlocal swapped
            if isinstance(fp, (str, Path)) and Path(fp).name == "page.jpg" and not swapped:
                swapped = True
                _swap(workspace / "source", outside)
            return original_open(fp, *args, **kwargs)

        class Provider:
            vision_model = "test"
            async def health_check(self): return True
            async def analyze_vision(self, image, prompt, model):
                with original_open(image) as crop:
                    pixel = crop.convert("RGB").getpixel((2, 2))
                return "red" if pixel[0] > pixel[2] else "blue"

        monkeypatch.setattr(Image, "open", swap_before_path_open)
        monkeypatch.setattr("engine.llm.registry.llm_registry.get_ollama_provider", lambda: Provider())
        result = await analyze_panel_vision_endpoint("project", "panel", db=db)
        assert result["visual_description"] == "red"
    finally:
        db.close()
        engine.dispose()
