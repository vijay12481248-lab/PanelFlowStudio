"""Load a chapter's panels and OCR text from the project DB as narration-compiler inputs."""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from engine.database.models import PanelRecord, ProjectRecord, TextRegionRecord
from engine.narration.bible.store import series_key_for
from engine.security.paths import resolve_contained_path


@dataclass(frozen=True)
class OcrRegionInput:
    region_id: str
    text: str
    region_type: str


@dataclass(frozen=True)
class PanelInput:
    panel_id: str
    order: int
    image_path: Path
    ocr: list[OcrRegionInput]
    sfx: list[str] = field(default_factory=list)  # SFX regions: never dialogue


@dataclass(frozen=True)
class ChapterInputs:
    project_id: str
    series_key: str
    panels: list[PanelInput]


def load_chapter_inputs(db: Session, project_id: str) -> ChapterInputs:
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise KeyError(project_id)
    rows = (
        db.query(PanelRecord)
        .filter(PanelRecord.project_id == project_id, PanelRecord.status != "IGNORED")
        .order_by(PanelRecord.sequence)
        .all()
    )
    if not rows:
        raise ValueError(f"project {project_id} has no usable panels")
    panels_dir = Path(project.workspace_path) / "panels"
    panels = []
    for order, row in enumerate(rows, start=1):
        regions = (
            db.query(TextRegionRecord)
            .filter(TextRegionRecord.panel_id == row.id, TextRegionRecord.status.notin_(("IGNORED", "BLURRED")),
                    TextRegionRecord.region_type != "REDACTED")
            .order_by(TextRegionRecord.sequence_global)
            .all()
        )
        ocr, sfx = [], []
        for r in regions:
            text = (r.corrected_text or "").strip() or (r.raw_text or "").strip()
            if text:
                (sfx if r.region_type == "SFX" else ocr).append(
                    text if r.region_type == "SFX" else OcrRegionInput(r.id, text, r.region_type))
        image = resolve_contained_path(panels_dir, row.crop_filename, must_be_file=True)
        panels.append(PanelInput(row.id, order, image, ocr, sfx))
    key = series_key_for(project.title, project.source_metadata)
    if not key:  # BibleStore rejects empty keys
        key = "project-" + "".join(c for c in project_id.lower() if c.isalnum())[:8]
    return ChapterInputs(project_id, key, panels)


def dump_chapter_inputs(inputs: ChapterInputs, dest: Path) -> None:
    """Write inputs.json plus panels/*.png under dest; image paths are stored relative to dest/panels."""
    panels_dir = Path(dest) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in inputs.panels:
        name = f"{p.order:04d}{p.image_path.suffix}"
        shutil.copyfile(p.image_path, panels_dir / name)
        rows.append({"panel_id": p.panel_id, "order": p.order, "image": name, "sfx": p.sfx,
                     "ocr": [asdict(r) for r in p.ocr]})
    (Path(dest) / "inputs.json").write_text(json.dumps(
        {"project_id": inputs.project_id, "series_key": inputs.series_key, "panels": rows},
        ensure_ascii=False, indent=1), encoding="utf-8")


def load_chapter_inputs_from_dir(src: Path) -> ChapterInputs:
    src = Path(src)
    data = json.loads((src / "inputs.json").read_text(encoding="utf-8"))
    panels = [PanelInput(r["panel_id"], r["order"], src / "panels" / r["image"],
                         [OcrRegionInput(**o) for o in r["ocr"]], r.get("sfx", [])) for r in data["panels"]]
    return ChapterInputs(data["project_id"], data["series_key"], panels)
