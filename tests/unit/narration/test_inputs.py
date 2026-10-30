import uuid

import pytest
from PIL import Image

from engine.database.models import PageRecord, PanelRecord, ProjectRecord, TextRegionRecord
from engine.database.session import SessionLocal, init_db
from engine.narration.inputs import load_chapter_inputs


def _project(tmp_path, panels, regions=(), title="Test - Chapter 1", meta=None):
    """panels: [(sequence, status)]; regions: [(panel_index, seq, raw, corrected, status)]."""
    init_db()
    pid = str(uuid.uuid4())
    (tmp_path / "panels").mkdir(exist_ok=True)
    with SessionLocal() as db:
        db.add(ProjectRecord(id=pid, title=title, source_type="LOCAL_FOLDER",
                             workspace_path=str(tmp_path), source_metadata=meta or {}))
        db.flush()
        page_id = str(uuid.uuid4())
        db.add(PageRecord(id=page_id, project_id=pid, sequence=1, filename="page.jpg"))
        db.flush()
        ids = []
        for i, (seq, status) in enumerate(panels):
            name = f"panel{i}.png"
            Image.new("RGB", (4, 4), "white").save(tmp_path / "panels" / name)
            panel_id = str(uuid.uuid4())
            ids.append(panel_id)
            db.add(PanelRecord(id=panel_id, project_id=pid, page_id=page_id, sequence=seq, page_sequence=i + 1,
                               x=0, y=0, width=4, height=4, crop_filename=name, status=status))
        db.flush()
        for pi, seq, raw, corrected, status in regions:
            db.add(TextRegionRecord(project_id=pid, page_id=page_id, panel_id=ids[pi], sequence_global=seq,
                                    x=0, y=0, width=1, height=1, raw_text=raw, corrected_text=corrected,
                                    status=status))
        db.commit()
    return pid, ids


def test_loads_panels_in_sequence_and_skips_ignored(tmp_path):
    pid, ids = _project(tmp_path, [(2, "DETECTED"), (1, "DETECTED"), (3, "IGNORED")])
    out = load_chapter_inputs(SessionLocal(), pid)
    assert [p.panel_id for p in out.panels] == [ids[1], ids[0]]
    assert [p.order for p in out.panels] == [1, 2]
    assert out.panels[0].image_path.name == "panel1.png"


def test_ocr_prefers_corrected_text_and_skips_empty_and_ignored(tmp_path):
    pid, _ = _project(tmp_path, [(1, "DETECTED")], [
        (0, 4, "x", "x", "IGNORED"),
        (0, 3, "World", "", "DETECTED"),
        (0, 2, "", "  ", "DETECTED"),
        (0, 1, "Helo", " Hello ", "DETECTED"),
    ])
    out = load_chapter_inputs(SessionLocal(), pid)
    assert [r.text for r in out.panels[0].ocr] == ["Hello", "World"]


def test_series_key_from_project_metadata(tmp_path):
    pid, _ = _project(tmp_path, [(1, "DETECTED")], meta={"series_title": "Magic Emperor"})
    assert load_chapter_inputs(SessionLocal(), pid).series_key == "magic-emperor"


def test_series_key_falls_back_to_project_id_when_title_yields_none(tmp_path):
    pid, _ = _project(tmp_path, [(1, "DETECTED")], title="!!!")
    expected = "project-" + "".join(c for c in pid.lower() if c.isalnum())[:8]
    assert load_chapter_inputs(SessionLocal(), pid).series_key == expected


def test_unknown_project_raises_key_error():
    init_db()
    with pytest.raises(KeyError):
        load_chapter_inputs(SessionLocal(), "missing")
