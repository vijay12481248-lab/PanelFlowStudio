path = "engine/projects/service.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

target = """        async def run_ocr(cancel_token: PipelineCancellationToken, progress_cb):
            from engine.database.session import SessionLocal
            with SessionLocal() as worker_db:
                ws_path = Path(record.workspace_path)
                panels_dir = resolve_contained_path(ws_path, "panels")
                total_panels = len(panels)

                for idx, panel in enumerate(panels, start=1):"""

replacement = """        async def run_ocr(cancel_token: PipelineCancellationToken, progress_cb):
            from engine.database.session import SessionLocal
            with SessionLocal() as worker_db:
                ws_path = Path(record.workspace_path)
                panels_dir = resolve_contained_path(ws_path, "panels")
                panel_id_list = [p.id for p in panels]
                worker_panels = (
                    worker_db.query(PanelRecord)
                    .filter(PanelRecord.id.in_(panel_id_list))
                    .order_by(PanelRecord.sequence.asc())
                    .all()
                )
                total_panels = len(worker_panels)

                for idx, panel in enumerate(worker_panels, start=1):"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("Fixed run_ocr detached instance bug in engine/projects/service.py")
else:
    print("Target not found")
