import json
import logging
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from engine.config.settings import settings
from engine.database.models import (
    ProjectRecord,
    PageRecord,
    PanelRecord,
    NormalizationRecord,
    JobRecord,
    OCRRecord,
    TextRegionRecord,
    OCRCacheRecord,
)
from engine.acquisition.models import (
    PipelineStage,
    SourceType,
    JobType,
    JobStatus,
    PageCandidate,
    ChapterInfo,
    AcquisitionManifest,
    ManifestPage,
)
from engine.acquisition.rights.models import RightsStatus, RightsDeclaration
from engine.acquisition.downloader.pipeline import (
    DownloadPipeline,
    PipelineCancellationToken,
)
from engine.acquisition.downloader.validation import rotate_image_file
from engine.acquisition.adapters.registry import AdapterRegistry
from engine.imaging.normalization import page_normalizer, NormalizationConfig
from engine.imaging.panels import panel_detector, PanelBox
from engine.jobs.manager import job_manager

logger = logging.getLogger(__name__)

def utc_now():
    return datetime.now(timezone.utc)

class ProjectService:
    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or settings.workspace_root
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def create_project(
        self,
        db: Session,
        title: str,
        source_type: str | SourceType,
        rights_status: str | RightsStatus,
        source_url: str | None = None,
        source_metadata: dict | None = None,
        license_info: str = "",
        project_settings: dict | None = None,
    ) -> ProjectRecord:
        # Rights validation
        r_enum = RightsStatus(rights_status)
        rights_decl = RightsDeclaration(
            status=r_enum,
            license_type=license_info,
            permission_notes=license_info,
        )

        project_id = str(uuid.uuid4())
        
        # User Project Location support: if specified in settings or metadata, write directly there
        custom_path = None
        if project_settings:
            custom_path = project_settings.get("project_path") or project_settings.get("destination_path")
        if not custom_path and source_metadata:
            custom_path = source_metadata.get("project_path")

        if custom_path:
            workspace_path = Path(custom_path).resolve()
        else:
            workspace_path = self.workspace_root / project_id

        workspace_path.mkdir(parents=True, exist_ok=True)
        for sub in ("source", "normalized", "panels", "ocr", "story", "script", "audio", "motion", "renders", "logs"):
            (workspace_path / sub).mkdir(exist_ok=True)

        initial_stage = (
            PipelineStage.RIGHTS_APPROVED
            if rights_decl.is_actionable()
            else PipelineStage.NEW
        )

        s_type = source_type.value if isinstance(source_type, SourceType) else source_type

        record = ProjectRecord(
            id=project_id,
            title=title.strip() or "Untitled Project",
            source_type=s_type,
            source_url=source_url,
            source_metadata=source_metadata or {},
            rights_status=r_enum.value,
            license_info=license_info,
            workspace_path=str(workspace_path.resolve()),
            current_stage=initial_stage.value,
            settings=project_settings or {},
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # Write initial project.json
        self._write_project_json(record)

        return record

    def _write_project_json(self, record: ProjectRecord) -> None:
        p_path = Path(record.workspace_path) / "project.json"
        data = {
            "id": record.id,
            "title": record.title,
            "source_type": record.source_type,
            "source_url": record.source_url,
            "rights_status": record.rights_status,
            "license_info": record.license_info,
            "current_stage": record.current_stage,
            "settings": record.settings,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
        with open(p_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_project(self, db: Session, project_id: str) -> ProjectRecord | None:
        return db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()

    def list_projects(self, db: Session) -> list[ProjectRecord]:
        return db.query(ProjectRecord).order_by(ProjectRecord.updated_at.desc()).all()

    def delete_project(self, db: Session, project_id: str) -> bool:
        record = self.get_project(db, project_id)
        if not record:
            return False

        ws_path = Path(record.workspace_path)
        if ws_path.is_dir():
            try:
                shutil.rmtree(ws_path)
            except Exception as e:
                logger.warning(f"Error deleting workspace {ws_path}: {e}")

        db.delete(record)
        db.commit()
        return True

    def sync_manifest_with_db(self, db: Session, project_id: str) -> AcquisitionManifest:
        """
        Reconstructs and atomically writes `manifest.json` from SQLite pages.
        """
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        pages = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id)
            .order_by(PageRecord.sequence.asc())
            .all()
        )

        ws_path = Path(record.workspace_path)
        manifest_file = ws_path / "manifest.json"

        created_at_iso = utc_now().isoformat()
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    created_at_iso = old_data.get("created_at", created_at_iso)
            except Exception:
                pass

        manifest_pages = [
            ManifestPage(
                id=p.id,
                sequence=p.sequence,
                filename=p.filename,
                source_url=p.source_url,
                sha256=p.sha256,
                width=p.width,
                height=p.height,
                bytes=p.byte_size,
                content_type=p.content_type,
                status=p.status,
                error_message=p.error_message,
            )
            for p in pages
        ]

        manifest = AcquisitionManifest(
            project_id=project_id,
            version="1.0",
            created_at=created_at_iso,
            updated_at=utc_now().isoformat(),
            source={
                "type": record.source_type,
                "url": record.source_url,
                "metadata": record.source_metadata,
            },
            rights={
                "status": record.rights_status,
                "license_info": record.license_info,
            },
            chapter={},
            pages=manifest_pages,
        )

        temp_manifest = ws_path / "manifest.json.tmp"
        with open(temp_manifest, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))
        temp_manifest.replace(manifest_file)

        return manifest

    def start_acquisition_job(
        self,
        db: Session,
        project_id: str,
        adapter_registry: AdapterRegistry,
        source_override: str | None = None,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        # Enforce rights status validation
        rights_decl = RightsDeclaration(
            status=RightsStatus(record.rights_status),
            license_type=record.license_info,
        )
        rights_decl.validate_for_acquisition()

        source_loc = source_override or record.source_url or record.source_metadata.get("path")
        if not source_loc:
            raise ValueError("No source URL or directory path provided for project acquisition.")

        adapter = adapter_registry.get_adapter_for(source_loc)
        inspection = adapter.inspect(source_loc)
        if not inspection.is_valid:
            raise ValueError(f"Source validation failed: {inspection.error}")

        chapters = adapter.list_chapters(source_loc)
        if not chapters:
            raise ValueError("No chapters or image sequences discovered from source.")

        selected_chapter = chapters[0]
        candidates = adapter.list_pages(selected_chapter)
        if not candidates:
            raise ValueError("No image candidates discovered in chapter.")

        # Check for simulated delay from project settings
        page_delay = 0.0
        if record.settings and "simulated_page_delay_sec" in record.settings:
            try:
                page_delay = float(record.settings["simulated_page_delay_sec"])
            except (ValueError, TypeError):
                page_delay = 0.0

        if page_delay > 0:
            for c in candidates:
                if not hasattr(c, "extra_metadata") or c.extra_metadata is None:
                    c.extra_metadata = {}
                c.extra_metadata["delay_sec"] = page_delay

        # Create job
        job = job_manager.create_job(
            project_id=project_id,
            job_type=JobType.ACQUISITION,
            job_input={
                "source": source_loc,
                "chapter_id": selected_chapter.id,
                "total_pages": len(candidates),
                "adapter_id": adapter.adapter_id,
                "page_delay_sec": page_delay,
            },
        )
        job_id = job.job_id

        # Define background async task
        async def run_acquisition(cancel_token: PipelineCancellationToken, progress_cb):
            concurrency = 1 if page_delay > 0 else 3
            pipeline = DownloadPipeline(concurrency=concurrency)
            ws_path = Path(record.workspace_path)
            
            results, manifest = await pipeline.execute(
                project_id=project_id,
                workspace_path=ws_path,
                adapter=adapter,
                candidates=candidates,
                source_meta={"type": record.source_type, "url": source_loc},
                rights_meta={"status": record.rights_status, "license_info": record.license_info},
                chapter_meta={"id": selected_chapter.id, "title": selected_chapter.title},
                progress_callback=progress_cb,
                cancel_token=cancel_token,
            )

            # Update DB Page records
            from engine.database.session import SessionLocal
            with SessionLocal() as inner_db:
                # Remove prior pages
                inner_db.query(PageRecord).filter(PageRecord.project_id == project_id).delete()
                
                ready_count = 0
                for mp in manifest.pages:
                    pr = PageRecord(
                        id=mp.id,
                        project_id=project_id,
                        sequence=mp.sequence,
                        filename=mp.filename,
                        source_url=mp.source_url,
                        content_type=mp.content_type or "image/jpeg",
                        width=mp.width,
                        height=mp.height,
                        byte_size=mp.bytes,
                        sha256=mp.sha256,
                        status=mp.status,
                        error_message=mp.error_message,
                        downloaded_at=utc_now(),
                    )
                    inner_db.add(pr)
                    if mp.status == "READY":
                        ready_count += 1

                # Update project stage ONLY if not cancelled
                if not cancel_token.is_cancelled:
                    proj = inner_db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                    if proj and ready_count > 0:
                        proj.current_stage = PipelineStage.ACQUIRED.value
                        proj.updated_at = utc_now()
                        self._write_project_json(proj)

                inner_db.commit()

            return {
                "total": len(candidates),
                "ready": len([r for r in results if r.success]),
                "failed": len([r for r in results if not r.success]),
            }

        job_manager.enqueue_async(job_id, run_acquisition)
        return job_id

    def retry_failed_pages(
        self,
        db: Session,
        project_id: str,
        adapter_registry: AdapterRegistry,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        failed_pages = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id, PageRecord.status == "FAILED")
            .order_by(PageRecord.sequence.asc())
            .all()
        )
        if not failed_pages:
            raise ValueError("No failed pages found to retry.")

        source_loc = record.source_url or record.source_metadata.get("path")
        adapter = adapter_registry.get_adapter_for(source_loc)

        candidates = [
            PageCandidate(
                sequence=p.sequence,
                source_uri=p.source_url or str(Path(record.workspace_path) / "source" / p.filename),
                suggested_filename=p.filename,
            )
            for p in failed_pages
        ]

        job = job_manager.create_job(
            project_id=project_id,
            job_type=JobType.RETRY_PAGES,
            job_input={"retry_count": len(candidates)},
        )
        job_id = job.job_id

        async def run_retry(cancel_token: PipelineCancellationToken, progress_cb):
            pipeline = DownloadPipeline()
            ws_path = Path(record.workspace_path)

            # Read existing manifest
            manifest_file = ws_path / "manifest.json"
            existing_manifest = None
            if manifest_file.exists():
                with open(manifest_file, "r", encoding="utf-8") as f:
                    existing_manifest = AcquisitionManifest.model_validate_json(f.read())

            results, manifest = await pipeline.execute(
                project_id=project_id,
                workspace_path=ws_path,
                adapter=adapter,
                candidates=candidates,
                source_meta={"type": record.source_type, "url": source_loc},
                rights_meta={"status": record.rights_status, "license_info": record.license_info},
                chapter_meta={},
                progress_callback=progress_cb,
                cancel_token=cancel_token,
                existing_manifest=existing_manifest,
            )

            # Update DB records for retried pages
            from engine.database.session import SessionLocal
            with SessionLocal() as inner_db:
                for r in results:
                    p_rec = (
                        inner_db.query(PageRecord)
                        .filter(PageRecord.project_id == project_id, PageRecord.sequence == r.sequence)
                        .first()
                    )
                    if p_rec:
                        if r.success:
                            p_rec.status = "READY"
                            p_rec.filename = r.filename
                            p_rec.content_type = r.content_type
                            p_rec.width = r.width
                            p_rec.height = r.height
                            p_rec.byte_size = r.byte_size
                            p_rec.sha256 = r.sha256
                            p_rec.error_message = None
                        else:
                            p_rec.status = "FAILED"
                            p_rec.error_message = r.error_message

                # Check if we now have ready pages and can advance stage
                if not cancel_token.is_cancelled:
                    ready_count = inner_db.query(PageRecord).filter(
                        PageRecord.project_id == project_id,
                        PageRecord.status == "READY"
                    ).count()
                    proj = inner_db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                    if proj and ready_count > 0 and proj.current_stage == PipelineStage.RIGHTS_APPROVED.value:
                        proj.current_stage = PipelineStage.ACQUIRED.value
                        proj.updated_at = utc_now()
                        self._write_project_json(proj)

                inner_db.commit()
                self.sync_manifest_with_db(inner_db, project_id)

            return {
                "retried": len(candidates),
                "recovered": len([r for r in results if r.success]),
                "remaining_failed": len([r for r in results if not r.success]),
            }

        job_manager.enqueue_async(job_id, run_retry)
        return job_id

    def reorder_pages(self, db: Session, project_id: str, ordered_page_ids: list[str]) -> list[PageRecord]:
        pages = db.query(PageRecord).filter(PageRecord.project_id == project_id).all()
        page_map = {p.id: p for p in pages}

        if set(ordered_page_ids) != set(page_map.keys()):
            raise ValueError("Provided page IDs do not match existing project pages.")

        for new_seq, pid in enumerate(ordered_page_ids, start=1):
            page_map[pid].sequence = new_seq

        db.commit()
        self.sync_manifest_with_db(db, project_id)
        
        return (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id)
            .order_by(PageRecord.sequence.asc())
            .all()
        )

    def delete_page(self, db: Session, project_id: str, page_id: str) -> None:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
        if not page:
            raise KeyError(f"Page not found: {page_id}")

        file_path = Path(record.workspace_path) / "source" / page.filename
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.warning(f"Error removing file {file_path}: {e}")

        db.delete(page)
        db.commit()

        # Resequence remaining pages 1..N
        remaining_pages = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id)
            .order_by(PageRecord.sequence.asc())
            .all()
        )
        for seq, p in enumerate(remaining_pages, start=1):
            p.sequence = seq
        db.commit()

        self.sync_manifest_with_db(db, project_id)

    def rotate_page(self, db: Session, project_id: str, page_id: str, degrees: int) -> PageRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
        if not page:
            raise KeyError(f"Page not found: {page_id}")

        file_path = Path(record.workspace_path) / "source" / page.filename
        if not file_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {file_path}")

        meta = rotate_image_file(file_path, degrees)
        page.width = meta["width"]
        page.height = meta["height"]
        page.sha256 = meta["sha256"]
        page.byte_size = meta["byte_size"]
        db.commit()

        self.sync_manifest_with_db(db, project_id)
        return page

    def confirm_acquisition(self, db: Session, project_id: str) -> ProjectRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        ready_count = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id, PageRecord.status == "READY")
            .count()
        )
        if ready_count == 0:
            raise ValueError("Cannot confirm acquisition with zero ready pages.")

        record.current_stage = PipelineStage.ACQUIRED.value
        record.updated_at = utc_now()
        db.commit()
        db.refresh(record)

        self._write_project_json(record)
        self.sync_manifest_with_db(db, project_id)
        return record

    def normalize_project(
        self,
        db: Session,
        project_id: str,
        target_width: int = 1920,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        pages = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id, PageRecord.status == "READY")
            .order_by(PageRecord.sequence.asc())
            .all()
        )
        if not pages:
            raise ValueError("No ready pages available to normalize.")

        job = job_manager.create_job(
            project_id=project_id,
            job_type=JobType.NORMALIZATION,
            job_input={"total_pages": len(pages), "target_width": target_width},
        )
        job_id = job.job_id

        async def run_normalization(cancel_token: PipelineCancellationToken, progress_cb):
            ws_path = Path(record.workspace_path)
            norm_dir = ws_path / "normalized"
            norm_dir.mkdir(parents=True, exist_ok=True)

            config = NormalizationConfig(target_width=target_width)
            total = len(pages)
            from engine.database.session import SessionLocal

            for idx, p in enumerate(pages, start=1):
                if cancel_token.is_cancelled:
                    break
                src_img = ws_path / "source" / p.filename
                out_img = norm_dir / f"page_{p.sequence:04d}.jpg"
                norm_res = page_normalizer.normalize_page(src_img, out_img, config)

                with SessionLocal() as inner_db:
                    inner_db.query(NormalizationRecord).filter(NormalizationRecord.page_id == p.id).delete()
                    norm_rec = NormalizationRecord(
                        id=str(uuid.uuid4()),
                        page_id=p.id,
                        project_id=project_id,
                        source_sha256=norm_res["source_sha256"],
                        normalized_sha256=norm_res["normalized_sha256"],
                        source_width=norm_res["source_width"],
                        source_height=norm_res["source_height"],
                        normalized_width=norm_res["width"],
                        normalized_height=norm_res["height"],
                        color_space=norm_res["color_space"],
                        orientation=norm_res["orientation"],
                        operations=norm_res["operations"],
                        status="SUCCESS",
                        created_at=utc_now(),
                    )
                    inner_db.add(norm_rec)
                    inner_db.commit()

                progress_cb(idx / total, f"Normalized page {idx}/{total}")

            with SessionLocal() as inner_db:
                proj = inner_db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if proj and not cancel_token.is_cancelled:
                    proj.current_stage = PipelineStage.NORMALIZED.value
                    proj.updated_at = utc_now()
                    self._write_project_json(proj)
                    inner_db.commit()

            return {"normalized_pages": total}

        job_manager.enqueue_async(job_id, run_normalization)
        return job_id

    def detect_panels_project(
        self,
        db: Session,
        project_id: str,
        reading_direction: str = "ltr",
        min_area_ratio: float = 0.02,
        profile: str = "AUTO",
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        pages = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id, PageRecord.status == "READY")
            .order_by(PageRecord.sequence.asc())
            .all()
        )
        if not pages:
            raise ValueError("No ready pages found for panel detection.")

        job = job_manager.create_job(
            project_id=project_id,
            job_type=JobType.PANEL_DETECTION,
            job_input={
                "total_pages": len(pages),
                "reading_direction": reading_direction,
                "min_area_ratio": min_area_ratio,
                "profile": profile,
            },
        )
        job_id = job.job_id

        async def run_detection(cancel_token: PipelineCancellationToken, progress_cb):
            ws_path = Path(record.workspace_path)
            norm_dir = ws_path / "normalized"
            panels_dir = ws_path / "panels"
            panels_dir.mkdir(parents=True, exist_ok=True)

            from engine.database.session import SessionLocal
            with SessionLocal() as inner_db:
                inner_db.query(PanelRecord).filter(PanelRecord.project_id == project_id).delete()
                inner_db.commit()

            total_pages = len(pages)
            overall_seq = 1

            for p_idx, page in enumerate(pages, start=1):
                if cancel_token.is_cancelled:
                    break

                img_path = norm_dir / f"page_{page.sequence:04d}.jpg"
                if not img_path.exists():
                    img_path = ws_path / "source" / page.filename

                detected_boxes = panel_detector.detect_panels(
                    img_path,
                    reading_direction=reading_direction,
                    page_id=page.id,
                    profile=profile,
                )

                with SessionLocal() as inner_db:
                    for p_box in detected_boxes:
                        crop_filename = f"panel_{overall_seq:04d}.jpg"
                        crop_path = panels_dir / crop_filename

                        panel_detector.extract_crop(img_path, p_box, crop_path)

                        pr = PanelRecord(
                            id=p_box.id,
                            project_id=project_id,
                            page_id=page.id,
                            sequence=overall_seq,
                            page_sequence=p_box.sequence,
                            x=p_box.x,
                            y=p_box.y,
                            width=p_box.width,
                            height=p_box.height,
                            normalized_x=p_box.normalized_x,
                            normalized_y=p_box.normalized_y,
                            normalized_width=p_box.normalized_width,
                            normalized_height=p_box.normalized_height,
                            crop_filename=crop_filename,
                            reading_direction=reading_direction,
                            detection_method=p_box.detection_method,
                            confidence=p_box.confidence,
                            panel_type=p_box.panel_type,
                            status=p_box.status,
                            manually_modified=False,
                            created_at=utc_now(),
                            updated_at=utc_now(),
                        )
                        inner_db.add(pr)
                        overall_seq += 1

                    inner_db.commit()

                progress_cb(p_idx / total_pages, f"Detected panels on page {p_idx}/{total_pages}")

            with SessionLocal() as inner_db:
                self._sync_panels_json(inner_db, project_id)

            return {"total_panels_detected": overall_seq - 1}

        job_manager.enqueue_async(job_id, run_detection)
        return job_id

    def detect_panels_page(
        self,
        db: Session,
        project_id: str,
        page_id: str,
        reading_direction: str = "ltr",
        min_area_ratio: float = 0.02,
        profile: str = "AUTO",
    ) -> list[PanelRecord]:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
        if not page:
            raise KeyError(f"Page not found: {page_id}")

        ws_path = Path(record.workspace_path)
        img_path = ws_path / "normalized" / f"page_{page.sequence:04d}.jpg"
        if not img_path.exists():
            img_path = ws_path / "source" / page.filename

        # Remove existing panels for this page
        existing_panels = db.query(PanelRecord).filter(PanelRecord.page_id == page_id).all()
        for ep in existing_panels:
            cf = ws_path / "panels" / ep.crop_filename
            if cf.exists():
                try:
                    cf.unlink()
                except Exception:
                    pass
            db.delete(ep)
        db.commit()

        detected_boxes = panel_detector.detect_panels(
            img_path,
            reading_direction=reading_direction,
            page_id=page.id,
            profile=profile,
        )

        panels_dir = ws_path / "panels"
        panels_dir.mkdir(parents=True, exist_ok=True)

        max_seq = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).count()

        for idx, p_box in enumerate(detected_boxes, start=1):
            crop_filename = f"panel_{page.sequence:04d}_{idx:03d}.jpg"
            crop_path = panels_dir / crop_filename
            panel_detector.extract_crop(img_path, p_box, crop_path)

            pr = PanelRecord(
                id=p_box.id,
                project_id=project_id,
                page_id=page.id,
                sequence=max_seq + idx,
                page_sequence=idx,
                x=p_box.x,
                y=p_box.y,
                width=p_box.width,
                height=p_box.height,
                normalized_x=p_box.normalized_x,
                normalized_y=p_box.normalized_y,
                normalized_width=p_box.normalized_width,
                normalized_height=p_box.normalized_height,
                crop_filename=crop_filename,
                reading_direction=reading_direction,
                detection_method=p_box.detection_method,
                confidence=p_box.confidence,
                panel_type=p_box.panel_type,
                status=p_box.status,
                manually_modified=False,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.add(pr)

        db.commit()
        self._resequence_project_panels(db, project_id)
        self._sync_panels_json(db, project_id)
        return db.query(PanelRecord).filter(PanelRecord.page_id == page_id).order_by(PanelRecord.page_sequence.asc()).all()

    def list_panels(self, db: Session, project_id: str, page_id: str | None = None) -> list[PanelRecord]:
        query = db.query(PanelRecord).filter(PanelRecord.project_id == project_id)
        if page_id:
            query = query.filter(PanelRecord.page_id == page_id)
        return query.order_by(PanelRecord.sequence.asc()).all()

    def add_panel(
        self,
        db: Session,
        project_id: str,
        page_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        panel_type: str = "STANDARD",
    ) -> PanelRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project_id).first()
        if not page:
            raise KeyError(f"Page not found: {page_id}")

        ws_path = Path(record.workspace_path)
        img_path = ws_path / "normalized" / f"page_{page.sequence:04d}.jpg"
        if not img_path.exists():
            img_path = ws_path / "source" / page.filename

        orig_w = page.width or 1200
        orig_h = page.height or 1800

        max_seq = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).count() + 1
        page_panels_count = db.query(PanelRecord).filter(PanelRecord.page_id == page_id).count() + 1

        panel_id = str(uuid.uuid4())
        crop_filename = f"panel_{max_seq:04d}.jpg"
        crop_path = ws_path / "panels" / crop_filename

        p_box = PanelBox(
            id=panel_id,
            page_id=page_id,
            sequence=page_panels_count,
            page_sequence=page_panels_count,
            x=x,
            y=y,
            width=width,
            height=height,
            confidence=1.0,
        )
        panel_detector.extract_crop(img_path, p_box, crop_path)

        panel = PanelRecord(
            id=panel_id,
            project_id=project_id,
            page_id=page_id,
            sequence=max_seq,
            page_sequence=page_panels_count,
            x=x,
            y=y,
            width=width,
            height=height,
            normalized_x=round(float(x) / float(orig_w), 4),
            normalized_y=round(float(y) / float(orig_h), 4),
            normalized_width=round(float(width) / float(orig_w), 4),
            normalized_height=round(float(height) / float(orig_h), 4),
            crop_filename=crop_filename,
            reading_direction="ltr",
            detection_method="MANUAL",
            confidence=1.0,
            panel_type=panel_type,
            status="MANUAL",
            manually_modified=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(panel)
        db.commit()
        db.refresh(panel)

        self._sync_panels_json(db, project_id)
        return panel

    def update_panel(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        status: str | None = None,
        panel_type: str | None = None,
    ) -> PanelRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        page = db.query(PageRecord).filter(PageRecord.id == panel.page_id).first()
        ws_path = Path(record.workspace_path)
        img_path = ws_path / "normalized" / f"page_{page.sequence:04d}.jpg"
        if not img_path.exists():
            img_path = ws_path / "source" / page.filename

        orig_w = page.width or 1200
        orig_h = page.height or 1800

        panel.x = x
        panel.y = y
        panel.width = width
        panel.height = height
        panel.normalized_x = round(float(x) / float(orig_w), 4)
        panel.normalized_y = round(float(y) / float(orig_h), 4)
        panel.normalized_width = round(float(width) / float(orig_w), 4)
        panel.normalized_height = round(float(height) / float(orig_h), 4)
        panel.manually_modified = True
        if status:
            panel.status = status
        if panel_type:
            panel.panel_type = panel_type
        panel.updated_at = utc_now()

        crop_path = ws_path / "panels" / panel.crop_filename
        p_box = PanelBox(
            id=panel.id,
            page_id=panel.page_id,
            sequence=panel.page_sequence,
            page_sequence=panel.page_sequence,
            x=x,
            y=y,
            width=width,
            height=height,
            confidence=panel.confidence,
        )
        panel_detector.extract_crop(img_path, p_box, crop_path)

        db.commit()
        db.refresh(panel)
        self._sync_panels_json(db, project_id)
        return panel

    def split_panel(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        split_type: str = "horizontal",
        ratio: float = 0.5,
    ) -> list[PanelRecord]:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        page = db.query(PageRecord).filter(PageRecord.id == panel.page_id).first()
        ws_path = Path(record.workspace_path)
        img_path = ws_path / "normalized" / f"page_{page.sequence:04d}.jpg"
        if not img_path.exists():
            img_path = ws_path / "source" / page.filename

        orig_w = page.width or 1200
        orig_h = page.height or 1800

        if split_type == "horizontal":
            split_h1 = max(20, int(panel.height * ratio))
            split_h2 = max(20, panel.height - split_h1)
            p1_box = (panel.x, panel.y, panel.width, split_h1)
            p2_box = (panel.x, panel.y + split_h1, panel.width, split_h2)
        else:
            split_w1 = max(20, int(panel.width * ratio))
            split_w2 = max(20, panel.width - split_w1)
            p1_box = (panel.x, panel.y, split_w1, panel.height)
            p2_box = (panel.x + split_w1, panel.y, split_w2, panel.height)

        panels_dir = ws_path / "panels"

        # Update first panel in-place
        panel.width = p1_box[2]
        panel.height = p1_box[3]
        panel.normalized_x = round(panel.x / float(orig_w), 4)
        panel.normalized_y = round(panel.y / float(orig_h), 4)
        panel.normalized_width = round(panel.width / float(orig_w), 4)
        panel.normalized_height = round(panel.height / float(orig_h), 4)
        panel.manually_modified = True
        panel.updated_at = utc_now()

        box1 = PanelBox(id=panel.id, page_id=panel.page_id, sequence=panel.page_sequence, x=panel.x, y=panel.y, width=panel.width, height=panel.height)
        panel_detector.extract_crop(img_path, box1, panels_dir / panel.crop_filename)

        # Create second panel
        p2_id = str(uuid.uuid4())
        crop2_name = f"panel_{p2_id[:8]}.jpg"
        box2 = PanelBox(id=p2_id, page_id=panel.page_id, sequence=panel.page_sequence + 1, x=p2_box[0], y=p2_box[1], width=p2_box[2], height=p2_box[3])
        panel_detector.extract_crop(img_path, box2, panels_dir / crop2_name)

        p2_rec = PanelRecord(
            id=p2_id,
            project_id=project_id,
            page_id=panel.page_id,
            sequence=panel.sequence + 1,
            page_sequence=panel.page_sequence + 1,
            x=p2_box[0],
            y=p2_box[1],
            width=p2_box[2],
            height=p2_box[3],
            normalized_x=round(p2_box[0] / float(orig_w), 4),
            normalized_y=round(p2_box[1] / float(orig_h), 4),
            normalized_width=round(p2_box[2] / float(orig_w), 4),
            normalized_height=round(p2_box[3] / float(orig_h), 4),
            crop_filename=crop2_name,
            reading_direction=panel.reading_direction,
            detection_method="MANUAL",
            confidence=1.0,
            panel_type=panel.panel_type,
            status="MANUAL",
            manually_modified=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(p2_rec)
        db.commit()

        self._resequence_project_panels(db, project_id)
        self._sync_panels_json(db, project_id)
        return db.query(PanelRecord).filter(PanelRecord.page_id == panel.page_id).order_by(PanelRecord.page_sequence.asc()).all()

    def merge_panels(
        self,
        db: Session,
        project_id: str,
        panel_ids: list[str],
    ) -> PanelRecord:
        if len(panel_ids) < 2:
            raise ValueError("Merging requires at least 2 panel IDs.")

        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panels = db.query(PanelRecord).filter(PanelRecord.id.in_(panel_ids), PanelRecord.project_id == project_id).all()
        if len(panels) != len(panel_ids):
            raise KeyError("One or more panel IDs were not found.")

        page_ids = {p.page_id for p in panels}
        if len(page_ids) > 1:
            raise ValueError("Panels to merge must belong to the same page.")

        page = db.query(PageRecord).filter(PageRecord.id == panels[0].page_id).first()
        ws_path = Path(record.workspace_path)
        img_path = ws_path / "normalized" / f"page_{page.sequence:04d}.jpg"
        if not img_path.exists():
            img_path = ws_path / "source" / page.filename

        orig_w = page.width or 1200
        orig_h = page.height or 1800

        sorted_panels = sorted(panels, key=lambda p: p.sequence)
        primary = sorted_panels[0]
        others = sorted_panels[1:]

        min_x = min(p.x for p in panels)
        min_y = min(p.y for p in panels)
        max_x = max(p.x + p.width for p in panels)
        max_y = max(p.y + p.height for p in panels)

        new_w = max_x - min_x
        new_h = max_y - min_y

        primary.x = min_x
        primary.y = min_y
        primary.width = new_w
        primary.height = new_h
        primary.normalized_x = round(min_x / float(orig_w), 4)
        primary.normalized_y = round(min_y / float(orig_h), 4)
        primary.normalized_width = round(new_w / float(orig_w), 4)
        primary.normalized_height = round(new_h / float(orig_h), 4)
        primary.status = "MANUAL"
        primary.detection_method = "MANUAL"
        primary.manually_modified = True
        primary.confidence = 1.0
        primary.updated_at = utc_now()

        p_box = PanelBox(id=primary.id, page_id=primary.page_id, sequence=primary.page_sequence, x=min_x, y=min_y, width=new_w, height=new_h)
        panel_detector.extract_crop(img_path, p_box, ws_path / "panels" / primary.crop_filename)

        for op in others:
            crop_f = ws_path / "panels" / op.crop_filename
            if crop_f.exists():
                try:
                    crop_f.unlink()
                except Exception:
                    pass
            db.delete(op)

        db.commit()
        self._resequence_project_panels(db, project_id)
        self._sync_panels_json(db, project_id)
        db.refresh(primary)
        return primary

    def _resequence_project_panels(self, db: Session, project_id: str):
        pages = db.query(PageRecord).filter(PageRecord.project_id == project_id).order_by(PageRecord.sequence.asc()).all()
        global_seq = 1
        for page in pages:
            page_panels = (
                db.query(PanelRecord)
                .filter(PanelRecord.page_id == page.id)
                .order_by(PanelRecord.sequence.asc())
                .all()
            )
            for page_seq, p in enumerate(page_panels, start=1):
                p.page_sequence = page_seq
                p.sequence = global_seq
                global_seq += 1
        db.commit()

    def delete_panel(self, db: Session, project_id: str, panel_id: str) -> None:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        crop_file = Path(record.workspace_path) / "panels" / panel.crop_filename
        if crop_file.exists():
            try:
                crop_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete crop {crop_file}: {e}")

        # Delete associated text regions and OCR records for this panel
        db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel_id).delete()
        db.query(OCRRecord).filter(OCRRecord.panel_id == panel_id).delete()

        db.delete(panel)
        db.commit()

        self._resequence_project_panels(db, project_id)
        self._sync_panels_json(db, project_id)

    def reorder_panels(self, db: Session, project_id: str, ordered_panel_ids: list[str]) -> list[PanelRecord]:
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).all()
        panel_map = {p.id: p for p in panels}

        if set(ordered_panel_ids) != set(panel_map.keys()):
            raise ValueError("Provided panel IDs do not match existing project panels.")

        for new_seq, pid in enumerate(ordered_panel_ids, start=1):
            panel_map[pid].sequence = new_seq
            panel_map[pid].updated_at = utc_now()

        db.commit()
        self._sync_panels_json(db, project_id)

        return (
            db.query(PanelRecord)
            .filter(PanelRecord.project_id == project_id)
            .order_by(PanelRecord.sequence.asc())
            .all()
        )

    def confirm_panels(self, db: Session, project_id: str) -> ProjectRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panels_count = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).count()
        if panels_count == 0:
            raise ValueError("Cannot confirm panel review with zero panels.")

        record.current_stage = PipelineStage.PANELS_DETECTED.value
        record.updated_at = utc_now()
        db.commit()
        db.refresh(record)

        self._write_project_json(record)
        self._sync_panels_json(db, project_id)
        return record

    def _sync_panels_json(self, db: Session, project_id: str) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            return {}

        panels = (
            db.query(PanelRecord)
            .filter(PanelRecord.project_id == project_id)
            .order_by(PanelRecord.sequence.asc())
            .all()
        )

        panels_dir = Path(record.workspace_path) / "panels"
        panels_dir.mkdir(parents=True, exist_ok=True)
        panels_json_file = panels_dir / "panels.json"

        data = {
            "project_id": project_id,
            "version": "1.0",
            "total_panels": len(panels),
            "updated_at": utc_now().isoformat(),
            "panels": [
                {
                    "id": p.id,
                    "sequence": p.sequence,
                    "sequence_global": p.sequence,
                    "sequence_page": p.page_sequence,
                    "page_id": p.page_id,
                    "x": p.x,
                    "y": p.y,
                    "width": p.width,
                    "height": p.height,
                    "normalized": {
                        "x": p.normalized_x,
                        "y": p.normalized_y,
                        "width": p.normalized_width,
                        "height": p.normalized_height,
                    },
                    "crop_reference": f"panels/{p.crop_filename}",
                    "reading_direction": p.reading_direction,
                    "confidence": p.confidence,
                    "panel_type": p.panel_type,
                    "status": p.status,
                    "detection_method": p.detection_method,
                    "manually_modified": p.manually_modified,
                }
                for p in panels
            ],
        }

        temp_file = panels_dir / "panels.json.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(panels_json_file)

        return data

    def extract_ocr_project(
        self,
        db: Session,
        project_id: str,
        engine_id: str = "mock_ocr",
        language: str = "en",
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panels = (
            db.query(PanelRecord)
            .filter(PanelRecord.project_id == project_id)
            .order_by(PanelRecord.sequence)
            .all()
        )
        if not panels:
            raise ValueError(
                f"Project {project_id} has no panels detected. Run panel detection first."
            )

        from engine.ocr.providers.registry import get_default_ocr_registry
        ocr_registry = get_default_ocr_registry()
        try:
            ocr_engine = ocr_registry.get_engine(engine_id)
        except KeyError:
            ocr_engine = ocr_registry.get_default_engine()

        job = job_manager.create_job(
            project_id=project_id,
            job_type=JobType.OCR_EXTRACTION,
            job_input={
                "total_panels": len(panels),
                "engine_id": ocr_engine.engine_id,
                "language": language,
            },
        )
        job_id = job.job_id

        async def run_ocr(cancel_token: PipelineCancellationToken, progress_cb):
            from engine.database.session import SessionLocal
            with SessionLocal() as worker_db:
                ws_path = Path(record.workspace_path)
                panels_dir = ws_path / "panels"
                total_panels = len(panels)

                for idx, panel in enumerate(panels, start=1):
                    if cancel_token.is_cancelled:
                        break

                    crop_path = panels_dir / panel.crop_filename
                    if not crop_path.exists():
                        norm_path = ws_path / "normalized" / panel.page.filename
                        src_path = (
                            norm_path
                            if norm_path.exists()
                            else ws_path / "source" / panel.page.filename
                        )
                        if src_path.exists():
                            from PIL import Image
                            with Image.open(src_path) as full_img:
                                box = (
                                    panel.x,
                                    panel.y,
                                    panel.x + panel.width,
                                    panel.y + panel.height,
                                )
                                crop = full_img.crop(box)
                                crop.save(crop_path, "JPEG", quality=95)

                    raw_result = ocr_engine.extract_text(
                        crop_path, panel.id, language=language
                    )

                    ocr_rec = (
                        worker_db.query(OCRRecord)
                        .filter(
                            OCRRecord.panel_id == panel.id,
                            OCRRecord.project_id == project_id,
                        )
                        .first()
                    )

                    raw_blocks_data = [r.model_dump() for r in raw_result.regions]
                    existing_adapted = ocr_rec.adapted_blocks if ocr_rec else []
                    if not existing_adapted:
                        adapted_blocks_data = [
                            {
                                "id": r.id,
                                "raw_region_id": r.id,
                                "speaker": None,
                                "text": r.detected_text,
                                "classification": "dialogue",
                                "notes": "",
                            }
                            for r in raw_result.regions
                        ]
                    else:
                        adapted_blocks_data = existing_adapted

                    if not ocr_rec:
                        ocr_rec = OCRRecord(
                            id=str(uuid.uuid4()),
                            project_id=project_id,
                            panel_id=panel.id,
                            engine_name=ocr_engine.engine_id,
                            engine_version=raw_result.engine_version,
                            raw_blocks=raw_blocks_data,
                            adapted_blocks=adapted_blocks_data,
                            full_text=raw_result.full_text,
                            confidence_avg=raw_result.confidence_avg,
                            status="DETECTED",
                            created_at=utc_now(),
                            updated_at=utc_now(),
                        )
                        worker_db.add(ocr_rec)
                    else:
                        ocr_rec.engine_name = ocr_engine.engine_id
                        ocr_rec.engine_version = raw_result.engine_version
                        ocr_rec.raw_blocks = raw_blocks_data
                        ocr_rec.full_text = raw_result.full_text
                        ocr_rec.confidence_avg = raw_result.confidence_avg
                        ocr_rec.updated_at = utc_now()

                    worker_db.commit()

                    # The review UI and canonical story export consume text regions,
                    # not the legacy panel-level OCR record above.
                    region_ids = [row.id for row in worker_db.query(TextRegionRecord).filter(
                        TextRegionRecord.project_id == project_id,
                        TextRegionRecord.panel_id == panel.id,
                    ).all()]
                    for region_id in region_ids:
                        if cancel_token.is_cancelled:
                            break
                        self.extract_ocr_region(
                            worker_db, project_id, region_id, ocr_engine.engine_id, language,
                        )

                    progress = idx / total_panels
                    progress_cb(
                        progress,
                        f"OCR extracted panel #{panel.sequence} ({idx}/{total_panels})",
                    )

                if not cancel_token.is_cancelled:
                    p_rec = (
                        worker_db.query(ProjectRecord)
                        .filter(ProjectRecord.id == project_id)
                        .first()
                    )
                    if p_rec:
                        p_rec.current_stage = PipelineStage.OCR_COMPLETE.value
                        p_rec.updated_at = utc_now()
                        worker_db.commit()
                        self._write_project_json(p_rec)

                self._sync_ocr_json(worker_db, project_id)

            return {
                "total_panels": len(panels),
                "engine": ocr_engine.engine_id,
            }

        job_manager.enqueue_async(job_id, run_ocr)
        return job_id

    def get_panel_ocr(
        self, db: Session, project_id: str, panel_id: str
    ) -> OCRRecord | None:
        return (
            db.query(OCRRecord)
            .filter(
                OCRRecord.project_id == project_id,
                OCRRecord.panel_id == panel_id,
            )
            .first()
        )

    def list_project_ocr(self, db: Session, project_id: str) -> list[OCRRecord]:
        return (
            db.query(OCRRecord)
            .filter(OCRRecord.project_id == project_id)
            .all()
        )

    def update_adapted_block(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        block_id: str,
        speaker: str | None,
        text: str,
        classification: str,
        notes: str,
    ) -> OCRRecord:
        record = self.get_panel_ocr(db, project_id, panel_id)
        if not record:
            raise KeyError(f"OCR record not found for panel {panel_id}")

        adapted = list(record.adapted_blocks or [])
        found = False
        for item in adapted:
            if item.get("id") == block_id or item.get("raw_region_id") == block_id:
                item["speaker"] = speaker
                item["text"] = text
                item["classification"] = classification
                item["notes"] = notes
                found = True
                break

        if not found:
            # Add new adapted block linked to block_id
            adapted.append({
                "id": block_id,
                "raw_region_id": block_id,
                "speaker": speaker,
                "text": text,
                "classification": classification,
                "notes": notes,
            })

        record.adapted_blocks = [dict(item) for item in adapted]
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(record, "adapted_blocks")
        record.status = "EDITED"
        record.updated_at = utc_now()
        db.commit()
        db.refresh(record)

        self._sync_ocr_json(db, project_id)
        return record

    def confirm_ocr(self, db: Session, project_id: str) -> ProjectRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        # Strict Gate 1: Check panels confirmed
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).all()
        if not panels:
            raise ValueError("Cannot approve OCR: No panels detected or confirmed in project.")

        # Strict Gate 2: Check for unresolved NEEDS_REVIEW text regions
        unresolved_regions = (
            db.query(TextRegionRecord)
            .filter(
                TextRegionRecord.project_id == project_id,
                TextRegionRecord.status == "NEEDS_REVIEW",
            )
            .all()
        )
        if unresolved_regions:
            raise ValueError(
                f"Cannot approve OCR: {len(unresolved_regions)} text regions have 'NEEDS_REVIEW' status. "
                f"Please review or confirm low-confidence regions before approval."
            )

        record.current_stage = PipelineStage.OCR_APPROVED.value
        record.updated_at = utc_now()
        db.commit()
        db.refresh(record)

        self._write_project_json(record)
        self._sync_ocr_json(db, project_id)
        return record

    def detect_text_regions_project(
        self,
        db: Session,
        project_id: str,
        page_id: str | None = None,
    ) -> list[TextRegionRecord]:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        from engine.imaging.text_regions import ClassicalTextRegionDetector
        detector = ClassicalTextRegionDetector()

        query = db.query(PanelRecord).filter(PanelRecord.project_id == project_id)
        if page_id:
            query = query.filter(PanelRecord.page_id == page_id)
        panels = query.order_by(PanelRecord.sequence).all()

        ws_path = Path(record.workspace_path)
        panels_dir = ws_path / "panels"
        regions_dir = ws_path / "text_regions"
        regions_dir.mkdir(parents=True, exist_ok=True)

        created_records: list[TextRegionRecord] = []
        global_seq = 1

        for panel in panels:
            crop_path = panels_dir / panel.crop_filename
            if not crop_path.exists():
                continue

            page_rec = db.query(PageRecord).filter(PageRecord.id == panel.page_id).first()
            page_w = page_rec.width if page_rec else 1200
            page_h = page_rec.height if page_rec else 1800

            detected_boxes = detector.detect(
                panel_image=crop_path,
                panel_id=panel.id,
                page_id=panel.page_id,
                project_id=project_id,
                panel_x=panel.x,
                panel_y=panel.y,
                page_w=page_w,
                page_h=page_h,
                reading_direction=panel.reading_direction,
            )

            # Delete old auto-detected regions for this panel (preserve MANUAL)
            db.query(TextRegionRecord).filter(
                TextRegionRecord.panel_id == panel.id,
                TextRegionRecord.detection_method != "MANUAL",
            ).delete()

            from PIL import Image
            import hashlib
            with Image.open(crop_path) as p_img:
                for box in detected_boxes:
                    rx1 = max(0, min(box.x, p_img.width - 1))
                    ry1 = max(0, min(box.y, p_img.height - 1))
                    rx2 = max(rx1 + 1, min(box.x + box.width, p_img.width))
                    ry2 = max(ry1 + 1, min(box.y + box.height, p_img.height))

                    region_crop = p_img.crop((rx1, ry1, rx2, ry2))
                    crop_filename = f"reg_{panel.id[:8]}_{box.sequence_in_panel}_{uuid.uuid4().hex[:6]}.jpg"
                    reg_crop_path = regions_dir / crop_filename
                    region_crop.save(reg_crop_path, "JPEG", quality=95)

                    crop_bytes = reg_crop_path.read_bytes()
                    crop_sha = hashlib.sha256(crop_bytes).hexdigest()

                    tr_rec = TextRegionRecord(
                        id=box.id,
                        project_id=project_id,
                        page_id=panel.page_id,
                        panel_id=panel.id,
                        sequence_in_panel=box.sequence_in_panel,
                        sequence_global=global_seq,
                        x=box.x,
                        y=box.y,
                        width=box.width,
                        height=box.height,
                        normalized_x=box.normalized_x,
                        normalized_y=box.normalized_y,
                        normalized_width=box.normalized_width,
                        normalized_height=box.normalized_height,
                        page_x=box.page_x,
                        page_y=box.page_y,
                        page_width=box.page_width,
                        page_height=box.page_height,
                        region_type=box.region_type,
                        confidence=box.confidence,
                        status=box.status,
                        detection_method=box.detection_method,
                        crop_filename=crop_filename,
                        crop_sha256=crop_sha,
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                    db.add(tr_rec)
                    created_records.append(tr_rec)
                    global_seq += 1

        db.commit()
        return created_records

    def list_text_regions(
        self,
        db: Session,
        project_id: str,
        page_id: str | None = None,
        panel_id: str | None = None,
    ) -> list[TextRegionRecord]:
        query = db.query(TextRegionRecord).filter(TextRegionRecord.project_id == project_id)
        if page_id:
            query = query.filter(TextRegionRecord.page_id == page_id)
        if panel_id:
            query = query.filter(TextRegionRecord.panel_id == panel_id)
        return query.order_by(TextRegionRecord.sequence_global).all()

    def get_text_region(self, db: Session, project_id: str, region_id: str) -> TextRegionRecord | None:
        return (
            db.query(TextRegionRecord)
            .filter(
                TextRegionRecord.project_id == project_id,
                TextRegionRecord.id == region_id,
            )
            .first()
        )

    def create_manual_text_region(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        region_type: str = "SPEECH",
    ) -> TextRegionRecord:
        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        existing = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel_id).all()
        seq_in_panel = len(existing) + 1
        total_project_regions = db.query(TextRegionRecord).filter(TextRegionRecord.project_id == project_id).count()

        tr = TextRegionRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            page_id=panel.page_id,
            panel_id=panel_id,
            sequence_in_panel=seq_in_panel,
            sequence_global=total_project_regions + 1,
            x=x,
            y=y,
            width=width,
            height=height,
            normalized_x=round(float(x) / float(panel.width), 4) if panel.width > 0 else 0.0,
            normalized_y=round(float(y) / float(panel.height), 4) if panel.height > 0 else 0.0,
            normalized_width=round(float(width) / float(panel.width), 4) if panel.width > 0 else 0.0,
            normalized_height=round(float(height) / float(panel.height), 4) if panel.height > 0 else 0.0,
            page_x=panel.x + x,
            page_y=panel.y + y,
            page_width=width,
            page_height=height,
            region_type=region_type,
            confidence=1.0,
            status="CONFIRMED",
            detection_method="MANUAL",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(tr)
        db.commit()
        db.refresh(tr)
        return tr

    def update_text_region(
        self,
        db: Session,
        project_id: str,
        region_id: str,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        region_type: str | None = None,
        status: str | None = None,
        corrected_text: str | None = None,
        corrected_by: str | None = None,
        correction_status: str | None = None,
        speaker_character_id: str | None = None,
        speaker_confidence: float | None = None,
        speaker_assignment_method: str | None = None,
    ) -> TextRegionRecord:
        tr = self.get_text_region(db, project_id, region_id)
        if not tr:
            raise KeyError(f"TextRegion not found: {region_id}")

        if x is not None:
            tr.x = x
        if y is not None:
            tr.y = y
        if width is not None:
            tr.width = width
        if height is not None:
            tr.height = height
        if region_type is not None:
            tr.region_type = region_type
        if status is not None:
            tr.status = status

        # Layer 2: Human correction
        if corrected_text is not None:
            tr.corrected_text = corrected_text
            tr.correction_status = correction_status or "EDITED"
            tr.corrected_by = corrected_by or "USER"
            tr.corrected_at = utc_now()
            from engine.story.dependency import dependency_graph, PipelineEntityTier
            dependency_graph.invalidate(project_id, PipelineEntityTier.OCR)

        # Layer 3: Speaker Attribution Preparation (Milestone 4 ready)
        if speaker_character_id is not None:
            tr.speaker_character_id = speaker_character_id
            from engine.story.dependency import dependency_graph, PipelineEntityTier
            dependency_graph.invalidate(project_id, PipelineEntityTier.SPEAKER)
        if speaker_confidence is not None:
            tr.speaker_confidence = speaker_confidence
        if speaker_assignment_method is not None:
            tr.speaker_assignment_method = speaker_assignment_method

        tr.updated_at = utc_now()
        db.commit()
        db.refresh(tr)
        return tr

    def delete_text_region(self, db: Session, project_id: str, region_id: str) -> None:
        tr = self.get_text_region(db, project_id, region_id)
        if not tr:
            raise KeyError(f"TextRegion not found: {region_id}")
        db.delete(tr)
        db.commit()

    def extract_ocr_region(
        self,
        db: Session,
        project_id: str,
        region_id: str,
        engine_id: str = "mock_ocr",
        language: str = "en",
    ) -> TextRegionRecord:
        tr = self.get_text_region(db, project_id, region_id)
        if not tr:
            raise KeyError(f"TextRegion not found: {region_id}")

        proj = self.get_project(db, project_id)
        ws_path = Path(proj.workspace_path)
        crop_path = ws_path / "text_regions" / tr.crop_filename

        if not crop_path.exists():
            # Extract crop on demand from panel crop
            panel = db.query(PanelRecord).filter(PanelRecord.id == tr.panel_id).first()
            p_crop = ws_path / "panels" / panel.crop_filename if panel else None
            if p_crop and p_crop.exists():
                from PIL import Image
                import hashlib
                with Image.open(p_crop) as p_img:
                    rx1 = max(0, min(tr.x, p_img.width - 1))
                    ry1 = max(0, min(tr.y, p_img.height - 1))
                    rx2 = max(rx1 + 1, min(tr.x + tr.width, p_img.width))
                    ry2 = max(ry1 + 1, min(tr.y + tr.height, p_img.height))
                    reg_img = p_img.crop((rx1, ry1, rx2, ry2))
                    crop_path.parent.mkdir(parents=True, exist_ok=True)
                    reg_img.save(crop_path, "JPEG", quality=95)
                    tr.crop_sha256 = hashlib.sha256(crop_path.read_bytes()).hexdigest()

        from engine.ocr.cache import compute_ocr_cache_key, get_cached_ocr, store_cached_ocr
        from engine.ocr.providers.registry import ocr_registry

        cache_key, settings_hash = compute_ocr_cache_key(
            crop_sha256=tr.crop_sha256,
            engine_id=engine_id,
            engine_version="1.0",
            language=language,
        )

        cached = get_cached_ocr(db, cache_key)
        if cached:
            raw_text = cached.raw_text
            raw_conf = cached.raw_confidence
            engine_ver = cached.engine_version
        else:
            engine = ocr_registry.get_engine(engine_id)
            res = engine.extract_text(crop_path, panel_id=tr.panel_id, language=language)
            raw_text = res.full_text
            raw_conf = res.confidence_avg
            engine_ver = res.engine_version
            store_cached_ocr(
                db=db,
                crop_sha256=tr.crop_sha256,
                engine_id=engine_id,
                engine_version=engine_ver,
                language=language,
                settings=None,
                raw_text=raw_text,
                raw_confidence=raw_conf,
                raw_blocks=[r.model_dump() for r in res.regions],
            )

        # Layer 1: Machine OCR (strictly immutable provenance)
        if not raw_text.strip():
            raw_conf = 0.0
        tr.raw_text = raw_text
        tr.raw_confidence = raw_conf
        tr.ocr_engine = engine_id
        tr.ocr_engine_version = engine_ver
        tr.ocr_extracted_at = utc_now()

        # If human text was never edited, initialize with raw text
        if tr.correction_status == "UNEDITED" or not tr.corrected_text:
            tr.corrected_text = raw_text

        if not (tr.correction_status == "VERIFIED" and tr.corrected_text.strip()):
            if not raw_text.strip() or raw_conf < 0.70:
                tr.status = "NEEDS_REVIEW"

        tr.updated_at = utc_now()
        db.commit()
        db.refresh(tr)
        return tr

    def get_canonical_export(self, db: Session, project_id: str) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        pages = db.query(PageRecord).filter(PageRecord.project_id == project_id).order_by(PageRecord.sequence).all()
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).order_by(PanelRecord.sequence).all()
        text_regions = db.query(TextRegionRecord).filter(
            TextRegionRecord.project_id == project_id,
            TextRegionRecord.status != "REJECTED",
        ).order_by(TextRegionRecord.sequence_global).all()

        return {
            "project_id": record.id,
            "title": record.title,
            "current_stage": record.current_stage,
            "rights": {
                "status": record.rights_status,
                "license_info": record.license_info,
            },
            "exported_at": utc_now().isoformat(),
            "pages": [
                {
                    "id": p.id,
                    "sequence": p.sequence,
                    "filename": p.filename,
                    "width": p.width,
                    "height": p.height,
                    "sha256": p.sha256,
                }
                for p in pages
            ],
            "panels": [
                {
                    "id": p.id,
                    "page_id": p.page_id,
                    "sequence_global": p.sequence,
                    "sequence_page": p.page_sequence,
                    "bbox": [p.x, p.y, p.width, p.height],
                    "normalized_bbox": [p.normalized_x, p.normalized_y, p.normalized_width, p.normalized_height],
                    "reading_direction": p.reading_direction,
                    "panel_type": p.panel_type,
                    "status": p.status,
                }
                for p in panels
            ],
            "text_regions": [
                {
                    "id": tr.id,
                    "page_id": tr.page_id,
                    "panel_id": tr.panel_id,
                    "sequence_in_panel": tr.sequence_in_panel,
                    "sequence_global": tr.sequence_global,
                    "bbox": [tr.x, tr.y, tr.width, tr.height],
                    "normalized_bbox": [tr.normalized_x, tr.normalized_y, tr.normalized_width, tr.normalized_height],
                    "page_bbox": [tr.page_x, tr.page_y, tr.page_width, tr.page_height],
                    "region_type": tr.region_type,
                    "status": tr.status,
                    "detection_method": tr.detection_method,
                    # Layer 1: Machine OCR (Immutable)
                    "raw_ocr": {
                        "text": tr.raw_text,
                        "confidence": tr.raw_confidence,
                        "polygon": tr.raw_polygon,
                        "engine": tr.ocr_engine,
                        "engine_version": tr.ocr_engine_version,
                        "extracted_at": tr.ocr_extracted_at.isoformat() if tr.ocr_extracted_at else None,
                    },
                    # Layer 2: Corrected Text (Human Revision)
                    "corrected_text": {
                        "text": tr.corrected_text,
                        "corrected_by": tr.corrected_by,
                        "status": tr.correction_status,
                        "corrected_at": tr.corrected_at.isoformat() if tr.corrected_at else None,
                    },
                    # Layer 3: Speaker Preparation (Milestone 4 ready)
                    "speaker": {
                        "character_id": tr.speaker_character_id,
                        "confidence": tr.speaker_confidence,
                        "assignment_method": tr.speaker_assignment_method,
                    },
                }
                for tr in text_regions
            ],
        }

    def _sync_ocr_json(self, db: Session, project_id: str) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        ocr_records = self.list_project_ocr(db, project_id)
        ws_path = Path(record.workspace_path)
        ocr_dir = ws_path / "ocr"
        ocr_dir.mkdir(parents=True, exist_ok=True)
        ocr_json_file = ocr_dir / "ocr.json"

        data = {
            "project_id": project_id,
            "version": "1.0",
            "total_records": len(ocr_records),
            "updated_at": utc_now().isoformat(),
            "panels": [
                {
                    "panel_id": r.panel_id,
                    "engine_name": r.engine_name,
                    "engine_version": r.engine_version,
                    "confidence_avg": r.confidence_avg,
                    "status": r.status,
                    "raw_blocks": r.raw_blocks,
                    "adapted_blocks": r.adapted_blocks,
                    "full_text": r.full_text,
                }
                for r in ocr_records
            ],
        }

        temp_file = ocr_dir / "ocr.json.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(ocr_json_file)

        return data


project_service = ProjectService()

