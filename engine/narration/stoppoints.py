"""Stop points: the decisions the workflow pauses for.

The workflow stops and asks when

- the story brief is uncertain,
- a new or cloned voice needs approval, or
- a proposed casting change would affect an assignment the owner already made.

Everything else — the generation, the retries, the repairs — carries on on its
own. A stop point is a question with a small set of answers; answering it
resolves the point and the run carries on.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from engine.narration.artifacts import StopPoint

STOP_POINTS_FILE = "stop_points.json"


def stop_points_path(run_dir: Path) -> Path:
    return Path(run_dir) / STOP_POINTS_FILE


def load_stop_points(run_dir: Path) -> list[StopPoint]:
    """The stop points a run is waiting on."""
    path = stop_points_path(run_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    out: list[StopPoint] = []
    for item in data if isinstance(data, list) else []:
        try:
            out.append(StopPoint.model_validate(item))
        except ValueError:
            continue  # one corrupt point must not hide the rest
    return out


def save_stop_points(run_dir: Path, points: list[StopPoint]) -> None:
    path = stop_points_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps([p.model_dump(mode="json") for p in points], ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def add_stop_point(run_dir: Path, point: StopPoint) -> list[StopPoint]:
    """Record a stop point, and return the ones now waiting."""
    points = [p for p in load_stop_points(run_dir) if not p.resolution]
    if not any(p.kind == point.kind and p.detail == point.detail for p in points):
        points.append(point)
    save_stop_points(run_dir, points)
    return points


def resolve_stop_point(run_dir: Path, kind: str, choice: str) -> list[StopPoint]:
    """The owner answers a stop point. The answer is kept with it."""
    points = load_stop_points(run_dir)
    for p in points:
        if p.kind == kind and not p.resolution:
            p.resolution = choice
            break
    save_stop_points(run_dir, points)
    return [p for p in points if not p.resolution]


def open_stop_points(run_dir: Path) -> list[StopPoint]:
    """The stop points still waiting for an answer."""
    return [p for p in load_stop_points(run_dir) if not p.resolution]
