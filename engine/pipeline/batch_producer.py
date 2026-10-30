"""

Smart Batch Video Producer for Manga Series and Multi-Chapter Compilations.

Coordinates chapter-by-chapter acquisition, segmentation, OCR, story adaptation,

neural audio generation, 1080p rendering, and smart multi-chapter compilation.

"""

import os

import sys

import json

import time

import uuid

import shutil

import asyncio

import logging

import subprocess

from pathlib import Path

from typing import List, Dict, Any, Optional, Callable



from engine.acquisition.web.series.models import (

    SeriesChapter,

    SeriesMetadata,

    CompilationBundle,

    CompilationMode,

    BatchVideoConfig,

    BatchJobStatus,

)

from engine.acquisition.web.series.discovery import SmartSeriesDiscoveryEngine

from engine.acquisition.web.series.grouper import SmartChapterGrouper

from engine.acquisition.web.chapter_extractor import AdaptiveChapterExtractor

from engine.database.session import SessionLocal

from engine.database.models import ProjectRecord, VideoScriptRecord, ScriptSegmentRecord, PanelRecord, RenderJobRecord

from engine.pipeline.autopilot import AutoPilotRunner

from sqlalchemy.orm.attributes import flag_modified



logger = logging.getLogger("panelflow.batch_producer")



# In-memory registry for active and past batch jobs

active_batch_jobs: Dict[str, BatchJobStatus] = {}





class SmartBatchVideoProducer:

    """

    End-to-end batch producer for manga series episodes and compilations.

    """



    def __init__(self, default_output_root: Optional[Path] = None):

        self.discovery_engine = SmartSeriesDiscoveryEngine()

        self.grouper = SmartChapterGrouper()

        self.extractor = AdaptiveChapterExtractor()

        project_root = Path(__file__).resolve().parent.parent.parent

        self.output_root = default_output_root or (project_root / "output")

        self.output_root.mkdir(parents=True, exist_ok=True)



    async def run_batch(

        self,

        config: BatchVideoConfig,

        progress_cb: Optional[Callable[[BatchJobStatus], None]] = None,

        cancel_check: Optional[Callable[[], bool]] = None,
        job_id: Optional[str] = None,
    ) -> BatchJobStatus:
        job_id = job_id or f"batch_{uuid.uuid4().hex[:10]}"

        now = time.time()

        job_status = BatchJobStatus(

            job_id=job_id,

            series_title="Discovering...",

            status="RUNNING",

            progress=0.01,

            created_at=now,

            updated_at=now,

        )

        active_batch_jobs[job_id] = job_status



        def update_job(step: str, chapter_name: Optional[str] = None, pct: Optional[float] = None):

            job_status.current_step = step

            if chapter_name:

                job_status.current_chapter = chapter_name

            if pct is not None:

                job_status.progress = round(pct, 3)

            job_status.updated_at = time.time()

            if progress_cb:

                try:

                    progress_cb(job_status)

                except Exception:

                    pass



        try:

            # ---------------------------------------------------------------

            # 1. Series & Chapter Discovery

            # ---------------------------------------------------------------

            update_job("Discovering series catalog & chapters...", pct=0.02)

            series_meta = await self.discovery_engine.discover_series(config.source_url)

            job_status.series_title = series_meta.title



            # Filter chapters according to user config

            selected_chapters: List[SeriesChapter] = []

            if config.chapter_urls:

                url_set = set(config.chapter_urls)

                selected_chapters = [c for c in series_meta.chapters if c.url in url_set]

            elif config.chapter_start is not None or config.chapter_end is not None:

                c_start = config.chapter_start if config.chapter_start is not None else series_meta.detected_range[0]

                c_end = config.chapter_end if config.chapter_end is not None else series_meta.detected_range[1]

                selected_chapters = [

                    c for c in series_meta.chapters if c_start - 1e-4 <= c.sequence <= c_end + 1e-4

                ]

                if not selected_chapters and series_meta.url_pattern and c_start is not None and c_end is not None:

                    for seq in range(int(c_start), int(c_end) + 1):

                        ch_url = series_meta.url_pattern.replace("{chapter_number}", str(seq))

                        selected_chapters.append(SeriesChapter(

                            sequence=float(seq),

                            title=f"Chapter {seq}",

                            url=ch_url,

                        ))

            else:

                selected_chapters = list(series_meta.chapters)



            if config.max_chapters and len(selected_chapters) > config.max_chapters:

                selected_chapters = selected_chapters[:config.max_chapters]



            if not selected_chapters:

                raise ValueError(f"No chapters matched criteria (Range: {config.chapter_start} to {config.chapter_end})")



            job_status.total_chapters = len(selected_chapters)

            logger.info(f"Batch {job_id}: Selected {len(selected_chapters)} chapters from {series_meta.title}.")



            # Setup series output folders

            clean_series_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in series_meta.title).strip("_")

            series_out_dir = Path(config.output_dir) if config.output_dir else (self.output_root / clean_series_name)

            indiv_dir = series_out_dir / "Individual_Episodes"

            comp_dir = series_out_dir / "Compilations"

            indiv_dir.mkdir(parents=True, exist_ok=True)

            comp_dir.mkdir(parents=True, exist_ok=True)



            # ---------------------------------------------------------------

            # 2. Produce Individual Chapter Videos

            # ---------------------------------------------------------------

            rendered_chapter_files: Dict[float, Path] = {}

            rendered_chapter_durations: Dict[float, float] = {}



            for idx, ch in enumerate(selected_chapters, 1):

                if cancel_check and cancel_check():

                    job_status.status = "CANCELLED"

                    update_job("Cancelled by user")

                    return job_status



                ch_num_str = f"{int(ch.sequence)}" if ch.sequence.is_integer() else f"{ch.sequence:g}"

                chapter_label = f"Chapter {ch_num_str}"

                base_pct = 0.05 + 0.85 * ((idx - 1) / len(selected_chapters))

                update_job(f"Processing {chapter_label} ({idx}/{len(selected_chapters)})...", chapter_name=chapter_label, pct=base_pct)



                expected_mp4 = indiv_dir / f"{clean_series_name}_Chapter_{ch_num_str}_1080p.mp4"



                # Check if already rendered

                if expected_mp4.exists() and expected_mp4.stat().st_size > 100_000:

                    logger.info(f"Using existing rendered MP4 for {chapter_label}: {expected_mp4}")

                    dur = self._probe_video_duration(expected_mp4)

                    rendered_chapter_files[ch.sequence] = expected_mp4

                    rendered_chapter_durations[ch.sequence] = dur

                    job_status.generated_videos.append(str(expected_mp4))

                    job_status.completed_chapters += 1

                    continue



                # Generate video for this single chapter

                mp4_path, dur = await self._produce_single_chapter(

                    chapter=ch,

                    series_title=series_meta.title,

                    clean_series_name=clean_series_name,

                    config=config,

                    target_output_path=expected_mp4,

                    progress_reporter=lambda step: update_job(f"[{chapter_label}] {step}", chapter_name=chapter_label),

                    cancel_check=cancel_check,

                )



                rendered_chapter_files[ch.sequence] = mp4_path

                rendered_chapter_durations[ch.sequence] = dur

                job_status.generated_videos.append(str(mp4_path))

                job_status.completed_chapters += 1



            # ---------------------------------------------------------------

            # 3. Mode: Smart Compilation Bundling & Concat

            # ---------------------------------------------------------------

            if config.compilation_mode == CompilationMode.COMPILED:

                update_job("Assembling smart compilation bundles...", pct=0.92)

                bundles = self.grouper.partition_chapters(

                    chapters=selected_chapters,

                    series_title=series_meta.title,

                    compilation_mode=CompilationMode.COMPILED,

                    target_duration_minutes=config.target_duration_minutes or 25.0,

                    known_durations=rendered_chapter_durations,

                )



                for b_idx, bundle in enumerate(bundles, 1):

                    update_job(f"Merging compilation {b_idx}/{len(bundles)}: {bundle.title}...", pct=0.92 + 0.07 * (b_idx / len(bundles)))

                    comp_mp4 = comp_dir / bundle.output_filename

                    bundle_files = [rendered_chapter_files[c.sequence] for c in bundle.chapters if c.sequence in rendered_chapter_files]



                    if bundle_files:

                        self._concat_videos(bundle_files, comp_mp4)

                        job_status.compilation_videos.append(str(comp_mp4))

                        # Write release packaging metadata with timestamps

                        meta_txt = comp_mp4.with_suffix(".txt")

                        self._write_compilation_metadata(bundle, series_meta.title, comp_mp4, meta_txt)



            job_status.status = "COMPLETED"

            job_status.progress = 1.0

            update_job("Batch video production completed successfully!", pct=1.0)

            return job_status



        except Exception as e:

            logger.exception(f"Batch production failed: {e}")

            job_status.status = "FAILED"

            job_status.errors.append(str(e))

            update_job(f"Error: {e}")

            return job_status



    async def _produce_single_chapter(

        self,

        chapter: SeriesChapter,

        series_title: str,

        clean_series_name: str,

        config: BatchVideoConfig,

        target_output_path: Path,

        progress_reporter: Callable[[str], None],

        cancel_check: Optional[Callable[[], bool]],

    ) -> Tuple[Path, float]:

        """

        Processes a single chapter through acquisition, segmentation, OCR,

        script synthesis, Kokoro-82M TTS, and 1080p render.

        """

        ch_num_str = f"{int(chapter.sequence)}" if chapter.sequence.is_integer() else f"{chapter.sequence:g}"

        project_title = f"{series_title} - Chapter {ch_num_str}"

        if target_output_path.exists() and target_output_path.stat().st_size > 1_000_000:
            logger.info(f"Target video already produced: {target_output_path}")
            dur = self._probe_video_duration(target_output_path)
            return target_output_path, dur

        # Check existing project in DB

        db = SessionLocal()

        try:

            existing_p = db.query(ProjectRecord).filter(

                ProjectRecord.source_url == chapter.url

            ).first()



            if existing_p:

                project_id = existing_p.id

                workspace_dir = Path(existing_p.workspace_path)

            else:

                from engine.projects.service import ProjectService

                from engine.acquisition.rights.models import RightsStatus

                ps = ProjectService()

                project_rec = ps.create_project(

                    db=db,

                    title=project_title,

                    source_type="AUTHORIZED_WEB",

                    rights_status=RightsStatus.EXPLICIT_PERMISSION,

                    source_url=chapter.url,

                    source_metadata={"series_title": series_title, "chapter_sequence": chapter.sequence},

                )

                project_id = project_rec.id

                workspace_dir = Path(project_rec.workspace_path)

        finally:

            db.close()



        # Step A: Download & Acquisition

        progress_reporter("Acquiring chapter pages...")

        source_dir = workspace_dir / "source"

        source_images = [f for f in source_dir.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".webp", ".png")] if source_dir.exists() else []

        if not source_dir.exists() or len(source_images) < 2:

            extract_res = await self.extractor.extract(chapter.url)

            if extract_res.state.value != "EXTRACTED" or not extract_res.manifest:

                raise ValueError(f"Failed to extract pages from {chapter.url}: {extract_res.error}")

            source_dir.mkdir(parents=True, exist_ok=True)

            await self.extractor.download(extract_res.manifest, source_dir)

            source_images = [f for f in source_dir.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".webp", ".png")]



        # Ensure PageRecords exist in SQLite DB for AutoPilot

        db_sync = SessionLocal()

        try:

            from engine.database.models import PageRecord, PipelineStage

            from engine.database.models import utc_now

            existing_count = db_sync.query(PageRecord).filter(PageRecord.project_id == project_id).count()

            if existing_count < 2 and source_images:

                db_sync.query(PageRecord).filter(PageRecord.project_id == project_id).delete()

                sorted_files = sorted(source_images, key=lambda x: x.name)

                for idx, img_file in enumerate(sorted_files, 1):

                    pr = PageRecord(

                        id=str(uuid.uuid4()),

                        project_id=project_id,

                        sequence=idx,

                        filename=img_file.name,

                        source_url=chapter.url,

                        content_type=f"image/{img_file.suffix.lstrip('.')}",

                        width=0,

                        height=0,

                        byte_size=img_file.stat().st_size,

                        status="READY",

                        downloaded_at=utc_now(),

                    )

                    db_sync.add(pr)

                proj = db_sync.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()

                if proj:

                    proj.current_stage = PipelineStage.ACQUIRED.value

                    proj.updated_at = utc_now()

                db_sync.commit()

        finally:

            db_sync.close()



        # Step B: AutoPilot Pipeline (Panels, OCR, Story, Script, Kokoro Audio, Render)

        progress_reporter("Executing pipeline autopilot...")

        runner = AutoPilotRunner(

            project_id=project_id,

            options={

                "skip_existing_stages": True,

                "target_profile": config.video_profile,

                "subtitles": config.subtitles,

            },

        )

        await runner.execute()
        if runner.status != "COMPLETED":
            raise RuntimeError(f"AutoPilot pipeline failed for {project_title}: {runner.error}")

        # Step C: Retrieve rendered MP4 from render job

        db = SessionLocal()

        try:

            last_job = db.query(RenderJobRecord).filter(

                RenderJobRecord.project_id == project_id,

                RenderJobRecord.status.in_(("COMPLETED", "COMPLETE"))

            ).order_by(RenderJobRecord.created_at.desc()).first()



            if not last_job or not last_job.output_path or not Path(last_job.output_path).exists():

                # Check workspace renders folder

                renders = list((workspace_dir / "renders").glob("*.mp4"))

                if not renders:

                    raise RuntimeError(f"No rendered MP4 found for {project_title}")

                rendered_mp4 = renders[0]

            else:

                rendered_mp4 = Path(last_job.output_path)



            shutil.copy2(str(rendered_mp4), str(target_output_path))

            dur = self._probe_video_duration(target_output_path)

            return target_output_path, dur



        finally:

            db.close()



    @staticmethod

    def _probe_video_duration(file_path: Path) -> float:

        try:

            res = subprocess.run(

                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],

                capture_output=True,

                text=True,

                check=True,

            )

            return float(res.stdout.strip())

        except Exception:

            return DEFAULT_ESTIMATED_CHAPTER_DURATION_SEC



    @staticmethod

    def _concat_videos(video_paths: List[Path], output_path: Path):

        """

        Concatenates multiple 1080p MP4 files using FFmpeg stream copy concat demuxer.

        Lossless and runs in seconds without re-encoding!

        """

        output_path.parent.mkdir(parents=True, exist_ok=True)

        list_file = output_path.with_suffix(".concat_list.txt")

        try:

            with open(list_file, "w", encoding="utf-8") as f:

                for vp in video_paths:

                    # FFmpeg concat syntax requires forward slashes or escaped backslashes

                    clean_p = str(vp.resolve()).replace("\\", "/")

                    f.write(f"file '{clean_p}'\n")



            cmd = [

                "ffmpeg", "-y", "-f", "concat", "-safe", "0",

                "-i", str(list_file),

                "-c", "copy",

                "-movflags", "+faststart",

                str(output_path),

            ]

            subprocess.run(cmd, check=True, capture_output=True)

            logger.info(f"Successfully concatenated {len(video_paths)} videos into {output_path}")

        finally:

            if list_file.exists():

                try:

                    list_file.unlink()

                except Exception:

                    pass



    @staticmethod

    def _write_compilation_metadata(

        bundle: CompilationBundle,

        series_title: str,

        video_path: Path,

        meta_txt_path: Path,

    ):

        """

        Generates YouTube-ready timestamps and description for multi-chapter compilation.

        """

        first_num = bundle.chapters[0].sequence

        last_num = bundle.chapters[-1].sequence

        first_str = f"{int(first_num)}" if first_num.is_integer() else f"{first_num:g}"

        last_str = f"{int(last_num)}" if last_num.is_integer() else f"{last_num:g}"



        title = f"{series_title} - Chapters {first_str} to {last_str} | Full Motion Manhua ({int(bundle.target_duration_minutes)}min Movie Cut)"

        

        desc_lines = [

            f"{title}",

            "",

            f"Binge watch {series_title} Chapters {first_str} through {last_str} in full 1080p motion comic quality with complete voiceover narration.",

            "",

            "CHAPTER TIMESTAMPS:",

        ]

        for m in bundle.chapter_markers:

            desc_lines.append(f"{m['timestamp_str']} - {m['title']}")



        desc_lines.extend([

            "",

            f"Original Series: {series_title}",

            "Produced with PanelFlow Studio.",

            "",

            "TAGS:",

            f"{series_title}, Chapters {first_str}-{last_str}, Manhua Motion Comic, Full Movie Cut, PanelFlow Studio",

        ])



        with open(meta_txt_path, "w", encoding="utf-8") as f:

            f.write("\n".join(desc_lines))

        logger.info(f"Wrote compilation metadata to {meta_txt_path}")

