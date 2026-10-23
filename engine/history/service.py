"""Atomic, revisioned SQLite command journal. Domain and cursor commit together.

File-changing strategies must NOT be registered until they implement retained-file
staging/recovery. A database transaction alone cannot roll back arbitrary files.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from engine.database.models import Base, ProjectRecord
from engine.history.contracts import CommandRegistry, HistoryFault
from engine.history.editor import EditorStateStrategy, document, sanitize
from engine.history.panels import (
    PanelBatchBlurStrategy,
    PanelBatchResetStrategy,
    PanelBlurBoxStrategy,
    PanelBlurEntireStrategy,
    PanelBlurTextStrategy,
    PanelConfirmStrategy,
    PanelCreateStrategy,
    PanelDeleteStrategy,
    PanelGeometryStrategy,
    PanelImageResetStrategy,
    PanelMergeStrategy,
    PanelReorderStrategy,
    PanelSelectionsStrategy,
    PanelSplitStrategy,
)
from engine.history.pages import (
    PageDeleteStrategy,
    PageReorderStrategy,
    PageRotateStrategy,
)
from engine.history.ocr import (
    OCRBlockUpdateStrategy,
    OCRConfirmStrategy,
    TextRegionCreateStrategy,
    TextRegionDeleteStrategy,
    TextRegionUpdateStrategy,
)
from engine.history.projects import (
    ProjectConfirmStrategy,
)
from engine.history.story import (
    CharacterMergeStrategy,
    CharacterSplitStrategy,
    CharacterUpdateStrategy,
    SceneMergeStrategy,
    ScriptApproveStrategy,
    ScriptSegmentUpdateStrategy,
    StoryboardRealignStrategy,
    StoryboardSegmentUpdateStrategy,
    StoryConfirmStrategy,
)
from engine.history.motion import (
    MotionApproveStrategy,
    MotionOverridesStrategy,
    MotionPlanAcceptStrategy,
)
from engine.history.audio import (
    AudioApproveStrategy,
    AudioDraftAcceptStrategy,
    AudioSynthesizedAcceptStrategy,
)
from engine.history.models import HistoryRecord, HistoryReceipt, HistoryArchive


def encoded(value) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
                          default=lambda item: item.isoformat() if isinstance(item, (date, datetime)) else (_ for _ in ()).throw(TypeError())).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as error:
        raise HistoryFault("VALIDATION", "History payload must be finite JSON", 422) from error


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


class ProjectHistory:
    def __init__(self, registry=None, *, max_entries=100, max_bytes=8 * 1024 * 1024):
        if type(max_entries) is not int or max_entries < 1 or type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("History limits must be positive integers")
        self.registry = registry or (CommandRegistry()
            .register("editor.replace", 1, EditorStateStrategy())
            .register("panel.reorder", 1, PanelReorderStrategy())
            .register("panel.create", 1, PanelCreateStrategy())
            .register("panel.delete", 1, PanelDeleteStrategy())
            .register("panel.selections", 1, PanelSelectionsStrategy())
            .register("panel.split", 1, PanelSplitStrategy())
            .register("panel.merge", 1, PanelMergeStrategy())
            .register("panel.confirm", 1, PanelConfirmStrategy())
            .register("panel.image.reset", 1, PanelImageResetStrategy())
            .register("panel.image.blur_region", 1, PanelBlurBoxStrategy())
            .register("panel.image.blur_text", 1, PanelBlurTextStrategy())
            .register("panel.image.blur_panel", 1, PanelBlurEntireStrategy())
            .register("panel.image.batch_blur", 1, PanelBatchBlurStrategy())
            .register("panel.image.batch_reset", 1, PanelBatchResetStrategy())
            .register("panel.geometry", 1, PanelGeometryStrategy())
            .register("page.reorder", 1, PageReorderStrategy())
            .register("page.rotate", 1, PageRotateStrategy())
            .register("page.delete", 1, PageDeleteStrategy())
            .register("ocr.region.create", 1, TextRegionCreateStrategy())
            .register("ocr.region.update", 1, TextRegionUpdateStrategy())
            .register("ocr.region.delete", 1, TextRegionDeleteStrategy())
            .register("ocr.block.update", 1, OCRBlockUpdateStrategy())
            .register("ocr.confirm", 1, OCRConfirmStrategy())
            .register("project.confirm", 1, ProjectConfirmStrategy())
            .register("story.confirm", 1, StoryConfirmStrategy())
            .register("character.update", 1, CharacterUpdateStrategy())
            .register("character.merge", 1, CharacterMergeStrategy())
            .register("character.split", 1, CharacterSplitStrategy())
            .register("scene.merge", 1, SceneMergeStrategy())
            .register("script.segment.update", 1, ScriptSegmentUpdateStrategy())
            .register("script.approve", 1, ScriptApproveStrategy())
            .register("storyboard.segment.update", 1, StoryboardSegmentUpdateStrategy())
            .register("storyboard.realign", 1, StoryboardRealignStrategy())
            .register("motion.overrides", 1, MotionOverridesStrategy())
            .register("motion.approve", 1, MotionApproveStrategy())
            .register("motion.plan.accept", 1, MotionPlanAcceptStrategy())
            .register("audio.approve", 1, AudioApproveStrategy())
            .register("audio.draft.accept", 1, AudioDraftAcceptStrategy())
            .register("audio.synthesized.accept", 1, AudioSynthesizedAcceptStrategy()))
        self.max_entries, self.max_bytes = max_entries, max_bytes

    @classmethod
    def create_default(cls, **kwargs) -> "ProjectHistory":
        return cls(**kwargs)

    @contextmanager
    def _transaction(self, db, *, write=True):
        if db.new or db.dirty or db.deleted:
            raise HistoryFault("VALIDATION", "History commands require a clean session", 422)
        # Own this transaction. End a previous clean read transaction before obtaining
        # SQLite's cross-process write reservation, BEFORE reading the baseline.
        if db.in_transaction():
            db.rollback()
        try:
            db.execute(text("BEGIN IMMEDIATE" if write else "BEGIN"))
            yield
            db.commit()
        except Exception:
            db.rollback()
            raise

    def _project(self, db, project_id):
        project = db.get(ProjectRecord, project_id, populate_existing=True)
        if project is None:
            raise HistoryFault("NOT_FOUND", "Project not found", 404)
        return project

    def _fingerprint(self, db, project):
        # Hash (do not persist copies of) relevant DB state. Legacy mutations and
        # background results invalidate history rather than being overwritten.
        state = {"settings": {**(project.settings or {}), "story_editor_state": document((project.settings or {}).get("story_editor_state"))}}
        for table in sorted(Base.metadata.tables.values(), key=lambda table: table.name):
            if "project_id" not in table.c or table.name.startswith("project_history") or table.name in {"jobs", "render_jobs"}:
                continue
            rows = db.execute(select(table).where(table.c.project_id == project.id).order_by(*table.primary_key.columns)).mappings().all()
            state[table.name] = [dict(row) for row in rows]
        return digest(state)

    def _validate(self, head):
        if head is None:
            return
        if head.schema_version != 1:
            raise HistoryFault("COMPATIBILITY", "Unsupported journal schema; archive and start fresh", 409)
        if type(head.revision) is not int or head.revision < 0 or not isinstance(head.entries, list) or type(head.cursor) is not int or not 0 <= head.cursor <= len(head.entries):
            raise HistoryFault("RECOVERY_REQUIRED", "Invalid history journal; recovery is required", 409)
        ids = set()
        for entry in head.entries:
            if (not isinstance(entry, dict) or entry.get("kind") != "command" or not isinstance(entry.get("id"), str)
                or not entry["id"] or entry["id"] in ids or not isinstance(entry.get("type"), str)
                or not isinstance(entry.get("label"), str) or not entry["label"].strip() or len(entry["label"]) > 120):
                raise HistoryFault("RECOVERY_REQUIRED", "Invalid stored command", 409)
            ids.add(entry["id"])
            strategy = self.registry.resolve(entry.get("type"), entry.get("version"))
            if not strategy.validate(entry.get("payload")):
                raise HistoryFault("RECOVERY_REQUIRED", "Invalid stored command payload", 409)
        if len(head.entries) > self.max_entries or len(encoded(head.entries)) > self.max_bytes:
            raise HistoryFault("CAPACITY", "History exceeds configured retention budget", 409)

    def _reply(self, db, project, head, *, replayed=False, operation_revision=None):
        blocked = None
        try:
            self._validate(head)
        except HistoryFault as error:
            blocked = {"code": error.code, "message": str(error)}
        fingerprint = self._fingerprint(db, project)
        cursor, entries = (head.cursor, head.entries) if head and not blocked else (0, [])
        conflict = bool(head and head.fingerprint != fingerprint)
        return {"state": sanitize(deepcopy((project.settings or {}).get("story_editor_state"))),
                "replayed": replayed, "operation_revision": operation_revision,
                "history": {"scope": f"project:{project.id}", "revision": head.revision if head else 0,
                    "undoCount": cursor, "redoCount": len(entries) - cursor,
                    "undoLabel": entries[cursor - 1]["label"] if cursor else None,
                    "redoLabel": entries[cursor]["label"] if cursor < len(entries) else None,
                    "canUndo": bool(cursor and not conflict and not blocked), "canRedo": bool(cursor < len(entries) and not conflict and not blocked),
                    "busy": False, "recoveryRequired": bool(blocked), "conflicted": conflict, "fingerprint": fingerprint,
                    "error": blocked or ({"code": "CONFLICT", "message": "Project changed outside history; reload and start a fresh baseline"} if conflict else None)}}

    def read(self, db: Session, project_id: str):
        with self._transaction(db, write=False):
            project = self._project(db, project_id)
            reply = self._reply(db, project, db.get(HistoryRecord, project_id, populate_existing=True))
        return reply

    def _request(self, operation_id, expected_revision, request):
        try:
            if str(UUID(operation_id)) != operation_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HistoryFault("VALIDATION", "operation_id must be a canonical UUID", 422)
        if type(expected_revision) is not int or expected_revision < 0:
            raise HistoryFault("VALIDATION", "expected_revision must be a nonnegative integer", 422)
        return digest({"revision": expected_revision, **request})

    def _begin(self, db, project_id, operation_id, request_hash, expected_revision, *, allow_conflict=False):
        project = self._project(db, project_id)
        head = db.get(HistoryRecord, project_id)
        if not allow_conflict:
            self._validate(head)
        receipt = db.get(HistoryReceipt, (project_id, operation_id))
        if receipt:
            if receipt.request_hash != request_hash:
                raise HistoryFault("CONFLICT", "Reused operation ID has a different request", 409)
            return project, head, receipt
        if expected_revision != (head.revision if head else 0):
            raise HistoryFault("CONFLICT", "History revision changed; reload before editing", 409)
        fingerprint = self._fingerprint(db, project)
        if head and head.fingerprint != fingerprint and not allow_conflict:
            raise HistoryFault("CONFLICT", "Project changed outside history; reload before starting a fresh baseline", 409)
        if head is None:
            head = HistoryRecord(project_id=project_id, schema_version=1, revision=0, cursor=0, entries=[], fingerprint=fingerprint)
            db.add(head)
        return project, head, None

    def _finish(self, db, project, head, operation_id, request_hash, changed):
        if changed:
            head.revision += 1
        db.flush()
        head.fingerprint = self._fingerprint(db, project)
        db.add(HistoryReceipt(project_id=project.id, operation_id=operation_id, request_hash=request_hash, revision=head.revision))
        db.flush()
        return self._reply(db, project, head, operation_revision=head.revision)

    def execute(self, db, project_id, *, operation_id, expected_revision, command_type, version, label, input):
        if not isinstance(label, str) or not label.strip() or len(label) > 120:
            raise HistoryFault("VALIDATION", "Command label must contain 1–120 characters", 422)
        request_hash = self._request(operation_id, expected_revision, {"action": "execute", "type": command_type, "version": version, "label": label, "input": input})
        strategy = self.registry.resolve(command_type, version)
        payload = project = None
        try:
            with self._transaction(db):
                project, head, receipt = self._begin(db, project_id, operation_id, request_hash, expected_revision)
                if receipt:
                    reply = self._reply(db, project, head, replayed=True, operation_revision=receipt.revision)
                else:
                    command_input = {**deepcopy(input), "_history_operation_id": operation_id}
                    payload = strategy.prepare(db, project, command_input)
                    if payload is not None:
                        if not strategy.validate(payload):
                            raise HistoryFault("VALIDATION", "Invalid prepared command payload", 422)
                        entry = {"kind": "command", "id": operation_id, "type": command_type, "version": version, "label": label, "payload": payload}
                        if len(encoded([entry])) > self.max_bytes:
                            raise HistoryFault("CAPACITY", "Command exceeds history byte budget", 413)
                        entries = [*deepcopy(head.entries[:head.cursor]), entry]
                        while len(entries) > self.max_entries or len(encoded(entries)) > self.max_bytes:
                            entries.pop(0)
                        strategy.apply(db, project, payload, forward=True)
                        head.entries, head.cursor = entries, len(entries)
                    reply = self._finish(db, project, head, operation_id, request_hash, payload is not None)
        except Exception:
            if payload is not None and project is not None and hasattr(strategy, "compensate"):
                strategy.compensate(project, payload, forward=True)
            raise
        return reply

    def move(self, db, project_id, *, direction, operation_id, expected_revision):
        if direction not in {"undo", "redo"}:
            raise HistoryFault("VALIDATION", "Invalid history direction", 422)
        request_hash = self._request(operation_id, expected_revision, {"action": direction})
        project = strategy = payload = None
        forward = direction == "redo"
        try:
            with self._transaction(db):
                project, head, receipt = self._begin(db, project_id, operation_id, request_hash, expected_revision)
                if receipt:
                    reply = self._reply(db, project, head, replayed=True, operation_revision=receipt.revision)
                else:
                    index = head.cursor - 1 if direction == "undo" else head.cursor
                    changed = 0 <= index < len(head.entries)
                    if changed:
                        entry = head.entries[index]
                        strategy = self.registry.resolve(entry["type"], entry["version"])
                        payload = deepcopy(entry["payload"])
                        strategy.apply(db, project, payload, forward=forward)
                        head.cursor += -1 if direction == "undo" else 1
                    reply = self._finish(db, project, head, operation_id, request_hash, changed)
        except Exception:
            if strategy is not None and payload is not None and project is not None and hasattr(strategy, "compensate"):
                strategy.compensate(project, payload, forward=forward)
            raise
        return reply

    def reset(self, db, project_id, *, operation_id, expected_revision, fingerprint):
        request_hash = self._request(operation_id, expected_revision, {"action": "reset", "fingerprint": fingerprint})
        with self._transaction(db):
            project, head, receipt = self._begin(db, project_id, operation_id, request_hash, expected_revision, allow_conflict=True)
            if receipt:
                reply = self._reply(db, project, head, replayed=True, operation_revision=receipt.revision)
            else:
                if self._fingerprint(db, project) != fingerprint:
                    raise HistoryFault("CONFLICT", "Reload canonical project state before resetting history", 409)
                db.add(HistoryArchive(id=str(uuid4()), project_id=project_id, journal={"schemaVersion": head.schema_version,
                    "revision": head.revision, "cursor": head.cursor, "entries": deepcopy(head.entries), "fingerprint": head.fingerprint}))
                head.entries, head.cursor, head.schema_version = [], 0, 1
                reply = self._finish(db, project, head, operation_id, request_hash, True)
        return reply


project_history = ProjectHistory()
HistoryService = ProjectHistory

