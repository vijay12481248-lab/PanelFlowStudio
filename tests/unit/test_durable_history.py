"""Real SQLite history transactions, not frontend-only snapshot restoration."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from engine.database.models import Base, OCRRecord, ProjectRecord, PanelRecord, PageRecord, TextRegionRecord


def test_server_history_adapter_exists():
    assert importlib.util.find_spec("engine.history") is not None, "SQLite project history is not implemented"


@pytest.fixture
def history(tmp_path):
    from engine.history.service import ProjectHistory
    engine = create_engine(f"sqlite:///{tmp_path / 'history.sqlite'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    initial = {"project_id": "p", "scenes": [], "narration_clips": [], "bgm_tracks": [], "aspect_ratio": "16:9", "is_playing": False, "playhead_sec": 0}
    with Session(engine) as db:
        db.add(ProjectRecord(id="p", title="History fixture", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path), settings={"story_editor_state": initial, "unrelated": "preserve"}))
        db.add(ProjectRecord(id="other", title="Other", source_type="LOCAL_FOLDER", workspace_path=str(tmp_path)))
        db.commit()
    yield engine, ProjectHistory(), initial
    engine.dispose()


def execute(service, db, state, revision=0, op=None):
    return service.execute(db, "p", operation_id=op or str(uuid4()), expected_revision=revision,
                           command_type="editor.replace", version=1, label="Edit story", input={"state": state})


def move(service, db, direction, revision, op=None):
    return service.move(db, "p", direction=direction, operation_id=op or str(uuid4()), expected_revision=revision)


def test_editor_execute_undo_redo_survive_new_sessions(history):
    engine, service, initial = history
    edited = {**initial, "aspect_ratio": "9:16"}
    with Session(engine) as db:
        reply = execute(service, db, edited)
        assert reply["history"]["revision"] == 1
        assert reply["history"]["undoCount"] == 1
    with Session(engine) as db:
        reply = move(service, db, "undo", 1)
        assert reply["state"]["aspect_ratio"] == "16:9"
        assert db.get(ProjectRecord, "p").settings["unrelated"] == "preserve"
    with Session(engine) as db:
        reply = move(service, db, "redo", 2)
        assert reply["state"]["aspect_ratio"] == "9:16"
        assert reply["history"]["revision"] == 3


def test_transaction_failure_rolls_back_domain_journal_and_receipt(history, monkeypatch):
    engine, service, initial = history
    from engine.history.models import HistoryRecord, HistoryReceipt
    with Session(engine) as db:
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(OSError("fixture disk failure")))
        with pytest.raises(OSError, match="disk failure"):
            execute(service, db, {**initial, "aspect_ratio": "1:1"})
    with Session(engine) as db:
        assert db.get(ProjectRecord, "p").settings["story_editor_state"] == initial
        assert db.query(HistoryRecord).count() == 0
        assert db.query(HistoryReceipt).count() == 0


def test_idempotent_retry_returns_canonical_state_without_reapplying(history):
    engine, service, initial = history
    op = str(uuid4()); edited = {**initial, "aspect_ratio": "9:16"}
    with Session(engine) as db:
        execute(service, db, edited, op=op)
        move(service, db, "undo", 1)
        reply = execute(service, db, edited, op=op)
        assert reply["replayed"] is True
        assert reply["operation_revision"] == 1
        assert reply["history"]["revision"] == 2
        assert reply["state"]["aspect_ratio"] == "16:9"
        with pytest.raises(Exception, match="operation ID"):
            execute(service, db, {**initial, "aspect_ratio": "1:1"}, op=op)


def test_noop_keeps_redo_and_new_edit_truncates_it(history):
    engine, service, initial = history
    with Session(engine) as db:
        execute(service, db, {**initial, "aspect_ratio": "9:16"})
        move(service, db, "undo", 1)
        reply = execute(service, db, {**initial, "playhead_sec": 50, "is_playing": True}, revision=2)
        assert reply["history"]["revision"] == 2
        assert reply["history"]["canRedo"] is True
        reply = execute(service, db, {**initial, "aspect_ratio": "1:1"}, revision=2)
        assert reply["history"]["canRedo"] is False


def test_concurrent_writers_with_same_revision_have_one_winner(history):
    engine, service, initial = history
    def writer(ratio):
        with Session(engine) as db:
            try:
                execute(service, db, {**initial, "aspect_ratio": ratio})
                return "ok"
            except Exception as error:
                return getattr(error, "code", str(error))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, ["9:16", "1:1"]))
    assert sorted(results) == ["CONFLICT", "ok"]
    with Session(engine) as db:
        assert service.read(db, "p")["history"]["revision"] == 1


def test_legacy_database_writes_invalidate_undo_instead_of_overwriting_them(history):
    engine, service, initial = history
    with Session(engine) as db:
        execute(service, db, {**initial, "aspect_ratio": "9:16"})
        project = db.get(ProjectRecord, "p")
        project.settings = {**project.settings, "story_editor_state": {**initial, "aspect_ratio": "1:1"}}
        db.commit()
        assert service.read(db, "p")["history"]["conflicted"] is True
        with pytest.raises(Exception) as caught:
            move(service, db, "undo", 1)
        assert caught.value.code == "CONFLICT"
        assert db.get(ProjectRecord, "p").settings["story_editor_state"]["aspect_ratio"] == "1:1"


def test_reset_requires_current_fingerprint_and_archives_old_history(history):
    engine, service, initial = history
    from engine.history.models import HistoryArchive
    with Session(engine) as db:
        execute(service, db, {**initial, "aspect_ratio": "9:16"})
        with pytest.raises(Exception):
            service.reset(db, "p", operation_id=str(uuid4()), expected_revision=1, fingerprint="stale")
        current = service.read(db, "p")
        reply = service.reset(db, "p", operation_id=str(uuid4()), expected_revision=1, fingerprint=current["history"]["fingerprint"])
        assert reply["history"]["undoCount"] == 0
        assert reply["state"]["aspect_ratio"] == "9:16"
        assert db.query(HistoryArchive).count() == 1


def test_retention_keeps_ids_baseline_and_bounds_reachable_undo(history):
    engine, _, initial = history
    from engine.history.service import ProjectHistory
    service = ProjectHistory(max_entries=2)
    with Session(engine) as db:
        for revision, ratio in enumerate(["9:16", "1:1", "16:9"]): execute(service, db, {**initial, "aspect_ratio": ratio}, revision=revision)
        move(service, db, "undo", 3); move(service, db, "undo", 4)
        reply = move(service, db, "undo", 5)
        assert reply["state"]["aspect_ratio"] == "9:16"
        assert reply["history"]["revision"] == 5


def test_unknown_versions_invalid_state_and_foreign_scope_never_change_data(history):
    engine, service, initial = history
    with Session(engine) as db:
        for version, state in [(99, initial), (1, {**initial, "project_id": "other"}), (1, {**initial, "scenes": "bad"})]:
            with pytest.raises(Exception):
                service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0, command_type="editor.replace", version=version, label="Invalid", input={"state": state})
        assert service.read(db, "p")["history"]["undoCount"] == 0
        assert db.get(ProjectRecord, "other").settings == {}


def test_history_does_not_store_engine_url_credentials(history):
    engine, service, initial = history
    from engine.history.models import HistoryRecord
    with Session(engine) as db:
        state = {**initial, "scenes": [{"id": "s", "layers": [{"id": "l", "image_url": "http://127.0.0.1:8765/api/projects/p/panels/panel/file;pf-token=secret?engine_token=secret&v=2"}]}]}
        execute(service, db, state)
        assert "secret" not in str(db.get(HistoryRecord, "p").entries)
        assert "secret" not in str(db.get(ProjectRecord, "p").settings)
        assert "v=2" in str(db.get(HistoryRecord, "p").entries)


def test_oversized_command_fails_before_domain_mutation(history):
    engine, _, initial = history
    from engine.history.service import ProjectHistory
    with Session(engine) as db:
        with pytest.raises(Exception) as caught:
            execute(ProjectHistory(max_bytes=500), db, {**initial, "text": "x" * 2000})
        assert caught.value.code == "CAPACITY"
        assert db.get(ProjectRecord, "p").settings["story_editor_state"] == initial


def test_unsupported_journal_is_inspectable_and_can_be_archived_without_executing_it(history):
    engine, service, initial = history
    from engine.history.models import HistoryRecord, HistoryArchive
    with Session(engine) as db:
        execute(service, db, {**initial, "aspect_ratio": "9:16"})
        head = db.get(HistoryRecord, "p"); head.schema_version = 99; db.commit()
        inspected = service.read(db, "p")
        assert inspected["history"]["recoveryRequired"] is True
        assert inspected["history"]["canUndo"] is False
        with pytest.raises(Exception): move(service, db, "undo", 1)
        reply = service.reset(db, "p", operation_id=str(uuid4()), expected_revision=1, fingerprint=inspected["history"]["fingerprint"])
        assert reply["history"]["recoveryRequired"] is False
        assert reply["state"]["aspect_ratio"] == "9:16"
        assert db.query(HistoryArchive).one().journal["schemaVersion"] == 99


def test_corrupt_stored_command_label_is_blocked_not_executed(history):
    engine, service, initial = history
    from engine.history.models import HistoryRecord
    with Session(engine) as db:
        execute(service, db, {**initial, "aspect_ratio": "9:16"})
        head = db.get(HistoryRecord, "p"); entries = deepcopy(head.entries); del entries[0]["label"]; head.entries = entries; db.commit()
        assert service.read(db, "p")["history"]["recoveryRequired"] is True
        with pytest.raises(Exception): move(service, db, "undo", 1)
        assert db.get(ProjectRecord, "p").settings["story_editor_state"]["aspect_ratio"] == "9:16"


def test_panel_reorder_restores_rows_and_manifest_after_reopen(history, tmp_path):
    engine, service, _ = history
    from engine.projects.service import project_service

    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        db.add(PageRecord(id="page", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add_all([
            PanelRecord(id="one", project_id="p", page_id="page", sequence=1, page_sequence=1, x=0, y=0, width=50, height=50, crop_filename="one.jpg"),
            PanelRecord(id="two", project_id="p", page_id="page", sequence=2, page_sequence=2, x=50, y=0, width=50, height=50, crop_filename="two.jpg"),
        ])
        db.commit()
        project_service._sync_panels_json(db, "p")
        reply = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.reorder", version=1, label="Reorder panels", input={"panel_ids": ["two", "one"]})
        assert [panel.id for panel in db.query(PanelRecord).filter(PanelRecord.project_id == "p").order_by(PanelRecord.sequence)] == ["two", "one"]
        assert '"id": "two"' in (tmp_path / "panels" / "panels.json").read_text(encoding="utf-8")
        revision = reply["history"]["revision"]
    with Session(engine) as db:
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=revision)
        assert [panel.id for panel in db.query(PanelRecord).filter(PanelRecord.project_id == "p").order_by(PanelRecord.sequence)] == ["one", "two"]
        assert '"id": "one"' in (tmp_path / "panels" / "panels.json").read_text(encoding="utf-8")
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert [panel.id for panel in db.query(PanelRecord).filter(PanelRecord.project_id == "p").order_by(PanelRecord.sequence)] == ["two", "one"]


def test_panel_reorder_commit_failure_restores_manifest(history, tmp_path, monkeypatch):
    engine, service, _ = history
    from engine.projects.service import project_service

    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        db.add(PageRecord(id="page-fail", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add_all([
            PanelRecord(id="one-fail", project_id="p", page_id="page-fail", sequence=1, page_sequence=1, x=0, y=0, width=50, height=50, crop_filename="one.jpg"),
            PanelRecord(id="two-fail", project_id="p", page_id="page-fail", sequence=2, page_sequence=2, x=50, y=0, width=50, height=50, crop_filename="two.jpg"),
        ])
        db.commit()
        project_service._sync_panels_json(db, "p")
        original = (tmp_path / "panels" / "panels.json").read_bytes()
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(OSError("fixture disk failure")))
        with pytest.raises(OSError, match="disk failure"):
            service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0,
                command_type="panel.reorder", version=1, label="Reorder panels", input={"panel_ids": ["two-fail", "one-fail"]})
        assert (tmp_path / "panels" / "panels.json").read_bytes() == original


def test_panel_geometry_restores_crop_and_manifest_after_reopen(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    from engine.projects.service import project_service

    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True)
        (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (100, 100), "red").save(tmp_path / "source" / "page.jpg")
        Image.new("RGB", (50, 50), "red").save(tmp_path / "panels" / "crop.jpg")
        db.add(PageRecord(id="page-geometry", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add(PanelRecord(id="geometry", project_id="p", page_id="page-geometry", sequence=1, page_sequence=1, x=0, y=0, width=50, height=50, crop_filename="crop.jpg"))
        db.commit()
        project_service._sync_panels_json(db, "p")
        reply = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.geometry", version=1, label="Resize panel", input={"panel_id": "geometry", "x": 10, "y": 20, "width": 30, "height": 40})
        changed = db.get(PanelRecord, "geometry")
        assert (changed.x, changed.y, changed.width, changed.height) == (10, 20, 30, 40)
        assert Image.open(tmp_path / "panels" / "crop.jpg").size == (30, 40)
        revision = reply["history"]["revision"]
    with Session(engine) as db:
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=revision)
        restored = db.get(PanelRecord, "geometry")
        assert (restored.x, restored.y, restored.width, restored.height) == (0, 0, 50, 50)
        assert Image.open(tmp_path / "panels" / "crop.jpg").size == (50, 50)
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        redone = db.get(PanelRecord, "geometry")
        assert (redone.x, redone.y, redone.width, redone.height) == (10, 20, 30, 40)
        assert Image.open(tmp_path / "panels" / "crop.jpg").size == (30, 40)


def test_panel_create_restores_row_crop_and_manifest_after_reopen(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    from engine.projects.service import project_service

    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True)
        (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (100, 100), "blue").save(tmp_path / "source" / "page.jpg")
        db.add(PageRecord(id="page-create", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.commit()
        project_service._sync_panels_json(db, "p")
        created = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.create", version=1, label="Add panel", input={"panel_id": "created", "page_id": "page-create", "x": 10, "y": 20, "width": 30, "height": 40, "panel_type": "STANDARD"})
        panel = db.get(PanelRecord, "created")
        assert panel is not None and panel.crop_filename == "panel_0001.jpg"
        assert Image.open(tmp_path / "panels" / panel.crop_filename).size == (30, 40)
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=created["history"]["revision"])
        assert db.get(PanelRecord, "created") is None
        assert not (tmp_path / "panels" / "panel_0001.jpg").exists()
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(PanelRecord, "created") is not None
        assert Image.open(tmp_path / "panels" / "panel_0001.jpg").size == (30, 40)


def test_panel_delete_restores_dependencies_crop_and_original_order(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    from engine.projects.service import project_service

    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (20, 20), "green").save(tmp_path / "panels" / "one.jpg")
        db.add(PageRecord(id="page-delete", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add_all([
            PanelRecord(id="one-delete", project_id="p", page_id="page-delete", sequence=1, page_sequence=1, x=0, y=0, width=20, height=20, crop_filename="one.jpg"),
            PanelRecord(id="two-delete", project_id="p", page_id="page-delete", sequence=2, page_sequence=2, x=20, y=0, width=20, height=20, crop_filename="two.jpg"),
            OCRRecord(id="ocr-delete", project_id="p", panel_id="one-delete", engine_name="fixture"),
            TextRegionRecord(id="region-delete", project_id="p", page_id="page-delete", panel_id="one-delete", x=1, y=1, width=2, height=2),
        ])
        db.commit(); project_service._sync_panels_json(db, "p")
        deleted = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.delete", version=1, label="Delete panel", input={"panel_id": "one-delete"})
        assert db.get(PanelRecord, "one-delete") is None
        assert db.get(OCRRecord, "ocr-delete") is None and db.get(TextRegionRecord, "region-delete") is None
        assert not (tmp_path / "panels" / "one.jpg").exists()
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=deleted["history"]["revision"])
        assert db.get(PanelRecord, "one-delete").sequence == 1
        assert db.get(OCRRecord, "ocr-delete") is not None and db.get(TextRegionRecord, "region-delete") is not None
        assert (tmp_path / "panels" / "one.jpg").exists()
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(PanelRecord, "one-delete") is None


def test_panel_selections_restore_replaced_and_created_panels(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    from engine.projects.service import project_service

    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True); (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (100, 100), "purple").save(tmp_path / "source" / "page.jpg")
        Image.new("RGB", (20, 20), "purple").save(tmp_path / "panels" / "original.jpg")
        db.add(PageRecord(id="page-select", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add(PanelRecord(id="selected", project_id="p", page_id="page-select", sequence=1, page_sequence=1, x=0, y=0, width=20, height=20, crop_filename="original.jpg"))
        db.commit(); project_service._sync_panels_json(db, "p")
        changed = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0, command_type="panel.selections", version=1,
            label="Save panel selectors", input={"panel_id": "selected", "page_bounds": True, "selections": [{"x": 10, "y": 10, "width": 30, "height": 20}, {"x": 50, "y": 20, "width": 20, "height": 30}]})
        assert db.get(PanelRecord, "selected").crop_filename.startswith("selector_")
        assert db.query(PanelRecord).filter(PanelRecord.project_id == "p").count() == 2
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=changed["history"]["revision"])
        original = db.get(PanelRecord, "selected")
        assert (original.x, original.y, original.width, original.height, original.crop_filename) == (0, 0, 20, 20, "original.jpg")
        assert db.query(PanelRecord).filter(PanelRecord.project_id == "p").count() == 1
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.query(PanelRecord).filter(PanelRecord.project_id == "p").count() == 2


def test_panel_split_restores_original_crop_and_children(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    from engine.projects.service import project_service
    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True); (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (100, 100), "orange").save(tmp_path / "source" / "page.jpg")
        Image.new("RGB", (100, 80), "orange").save(tmp_path / "panels" / "original.jpg")
        db.add(PageRecord(id="page-split", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add(PanelRecord(id="split-me", project_id="p", page_id="page-split", sequence=1, page_sequence=1, x=0, y=10, width=100, height=80, crop_filename="original.jpg"))
        db.commit(); project_service._sync_panels_json(db, "p")
        changed = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0, command_type="panel.split", version=1,
            label="Split panel", input={"panel_id": "split-me", "split_type": "horizontal", "ratio": 0.5})
        rows = db.query(PanelRecord).filter(PanelRecord.project_id == "p").order_by(PanelRecord.sequence).all()
        assert [(row.y, row.height) for row in rows] == [(10, 40), (50, 40)]
        assert Image.open(tmp_path / "panels" / "original.jpg").size == (100, 40)
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=changed["history"]["revision"])
        assert db.query(PanelRecord).filter(PanelRecord.project_id == "p").count() == 1
        assert Image.open(tmp_path / "panels" / "original.jpg").size == (100, 80)
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.query(PanelRecord).filter(PanelRecord.project_id == "p").count() == 2


def test_panel_merge_restores_removed_dependencies_and_crops(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    from engine.projects.service import project_service
    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True); (tmp_path / "panels").mkdir(exist_ok=True)
        Image.new("RGB", (100, 100), "cyan").save(tmp_path / "source" / "page.jpg")
        Image.new("RGB", (40, 40), "cyan").save(tmp_path / "panels" / "first.jpg")
        Image.new("RGB", (40, 40), "cyan").save(tmp_path / "panels" / "second.jpg")
        db.add(PageRecord(id="page-merge", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add_all([
            PanelRecord(id="first-merge", project_id="p", page_id="page-merge", sequence=1, page_sequence=1, x=0, y=0, width=40, height=40, crop_filename="first.jpg"),
            PanelRecord(id="second-merge", project_id="p", page_id="page-merge", sequence=2, page_sequence=2, x=40, y=0, width=40, height=40, crop_filename="second.jpg"),
            OCRRecord(id="ocr-merge", project_id="p", panel_id="second-merge", engine_name="fixture"),
        ])
        db.commit(); project_service._sync_panels_json(db, "p")
        changed = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0, command_type="panel.merge", version=1,
            label="Merge panels", input={"panel_ids": ["second-merge", "first-merge"]})
        primary = db.get(PanelRecord, "first-merge")
        assert db.get(PanelRecord, "second-merge") is None and (primary.x, primary.width) == (0, 80)
        assert db.get(OCRRecord, "ocr-merge") is None and not (tmp_path / "panels" / "second.jpg").exists()
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=changed["history"]["revision"])
        assert db.get(PanelRecord, "second-merge") is not None and db.get(OCRRecord, "ocr-merge") is not None
        assert Image.open(tmp_path / "panels" / "second.jpg").size == (40, 40)
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(PanelRecord, "second-merge") is None


def test_panel_confirmation_restores_project_stage_settings_and_files(history, tmp_path):
    engine, service, _ = history
    from engine.projects.service import project_service
    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        db.add(PageRecord(id="page-confirm", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add(PanelRecord(id="confirm-panel", project_id="p", page_id="page-confirm", sequence=1, page_sequence=1, x=0, y=0, width=20, height=20, crop_filename="confirm.jpg"))
        project = db.get(ProjectRecord, "p")
        project.current_stage, project.settings = "NORMALIZED", {"story_editor_state": {"project_id": "p", "scenes": []}}
        db.commit(); project_service._write_project_json(project); project_service._sync_panels_json(db, "p")
        changed = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0, command_type="panel.confirm", version=1, label="Confirm panels", input={})
        confirmed = db.get(ProjectRecord, "p")
        assert confirmed.current_stage == "PANELS_DETECTED"
        assert confirmed.settings["story_editor_state"]["panel_review_sync"]["panels_stale"] is True
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=changed["history"]["revision"])
        restored = db.get(ProjectRecord, "p")
        assert restored.current_stage == "NORMALIZED" and "panel_review_sync" not in restored.settings["story_editor_state"]
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "PANELS_DETECTED"


def test_panel_image_reset_restores_exact_blurred_bytes_and_region_metadata(history, tmp_path):
    from PIL import Image
    from engine.imaging.redaction import blur_entire_image, has_image_backup
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        crop = tmp_path / "panels" / "edited.jpg"
        Image.new("RGB", (60, 60), "yellow").save(crop)
        original = crop.read_bytes()
        db.add(PageRecord(id="page-reset", project_id="p", sequence=1, filename="page.jpg", width=60, height=60))
        db.add_all([
            PanelRecord(id="reset-panel", project_id="p", page_id="page-reset", sequence=1, page_sequence=1, x=0, y=0, width=60, height=60, crop_filename="edited.jpg"),
            TextRegionRecord(id="reset-region", project_id="p", page_id="page-reset", panel_id="reset-panel", x=1, y=1, width=10, height=10,
                             raw_text="hello", corrected_text="[BLURRED / REDACTED]", correction_status="VERIFIED", status="BLURRED", region_type="REDACTED"),
        ])
        db.commit(); assert blur_entire_image(crop, blur_radius=12, backup=True)
        blurred = crop.read_bytes(); assert blurred != original and has_image_backup(crop)
        reset = service.execute(db, "p", operation_id=str(uuid4()), expected_revision=0, command_type="panel.image.reset", version=1,
            label="Reset panel image", input={"panel_id": "reset-panel"})
        assert crop.read_bytes() == original and not has_image_backup(crop)
        assert db.get(TextRegionRecord, "reset-region").status == "CONFIRMED"
        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=reset["history"]["revision"])
        assert crop.read_bytes() == blurred and has_image_backup(crop)
        assert db.get(TextRegionRecord, "reset-region").status == "BLURRED"
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert crop.read_bytes() == original and db.get(TextRegionRecord, "reset-region").status == "CONFIRMED"



def test_panel_blur_box_restores_image_bytes_and_backup_on_undo_redo(history, tmp_path):
    from PIL import Image
    from engine.imaging.redaction import has_image_backup
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        crop = tmp_path / "panels" / "box_crop.jpg"
        Image.new("RGB", (80, 80), "white").save(crop)
        original_bytes = crop.read_bytes()
        db.add(PageRecord(id="page-box", project_id="p", sequence=1, filename="page.jpg", width=80, height=80))
        db.add(PanelRecord(id="panel-box", project_id="p", page_id="page-box", sequence=1, page_sequence=1, x=0, y=0, width=80, height=80, crop_filename="box_crop.jpg"))
        db.commit()

        assert not has_image_backup(crop)
        blurred_reply = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.image.blur_region", version=1,
            label="Blur panel region", input={"panel_id": "panel-box", "x": 10, "y": 10, "width": 40, "height": 40, "blur_radius": 12, "feather": 2}
        )
        blurred_bytes = crop.read_bytes()
        assert blurred_bytes != original_bytes
        assert has_image_backup(crop)

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=blurred_reply["history"]["revision"])
        assert crop.read_bytes() == original_bytes
        assert not has_image_backup(crop)

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert crop.read_bytes() == blurred_bytes
        assert has_image_backup(crop)


def test_panel_blur_text_restores_image_and_text_region_records(history, tmp_path):
    from PIL import Image
    from engine.imaging.redaction import has_image_backup
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        (tmp_path / "text_regions").mkdir(exist_ok=True)
        crop = tmp_path / "panels" / "text_crop.jpg"
        thumb = tmp_path / "text_regions" / "thumb_001.jpg"
        Image.new("RGB", (100, 100), "red").save(crop)
        Image.new("RGB", (30, 30), "red").save(thumb)
        orig_crop = crop.read_bytes()
        orig_thumb = thumb.read_bytes()

        db.add(PageRecord(id="page-txt", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add(PanelRecord(id="panel-txt", project_id="p", page_id="page-txt", sequence=1, page_sequence=1, x=0, y=0, width=100, height=100, crop_filename="text_crop.jpg"))
        db.add(TextRegionRecord(
            id="tr-1", project_id="p", page_id="page-txt", panel_id="panel-txt",
            x=10, y=10, width=30, height=30, crop_filename="thumb_001.jpg",
            raw_text="Sample dialog", corrected_text="Sample dialog", correction_status="UNEDITED", status="CONFIRMED", region_type="SPEECH"
        ))
        db.commit()

        blurred_reply = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.image.blur_text", version=1,
            label="Blur panel text", input={"panel_id": "panel-txt", "region_ids": ["tr-1"], "blur_radius": 16, "feather": 2}
        )
        assert crop.read_bytes() != orig_crop
        assert thumb.read_bytes() != orig_thumb
        tr = db.get(TextRegionRecord, "tr-1")
        assert tr.status == "BLURRED"
        assert tr.region_type == "REDACTED"
        assert tr.corrected_text == "[BLURRED / REDACTED]"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=blurred_reply["history"]["revision"])
        assert crop.read_bytes() == orig_crop
        assert thumb.read_bytes() == orig_thumb
        tr_undone = db.get(TextRegionRecord, "tr-1")
        assert tr_undone.status == "CONFIRMED"
        assert tr_undone.region_type == "SPEECH"
        assert tr_undone.corrected_text == "Sample dialog"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert crop.read_bytes() != orig_crop
        assert thumb.read_bytes() != orig_thumb
        tr_redone = db.get(TextRegionRecord, "tr-1")
        assert tr_redone.status == "BLURRED"
        assert tr_redone.region_type == "REDACTED"


def test_panel_batch_blur_and_batch_reset_across_panels(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "panels").mkdir(exist_ok=True)
        crop1 = tmp_path / "panels" / "batch1.jpg"
        crop2 = tmp_path / "panels" / "batch2.jpg"
        Image.new("RGB", (100, 100), "blue").save(crop1)
        Image.new("RGB", (100, 100), "green").save(crop2)
        orig1 = crop1.read_bytes()
        orig2 = crop2.read_bytes()

        db.add(PageRecord(id="page-batch", project_id="p", sequence=1, filename="page.jpg", width=100, height=100))
        db.add_all([
            PanelRecord(id="p-1", project_id="p", page_id="page-batch", sequence=1, page_sequence=1, x=0, y=0, width=100, height=50, crop_filename="batch1.jpg"),
            PanelRecord(id="p-2", project_id="p", page_id="page-batch", sequence=2, page_sequence=2, x=0, y=50, width=100, height=50, crop_filename="batch2.jpg"),
        ])
        db.commit()

        batch_blur = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="panel.image.batch_blur", version=1,
            label="Batch blur panels", input={"preset": "TOP_WATERMARK", "height_px": 20, "panel_ids": ["p-1", "p-2"]}
        )
        assert crop1.read_bytes() != orig1
        assert crop2.read_bytes() != orig2

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=batch_blur["history"]["revision"])
        assert crop1.read_bytes() == orig1
        assert crop2.read_bytes() == orig2

        redone = service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert crop1.read_bytes() != orig1
        assert crop2.read_bytes() != orig2

        batch_reset = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=redone["history"]["revision"],
            command_type="panel.image.batch_reset", version=1,
            label="Batch reset panels", input={"panel_ids": ["p-1", "p-2"]}
        )
        assert crop1.read_bytes() == orig1
        assert crop2.read_bytes() == orig2

        undone_reset = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=batch_reset["history"]["revision"])
        assert crop1.read_bytes() != orig1
        assert crop2.read_bytes() != orig2



def test_page_reorder_restores_sequences_and_manifest_on_undo_redo(history, tmp_path):
    engine, service, _ = history
    from engine.projects.service import project_service
    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True)
        (tmp_path / "source" / "p1.jpg").write_bytes(b"p1")
        (tmp_path / "source" / "p2.jpg").write_bytes(b"p2")
        db.add_all([
            PageRecord(id="page-1", project_id="p", sequence=1, filename="p1.jpg", width=10, height=10),
            PageRecord(id="page-2", project_id="p", sequence=2, filename="p2.jpg", width=10, height=10),
        ])
        db.commit()
        project_service.sync_manifest_with_db(db, "p")

        reordered = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="page.reorder", version=1,
            label="Reorder pages", input={"page_ids": ["page-2", "page-1"]}
        )
        assert db.get(PageRecord, "page-2").sequence == 1
        assert db.get(PageRecord, "page-1").sequence == 2

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=reordered["history"]["revision"])
        assert db.get(PageRecord, "page-1").sequence == 1
        assert db.get(PageRecord, "page-2").sequence == 2

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(PageRecord, "page-2").sequence == 1
        assert db.get(PageRecord, "page-1").sequence == 2


def test_page_rotate_restores_image_bytes_and_metadata_on_undo_redo(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True)
        img_path = tmp_path / "source" / "rot.jpg"
        Image.new("RGB", (60, 40), "white").save(img_path)
        orig_bytes = img_path.read_bytes()

        db.add(PageRecord(id="page-rot", project_id="p", sequence=1, filename="rot.jpg", width=60, height=40))
        db.commit()

        rotated = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="page.rotate", version=1,
            label="Rotate page", input={"page_id": "page-rot", "degrees": 90}
        )
        page = db.get(PageRecord, "page-rot")
        assert page.width == 40 and page.height == 60
        assert img_path.read_bytes() != orig_bytes

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=rotated["history"]["revision"])
        page_undone = db.get(PageRecord, "page-rot")
        assert page_undone.width == 60 and page_undone.height == 40
        assert img_path.read_bytes() == orig_bytes

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        page_redone = db.get(PageRecord, "page-rot")
        assert page_redone.width == 40 and page_redone.height == 60
        assert img_path.read_bytes() != orig_bytes


def test_page_delete_restores_page_panels_and_assets_on_undo_redo(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "source").mkdir(exist_ok=True)
        (tmp_path / "panels").mkdir(exist_ok=True)
        src1 = tmp_path / "source" / "del1.jpg"
        src2 = tmp_path / "source" / "del2.jpg"
        panel_crop = tmp_path / "panels" / "pdel.jpg"
        Image.new("RGB", (100, 100), "white").save(src1)
        Image.new("RGB", (100, 100), "white").save(src2)
        Image.new("RGB", (50, 50), "yellow").save(panel_crop)
        orig_src1 = src1.read_bytes()

        db.add_all([
            PageRecord(id="page-del-1", project_id="p", sequence=1, filename="del1.jpg", width=100, height=100),
            PageRecord(id="page-del-2", project_id="p", sequence=2, filename="del2.jpg", width=100, height=100),
            PanelRecord(id="panel-del-1", project_id="p", page_id="page-del-1", sequence=1, page_sequence=1, x=0, y=0, width=50, height=50, crop_filename="pdel.jpg"),
            OCRRecord(id="ocr-del-1", project_id="p", panel_id="panel-del-1", engine_name="mock"),
            TextRegionRecord(id="tr-del-1", project_id="p", page_id="page-del-1", panel_id="panel-del-1", x=0, y=0, width=20, height=20),
        ])
        db.commit()

        deleted = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="page.delete", version=1,
            label="Delete page", input={"page_id": "page-del-1"}
        )
        assert db.get(PageRecord, "page-del-1") is None
        assert db.get(PanelRecord, "panel-del-1") is None
        assert db.get(OCRRecord, "ocr-del-1") is None
        assert db.get(TextRegionRecord, "tr-del-1") is None
        assert db.get(PageRecord, "page-del-2").sequence == 1
        assert not src1.exists()

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=deleted["history"]["revision"])
        assert db.get(PageRecord, "page-del-1") is not None
        assert db.get(PageRecord, "page-del-1").sequence == 1
        assert db.get(PageRecord, "page-del-2").sequence == 2
        assert db.get(PanelRecord, "panel-del-1") is not None
        assert db.get(OCRRecord, "ocr-del-1") is not None
        assert db.get(TextRegionRecord, "tr-del-1") is not None
        assert src1.exists() and src1.read_bytes() == orig_src1

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(PageRecord, "page-del-1") is None
        assert db.get(PageRecord, "page-del-2").sequence == 1
        assert not src1.exists()


def test_text_region_create_undo_redo(history, tmp_path):
    engine, service, _ = history
    with Session(engine) as db:
        db.add(PageRecord(id="page-ocr-1", project_id="p", sequence=1, filename="p1.jpg", width=100, height=100))
        db.add(PanelRecord(id="panel-ocr-1", project_id="p", page_id="page-ocr-1", sequence=1, page_sequence=1, x=10, y=10, width=80, height=80, crop_filename="p1.jpg"))
        db.commit()

        created = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="ocr.region.create", version=1,
            label="Create text region",
            input={"region_id": "tr-new-1", "panel_id": "panel-ocr-1", "x": 5, "y": 5, "width": 20, "height": 20, "region_type": "SPEECH"}
        )
        tr = db.get(TextRegionRecord, "tr-new-1")
        assert tr is not None
        assert tr.panel_id == "panel-ocr-1"
        assert tr.x == 5 and tr.y == 5 and tr.width == 20 and tr.height == 20
        assert tr.status == "CONFIRMED"
        assert tr.detection_method == "MANUAL"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=created["history"]["revision"])
        assert db.get(TextRegionRecord, "tr-new-1") is None

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        tr_redo = db.get(TextRegionRecord, "tr-new-1")
        assert tr_redo is not None
        assert tr_redo.x == 5 and tr_redo.width == 20


def test_text_region_update_undo_redo(history, tmp_path):
    engine, service, _ = history
    with Session(engine) as db:
        db.add(PageRecord(id="page-ocr-2", project_id="p", sequence=1, filename="p2.jpg", width=100, height=100))
        db.add(PanelRecord(id="panel-ocr-2", project_id="p", page_id="page-ocr-2", sequence=1, page_sequence=1, x=0, y=0, width=100, height=100, crop_filename="p2.jpg"))
        db.add(TextRegionRecord(id="tr-upd-1", project_id="p", page_id="page-ocr-2", panel_id="panel-ocr-2", x=10, y=10, width=20, height=20, corrected_text=""))
        db.commit()

        updated = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="ocr.region.update", version=1,
            label="Update text region",
            input={"region_id": "tr-upd-1", "x": 15, "y": 25, "width": 30, "height": 40, "corrected_text": "Hello world!", "speaker_character_id": "char-1"}
        )
        tr = db.get(TextRegionRecord, "tr-upd-1")
        assert tr.x == 15 and tr.y == 25 and tr.width == 30 and tr.height == 40
        assert tr.corrected_text == "Hello world!"
        assert tr.speaker_character_id == "char-1"
        assert tr.correction_status == "EDITED"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=updated["history"]["revision"])
        tr_undo = db.get(TextRegionRecord, "tr-upd-1")
        assert tr_undo.x == 10 and tr_undo.y == 10 and tr_undo.width == 20 and tr_undo.height == 20
        assert tr_undo.corrected_text == ""
        assert tr_undo.speaker_character_id is None

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        tr_redo = db.get(TextRegionRecord, "tr-upd-1")
        assert tr_redo.x == 15 and tr_redo.corrected_text == "Hello world!"


def test_text_region_delete_restores_crop_thumbnail_on_undo_redo(history, tmp_path):
    from PIL import Image
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "text_regions").mkdir(exist_ok=True)
        crop_file = tmp_path / "text_regions" / "thumb1.jpg"
        Image.new("RGB", (30, 30), "blue").save(crop_file)
        orig_bytes = crop_file.read_bytes()

        db.add(PageRecord(id="page-ocr-3", project_id="p", sequence=1, filename="p3.jpg", width=100, height=100))
        db.add(PanelRecord(id="panel-ocr-3", project_id="p", page_id="page-ocr-3", sequence=1, page_sequence=1, x=0, y=0, width=100, height=100, crop_filename="p3.jpg"))
        db.add(TextRegionRecord(id="tr-del-target", project_id="p", page_id="page-ocr-3", panel_id="panel-ocr-3", x=5, y=5, width=30, height=30, crop_filename="thumb1.jpg"))
        db.commit()

        deleted = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="ocr.region.delete", version=1,
            label="Delete text region",
            input={"region_id": "tr-del-target"}
        )
        assert db.get(TextRegionRecord, "tr-del-target") is None
        assert not crop_file.exists()

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=deleted["history"]["revision"])
        assert db.get(TextRegionRecord, "tr-del-target") is not None
        assert crop_file.exists() and crop_file.read_bytes() == orig_bytes

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(TextRegionRecord, "tr-del-target") is None
        assert not crop_file.exists()


def test_ocr_block_update_and_ocr_json_sync_on_undo_redo(history, tmp_path):
    import json
    from engine.projects.service import project_service
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "ocr").mkdir(exist_ok=True)
        db.add(PageRecord(id="page-ocr-4", project_id="p", sequence=1, filename="p4.jpg", width=100, height=100))
        db.add(PanelRecord(id="panel-ocr-4", project_id="p", page_id="page-ocr-4", sequence=1, page_sequence=1, x=0, y=0, width=100, height=100, crop_filename="p4.jpg"))
        ocr_rec = OCRRecord(
            id="ocr-rec-1", project_id="p", panel_id="panel-ocr-4", engine_name="mock",
            adapted_blocks=[{"id": "blk-1", "raw_region_id": "blk-1", "text": "Original text", "speaker": None, "classification": "dialogue", "notes": ""}]
        )
        db.add(ocr_rec)
        db.commit()
        project_service._sync_ocr_json(db, "p")

        updated = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="ocr.block.update", version=1,
            label="Update OCR block",
            input={"panel_id": "panel-ocr-4", "block_id": "blk-1", "text": "Edited dialog", "speaker": "Hero", "classification": "dialogue", "notes": "Shouting"}
        )
        rec = db.get(OCRRecord, "ocr-rec-1")
        assert rec.adapted_blocks[0]["text"] == "Edited dialog"
        assert rec.adapted_blocks[0]["speaker"] == "Hero"
        assert rec.status == "EDITED"

        ocr_json_path = tmp_path / "ocr" / "ocr.json"
        assert ocr_json_path.exists()
        data = json.loads(ocr_json_path.read_text(encoding="utf-8"))
        assert data["panels"][0]["adapted_blocks"][0]["text"] == "Edited dialog"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=updated["history"]["revision"])
        rec_undo = db.get(OCRRecord, "ocr-rec-1")
        assert rec_undo.adapted_blocks[0]["text"] == "Original text"
        data_undo = json.loads(ocr_json_path.read_text(encoding="utf-8"))
        assert data_undo["panels"][0]["adapted_blocks"][0]["text"] == "Original text"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        rec_redo = db.get(OCRRecord, "ocr-rec-1")
        assert rec_redo.adapted_blocks[0]["text"] == "Edited dialog"


def test_ocr_confirm_restores_stage_and_files_on_undo_redo(history, tmp_path):
    from engine.projects.service import project_service
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "ocr").mkdir(exist_ok=True)
        (tmp_path / "panels").mkdir(exist_ok=True)
        db.add(PageRecord(id="page-ocr-5", project_id="p", sequence=1, filename="p5.jpg", width=100, height=100))
        db.add(PanelRecord(id="panel-ocr-5", project_id="p", page_id="page-ocr-5", sequence=1, page_sequence=1, x=0, y=0, width=50, height=50, crop_filename="p5.jpg"))
        db.add(TextRegionRecord(id="tr-conf-1", project_id="p", page_id="page-ocr-5", panel_id="panel-ocr-5", x=0, y=0, width=20, height=20, status="CONFIRMED"))
        project = db.get(ProjectRecord, "p")
        project.current_stage = "PANELS_DETECTED"
        db.commit()
        project_service._write_project_json(project)
        project_service._sync_ocr_json(db, "p")

        confirmed = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="ocr.confirm", version=1,
            label="Confirm OCR", input={}
        )
        assert db.get(ProjectRecord, "p").current_stage == "OCR_APPROVED"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=confirmed["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "PANELS_DETECTED"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "OCR_APPROVED"


def test_project_confirm_restores_stage_and_manifest_on_undo_redo(history, tmp_path):
    from engine.projects.service import project_service
    engine, service, _ = history
    with Session(engine) as db:
        db.add(PageRecord(id="page-acq-1", project_id="p", sequence=1, filename="acq1.jpg", width=100, height=100, status="READY"))
        project = db.get(ProjectRecord, "p")
        project.current_stage = "RIGHTS_APPROVED"
        db.commit()
        project_service._write_project_json(project)
        project_service.sync_manifest_with_db(db, "p")

        confirmed = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="project.confirm", version=1,
            label="Confirm acquisition", input={}
        )
        assert db.get(ProjectRecord, "p").current_stage == "ACQUIRED"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=confirmed["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "RIGHTS_APPROVED"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "ACQUIRED"


def test_story_confirm_undo_redo(history, tmp_path):
    from engine.database.models import NarrativeRecord
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "story").mkdir(exist_ok=True)
        narrative_doc = {
            "project_id": "p", "chapter_title": "Ch 1",
            "characters": [], "locations": [], "scenes": [], "story_beats": [],
            "events": [], "continuity_warnings": [], "analysis_metadata": {},
        }
        db.add(NarrativeRecord(id="nar-1", project_id="p", document=narrative_doc))
        project = db.get(ProjectRecord, "p")
        project.current_stage = "OCR_APPROVED"
        db.commit()

        confirmed = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="story.confirm", version=1,
            label="Confirm story", input={}
        )
        assert db.get(ProjectRecord, "p").current_stage == "STORY_APPROVED"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=confirmed["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "OCR_APPROVED"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(ProjectRecord, "p").current_stage == "STORY_APPROVED"


def test_character_update_undo_redo(history, tmp_path):
    from engine.database.models import CharacterRecord
    engine, service, _ = history
    with Session(engine) as db:
        db.add(CharacterRecord(id="char-u-1", project_id="p", display_name="Hero", role="PROTAGONIST", aliases=["H1"]))
        db.commit()

        updated = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="character.update", version=1,
            label="Update character",
            input={"character_id": "char-u-1", "display_name": "Super Hero", "role": "MAIN"}
        )
        c = db.get(CharacterRecord, "char-u-1")
        assert c.display_name == "Super Hero" and c.role == "MAIN" and c.manual_override is True

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=updated["history"]["revision"])
        c_undo = db.get(CharacterRecord, "char-u-1")
        assert c_undo.display_name == "Hero" and c_undo.role == "PROTAGONIST"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        c_redo = db.get(CharacterRecord, "char-u-1")
        assert c_redo.display_name == "Super Hero" and c_redo.role == "MAIN"


def test_character_merge_undo_redo(history, tmp_path):
    from engine.database.models import CharacterRecord, TextRegionRecord, EventRecord, PageRecord, PanelRecord
    engine, service, _ = history
    with Session(engine) as db:
        db.add(PageRecord(id="page-1", project_id="p", sequence=1, filename="page.jpg", width=10, height=10))
        db.add(PanelRecord(id="pan-1", project_id="p", page_id="page-1", sequence=1, page_sequence=1, x=0, y=0, width=10, height=10, crop_filename="crop.jpg"))
        db.add_all([
            CharacterRecord(id="char-src", project_id="p", display_name="Old Alias", role="UNKNOWN", aliases=["A1"]),
            CharacterRecord(id="char-tgt", project_id="p", display_name="True Name", role="PROTAGONIST", aliases=["T1"]),
            TextRegionRecord(id="tr-merge-1", project_id="p", page_id="page-1", panel_id="pan-1", x=0, y=0, width=10, height=10, speaker_character_id="char-src"),
            EventRecord(id="ev-merge-1", project_id="p", event_type="DIALOGUE", actor_character_id="char-src", panel_ids=[]),
        ])
        db.commit()

        merged = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="character.merge", version=1,
            label="Merge characters",
            input={"source_character_id": "char-src", "target_character_id": "char-tgt"}
        )
        assert db.get(CharacterRecord, "char-src") is None
        assert db.get(TextRegionRecord, "tr-merge-1").speaker_character_id == "char-tgt"
        assert db.get(EventRecord, "ev-merge-1").actor_character_id == "char-tgt"
        assert "Old Alias" in db.get(CharacterRecord, "char-tgt").aliases

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=merged["history"]["revision"])
        assert db.get(CharacterRecord, "char-src") is not None
        assert db.get(TextRegionRecord, "tr-merge-1").speaker_character_id == "char-src"
        assert db.get(EventRecord, "ev-merge-1").actor_character_id == "char-src"
        assert db.get(CharacterRecord, "char-tgt").aliases == ["T1"]

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(CharacterRecord, "char-src") is None
        assert db.get(TextRegionRecord, "tr-merge-1").speaker_character_id == "char-tgt"
        assert db.get(EventRecord, "ev-merge-1").actor_character_id == "char-tgt"


def test_character_split_undo_redo(history, tmp_path):
    from engine.database.models import CharacterRecord, TextRegionRecord, PageRecord, PanelRecord
    engine, service, _ = history
    with Session(engine) as db:
        db.add(PageRecord(id="page-1", project_id="p", sequence=1, filename="page.jpg", width=10, height=10))
        db.add_all([
            PanelRecord(id="pan-split-1", project_id="p", page_id="page-1", sequence=1, page_sequence=1, x=0, y=0, width=10, height=10, crop_filename="crop1.jpg"),
            PanelRecord(id="pan-other-1", project_id="p", page_id="page-1", sequence=2, page_sequence=2, x=0, y=0, width=10, height=10, crop_filename="crop2.jpg"),
        ])
        db.add_all([
            CharacterRecord(id="char-orig", project_id="p", display_name="Combined Hero", role="PROTAGONIST"),
            TextRegionRecord(id="tr-split-1", project_id="p", page_id="page-1", panel_id="pan-split-1", x=0, y=0, width=10, height=10, speaker_character_id="char-orig"),
            TextRegionRecord(id="tr-split-2", project_id="p", page_id="page-1", panel_id="pan-other-1", x=0, y=0, width=10, height=10, speaker_character_id="char-orig"),
        ])
        db.commit()

        split = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="character.split", version=1,
            label="Split character",
            input={"character_id": "char-orig", "new_name": "Separated Hero", "panel_ids": ["pan-split-1"], "new_character_id": "char-new-split"}
        )
        assert db.get(CharacterRecord, "char-new-split") is not None
        assert db.get(TextRegionRecord, "tr-split-1").speaker_character_id == "char-new-split"
        assert db.get(TextRegionRecord, "tr-split-2").speaker_character_id == "char-orig"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=split["history"]["revision"])
        assert db.get(CharacterRecord, "char-new-split") is None
        assert db.get(TextRegionRecord, "tr-split-1").speaker_character_id == "char-orig"
        assert db.get(TextRegionRecord, "tr-split-2").speaker_character_id == "char-orig"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(CharacterRecord, "char-new-split") is not None
        assert db.get(TextRegionRecord, "tr-split-1").speaker_character_id == "char-new-split"


def test_scene_merge_undo_redo(history, tmp_path):
    from engine.database.models import SceneRecord, StoryBeatRecord
    engine, service, _ = history
    with Session(engine) as db:
        db.add_all([
            SceneRecord(id="scene-m-1", project_id="p", sequence=1, title="Scene 1", panel_start="p1", panel_end="p3", summary="Intro"),
            SceneRecord(id="scene-m-2", project_id="p", sequence=2, title="Scene 2", panel_start="p4", panel_end="p6", summary="Climax"),
            StoryBeatRecord(id="beat-m-1", project_id="p", scene_id="scene-m-2", sequence=1, summary="Beat in scene 2", panel_ids=[]),
        ])
        db.commit()

        merged = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="scene.merge", version=1,
            label="Merge scenes",
            input={"scene_id_1": "scene-m-1", "scene_id_2": "scene-m-2"}
        )
        assert db.get(SceneRecord, "scene-m-2") is None
        s1 = db.get(SceneRecord, "scene-m-1")
        assert s1.panel_end == "p6"
        assert s1.summary == "Intro Climax"
        assert db.get(StoryBeatRecord, "beat-m-1").scene_id == "scene-m-1"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=merged["history"]["revision"])
        assert db.get(SceneRecord, "scene-m-2") is not None
        s1_undo = db.get(SceneRecord, "scene-m-1")
        assert s1_undo.panel_end == "p3"
        assert s1_undo.summary == "Intro"
        assert db.get(StoryBeatRecord, "beat-m-1").scene_id == "scene-m-2"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(SceneRecord, "scene-m-2") is None
        assert db.get(StoryBeatRecord, "beat-m-1").scene_id == "scene-m-1"


def test_script_segment_update_and_timing_undo_redo(history, tmp_path):
    from engine.database.models import VideoScriptRecord, ScriptSegmentRecord
    engine, service, _ = history
    with Session(engine) as db:
        script = VideoScriptRecord(id="script-t-1", project_id="p", status="APPROVED", estimated_duration=5.0)
        seg1 = ScriptSegmentRecord(id="seg-t-1", script_id="script-t-1", project_id="p", scene_id="s1", sequence=1, text="Initial line", estimated_start=0.0, estimated_end=2.0, estimated_duration=2.0)
        seg2 = ScriptSegmentRecord(id="seg-t-2", script_id="script-t-1", project_id="p", scene_id="s1", sequence=2, text="Second line", estimated_start=2.0, estimated_end=5.0, estimated_duration=3.0)
        db.add_all([script, seg1, seg2])
        db.commit()

        updated = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="script.segment.update", version=1,
            label="Update script segment",
            input={"script_id": "script-t-1", "segment_id": "seg-t-1", "text": "Much longer dialogue line rewritten", "estimated_duration": 4.0}
        )
        s1 = db.get(ScriptSegmentRecord, "seg-t-1")
        s2 = db.get(ScriptSegmentRecord, "seg-t-2")
        scr = db.get(VideoScriptRecord, "script-t-1")
        assert s1.text == "Much longer dialogue line rewritten"
        assert s1.estimated_duration == 4.0
        assert s2.estimated_start == 4.0 and s2.estimated_end == 7.0
        assert scr.estimated_duration == 7.0
        assert scr.status == "DRAFT"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=updated["history"]["revision"])
        s1_undo = db.get(ScriptSegmentRecord, "seg-t-1")
        s2_undo = db.get(ScriptSegmentRecord, "seg-t-2")
        scr_undo = db.get(VideoScriptRecord, "script-t-1")
        assert s1_undo.text == "Initial line" and s1_undo.estimated_duration == 2.0
        assert s2_undo.estimated_start == 2.0 and s2_undo.estimated_end == 5.0
        assert scr_undo.estimated_duration == 5.0
        assert scr_undo.status == "APPROVED"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        s1_redo = db.get(ScriptSegmentRecord, "seg-t-1")
        assert s1_redo.estimated_duration == 4.0
        assert db.get(VideoScriptRecord, "script-t-1").estimated_duration == 7.0


def test_script_approve_undo_redo(history, tmp_path):
    from engine.database.models import VideoScriptRecord
    from engine.projects.service import project_service
    engine, service, _ = history
    with Session(engine) as db:
        script = VideoScriptRecord(id="script-app-1", project_id="p", status="DRAFT", estimated_duration=3.0)
        project = db.get(ProjectRecord, "p")
        project.current_stage = "STORY_APPROVED"
        db.add(script)
        db.commit()
        project_service._write_project_json(project)

        approved = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="script.approve", version=1,
            label="Approve script",
            input={"script_id": "script-app-1"}
        )
        assert db.get(VideoScriptRecord, "script-app-1").status == "APPROVED"
        assert db.get(ProjectRecord, "p").current_stage == "SCRIPT_APPROVED"

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=approved["history"]["revision"])
        assert db.get(VideoScriptRecord, "script-app-1").status == "DRAFT"
        assert db.get(ProjectRecord, "p").current_stage == "STORY_APPROVED"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        assert db.get(VideoScriptRecord, "script-app-1").status == "APPROVED"
        assert db.get(ProjectRecord, "p").current_stage == "SCRIPT_APPROVED"


def test_storyboard_segment_update_and_realign_undo_redo(history, tmp_path):
    import json
    engine, service, _ = history
    with Session(engine) as db:
        (tmp_path / "story").mkdir(exist_ok=True)
        sb_file = tmp_path / "story" / "storyboard.json"
        initial_doc = {
            "project_id": "p", "script_id": "s1", "total_duration_sec": 4.0, "updated_at": "2026-10-21T00:00:00",
            "segments": [
                {
                    "segment_id": "sb-seg-1", "scene_id": "s1", "sequence": 1, "text": "Original narration", "speaker_name": "Narrator",
                    "emotion": "NEUTRAL", "intensity": 0.5, "measured_duration_sec": 4.0,
                    "target_panel_id": "pan-1", "supporting_panels": [],
                    "camera_motion": {"type": "SLOW_PUSH", "start_zoom": 1.0, "end_zoom": 1.05, "easing": "EASE_IN_OUT"},
                    "manual_override": False
                }
            ]
        }
        sb_file.write_text(json.dumps(initial_doc, indent=2), encoding="utf-8")

        updated = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="storyboard.segment.update", version=1,
            label="Update storyboard segment",
            input={"segment_id": "sb-seg-1", "updates": {"text": "Updated voiceover text", "intensity": 0.8}}
        )
        data = json.loads(sb_file.read_text(encoding="utf-8"))
        assert data["segments"][0]["text"] == "Updated voiceover text"
        assert data["segments"][0]["intensity"] == 0.8

        undone = service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=updated["history"]["revision"])
        data_undo = json.loads(sb_file.read_text(encoding="utf-8"))
        assert data_undo["segments"][0]["text"] == "Original narration"

        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=undone["history"]["revision"])
        data_redo = json.loads(sb_file.read_text(encoding="utf-8"))
        assert data_redo["segments"][0]["text"] == "Updated voiceover text"


def test_motion_domain_history_strategies(history, tmp_path):
    from engine.database.models import VisualTimelineRecord
    from engine.acquisition.models import PipelineStage
    import json
    engine, service, _ = history
    motion_dir = tmp_path / "motion"
    motion_dir.mkdir(parents=True, exist_ok=True)
    timeline_file = motion_dir / "visual_timeline.json"

    with Session(engine) as db:
        proj = db.get(ProjectRecord, "p")
        proj.current_stage = "STORY_APPROVED"
        db.commit()

    # 1. Accept Motion Plan
    with Session(engine) as db:
        res = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="motion.plan.accept", version=1,
            label="Accept plan", input={"plan": {"total_duration": 15.0, "total_shots": 3, "style_preset": "cinematic", "shots": [{"id": "shot1"}]}}
        )
        assert res["history"]["revision"] == 1
        rec = db.query(VisualTimelineRecord).filter_by(project_id="p").first()
        assert rec is not None and rec.total_duration == 15.0 and rec.status == "DRAFT"
        assert timeline_file.exists()
        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        assert data["total_duration"] == 15.0

    # 2. Motion Overrides
    with Session(engine) as db:
        res = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=1,
            command_type="motion.overrides", version=1,
            label="Set shot overrides", input={"overrides": {"shot1": {"zoom": 1.2}}}
        )
        assert res["history"]["revision"] == 2
        rec = db.query(VisualTimelineRecord).filter_by(project_id="p").first()
        assert rec.overrides_json == {"shot1": {"zoom": 1.2}}
        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        assert data["overrides"] == {"shot1": {"zoom": 1.2}}

    # Undo overrides
    with Session(engine) as db:
        service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=2)
        rec = db.query(VisualTimelineRecord).filter_by(project_id="p").first()
        assert rec.overrides_json == {}
        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        assert data.get("overrides") == {}

    # Redo overrides
    with Session(engine) as db:
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=3)
        rec = db.query(VisualTimelineRecord).filter_by(project_id="p").first()
        assert rec.overrides_json == {"shot1": {"zoom": 1.2}}

    # 3. Approve Motion
    with Session(engine) as db:
        res = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=4,
            command_type="motion.approve", version=1,
            label="Approve motion", input={}
        )
        assert res["history"]["revision"] == 5
        rec = db.query(VisualTimelineRecord).filter_by(project_id="p").first()
        assert rec.status == "APPROVED"
        proj = db.get(ProjectRecord, "p")
        assert proj.current_stage == PipelineStage.MOTION_APPROVED.value
        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        assert data["status"] == "APPROVED"

    # Undo approval
    with Session(engine) as db:
        service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=5)
        rec = db.query(VisualTimelineRecord).filter_by(project_id="p").first()
        assert rec.status == "DRAFT"
        proj = db.get(ProjectRecord, "p")
        assert proj.current_stage == "STORY_APPROVED"


def test_audio_domain_history_strategies(history, tmp_path):
    from engine.database.models import AudioTimelineRecord
    from engine.acquisition.models import PipelineStage
    import json
    engine, service, _ = history
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    timeline_file = audio_dir / "master_audio_timeline.json"
    clip_file = audio_dir / "clip1.wav"
    clip_file.write_bytes(b"RIFF_WAV_ORIG")

    with Session(engine) as db:
        proj = db.get(ProjectRecord, "p")
        proj.current_stage = "MOTION_APPROVED"
        db.commit()

    # 1. Accept Audio Draft
    with Session(engine) as db:
        res = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=0,
            command_type="audio.draft.accept", version=1,
            label="Accept draft", input={"draft": {"total_duration": 10.0, "voice_casting": {"v1": "actor"}}}
        )
        assert res["history"]["revision"] == 1
        rec = db.query(AudioTimelineRecord).filter_by(project_id="p").first()
        assert rec is not None and rec.total_duration == 10.0 and rec.status == "DRAFT"
        assert timeline_file.exists()
        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        assert data["total_duration"] == 10.0

    # 2. Accept Synthesized Audio
    with Session(engine) as db:
        clip_file.write_bytes(b"RIFF_WAV_SYNTHESIZED")
        res = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=1,
            command_type="audio.synthesized.accept", version=1,
            label="Accept synthesized",
            input={"result": {"total_duration": 10.5, "intervals": [{"start": 0, "end": 5}], "audio_files": ["audio/clip1.wav"]}}
        )
        assert res["history"]["revision"] == 2
        rec = db.query(AudioTimelineRecord).filter_by(project_id="p").first()
        assert rec.total_duration == 10.5
        assert rec.timeline_json["intervals"] == [{"start": 0, "end": 5}]
        assert clip_file.read_bytes() == b"RIFF_WAV_SYNTHESIZED"

    # Undo synthesized audio
    with Session(engine) as db:
        service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=2)
        rec = db.query(AudioTimelineRecord).filter_by(project_id="p").first()
        assert rec.total_duration == 10.0
        assert clip_file.read_bytes() == b"RIFF_WAV_ORIG"

    # Redo synthesized audio
    with Session(engine) as db:
        service.move(db, "p", direction="redo", operation_id=str(uuid4()), expected_revision=3)
        rec = db.query(AudioTimelineRecord).filter_by(project_id="p").first()
        assert rec.total_duration == 10.5
        assert clip_file.read_bytes() == b"RIFF_WAV_SYNTHESIZED"

    # 3. Approve Audio
    with Session(engine) as db:
        res = service.execute(
            db, "p", operation_id=str(uuid4()), expected_revision=4,
            command_type="audio.approve", version=1,
            label="Approve audio", input={}
        )
        assert res["history"]["revision"] == 5
        rec = db.query(AudioTimelineRecord).filter_by(project_id="p").first()
        assert rec.status == "APPROVED"
        proj = db.get(ProjectRecord, "p")
        assert proj.current_stage == PipelineStage.AUDIO_APPROVED.value
        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        assert data["status"] == "APPROVED"

    # Undo audio approve
    with Session(engine) as db:
        service.move(db, "p", direction="undo", operation_id=str(uuid4()), expected_revision=5)
        rec = db.query(AudioTimelineRecord).filter_by(project_id="p").first()
        assert rec.status == "DRAFT"
        proj = db.get(ProjectRecord, "p")
        assert proj.current_stage == "MOTION_APPROVED"

