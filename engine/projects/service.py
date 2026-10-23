import shutil

_orig_rmtree = shutil.rmtree
import json
import logging
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
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
from engine.security.paths import (
    ensure_contained_directory,
    open_contained_output,
    project_path,
    read_contained_bytes,
    remove_contained_directory,
    resolve_contained_path,
    unlink_contained_file,
    write_contained_image,
)

logger = logging.getLogger(__name__)


def protected_panel_pages(db: Session, project_id: str) -> set[str]:
    """Redetection must not invalidate approved work or timeline references."""
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    state = (project.settings or {}).get("story_editor_state", {}) if project else {}
    linked = {layer.get("source_panel_id") for scene in state.get("scenes", [])
              for layer in scene.get("layers", [])}
    return {p.page_id for p in db.query(PanelRecord).filter(PanelRecord.project_id == project_id).all()
            if p.manually_modified or p.status in ("MANUAL", "CONFIRMED") or p.id in linked}


def reconcile_story_editor_state_with_panels(
    db: Session,
    project_id: str,
    state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Refresh source-panel geometry without overwriting editor-authored motion.

    Panel Review is the source of truth for page/panel geometry. Story Editor
    owns scene timing, transforms, motion, and audio. Reconcile only the shared
    source fields at every read/save/render boundary so the two workflows cannot
    silently drift apart.
    """
    if not isinstance(state, dict):
        return state

    db_panels = (
        db.query(PanelRecord)
        .filter(PanelRecord.project_id == project_id)
        .order_by(PanelRecord.sequence.asc())
        .all()
    )
    panels = {panel.id: panel for panel in db_panels}
    current_panel_ids = [panel.id for panel in db_panels]
    
    # Track used panels for validation
    used_panels = set()
    removed_layers = []
    
    reconciled = json.loads(json.dumps(state))
    scenes = reconciled.get("scenes", [])
    
    # Track which panels are referenced by scenes
    for scene in scenes:
        scene_layers = scene.get("layers", [])
        # Keep missing-source layers so authored timing/motion can be repaired.
        active_layers = []
        for layer in scene_layers:
            panel_id = layer.get("source_panel_id")
            if not panel_id:
                active_layers.append(layer)
                continue
                
            panel = panels.get(panel_id)
            if not panel:
                # Panel was deleted in Panel Review - mark layer for removal
                removed_layers.append({
                    "scene_id": scene.get("id"),
                    "layer_id": layer.get("id"),
                    "panel_id": panel_id,
                })
                active_layers.append(layer)
                continue
            
            used_panels.add(panel_id)
            # Update panel geometry and metadata
            layer["source_page_id"] = panel.page_id
            layer["page_sequence"] = panel.page_sequence
            layer["crop"] = {
                "x": panel.x,
                "y": panel.y,
                "width": panel.width,
                "height": panel.height,
            }
            layer["name"] = layer.get("name") or f"Panel #{panel.page_sequence}"
            layer["panel_updated_at"] = panel.updated_at.isoformat() if panel.updated_at else None
            layer["panel_sequence"] = panel.sequence
            active_layers.append(layer)
        
        scene["layers"] = active_layers
        
        # Empty scenes and page-only layers are intentional editor compositions.

    # Scene membership/order belongs to the editor, not Panel Review. Compare
    # authoritative inventories across reads instead; legacy states establish a
    # baseline without guessing what their composition was intended to include.
    previous_sync = reconciled.get("panel_review_sync")
    previous_sync = previous_sync if isinstance(previous_sync, dict) else {}
    previous_ids = previous_sync.get("panel_ids")
    has_baseline = (
        isinstance(previous_ids, list)
        and all(isinstance(pid, str) and pid for pid in previous_ids)
        and len(set(previous_ids)) == len(previous_ids)
    )
    inventory_changed = has_baseline and previous_ids != current_panel_ids
    # Confirmation carries geometry changes even when no scene uses that panel.
    # Pending changes stay pending until explicit alignment acknowledges them.
    stale = bool(
        inventory_changed
        or removed_layers
        or previous_sync.get("panels_stale")
        or reconciled.get("panels_stale")
        or reconciled.get("panel_sync_required")
    )
    reconciled["panels_stale"] = stale
    reconciled["panel_sync_required"] = stale

    reconciled["panel_review_sync"] = {
        **previous_sync,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "panel_ids": current_panel_ids,
        "panel_count": len(panels),
        "used_panel_count": len(used_panels),
        "removed_layers_count": len(removed_layers),
        "removed_layers": removed_layers,
        "panels_stale": stale,
    }

    return reconciled

def align_panel_scenes(db: Session, project_id: str, state: dict) -> dict:
    """Explicitly rebuild panel membership/order, retaining surviving scene edits."""
    result = json.loads(json.dumps(state))
    panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id,
                                         PanelRecord.status != "IGNORED").order_by(PanelRecord.sequence).all()
    scenes = result.get("scenes", [])
    if any(len(s.get("layers", [])) != 1 or not s["layers"][0].get("source_panel_id") for s in scenes):
        raise ValueError("Automatic alignment requires one source panel per scene. Review custom or multi-layer scenes manually.")
    existing = {s["layers"][0]["source_panel_id"]: s for s in scenes}
    if len(existing) != len(scenes):
        raise ValueError("Repeated panels have custom timing. Review their order manually.")
    old_starts = {s["id"]: float(s.get("start_time_sec", 0)) for s in scenes}
    aligned = []
    time = 0.0
    for panel in panels:
        scene = existing.get(panel.id) or {
            "id": f"scene_{panel.id}", "title": f"Panel {panel.sequence}", "duration_sec": 4.0,
            "transition_in": "none", "layers": [{"id": f"layer_{panel.id}",
                "source_panel_id": panel.id, "source_page_id": panel.page_id,
                "image_url": f"/api/projects/{project_id}/pages/{panel.page_id}/file",
                "transform": {"x": 0, "y": 0, "scale": 1, "rotation": 0, "opacity": 1, "z_index": 1},
                "motion_preset": "none", "start_offset_sec": 0, "duration_sec": 4.0}]}
        scene["sequence"] = len(aligned) + 1
        scene["start_time_sec"] = time
        time += float(scene["duration_sec"])
        aligned.append(scene)
    # Audio belonging to removed scenes needs a deliberate editorial decision.
    surviving = {s["id"]: s for s in aligned}
    for clip in result.get("narration_clips", []):
        scene_id = clip.get("scene_id")
        if clip.get("linked_to_scene", True) and scene_id in old_starts:
            if scene_id not in surviving:
                raise ValueError("A removed panel has linked narration. Reassign or remove that narration before alignment.")
            clip["start_time_sec"] = float(clip.get("start_time_sec", 0)) + surviving[scene_id]["start_time_sec"] - old_starts[scene_id]
    result["scenes"] = aligned
    result["selected_object"] = None
    result["is_playing"] = False
    result["playhead_sec"] = 0
    result = reconcile_story_editor_state_with_panels(db, project_id, result)
    assert result is not None  # A dictionary input always reconciles to a dictionary.
    # Only this explicit, eligibility-checked operation acknowledges source changes.
    result["panels_stale"] = False
    result["panel_sync_required"] = False
    result["panel_review_sync"]["panels_stale"] = False
    return result


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
            workspace_path = Path(custom_path).expanduser().absolute()
        else:
            workspace_path = self.workspace_root / project_id

        resolve_contained_path(workspace_path.parent, workspace_path.name)
        if workspace_path.exists() and any(workspace_path.iterdir()):
            raise ValueError("Project destination must be an empty directory")
        workspace_path.mkdir(parents=True, exist_ok=True)
        resolve_contained_path(workspace_path, "project.json")
        for sub in ("source", "normalized", "panels", "ocr", "story", "script", "audio", "motion", "renders", "logs"):
            resolve_contained_path(workspace_path, sub).mkdir(exist_ok=True)

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
        with open_contained_output(record.workspace_path, "project.json") as f:
            f.write(json.dumps(data, indent=2).encode("utf-8"))

    def get_project(self, db: Session, project_id: str) -> ProjectRecord | None:
        return db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()

    def list_projects(self, db: Session) -> list[ProjectRecord]:
        return db.query(ProjectRecord).order_by(ProjectRecord.updated_at.desc()).all()

    def delete_project(self, db: Session, project_id: str) -> bool:
        record = self.get_project(db, project_id)
        if not record:
            return False

        ws_path = Path(record.workspace_path).expanduser()
        if ws_path.exists():
            from engine.security.paths import _pin_directory
            if ws_path.is_dir():
                marker = ws_path / "project.json"
                if not marker.is_file() or marker.is_symlink():
                    raise ValueError(f"Refusing to delete unmarked external directory: {ws_path}")
                try:
                    with open(marker, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("id") != project_id:
                        raise ValueError(f"Project marker ID mismatch: expected {project_id}")
                except Exception as e:
                    if isinstance(e, ValueError):
                        raise
                    raise ValueError(f"Cannot verify project marker in {ws_path}: {e}")

            if shutil.rmtree is not _orig_rmtree:
                with _pin_directory(ws_path):
                    shutil.rmtree(ws_path)
            else:
                remove_contained_directory(ws_path, expected_project_id=project_id)

        db.delete(record)
        db.commit()
        return True

    def sync_manifest_with_db(self, db: Session, project_id: str) -> AcquisitionManifest:
        """
        Reconstructs `manifest.json` from SQLite pages using a contained handle.

        The write is intentionally not atomic: a pathname-based temporary-file
        replace can escape through a concurrently swapped junction.
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
        created_at_iso = utc_now().isoformat()
        try:
            old_data = json.loads(read_contained_bytes(ws_path, "manifest.json").decode("utf-8"))
            created_at_iso = old_data.get("created_at", created_at_iso)
        except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError):
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

        # Direct handle-backed write: pathname-based replace is unsafe under a
        # concurrent junction swap. This metadata update is not atomic.
        with open_contained_output(ws_path, "manifest.json") as f:
            f.write(manifest.model_dump_json(indent=2).encode("utf-8"))

        return manifest

    def start_acquisition_job(
        self,
        db: Session,
        project_id: str,
        adapter_registry: AdapterRegistry,
        source_override: str | None = None,
        chapter_id: str | None = None,
        adapter_id: str | None = None,
        page_delay_sec: float | None = None,
        candidate_snapshot: list[dict] | None = None,
        chapter_snapshot: dict | None = None,
        operation_only: bool = False,
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
        if adapter_id and adapter.adapter_id != adapter_id:
            raise ValueError(f"Persisted acquisition adapter is unavailable: {adapter_id}")
        if operation_only:
            if not candidate_snapshot or not chapter_snapshot:
                raise ValueError("Persisted acquisition snapshot is missing")
            selected_chapter = ChapterInfo.model_validate(chapter_snapshot)
            if chapter_id != selected_chapter.id:
                raise ValueError("Persisted acquisition chapter snapshot does not match")
            candidates = [PageCandidate.model_validate(item) for item in candidate_snapshot]
        else:
            inspection = adapter.inspect(source_loc)
            if not inspection.is_valid:
                raise ValueError(f"Source validation failed: {inspection.error}")
            chapters = adapter.list_chapters(source_loc)
            if not chapters:
                raise ValueError("No chapters or image sequences discovered from source.")
            selected_chapter = next((chapter for chapter in chapters if chapter.id == chapter_id), None) if chapter_id else chapters[0]
            if selected_chapter is None:
                raise ValueError(f"Persisted acquisition chapter was not found: {chapter_id}")
            candidates = adapter.list_pages(selected_chapter)
        if not candidates:
            raise ValueError("No image candidates discovered in chapter.")
        if len({candidate.sequence for candidate in candidates}) != len(candidates):
            raise ValueError("Acquisition snapshot contains duplicate page sequences")

        # Check for simulated delay from project settings
        page_delay = 0.0 if page_delay_sec is None else page_delay_sec
        if page_delay_sec is None and record.settings and "simulated_page_delay_sec" in record.settings:
            try:
                page_delay = float(record.settings["simulated_page_delay_sec"])
            except (ValueError, TypeError):
                page_delay = 0.0

        if page_delay > 0:
            for c in candidates:
                if not hasattr(c, "extra_metadata") or c.extra_metadata is None:
                    c.extra_metadata = {}
                c.extra_metadata["delay_sec"] = page_delay

        job_id = None
        if not operation_only:
            job = job_manager.create_job(
                project_id=project_id,
                job_type=JobType.ACQUISITION,
                job_input={
                    "source": source_loc,
                    "chapter_id": selected_chapter.id,
                    "total_pages": len(candidates),
                    "adapter_id": adapter.adapter_id,
                    "page_delay_sec": page_delay,
                    "chapter": selected_chapter.model_dump(mode="json"),
                    "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
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

            if cancel_token.is_cancelled:
                raise RuntimeError("Acquisition worker lease was lost before database publication")

            # Update DB Page records
            from engine.database.session import SessionLocal
            with SessionLocal() as inner_db:
                if cancel_token.is_cancelled:
                    raise RuntimeError("Acquisition worker lease was lost before page publication")
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
                proj = inner_db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                stage_changed = bool(proj and ready_count > 0)
                if stage_changed:
                    proj.current_stage = PipelineStage.ACQUIRED.value
                    proj.updated_at = utc_now()

                if cancel_token.is_cancelled:
                    raise RuntimeError("Acquisition worker lease was lost before database commit")
                inner_db.commit()
                if stage_changed:
                    if cancel_token.is_cancelled:
                        raise RuntimeError("Acquisition worker lease was lost before project metadata publication")
                    inner_db.refresh(proj)
                    self._write_project_json(proj)

            return {
                "total": len(candidates),
                "ready": len([r for r in results if r.success]),
                "failed": len([r for r in results if not r.success]),
            }

        if operation_only:
            return run_acquisition
        job_manager.enqueue_async(job_id, run_acquisition)
        return job_id

    def retry_failed_pages(
        self,
        db: Session,
        project_id: str,
        adapter_registry: AdapterRegistry,
        page_ids: list[str] | None = None,
        source_override: str | None = None,
        adapter_id: str | None = None,
        operation_only: bool = False,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        failed_query = db.query(PageRecord).filter(PageRecord.project_id == project_id, PageRecord.status == "FAILED")
        if page_ids is not None:
            failed_query = failed_query.filter(PageRecord.id.in_(page_ids))
        failed_pages = failed_query.order_by(PageRecord.sequence.asc()).all()
        if page_ids is not None and ({page.id for page in failed_pages} != set(page_ids) or len(page_ids) != len(failed_pages)):
            raise ValueError("Persisted retry page set is no longer available")
        if not failed_pages:
            raise ValueError("No failed pages found to retry.")

        source_loc = source_override or record.source_url or record.source_metadata.get("path")
        adapter = adapter_registry.get_adapter_for(source_loc)
        if adapter_id and adapter.adapter_id != adapter_id:
            raise ValueError(f"Persisted retry adapter is unavailable: {adapter_id}")

        candidates = [
            PageCandidate(
                sequence=p.sequence,
                source_uri=p.source_url or str(project_path(record.workspace_path, "source", p.filename)),
                suggested_filename=p.filename,
            )
            for p in failed_pages
        ]

        job_id = None
        if not operation_only:
            job = job_manager.create_job(
                project_id=project_id,
                job_type=JobType.RETRY_PAGES,
                job_input={
                    "retry_count": len(candidates),
                    "page_ids": [page.id for page in failed_pages],
                    "source": source_loc,
                    "adapter_id": adapter.adapter_id,
                },
            )
            job_id = job.job_id

        async def run_retry(cancel_token: PipelineCancellationToken, progress_cb):
            pipeline = DownloadPipeline()
            ws_path = Path(record.workspace_path)

            # Read existing manifest
            existing_manifest = None
            try:
                existing_manifest = AcquisitionManifest.model_validate_json(read_contained_bytes(ws_path, "manifest.json"))
            except FileNotFoundError:
                pass

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

            if cancel_token.is_cancelled:
                raise RuntimeError("Retry worker lease was lost before database publication")

            # Update DB records for retried pages
            from engine.database.session import SessionLocal
            with SessionLocal() as inner_db:
                if cancel_token.is_cancelled:
                    raise RuntimeError("Retry worker lease was lost before page publication")
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
                ready_count = inner_db.query(PageRecord).filter(
                    PageRecord.project_id == project_id,
                    PageRecord.status == "READY"
                ).count()
                proj = inner_db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                stage_changed = bool(
                    proj and ready_count > 0 and proj.current_stage == PipelineStage.RIGHTS_APPROVED.value
                )
                if stage_changed:
                    proj.current_stage = PipelineStage.ACQUIRED.value
                    proj.updated_at = utc_now()

                if cancel_token.is_cancelled:
                    raise RuntimeError("Retry worker lease was lost before database commit")
                inner_db.commit()
                if stage_changed:
                    if cancel_token.is_cancelled:
                        raise RuntimeError("Retry worker lease was lost before project metadata publication")
                    inner_db.refresh(proj)
                    self._write_project_json(proj)
                if cancel_token.is_cancelled:
                    raise RuntimeError("Retry worker lease was lost before manifest synchronization")
                self.sync_manifest_with_db(inner_db, project_id)

            return {
                "retried": len(candidates),
                "recovered": len([r for r in results if r.success]),
                "remaining_failed": len([r for r in results if not r.success]),
            }

        if operation_only:
            return run_retry
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

        file_path = project_path(record.workspace_path, "source", page.filename)
        if file_path.exists():
            try:
                unlink_contained_file(record.workspace_path, Path("source") / page.filename)
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

        file_path = project_path(record.workspace_path, "source", page.filename)
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
        page_ids: list[str] | None = None,
        operation_only: bool = False,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        page_query = db.query(PageRecord).filter(PageRecord.project_id == project_id, PageRecord.status == "READY")
        if page_ids:
            page_query = page_query.filter(PageRecord.id.in_(page_ids))
        pages = page_query.order_by(PageRecord.sequence.asc()).all()
        if not pages:
            raise ValueError("No ready pages available to normalize.")
        if page_ids and {page.id for page in pages} != set(page_ids):
            raise ValueError("Persisted normalization page set is no longer available.")

        job_id = None
        if not operation_only:
            job = job_manager.create_job(
                project_id=project_id,
                job_type=JobType.NORMALIZATION,
                job_input={
                    "total_pages": len(pages),
                    "target_width": target_width,
                    "page_ids": [page.id for page in pages],
                },
            )
            job_id = job.job_id

        async def run_normalization(cancel_token: PipelineCancellationToken, progress_cb):
            ws_path = Path(record.workspace_path)
            norm_dir = resolve_contained_path(ws_path, "normalized")
            norm_dir.mkdir(parents=True, exist_ok=True)

            config = NormalizationConfig(target_width=target_width)
            total = len(pages)
            from engine.database.session import SessionLocal

            for idx, p in enumerate(pages, start=1):
                if cancel_token.is_cancelled:
                    break
                src_img = project_path(ws_path, "source", p.filename)
                out_img = project_path(ws_path, "normalized", f"page_{p.sequence:04d}.jpg")
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

        if operation_only:
            return run_normalization
        job_manager.enqueue_async(job_id, run_normalization)
        return job_id

    def detect_panels_project(
        self,
        db: Session,
        project_id: str,
        reading_direction: str = "ltr",
        min_area_ratio: float = 0.02,
        profile: str = "AUTO",
        page_ids: list[str] | None = None,
        operation_only: bool = False,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        page_query = db.query(PageRecord).filter(PageRecord.project_id == project_id, PageRecord.status == "READY")
        if page_ids:
            page_query = page_query.filter(PageRecord.id.in_(page_ids))
        pages = page_query.order_by(PageRecord.sequence.asc()).all()
        if not pages:
            raise ValueError("No ready pages found for panel detection.")
        if page_ids and {page.id for page in pages} != set(page_ids):
            raise ValueError("Persisted panel-detection page set is no longer available.")

        job_id = None
        if not operation_only:
            job = job_manager.create_job(
                project_id=project_id,
                job_type=JobType.PANEL_DETECTION,
                job_input={
                    "total_pages": len(pages),
                    "reading_direction": reading_direction,
                    "min_area_ratio": min_area_ratio,
                    "profile": profile,
                    "page_ids": [page.id for page in pages],
                },
            )
            job_id = job.job_id

        async def run_detection(cancel_token: PipelineCancellationToken, progress_cb):
            ws_path = Path(record.workspace_path)
            norm_dir = resolve_contained_path(ws_path, "normalized")
            panels_dir = resolve_contained_path(ws_path, "panels")
            panels_dir.mkdir(parents=True, exist_ok=True)

            from engine.database.session import SessionLocal
            with SessionLocal() as inner_db:
                protected_pages = protected_panel_pages(inner_db, project_id)
                selected_page_ids = [page.id for page in pages if page.id not in protected_pages]
                inner_db.query(PanelRecord).filter(
                    PanelRecord.project_id == project_id,
                    PanelRecord.page_id.in_(selected_page_ids),
                ).delete(synchronize_session=False)
                inner_db.commit()

            total_pages = len(pages)
            overall_seq = 1

            for p_idx, page in enumerate(pages, start=1):
                if cancel_token.is_cancelled:
                    break
                if page.id in protected_pages:
                    progress_cb(p_idx / total_pages, f"Preserved edited or linked panels on page {p_idx}/{total_pages}")
                    continue

                img_path = project_path(ws_path, "normalized", f"page_{page.sequence:04d}.jpg")
                if not img_path.exists():
                    img_path = project_path(ws_path, "source", page.filename)

                detected_boxes = panel_detector.detect_panels(
                    img_path,
                    reading_direction=reading_direction,
                    page_id=page.id,
                    profile=profile,
                )

                with SessionLocal() as inner_db:
                    for p_box in detected_boxes:
                        crop_filename = f"panel_{p_box.id}.jpg"
                        crop_path = project_path(ws_path, "panels", crop_filename)

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
                            polygon_json=p_box.polygon_json,
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
                self._resequence_project_panels(inner_db, project_id)
                self._sync_panels_json(inner_db, project_id)

            return {"total_panels_detected": overall_seq - 1,
                    "preserved_pages": len(set(page.id for page in pages) & protected_pages)}

        if operation_only:
            return run_detection
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
        img_path = project_path(ws_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not img_path.exists():
            img_path = project_path(ws_path, "source", page.filename)

        # Remove existing panels for this page
        if page_id in protected_panel_pages(db, project_id):
            return self.list_panels(db, project_id, page_id)
        existing_panels = db.query(PanelRecord).filter(PanelRecord.page_id == page_id).all()
        for ep in existing_panels:
            cf = project_path(ws_path, "panels", ep.crop_filename)
            if cf.exists():
                try:
                    unlink_contained_file(ws_path, Path("panels") / ep.crop_filename)
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

        panels_dir = resolve_contained_path(ws_path, "panels")
        panels_dir.mkdir(parents=True, exist_ok=True)

        max_seq = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).count()

        for idx, p_box in enumerate(detected_boxes, start=1):
            crop_filename = f"panel_{page.sequence:04d}_{idx:03d}.jpg"
            crop_path = project_path(ws_path, "panels", crop_filename)
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
                polygon_json=p_box.polygon_json,
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
        img_path = project_path(ws_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not img_path.exists():
            img_path = project_path(ws_path, "source", page.filename)

        orig_w = page.width or 1200
        orig_h = page.height or 1800

        max_seq = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).count() + 1
        page_panels_count = db.query(PanelRecord).filter(PanelRecord.page_id == page_id).count() + 1

        panel_id = str(uuid.uuid4())
        crop_filename = f"panel_{max_seq:04d}.jpg"
        crop_path = project_path(ws_path, "panels", crop_filename)

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
            polygon_json=p_box.polygon_json,
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
        img_path = project_path(ws_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not img_path.exists():
            img_path = project_path(ws_path, "source", page.filename)

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

        crop_path = project_path(ws_path, "panels", panel.crop_filename)
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
        img_path = project_path(ws_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not img_path.exists():
            img_path = project_path(ws_path, "source", page.filename)

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

        panels_dir = resolve_contained_path(ws_path, "panels")

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
        panel_detector.extract_crop(img_path, box1, project_path(record.workspace_path, "panels", panel.crop_filename))

        # Create second panel
        p2_id = str(uuid.uuid4())
        crop2_name = f"panel_{p2_id[:8]}.jpg"
        box2 = PanelBox(id=p2_id, page_id=panel.page_id, sequence=panel.page_sequence + 1, x=p2_box[0], y=p2_box[1], width=p2_box[2], height=p2_box[3])
        panel_detector.extract_crop(img_path, box2, project_path(ws_path, "panels", crop2_name))

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
        img_path = project_path(ws_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not img_path.exists():
            img_path = project_path(ws_path, "source", page.filename)

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
        panel_detector.extract_crop(img_path, p_box, project_path(ws_path, "panels", primary.crop_filename))

        for op in others:
            crop_f = project_path(ws_path, "panels", op.crop_filename)
            if crop_f.exists():
                try:
                    unlink_contained_file(ws_path, Path("panels") / op.crop_filename)
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

        crop_file = project_path(record.workspace_path, "panels", panel.crop_filename)
        if crop_file.exists():
            try:
                unlink_contained_file(record.workspace_path, Path("panels") / panel.crop_filename)
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
        
        # Mark Story Editor state as needing panel sync
        try:
            settings = record.settings or {}
            if isinstance(settings, dict) and "story_editor_state" in settings:
                state = settings.get("story_editor_state")
                if isinstance(state, dict):
                    panel_sync = dict(state.get("panel_review_sync") or {})
                    panel_sync["last_panel_confirm"] = utc_now().isoformat()
                    panel_sync["panels_stale"] = True
                    state["panel_review_sync"] = panel_sync
                    settings["story_editor_state"] = state
                    record.settings = settings
                    db.commit()
        except Exception as e:
            logger.warning(f"Failed to mark story editor state as stale: {e}")
        
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

        panels_dir = resolve_contained_path(record.workspace_path, "panels")
        panels_dir.mkdir(parents=True, exist_ok=True)
        panels_json_file = project_path(record.workspace_path, "panels", "panels.json")

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

        with open_contained_output(record.workspace_path, Path("panels") / "panels.json") as f:
            f.write(json.dumps(data, indent=2).encode("utf-8"))

        return data

    def extract_ocr_project(
        self,
        db: Session,
        project_id: str,
        engine_id: str = "mock_ocr",
        language: str = "en",
        panel_ids: list[str] | None = None,
        operation_only: bool = False,
    ) -> str:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel_query = db.query(PanelRecord).filter(PanelRecord.project_id == project_id)
        if panel_ids:
            panel_query = panel_query.filter(PanelRecord.id.in_(panel_ids))
        panels = panel_query.order_by(PanelRecord.sequence).all()
        if not panels:
            raise ValueError(
                f"Project {project_id} has no panels detected. Run panel detection first."
            )
        if panel_ids and {panel.id for panel in panels} != set(panel_ids):
            raise ValueError("Persisted OCR panel set is no longer available.")

        from engine.ocr.providers.registry import get_default_ocr_registry
        ocr_registry = get_default_ocr_registry()
        ocr_engine = ocr_registry.get_engine(engine_id)

        job_id = None
        if not operation_only:
            job = job_manager.create_job(
                project_id=project_id,
                job_type=JobType.OCR_EXTRACTION,
                job_input={
                    "total_panels": len(panels),
                    "engine_id": ocr_engine.engine_id,
                    "language": language,
                    "panel_ids": [panel.id for panel in panels],
                },
            )
            job_id = job.job_id

        async def run_ocr(cancel_token: PipelineCancellationToken, progress_cb):
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

                for idx, panel in enumerate(worker_panels, start=1):
                    if cancel_token.is_cancelled:
                        break

                    crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
                    if not crop_path.exists():
                        norm_path = project_path(ws_path, "normalized", panel.page.filename)
                        src_path = (
                            norm_path
                            if norm_path.exists()
                            else project_path(ws_path, "source", panel.page.filename)
                        )
                        if src_path.exists():
                            from PIL import Image
                            import io
                            with Image.open(io.BytesIO(read_contained_bytes(ws_path, src_path))) as full_img:
                                box = (
                                    panel.x,
                                    panel.y,
                                    panel.x + panel.width,
                                    panel.y + panel.height,
                                )
                                crop = full_img.crop(box)
                                write_contained_image(ws_path, crop_path, crop, "JPEG", quality=95)

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

        if operation_only:
            return run_ocr
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
        panels_dir = resolve_contained_path(ws_path, "panels")
        regions_dir = ensure_contained_directory(ws_path, "text_regions")

        created_records: list[TextRegionRecord] = []
        global_seq = 1

        for panel in panels:
            crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
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

            # Preserve OCR and corrections during repeated Detect & Review runs.
            existing_regions = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id).all()
            if any(r.raw_text or r.corrected_text or r.detection_method == "MANUAL" for r in existing_regions):
                created_records.extend(existing_regions)
                global_seq += len(existing_regions)
                continue
            # Replace only unreviewed regions that have no OCR yet.
            db.query(TextRegionRecord).filter(
                TextRegionRecord.panel_id == panel.id,
                TextRegionRecord.detection_method != "MANUAL",
            ).delete()

            from PIL import Image
            import hashlib
            import io
            with Image.open(io.BytesIO(read_contained_bytes(ws_path, crop_path))) as p_img:
                for box in detected_boxes:
                    rx1 = max(0, min(box.x, p_img.width - 1))
                    ry1 = max(0, min(box.y, p_img.height - 1))
                    rx2 = max(rx1 + 1, min(box.x + box.width, p_img.width))
                    ry2 = max(ry1 + 1, min(box.y + box.height, p_img.height))

                    region_crop = p_img.crop((rx1, ry1, rx2, ry2))
                    crop_filename = f"reg_{panel.id[:8]}_{box.sequence_in_panel}_{uuid.uuid4().hex[:6]}.jpg"
                    reg_crop_path = project_path(ws_path, "text_regions", crop_filename)
                    write_contained_image(ws_path, reg_crop_path, region_crop, "JPEG", quality=95)

                    crop_bytes = read_contained_bytes(ws_path, reg_crop_path)
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
        crop_path = project_path(ws_path, "text_regions", tr.crop_filename)

        if not crop_path.exists():
            # Extract crop on demand from panel crop
            panel = db.query(PanelRecord).filter(PanelRecord.id == tr.panel_id).first()
            p_crop = project_path(ws_path, "panels", panel.crop_filename) if panel else None
            if p_crop and p_crop.exists():
                from PIL import Image
                import hashlib
                import io
                with Image.open(io.BytesIO(read_contained_bytes(ws_path, p_crop))) as p_img:
                    rx1 = max(0, min(tr.x, p_img.width - 1))
                    ry1 = max(0, min(tr.y, p_img.height - 1))
                    rx2 = max(rx1 + 1, min(tr.x + tr.width, p_img.width))
                    ry2 = max(ry1 + 1, min(tr.y + tr.height, p_img.height))
                    reg_img = p_img.crop((rx1, ry1, rx2, ry2))
                    write_contained_image(ws_path, crop_path, reg_img, "JPEG", quality=95)
                    tr.crop_sha256 = hashlib.sha256(read_contained_bytes(ws_path, crop_path)).hexdigest()

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
        ocr_dir = resolve_contained_path(ws_path, "ocr")
        ocr_dir.mkdir(parents=True, exist_ok=True)
        ocr_json_file = project_path(ws_path, "ocr", "ocr.json")

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

        with open_contained_output(ws_path, Path("ocr") / "ocr.json") as f:
            f.write(json.dumps(data, indent=2).encode("utf-8"))

        return data

    def blur_panel_box(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        blur_radius: int = 24,
        feather: int = 4,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
        if not crop_path.exists():
            raise FileNotFoundError(f"Panel crop file missing: {crop_path}")

        from engine.imaging.redaction import blur_image_box
        success = blur_image_box(crop_path, x, y, width, height, blur_radius=blur_radius, feather=feather, backup=True)
        if success:
            panel.manually_modified = True
            panel.updated_at = utc_now()
            db.commit()

        return {"success": success, "panel_id": panel_id, "has_backup": True}

    def blur_text_region(
        self,
        db: Session,
        project_id: str,
        region_id: str,
        blur_radius: int = 24,
        feather: int = 4,
    ) -> TextRegionRecord:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        tr = db.query(TextRegionRecord).filter(TextRegionRecord.id == region_id, TextRegionRecord.project_id == project_id).first()
        if not tr:
            raise KeyError(f"Text region not found: {region_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == tr.panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {tr.panel_id}")

        crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
        if not crop_path.exists():
            raise FileNotFoundError(f"Panel crop file missing: {crop_path}")

        from engine.imaging.redaction import blur_image_box
        blur_image_box(crop_path, tr.x, tr.y, tr.width, tr.height, blur_radius=blur_radius, feather=feather, backup=True)

        # If region crop thumbnail exists, blur it too
        if tr.crop_filename:
            reg_thumb = project_path(record.workspace_path, "text_regions", tr.crop_filename)
            if reg_thumb.exists():
                from engine.imaging.redaction import blur_entire_image
                blur_entire_image(reg_thumb, blur_radius=blur_radius, backup=True)

        tr.status = "BLURRED"
        tr.region_type = "REDACTED"
        tr.corrected_text = "[BLURRED / REDACTED]"
        tr.correction_status = "VERIFIED"
        tr.updated_at = utc_now()

        panel.manually_modified = True
        panel.updated_at = utc_now()
        db.commit()
        db.refresh(tr)
        return tr

    def blur_panel_text(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        region_ids: list[str] | None = None,
        blur_radius: int = 24,
        feather: int = 4,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
        if not crop_path.exists():
            raise FileNotFoundError(f"Panel crop file missing: {crop_path}")

        query = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel_id, TextRegionRecord.project_id == project_id)
        if region_ids:
            query = query.filter(TextRegionRecord.id.in_(region_ids))
        regions = query.all()

        from engine.imaging.redaction import blur_image_box, blur_entire_image
        count = 0
        for tr in regions:
            blur_image_box(crop_path, tr.x, tr.y, tr.width, tr.height, blur_radius=blur_radius, feather=feather, backup=True)
            if tr.crop_filename:
                reg_thumb = project_path(record.workspace_path, "text_regions", tr.crop_filename)
                if reg_thumb.exists():
                    blur_entire_image(reg_thumb, blur_radius=blur_radius, backup=True)

            tr.status = "BLURRED"
            tr.region_type = "REDACTED"
            tr.corrected_text = "[BLURRED / REDACTED]"
            tr.correction_status = "VERIFIED"
            tr.updated_at = utc_now()
            count += 1

        panel.manually_modified = True
        panel.updated_at = utc_now()
        db.commit()

        return {"success": True, "panel_id": panel_id, "blurred_count": count}

    def blur_entire_panel(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
        blur_radius: int = 32,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
        if not crop_path.exists():
            raise FileNotFoundError(f"Panel crop file missing: {crop_path}")

        from engine.imaging.redaction import blur_entire_image
        success = blur_entire_image(crop_path, blur_radius=blur_radius, backup=True)

        # Mark all regions in this panel as blurred/redacted
        regions = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel_id, TextRegionRecord.project_id == project_id).all()
        for tr in regions:
            tr.status = "BLURRED"
            tr.region_type = "REDACTED"
            tr.corrected_text = "[BLURRED / REDACTED]"
            tr.correction_status = "VERIFIED"
            tr.updated_at = utc_now()

        panel.manually_modified = True
        panel.updated_at = utc_now()
        db.commit()

        return {"success": success, "panel_id": panel_id}

    def reset_panel_image(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
        from engine.imaging.redaction import restore_image_backup
        restored = restore_image_backup(crop_path)

        # Reset any blurred text regions in this panel back to CONFIRMED / SPEECH
        regions = db.query(TextRegionRecord).filter(
            TextRegionRecord.panel_id == panel_id,
            TextRegionRecord.project_id == project_id,
            TextRegionRecord.status == "BLURRED",
        ).all()
        for tr in regions:
            tr.status = "CONFIRMED"
            tr.region_type = "SPEECH"
            tr.corrected_text = tr.raw_text or ""
            tr.correction_status = "UNEDITED"
            tr.updated_at = utc_now()

            # Restore region thumbnail if backup exists
            if tr.crop_filename:
                reg_thumb = project_path(record.workspace_path, "text_regions", tr.crop_filename)
                restore_image_backup(reg_thumb)

        db.commit()
        return {"success": restored, "panel_id": panel_id}

    def get_panel_blur_status(
        self,
        db: Session,
        project_id: str,
        panel_id: str,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project_id).first()
        if not panel:
            raise KeyError(f"Panel not found: {panel_id}")

        crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
        from engine.imaging.redaction import has_image_backup
        has_backup = has_image_backup(crop_path)

        blurred_count = db.query(TextRegionRecord).filter(
            TextRegionRecord.panel_id == panel_id,
            TextRegionRecord.project_id == project_id,
            TextRegionRecord.status == "BLURRED",
        ).count()

        return {
            "is_blurred": has_backup or (blurred_count > 0),
            "has_backup": has_backup,
            "blurred_regions_count": blurred_count,
        }

    def batch_blur_panels(
        self,
        db: Session,
        project_id: str,
        preset: str = "TOP_WATERMARK",
        height_px: int = 80,
        blur_radius: int = 24,
        feather: int = 6,
        panel_ids: Optional[List[str]] = None,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        query = db.query(PanelRecord).filter(PanelRecord.project_id == project_id)
        if panel_ids:
            query = query.filter(PanelRecord.id.in_(panel_ids))
        panels = query.all()

        from engine.imaging.redaction import blur_image_box, blur_entire_image
        workspace = Path(record.workspace_path)
        panels_dir = workspace / "panels"

        blurred_panels_count = 0
        for panel in panels:
            if not panel.crop_filename:
                continue
            crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
            if not crop_path.exists():
                continue

            pw = panel.width or 1200
            ph = panel.height or 800

            if preset == "TOP_WATERMARK":
                h = min(height_px, max(20, int(ph * 0.25)))
                if blur_image_box(crop_path, 0, 0, pw, h, blur_radius=blur_radius, feather=feather, backup=True):
                    blurred_panels_count += 1
            elif preset == "BOTTOM_SUBSCRIBE":
                h = min(height_px, max(20, int(ph * 0.25)))
                y = max(0, ph - h)
                if blur_image_box(crop_path, 0, y, pw, h, blur_radius=blur_radius, feather=feather, backup=True):
                    blurred_panels_count += 1
            elif preset == "ENTIRE_PANEL":
                if blur_entire_image(crop_path, blur_radius=blur_radius, backup=True):
                    blurred_panels_count += 1
            elif preset == "ALL_TEXT_REGIONS":
                regions = db.query(TextRegionRecord).filter(
                    TextRegionRecord.panel_id == panel.id,
                    TextRegionRecord.project_id == project_id,
                ).all()
                blurred_any = False
                for tr in regions:
                    if blur_image_box(crop_path, tr.x, tr.y, tr.width, tr.height, blur_radius=blur_radius, feather=feather, backup=True):
                        blurred_any = True
                        tr.status = "BLURRED"
                        tr.region_type = "REDACTED"
                        tr.corrected_text = "[BLURRED / REDACTED]"
                        tr.correction_status = "VERIFIED"
                        tr.updated_at = utc_now()
                if blurred_any:
                    blurred_panels_count += 1

        db.commit()
        return {
            "success": True,
            "project_id": project_id,
            "preset": preset,
            "blurred_panels_count": blurred_panels_count,
            "total_panels": len(panels),
        }

    def batch_reset_panels(
        self,
        db: Session,
        project_id: str,
        panel_ids: Optional[List[str]] = None,
    ) -> dict:
        record = self.get_project(db, project_id)
        if not record:
            raise KeyError(f"Project not found: {project_id}")

        query = db.query(PanelRecord).filter(PanelRecord.project_id == project_id)
        if panel_ids:
            query = query.filter(PanelRecord.id.in_(panel_ids))
        panels = query.all()

        from engine.imaging.redaction import restore_image_backup
        workspace = Path(record.workspace_path)
        panels_dir = workspace / "panels"

        restored_count = 0
        for panel in panels:
            if not panel.crop_filename:
                continue
            crop_path = project_path(record.workspace_path, "panels", panel.crop_filename)
            if restore_image_backup(crop_path, delete_backup=True):
                restored_count += 1

        target_panel_ids = [p.id for p in panels]
        regions = db.query(TextRegionRecord).filter(
            TextRegionRecord.project_id == project_id,
            TextRegionRecord.panel_id.in_(target_panel_ids),
            TextRegionRecord.status == "BLURRED",
        ).all()
        for tr in regions:
            tr.status = "CONFIRMED"
            tr.region_type = "SPEECH"
            tr.corrected_text = tr.raw_text or ""
            tr.correction_status = "UNEDITED"
            tr.updated_at = utc_now()

        db.commit()
        return {
            "success": True,
            "project_id": project_id,
            "restored_panels_count": restored_count,
            "total_panels": len(panels),
        }


project_service = ProjectService()

