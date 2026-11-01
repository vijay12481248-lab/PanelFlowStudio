"""Versioned, backed-up store for models we train, so a retrain can never destroy a good model.

Layout: <app_data>/models/registry/<name>/versions/vN/{files, manifest.json}, current.json, and a mirror of
every version under the backup root (default <repo>/model_backups, override with PANELFLOW_MODEL_BACKUP).
Versions are immutable: publishing never overwrites, and nothing here ever deletes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from engine.config.settings import settings

_REPO = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class ModelStore:
    def __init__(self, root: Path | None = None, backup_root: Path | None = None):
        self.root = Path(root) if root else settings.app_data_dir / "models" / "registry"
        env = os.environ.get("PANELFLOW_MODEL_BACKUP")
        self.backup_root = Path(backup_root) if backup_root else Path(env) if env else _REPO / "model_backups"

    def _dir(self, name: str, version: int, backup: bool = False) -> Path:
        return (self.backup_root if backup else self.root) / name / "versions" / f"v{version}"

    def versions(self, name: str) -> list[int]:
        folder = self.root / name / "versions"
        return sorted(int(p.name[1:]) for p in folder.glob("v*") if p.name[1:].isdigit()) if folder.is_dir() else []

    def current(self, name: str) -> int | None:
        try:
            return int(json.loads((self.root / name / "current.json").read_text(encoding="utf-8"))["version"])
        except (OSError, ValueError, KeyError):
            return None

    def current_path(self, name: str) -> Path | None:
        v = self.current(name)
        return self._dir(name, v) if v is not None else None

    def publish(self, name: str, src: Path, *, metrics: dict, base_model: str, data: dict, notes: str = "",
                make_current: bool = True) -> int:
        src = Path(src)
        files = sorted(p for p in src.rglob("*") if p.is_file())
        if not files:
            raise ValueError(f"nothing to publish in {src}")
        version = (self.versions(name) or [0])[-1] + 1
        dest = self._dir(name, version)
        if dest.exists():
            raise FileExistsError(dest)
        shutil.copytree(src, dest)
        manifest = {
            "name": name, "version": version, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "base_model": base_model, "metrics": metrics, "data": data, "notes": notes,
            "git_commit": self._git_commit(), "files": {str(p.relative_to(dest)): _sha256(p) for p in dest.rglob("*") if p.is_file()},
        }
        _write_atomic(dest / "manifest.json", manifest)
        self._mirror(name, version)
        if make_current:
            self.set_current(name, version)
        return version

    def set_current(self, name: str, version: int) -> None:
        problems = self.verify(name, version)
        if problems:
            raise ValueError(f"{name} v{version} failed verification: {problems}")
        _write_atomic(self.root / name / "current.json", {"version": version, "set": time.strftime("%Y-%m-%dT%H:%M:%S%z")})

    def verify(self, name: str, version: int, backup: bool = False) -> list[str]:
        """Empty list when every file still matches the hash recorded at publish time."""
        d = self._dir(name, version, backup)
        try:
            manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ["manifest.json missing or unreadable"]
        problems = [f"{rel}: missing" if not (d / rel).is_file() else f"{rel}: hash changed"
                    for rel, digest in manifest["files"].items() if not (d / rel).is_file() or _sha256(d / rel) != digest]
        return problems

    def restore_from_backup(self, name: str, version: int) -> None:
        """Bring back a damaged or deleted version from the mirror; refuses if the mirror is not intact too."""
        if (bad := self.verify(name, version, backup=True)):
            raise ValueError(f"backup of {name} v{version} is not intact: {bad}")
        dest = self._dir(name, version)
        if dest.exists():
            dest.rename(dest.with_name(dest.name + f".damaged-{int(time.time())}"))  # keep, never delete
        shutil.copytree(self._dir(name, version, backup=True), dest)

    def _mirror(self, name: str, version: int) -> None:
        dest = self._dir(name, version, backup=True)
        try:
            shutil.copytree(self._dir(name, version), dest, dirs_exist_ok=True)
        except OSError as exc:
            raise RuntimeError(f"model saved, but the backup copy to {dest} failed: {exc}") from exc
        if (bad := self.verify(name, version, backup=True)):
            raise RuntimeError(f"backup copy of {name} v{version} did not verify: {bad}")

    @staticmethod
    def _git_commit() -> str | None:
        try:
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True, text=True,
                                  timeout=10, check=True).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None


def mirror_tree(src: Path, dst: Path) -> int:
    """Copy new or changed files from src to dst (training data, bibles). Never deletes; returns files copied."""
    copied = 0
    for p in Path(src).rglob("*"):
        if not p.is_file():
            continue
        target = Path(dst) / p.relative_to(src)
        if target.exists() and target.stat().st_size == p.stat().st_size and target.stat().st_mtime >= p.stat().st_mtime:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        copied += 1
    return copied
