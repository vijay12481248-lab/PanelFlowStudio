"""Mirror training data and series bibles to the backup drive (new/changed files only; never deletes).

Usage: python scripts/backup_training_assets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config.settings import settings  # noqa: E402
from engine.training.registry import ModelStore, mirror_tree  # noqa: E402

if __name__ == "__main__":
    backup = ModelStore().backup_root
    for name in ("training", "series"):
        src = settings.app_data_dir / name
        if src.is_dir():
            print(f"{name}: {mirror_tree(src, backup / '_assets' / name)} files copied -> {backup / '_assets' / name}")
