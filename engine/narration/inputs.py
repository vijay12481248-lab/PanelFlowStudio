"""Load a chapter's panels and OCR text from the project DB as narration-compiler inputs."""
from __future__ import annotations

from dataclasses import dataclass
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
            .filter(TextRegionRecord.panel_id == row.id, TextRegionRecord.status != "IGNORED")
            .order_by(TextRegionRecord.sequence_global)
            .all()
        )
        ocr = []
        for r in regions:
            text = (r.corrected_text or "").strip() or (r.raw_text or "").strip()
            if text:
                ocr.append(OcrRegionInput(r.id, text, r.region_type))
        image = resolve_contained_path(panels_dir, row.crop_filename, must_be_file=True)
        panels.append(PanelInput(row.id, order, image, ocr))
    key = series_key_for(project.title, project.source_metadata)
    if not key:  # BibleStore rejects empty keys
        key = "project-" + "".join(c for c in project_id.lower() if c.isalnum())[:8]
    return ChapterInputs(project_id, key, panels)
