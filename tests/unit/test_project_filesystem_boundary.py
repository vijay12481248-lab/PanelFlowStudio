"""Project filesystem boundary regressions (including user-selected external roots)."""
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from engine.api.routers.audio import stream_audio_file
from engine.api.routers.ocr import get_text_region_file
from engine.api.routers.pages import get_page_image_file, get_normalized_page_file
from engine.database.models import Base, PageRecord, PanelRecord, ProjectRecord, TextRegionRecord
from engine.projects.service import ProjectService
from engine.comfyui.service import _write_project_image


@pytest.fixture
def project_db(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        workspace = tmp_path / "user-selected" / "project"
        workspace.mkdir(parents=True)
        for name in ("source", "normalized", "panels", "text_regions"):
            (workspace / name).mkdir()
        project = ProjectRecord(id="project", title="p", source_type="LOCAL_FOLDER", workspace_path=str(workspace))
        page = PageRecord(id="page", project_id="project", sequence=1, filename="page.jpg")
        panel = PanelRecord(id="panel", project_id="project", page_id="page", sequence=1, page_sequence=1, x=0, y=0, width=10, height=10, crop_filename="panel.jpg")
        region = TextRegionRecord(id="region", project_id="project", page_id="page", panel_id="panel", sequence_in_panel=1, sequence_global=1, x=0, y=0, width=4, height=4, crop_filename="crop.jpg")
        db.add_all((project, page, panel, region))
        db.commit()
        yield db, workspace
    engine.dispose()


def _link(link: Path, target: Path):
    import os
    import subprocess
    if os.name == "nt" and target.is_dir():
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if result.returncode:
            pytest.skip(f"junctions unavailable: {result.stderr!r}")
        return
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")


def test_comfy_write_rejects_parent_swap_before_open(tmp_path, monkeypatch):
    from engine.comfyui import service as comfy_service
    workspace = tmp_path / "project"
    parent = workspace / "generated" / "comfyui"
    parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    original = comfy_service.resolve_contained_path
    swapped = False

    def swap_after_validation(root, candidate, **kwargs):
        nonlocal swapped
        result = original(root, candidate, **kwargs)
        if not swapped and str(candidate).endswith("image.png"):
            swapped = True
            parent.rename(parent.with_name("old"))
            _link(parent, outside)
        return result

    monkeypatch.setattr(comfy_service, "resolve_contained_path", swap_after_validation)
    with pytest.raises((ValueError, OSError, comfy_service.ComfyImageGenerationError)):
        _write_project_image(workspace, "generated/comfyui/image.png", b"data")
    assert not (outside / "image.png").exists()


def test_project_json_rejects_parent_swap_before_open(project_db, tmp_path, monkeypatch):
    from engine.projects import service as projects_service
    db, workspace = project_db
    outside = tmp_path / "outside"
    outside.mkdir()
    original = projects_service.open_contained_output

    def swap_before_open(root, candidate, **kwargs):
        workspace.rename(workspace.with_name("previous"))
        _link(workspace, outside)
        return original(root, candidate, **kwargs)

    monkeypatch.setattr(projects_service, "open_contained_output", swap_before_open)
    with pytest.raises((ValueError, OSError)):
        ProjectService(tmp_path / "default")._write_project_json(db.get(ProjectRecord, "project"))
    assert not (outside / "project.json").exists()


def test_delete_page_does_not_follow_swapped_source_directory(project_db, tmp_path, monkeypatch):
    from engine.projects import service as projects_service
    db, workspace = project_db
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "page.jpg").write_bytes(b"keep")
    original = projects_service.project_path
    swapped = False

    def swap_after_validation(*args, **kwargs):
        nonlocal swapped
        result = original(*args, **kwargs)
        if not swapped and args[1] == "source":
            swapped = True
            (workspace / "source").rename(workspace / "previous")
            _link(workspace / "source", outside)
        return result

    monkeypatch.setattr(projects_service, "project_path", swap_after_validation)
    try:
        ProjectService(tmp_path / "default").delete_page(db, "project", "page")
    except (ValueError, OSError):
        pass
    assert (outside / "page.jpg").read_bytes() == b"keep"


def test_delete_page_removes_regular_source_file(project_db, tmp_path):
    db, workspace = project_db
    source = workspace / "source" / "page.jpg"
    source.write_bytes(b"image")
    ProjectService(tmp_path / "default").delete_page(db, "project", "page")
    assert not source.exists()


def test_manifest_write_rejects_workspace_swap(project_db, tmp_path, monkeypatch):
    from engine.projects import service as projects_service
    db, workspace = project_db
    outside = tmp_path / "outside"
    outside.mkdir()
    original = projects_service.open_contained_output

    def swap_before_open(root, candidate, **kwargs):
        workspace.rename(workspace.with_name("previous"))
        _link(workspace, outside)
        return original(root, candidate, **kwargs)

    monkeypatch.setattr(projects_service, "open_contained_output", swap_before_open)
    with pytest.raises((ValueError, OSError)):
        ProjectService(tmp_path / "default").sync_manifest_with_db(db, "project")
    assert not (outside / "manifest.json").exists()



@pytest.mark.parametrize("endpoint,folder,field", [
    (get_page_image_file, "source", "filename"),
    (get_normalized_page_file, "source", "filename"),
    (get_text_region_file, "text_regions", "crop_filename"),
])
def test_file_endpoints_reject_parent_escape(project_db, tmp_path, endpoint, folder, field):
    db, workspace = project_db
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    item = db.get(PageRecord if folder == "source" else TextRegionRecord, "page" if folder == "source" else "region")
    setattr(item, field, "../../../secret.jpg")
    db.commit()
    with pytest.raises(HTTPException) as exc:
        endpoint("project", "page" if folder == "source" else "region", db)
    assert exc.value.status_code in (400, 404)


@pytest.mark.parametrize("endpoint,folder,item_id", [
    (get_page_image_file, "source", "page"),
    (get_normalized_page_file, "normalized", "page"),
    (get_text_region_file, "text_regions", "region"),
])
def test_file_endpoints_reject_symlink(project_db, tmp_path, endpoint, folder, item_id):
    db, workspace = project_db
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    name = "crop.jpg" if folder == "text_regions" else "page.jpg"
    _link(workspace / folder / name, outside)
    with pytest.raises(HTTPException) as exc:
        endpoint("project", item_id, db)
    assert exc.value.status_code in (400, 404)


def test_page_file_is_served_from_authorized_external_project(project_db):
    db, workspace = project_db
    (workspace / "source" / "page.jpg").write_bytes(b"image")
    response = get_page_image_file("project", "page", db)
    import asyncio

    async def read_response():
        return b"".join([chunk async for chunk in response.body_iterator])

    assert asyncio.run(read_response()) == b"image"


def test_page_response_keeps_opened_file_when_path_changes(project_db):
    import os
    if os.name == "nt":
        pytest.skip("Windows refuses to rename a file with an open reader handle")
    db, workspace = project_db
    source = workspace / "source" / "page.jpg"
    source.write_bytes(b"original")
    response = get_page_image_file("project", "page", db)
    source.rename(source.with_name("previous.jpg"))
    source.write_bytes(b"replacement")
    import asyncio

    async def read_response():
        return b"".join([chunk async for chunk in response.body_iterator])

    assert asyncio.run(read_response()) == b"original"


def test_audio_rejects_symlinked_workspace_root(project_db, tmp_path):
    db, workspace = project_db
    (workspace / "audio").mkdir()
    (workspace / "audio" / "track.wav").write_bytes(b"sound")
    link = tmp_path / "workspace-link"
    _link(link, workspace)
    db.get(ProjectRecord, "project").workspace_path = str(link)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        stream_audio_file("project", str(link / "audio" / "track.wav"), db)
    assert exc.value.status_code == 404


def test_service_delete_page_cannot_unlink_outside_project(project_db, tmp_path):
    db, workspace = project_db
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    db.get(PageRecord, "page").filename = "../../../secret.jpg"
    db.commit()
    with pytest.raises(ValueError):
        ProjectService(tmp_path / "default").delete_page(db, "project", "page")
    assert outside.read_bytes() == b"secret"
    assert db.get(PageRecord, "page") is not None


def test_service_rotate_page_cannot_modify_outside_project(project_db, tmp_path):
    db, workspace = project_db
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    db.get(PageRecord, "page").filename = "../../../secret.jpg"
    db.commit()
    with pytest.raises(ValueError):
        ProjectService(tmp_path / "default").rotate_page(db, "project", "page", 90)
    assert outside.read_bytes() == b"secret"


def test_service_blur_panel_cannot_modify_outside_project(project_db, tmp_path):
    db, workspace = project_db
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    db.get(PanelRecord, "panel").crop_filename = "../../../secret.jpg"
    db.commit()
    with pytest.raises(ValueError):
        ProjectService(tmp_path / "default").blur_entire_panel(db, "project", "panel")
    assert outside.read_bytes() == b"secret"


def test_service_ocr_region_cannot_read_outside_project(project_db, tmp_path):
    db, workspace = project_db
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    db.get(TextRegionRecord, "region").crop_filename = "../../../secret.jpg"
    db.commit()
    with pytest.raises(ValueError):
        ProjectService(tmp_path / "default").extract_ocr_region(db, "project", "region")


def test_explicit_external_project_directory_is_supported(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        outside_default = tmp_path / "chosen" / "book"
        project = ProjectService(tmp_path / "default").create_project(
            db, "Book", "LOCAL_FOLDER", "PUBLIC_DOMAIN",
            project_settings={"project_path": str(outside_default)},
        )
        assert Path(project.workspace_path) == outside_default
        assert (outside_default / "project.json").is_file()
    engine.dispose()


def test_project_creation_refuses_populated_external_directory(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    (chosen / "project.json").write_text("original", encoding="utf-8")
    with Session(engine) as db:
        with pytest.raises(ValueError, match="empty directory"):
            ProjectService(tmp_path / "default").create_project(
                db, "Book", "LOCAL_FOLDER", "PUBLIC_DOMAIN",
                project_settings={"project_path": str(chosen)},
            )
        assert (chosen / "project.json").read_text(encoding="utf-8") == "original"
        assert db.query(ProjectRecord).count() == 0
    engine.dispose()


def test_external_project_deletion_only_removes_its_own_directory(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = ProjectService(tmp_path / "default")
        chosen = tmp_path / "chosen" / "book"
        sibling = chosen.parent / "keep.txt"
        sibling.parent.mkdir()
        sibling.write_text("preserve", encoding="utf-8")
        project = svc.create_project(db, "Book", "LOCAL_FOLDER", "PUBLIC_DOMAIN", project_settings={"project_path": str(chosen)})
        with pytest.raises(NotImplementedError, match="handle-bound"):
            svc.delete_project(db, project.id)
        assert chosen.exists()
        assert sibling.read_text(encoding="utf-8") == "preserve"
        assert db.get(ProjectRecord, project.id) is not None
    engine.dispose()


def test_delete_project_refuses_unmarked_external_directory(project_db, tmp_path):
    db, workspace = project_db
    (workspace / "source" / "page.jpg").write_bytes(b"keep")
    with pytest.raises(NotImplementedError, match="handle-bound"):
        ProjectService(tmp_path / "default").delete_project(db, "project")
    assert (workspace / "source" / "page.jpg").read_bytes() == b"keep"
    assert db.get(ProjectRecord, "project") is not None


def test_delete_project_preserves_db_if_filesystem_deletion_fails(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        svc = ProjectService(tmp_path / "default")
        chosen = tmp_path / "other" / "book"
        project = svc.create_project(db, "Book", "LOCAL_FOLDER", "PUBLIC_DOMAIN", project_settings={"project_path": str(chosen)})

        def fail(_):
            raise PermissionError("locked")

        monkeypatch.setattr("engine.projects.service.shutil.rmtree", fail)
        with pytest.raises(NotImplementedError, match="handle-bound"):
            svc.delete_project(db, project.id)
        assert db.get(ProjectRecord, project.id) is not None
        assert chosen.is_dir()
    engine.dispose()


def test_ocr_unknown_engine_fails_closed(project_db):
    db, workspace = project_db
    with pytest.raises(KeyError):
        ProjectService(workspace.parent).extract_ocr_project(db, "project", engine_id="nonexistent-provider", operation_only=True)


def test_retry_rejects_missing_persisted_page_ids(project_db):
    db, workspace = project_db
    db.get(PageRecord, "page").status = "FAILED"
    db.commit()

    class Registry:
        def get_adapter_for(self, source):
            raise AssertionError("Missing retry page must fail before adapter selection")

    with pytest.raises(ValueError, match="page set"):
        ProjectService(workspace.parent).retry_failed_pages(
            db, "project", Registry(), page_ids=["page", "missing"], operation_only=True,
        )
