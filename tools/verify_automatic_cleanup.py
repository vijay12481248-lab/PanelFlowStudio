"""Run real OCR cleanup on isolated copies, never on the user's project media.

Usage: python -m tools.verify_automatic_cleanup --project-id ID --panels 1 5 23
"""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from engine.database.models import Base, PageRecord, PanelRecord, ProjectRecord
from engine.database.session import SessionLocal
from engine.imaging.content_cleanup import cleanup_detected_panels, load_rules


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--panels", nargs="+", type=int, required=True)
    parser.add_argument("--output", default="output/automatic-cleanup-proof")
    args = parser.parse_args()
    out = Path(args.output).resolve()
    workspace = out / f"isolated-{uuid4().hex[:8]}"
    (workspace / "panels").mkdir(parents=True)
    with SessionLocal() as source:
        project = source.get(ProjectRecord, args.project_id)
        if project is None:
            raise ValueError("Project not found")
        samples = [{"sequence": p.sequence, "width": p.width, "height": p.height,
                    "path": str(Path(project.workspace_path) / "panels" / p.crop_filename)}
                   for p in source.query(PanelRecord).filter(PanelRecord.project_id == project.id,
                           PanelRecord.sequence.in_(args.panels)).order_by(PanelRecord.sequence)]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ProjectRecord(id="proof", title="Isolated verification", source_type="LOCAL_FOLDER",
                             workspace_path=str(workspace), rights_status="PUBLIC_DOMAIN"))
        db.add(PageRecord(id="page", project_id="proof", sequence=1, filename="unused.jpg", width=1920, height=10000))
        for sample in samples:
            filename = f"panel-{sample['sequence']}.jpg"
            shutil.copyfile(sample["path"], workspace / "panels" / filename)
            db.add(PanelRecord(id=str(sample["sequence"]), project_id="proof", page_id="page",
                               sequence=sample["sequence"], page_sequence=sample["sequence"], x=0, y=0,
                               width=sample["width"], height=sample["height"], crop_filename=filename))
        db.commit()
        report = cleanup_detected_panels(db, "proof", [str(s["sequence"]) for s in samples])
        report.update(scope="Real OCR on isolated copies; source project unchanged", rules=load_rules().model_dump())
        (out / "real-ocr-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    actions = {item["sequence"]: item["action"] for item in report["items"]}
    sheet = Image.new("RGB", (900, max(1, len(samples))*240), "#202024")
    draw = ImageDraw.Draw(sheet)
    for i, sample in enumerate(samples):
        y = i*240
        draw.text((10, y+5), f"Panel {sample['sequence']} | BEFORE", fill="white")
        draw.text((460, y+5), f"AFTER: {actions[sample['sequence']]}", fill="white")
        with Image.open(sample["path"]) as image:
            sheet.paste(ImageOps.contain(image.convert("RGB"), (430, 210)), (10, y+25))
        if actions[sample["sequence"]] == "EXCLUDE":
            draw.text((460, y+90), "Excluded from story / timeline", fill="#ffcc66")
        else:
            with Image.open(workspace / "panels" / f"panel-{sample['sequence']}.jpg") as image:
                sheet.paste(ImageOps.contain(image.convert("RGB"), (430, 210)), (460, y+25))
    sheet.save(out / "before-after.jpg")
    print(json.dumps(actions))


if __name__ == "__main__":
    main()
