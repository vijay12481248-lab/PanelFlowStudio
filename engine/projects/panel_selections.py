"""Validated, atomic selector replacement without overwriting existing crop files."""
import json
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import PageRecord, PanelRecord, ProjectRecord
from engine.security.paths import resolve_contained_path, open_contained_output


class Selection(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=4)
    height: int = Field(ge=4)
    points: list[tuple[int, int]] | None = Field(default=None, min_length=3, max_length=512)


class SaveSelectionsRequest(BaseModel):
    selections: list[Selection] = Field(min_length=1, max_length=64)
    page_bounds: bool = False


def validate_selection(selection: Selection, bounds: tuple[int, int, int, int]):
    x, y, w, h = bounds
    s = selection
    if s.x < x or s.y < y or s.x + s.width > x + w or s.y + s.height > y + h:
        raise ValueError("Selectors must remain inside the editing bounds.")
    points = s.points
    if not points:
        return
    if any(not (s.x <= px <= s.x + s.width and s.y <= py <= s.y + s.height) for px, py in points):
        raise ValueError("Polygon vertices must remain inside their selector bounds.")
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))
    if abs(area) < 8:
        raise ValueError("Polygon has no usable area.")
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    edges = list(zip(points, points[1:] + points[:1]))
    for i, (a, b) in enumerate(edges):
        if a == b:
            raise ValueError("Polygon contains duplicate adjacent vertices.")
        for j in range(i + 2, len(edges)):
            if i == 0 and j == len(edges) - 1:
                continue
            c, d = edges[j]
            if (cross(a, b, c) * cross(a, b, d) <= 0 and cross(c, d, a) * cross(c, d, b) <= 0
                and max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
                and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))):
                raise ValueError("Polygon edges must not cross or overlap.")


def save_selections(db: Session, project_id: str, panel_id: str | None, selections: list[Selection], *,
                    page_bounds: bool = False, page_id: str | None = None) -> list[PanelRecord]:
    project = db.query(ProjectRecord).filter_by(id=project_id).first()
    panel = db.query(PanelRecord).filter_by(id=panel_id, project_id=project_id).first() if panel_id else None
    if not project or (panel_id and not panel):
        raise KeyError("Project or panel not found.")
    page = db.query(PageRecord).filter_by(id=panel.page_id if panel else page_id, project_id=project_id).first()
    if not page:
        raise KeyError("Source page not found.")
    workspace = Path(project.workspace_path).resolve()
    source = resolve_contained_path(workspace, Path("normalized") / f"page_{page.sequence:04d}.jpg")
    if not source.is_file():
        source = resolve_contained_path(workspace, Path("source") / page.filename, must_be_file=True)
    all_panels = db.query(PanelRecord).filter_by(project_id=project_id).order_by(PanelRecord.sequence).all()
    pages = db.query(PageRecord).filter_by(project_id=project_id).order_by(PageRecord.sequence).all()
    created_files = []
    replacements = []
    manifest = resolve_contained_path(workspace, Path("panels") / "panels.json")
    previous_manifest = manifest.read_bytes() if manifest.is_file() else None
    manifest_changed = False
    try:
        with Image.open(source) as image:
            limit = (0, 0, image.width, image.height) if page_bounds or not panel else (panel.x, panel.y, panel.width, panel.height)
            for selection in selections:
                validate_selection(selection, limit)
            for index, selection in enumerate(selections):
                s = selection
                if s.x + s.width > image.width or s.y + s.height > image.height:
                    raise ValueError("Selector exceeds the source image dimensions.")
                filename = f"selector_{uuid4().hex}.png"
                target = resolve_contained_path(workspace, Path("panels") / filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                crop = image.crop((s.x, s.y, s.x + s.width, s.y + s.height)).convert("RGBA")
                if s.points:
                    mask = Image.new("L", crop.size, 0)
                    ImageDraw.Draw(mask).polygon([(px - s.x, py - s.y) for px, py in s.points], fill=255)
                    crop.putalpha(mask)
                created_files.append(target)
                crop.save(target)
                replacement = panel if index == 0 and panel else PanelRecord(
                    id=str(uuid4()), project_id=project_id, page_id=page.id,
                    sequence=panel.sequence if panel else len(all_panels) + index + 1, page_sequence=1,
                    reading_direction=panel.reading_direction if panel else "ltr", panel_type=panel.panel_type if panel else "STANDARD",
                )
                replacement.x, replacement.y, replacement.width, replacement.height = s.x, s.y, s.width, s.height
                replacement.normalized_x = s.x / max(1, page.width)
                replacement.normalized_y = s.y / max(1, page.height)
                replacement.normalized_width = s.width / max(1, page.width)
                replacement.normalized_height = s.height / max(1, page.height)
                replacement.polygon_json = json.dumps(s.points) if s.points else None
                replacement.crop_filename = filename
                replacement.manually_modified = True
                replacement.detection_method = "MANUAL"
                replacement.status = "MANUAL"
                replacement.confidence = 1.0
                db.add(replacement)
                replacements.append(replacement)
        ordered = []
        for item in all_panels:
            ordered.extend(replacements if item.id == panel_id else [item])
        if not panel:
            ordered.extend(replacements)
        sequence = 1
        for source_page in pages:
            page_items = [item for item in ordered if item.page_id == source_page.id]
            for page_sequence, item in enumerate(page_items, 1):
                item.sequence, item.page_sequence = sequence, page_sequence
                sequence += 1
        db.flush()
        inventory = {"project_id": project_id, "version": "1.0", "total_panels": len(ordered), "panels": [
            {"id": p.id, "page_id": p.page_id, "sequence": p.sequence, "sequence_global": p.sequence, "sequence_page": p.page_sequence,
             "x": p.x, "y": p.y, "width": p.width, "height": p.height,
             "normalized": {"x": p.normalized_x, "y": p.normalized_y, "width": p.normalized_width, "height": p.normalized_height},
             "crop_reference": f"panels/{p.crop_filename}", "polygon_json": p.polygon_json,
             "reading_direction": p.reading_direction, "confidence": p.confidence, "panel_type": p.panel_type,
             "status": p.status, "detection_method": p.detection_method, "manually_modified": p.manually_modified}
            for p in sorted(ordered, key=lambda p: p.sequence)]}
        manifest_changed = True
        with open_contained_output(workspace, Path("panels") / "panels.json") as output:
            output.write(json.dumps(inventory, indent=2).encode("utf-8"))
        db.commit()
    except Exception:
        db.rollback()
        for target in created_files:
            target.unlink(missing_ok=True)
        if manifest_changed:
            if previous_manifest is None:
                manifest.unlink(missing_ok=True)
            else:
                with open_contained_output(workspace, Path("panels") / "panels.json") as output:
                    output.write(previous_manifest)
        raise
    return db.query(PanelRecord).filter_by(project_id=project_id).order_by(PanelRecord.sequence).all()
