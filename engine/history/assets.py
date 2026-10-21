"""Retained project-file snapshots for commands that also mutate the filesystem.

The database journal stores command intent. This store retains the file bytes
needed to replay that intent, and leaves a small recovery manifest inside the
project workspace. It intentionally accepts only regular files contained by
that workspace; callers must handle directories as explicit file lists.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4


class RetainedAssetStore:
    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".panelflow-history-assets"

    def capture_before(self, operation_id: str, paths: list[str]) -> None:
        if not operation_id or any(char in operation_id for char in "\\/"):
            raise ValueError("operation ID must be a simple identifier")
        if not paths:
            raise ValueError("at least one retained asset path is required")
        operation = self.root / operation_id
        if operation.exists():
            raise ValueError("retained asset operation already exists")
        entries = []
        for relative in paths:
            target = self._target(relative)
            existed = target.exists()
            if existed:
                self._require_regular_file(target)
                self._copy_atomic(target, operation / "before" / relative)
            entries.append({"path": relative.replace("\\", "/"), "before": existed, "after": None})
        self._write_manifest(operation, {"version": 1, "state": "prepared", "paths": entries})

    def capture_after(self, operation_id: str) -> None:
        operation, manifest = self._manifest(operation_id)
        if manifest["state"] != "prepared":
            raise ValueError("retained asset operation is not prepared")
        for entry in manifest["paths"]:
            target = self._target(entry["path"])
            existed = target.exists()
            if existed:
                self._require_regular_file(target)
                self._copy_atomic(target, operation / "after" / entry["path"])
            entry["after"] = existed
        manifest["state"] = "complete"
        self._write_manifest(operation, manifest)

    def is_complete(self, operation_id: str) -> bool:
        """Whether the operation has a durable after-image for safe replay."""
        _, manifest = self._manifest(operation_id)
        return manifest["state"] == "complete"

    def restore(self, operation_id: str, phase: str) -> None:
        if phase not in {"before", "after"}:
            raise ValueError("restore phase must be before or after")
        operation, manifest = self._manifest(operation_id)
        if phase == "after" and manifest["state"] != "complete":
            raise ValueError("cannot restore incomplete retained assets")
        for entry in manifest["paths"]:
            target = self._target(entry["path"])
            if entry[phase]:
                source = operation / phase / entry["path"]
                self._require_snapshot(source)
                self._copy_atomic(source, target)
            elif target.exists():
                self._require_regular_file(target)
                target.unlink()

    def recover(self) -> list[str]:
        if not self.root.exists():
            return []
        recovered: list[str] = []
        for operation in sorted(path for path in self.root.iterdir() if path.is_dir()):
            manifest_path = operation / "manifest.json"
            if not manifest_path.exists():
                continue
            _, manifest = self._manifest(operation.name)
            if manifest["state"] == "prepared":
                self.restore(operation.name, "before")
                manifest["state"] = "recovered"
                self._write_manifest(operation, manifest)
                recovered.append(operation.name)
        return recovered

    def _manifest(self, operation_id: str) -> tuple[Path, dict]:
        if not operation_id or any(char in operation_id for char in "\\/"):
            raise ValueError("operation ID must be a simple identifier")
        operation = self.root / operation_id
        try:
            manifest = json.loads((operation / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("retained asset manifest is invalid") from error
        if (not isinstance(manifest, dict) or manifest.get("version") != 1
                or manifest.get("state") not in {"prepared", "complete", "recovered"}
                or not isinstance(manifest.get("paths"), list)
                or any(not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                       or type(entry.get("before")) is not bool or entry.get("after") not in {None, True, False}
                       for entry in manifest["paths"])):
            raise ValueError("retained asset manifest is invalid")
        for entry in manifest["paths"]:
            self._target(entry["path"])
        return operation, manifest

    def _target(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative:
            raise ValueError("asset path must be contained by the project workspace")
        candidate = (self.workspace / relative).resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as error:
            raise ValueError("asset path must be contained by the project workspace") from error
        return candidate

    @staticmethod
    def _require_regular_file(path: Path) -> None:
        if not path.is_file() or path.is_symlink():
            raise ValueError("retained assets must be regular files")

    @staticmethod
    def _require_snapshot(path: Path) -> None:
        if not path.is_file() or path.is_symlink():
            raise ValueError("retained asset snapshot is missing or unsafe")

    @staticmethod
    def _copy_atomic(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with source.open("rb") as reader, temporary.open("xb") as writer:
                while chunk := reader.read(1024 * 1024):
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _write_manifest(operation: Path, manifest: dict) -> None:
        operation.mkdir(parents=True, exist_ok=True)
        destination = operation / "manifest.json"
        temporary = operation / f".manifest.{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as writer:
                json.dump(manifest, writer, sort_keys=True, separators=(",", ":"))
                writer.flush()
                os.fsync(writer.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def recover_workspaces(workspaces: list[Path | str]) -> dict[str, list[str]]:
    """Recover prepared retained-file operations before serving project history."""
    recovered: dict[str, list[str]] = {}
    for workspace in workspaces:
        root = Path(workspace)
        if not root.is_dir():
            continue
        restored = RetainedAssetStore(root).recover()
        if restored:
            recovered[str(root.resolve())] = restored
    return recovered
