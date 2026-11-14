"""
ChronoFlow Pro Studio — Centralized Job Supervisor & State Manager
Implements the Supervisor Pattern, State Machine Pattern, and Observer Pattern
for deterministic, race-condition-free UI synchronization and job execution.
"""

import sys
import json
import time
import asyncio
from pathlib import Path

# Paths
from engine.chronoflow.pipeline import BASE_DIR, COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR

VAULT_DIR = Path(__file__).resolve().parent / "vault"
JOBS_FILE = VAULT_DIR / "jobs.json"

VAULT_DIR.mkdir(parents=True, exist_ok=True)
STUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def _clean_surrogates(obj):
    if isinstance(obj, str):
        return obj.encode("utf-8", errors="replace").decode("utf-8")
    elif isinstance(obj, dict):
        return {k: _clean_surrogates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_surrogates(item) for item in obj]
    return obj


class JobSupervisor:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, pipeline=None):
        if self._initialized:
            if pipeline and not self.pipeline:
                self.pipeline = pipeline
            return

        self.pipeline = pipeline
        self.state_version = 1
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._last_disk_mtime = JOBS_FILE.stat().st_mtime if JOBS_FILE.exists() else 0
        self.active_jobs = self._load_jobs_from_disk()
        self._clean_orphaned_jobs_on_boot()
        self._watchdog_task = None
        self._initialized = True

    def _sync_with_disk_and_storage(self):
        """Reloads jobs.json if modified on disk, and reconciles STUDIO_OUTPUT_DIR to ensure all on-disk chunks are included."""
        try:
            mtime = JOBS_FILE.stat().st_mtime if JOBS_FILE.exists() else 0
            if getattr(self, "_last_disk_mtime", 0) < mtime:
                disk_jobs = self._load_jobs_from_disk()
                for jid, j in disk_jobs.items():
                    if jid not in self.active_jobs or self.active_jobs[jid].get("status") not in ("starting", "regenerating"):
                        self.active_jobs[jid] = j
                    else:
                        if len(j.get("chunks", [])) > len(self.active_jobs[jid].get("chunks", [])):
                            self.active_jobs[jid]["chunks"] = j["chunks"]
                        if len(j.get("chunk_prompts", [])) > len(self.active_jobs[jid].get("chunk_prompts", [])):
                            self.active_jobs[jid]["chunk_prompts"] = j["chunk_prompts"]
                self._last_disk_mtime = mtime
                self.state_version += 1
        except Exception:
            pass

        changed = False
        try:
            for jid, job in list(self.active_jobs.items()):
                pattern = f"{jid}_chunk_*.mp4"
                found_files = sorted(
                    list(STUDIO_OUTPUT_DIR.glob(pattern)),
                    key=lambda p: int(p.stem.split("_chunk_")[-1]) if p.stem.split("_chunk_")[-1].isdigit() else 999
                )
                tombstones = set(job.get("deleted_chunks", []))
                existing_chunks = job.get("chunks", [])
                filtered_chunks = [c for c in existing_chunks if Path(c).name not in tombstones]
                existing_basenames = {Path(c).name for c in filtered_chunks}
                new_chunks = list(filtered_chunks)
                for f in found_files:
                    if f.name in tombstones:
                        continue
                    if f.name not in existing_basenames:
                        new_chunks.append(f"/outputs/{f.name}")
                        existing_basenames.add(f.name)
                if len(new_chunks) != len(existing_chunks) or new_chunks != existing_chunks:
                    job["chunks"] = new_chunks
                    job["total_chunks"] = max(job.get("total_chunks", 0), len(new_chunks))
                    job["current_chunk"] = len(new_chunks)
                    changed = True
        except Exception:
            pass

        if changed:
            self.state_version += 1
            self._save_jobs_to_disk()

    def _load_jobs_from_disk(self) -> dict:
        if JOBS_FILE.exists():
            try:
                raw_text = JOBS_FILE.read_text(encoding="utf-8", errors="replace")
                return json.loads(raw_text)
            except Exception as e:
                print(f"[SUPERVISOR] Warning: Could not parse jobs.json: {e}")
                return {}
        return {}

    def _save_jobs_to_disk(self):
        try:
            temp_file = VAULT_DIR / f"jobs_tmp_{int(time.time()*1000)}.json"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.active_jobs, f, indent=2)
            temp_file.replace(JOBS_FILE)
        except Exception as e:
            print(f"[SUPERVISOR] Warning: Could not save jobs.json: {e}")

    def _clean_orphaned_jobs_on_boot(self):
        """On boot, any job previously in starting or regenerating without a live task is reconciled."""
        changed = False
        for jid, j in self.active_jobs.items():
            if j.get("status") in ("starting", "regenerating"):
                chunks = j.get("chunks", [])
                if chunks:
                    j["status"] = "completed"
                    j["status_msg"] = f"Job restored with {len(chunks)} completed scene chunks."
                else:
                    j["status"] = "cancelled"
                    j["status_msg"] = "Interrupted prior to studio restart."
                changed = True
        if changed:
            self.state_version += 1
            self._save_jobs_to_disk()

    def bump_version(self):
        self.state_version += 1

    def get_job(self, job_id: str) -> dict:
        self._sync_with_disk_and_storage()
        job = self.active_jobs.get(job_id)
        return _clean_surrogates(job) if job else None

    def list_jobs(self) -> list:
        self._sync_with_disk_and_storage()
        return sorted([_clean_surrogates(j) for j in self.active_jobs.values()], key=lambda j: j.get("created_at", 0), reverse=True)

    def update_job(self, job_id: str, **kwargs):
        if job_id not in self.active_jobs:
            return
        job = self.active_jobs[job_id]
        for k, v in kwargs.items():
            job[k] = v
        job["last_updated_at"] = time.time()
        self.state_version += 1
        self._save_jobs_to_disk()

    def register_new_job(self, job_id: str, job_dict: dict):
        self.active_jobs[job_id] = job_dict
        self.state_version += 1
        self._save_jobs_to_disk()

    def start_task(self, job_id: str, coroutine):
        """Starts an asyncio task and stores a strong reference to prevent garbage collection."""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coroutine)
        except RuntimeError:
            loop = getattr(self, "_loop", None)
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(coroutine, loop)
                self._tasks[job_id] = future
                return future
            else:
                task = asyncio.create_task(coroutine)

        self._tasks[job_id] = task

        def _on_done(t):
            self._tasks.pop(job_id, None)
            if t.cancelled():
                print(f"[SUPERVISOR] Task for job {job_id} was cancelled.")
                self.update_job(job_id, status="cancelled", status_msg="Task was cancelled by user or system.")
            elif t.exception():
                err = t.exception()
                print(f"[SUPERVISOR] Task for job {job_id} raised unhandled exception: {err}")
                self.update_job(job_id, status="failed", error=str(err), status_msg=f"Error: {err}")
            else:
                print(f"[SUPERVISOR] Task for job {job_id} completed successfully.")

        task.add_done_callback(_on_done)
        return task

    def cancel_job(self, job_id: str) -> bool:
        if job_id not in self.active_jobs:
            return False
        
        # Cancel live task if running
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            self._tasks.pop(job_id, None)

        self.update_job(
            job_id,
            cancelled=True,
            status="cancelled",
            status_msg="Cancelled by user."
        )
        return True

    def start_watchdog(self):
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    async def _watchdog_loop(self):
        """Runs periodic health checks to reconcile any disconnected or hung jobs."""
        while True:
            await asyncio.sleep(4.0)
            try:
                await self.reconcile_state()
            except Exception as e:
                print(f"[SUPERVISOR WATCHDOG] Error: {e}")

    async def reconcile_state(self):
        """Checks for jobs that are in running state but whose tasks have terminated or ComfyUI is idle."""
        if not self.pipeline:
            return

        comfy_stat = await self.pipeline.check_comfy_status()
        q = comfy_stat.get("queue", {})
        # idle only when ComfyUI actually ANSWERED that its queue is empty: a slow or missing answer (a heavy render starves its web server) is "unknown", not idle
        is_comfy_idle = bool(comfy_stat.get("connected")) and bool(q.get("reachable")) and not q.get("busy", False) and q.get("pending_count", 0) == 0

        changed = False
        now = time.time()
        # how long ComfyUI has been CONTINUOUSLY idle: the gap between two shots (or after the last one, before the task has registered it) is a few
        # seconds of idle that must never count as a hung job
        self._idle_since = (getattr(self, "_idle_since", None) or now) if is_comfy_idle else None
        idle_for = now - self._idle_since if self._idle_since else 0.0

        for jid, job in self.active_jobs.items():
            status = job.get("status")
            if status in ("starting", "regenerating"):
                # a shot regeneration registers its task as "<job>_regen_<n>", the production run as "<job>"
                task = next((t for k, t in self._tasks.items() if (k == jid or k.startswith(f"{jid}_regen_")) and not t.done()), None)
                task_is_alive = task is not None

                # If no Python task is running for this job
                if not task_is_alive:
                    chunks = job.get("chunks", [])
                    if chunks:
                        job["status"] = "completed"
                        job["status_msg"] = f"Finished with {len(chunks)} completed scene chunks."
                    else:
                        job["status"] = "cancelled"
                        job["status_msg"] = "Interrupted (no active task)."
                    changed = True

                # If task is alive, but ComfyUI has been idle for > 45 seconds and step_progress hasn't moved
                elif is_comfy_idle and idle_for > 45.0:
                    last_up = job.get("last_updated_at", job.get("created_at", now))
                    if now - last_up > 45.0:
                        # Recheck if media was completed in outputs/
                        chunks = job.get("chunks", [])
                        if chunks:
                            job["status"] = "completed"
                            job["status_msg"] = f"Finished with {len(chunks)} scene chunks."
                        else:
                            job["status"] = "failed"
                            job["status_msg"] = "ComfyUI reported idle without output."
                        if task and not task.done():
                            task.cancel()
                        changed = True

        if changed:
            self.state_version += 1
            self._save_jobs_to_disk()

    async def get_unified_sync_state(self, client_version: int = 0, requested_job_id: str = None) -> dict:
        """Returns the atomic unified state for frontend synchronization."""
        comfy_stat = {"connected": False, "gpu": "Unknown", "vram_free_gb": 0, "vram_total_gb": 0, "queue": {"busy": False, "pending_count": 0}}
        if self.pipeline:
            comfy_stat = await self.pipeline.check_comfy_status()

        jobs_list = self.list_jobs()

        # Find actively running job if any (must have a live active task)
        running_job = None
        for j in jobs_list:
            if j.get("status") in ("starting", "regenerating"):
                task = self._tasks.get(j.get("id"))
                if task is not None and not (task.done() if hasattr(task, "done") else False):
                    running_job = j
                    break

        # Resolve active job
        active_job = None
        if requested_job_id and requested_job_id in self.active_jobs:
            active_job = self.active_jobs[requested_job_id]
        elif running_job:
            active_job = running_job
        elif jobs_list:
            # Prefer the latest job that actually has rendered clips/video
            with_clips = [j for j in jobs_list if j.get("chunks") or j.get("master_video")]
            active_job = with_clips[0] if with_clips else jobs_list[0]

        # Fast response if version matches and job/queue is idle
        is_dynamic = False
        if active_job and active_job.get("status") in ("starting", "regenerating"):
            is_dynamic = True
        if comfy_stat.get("queue", {}).get("busy", False) or comfy_stat.get("queue", {}).get("pending_count", 0) > 0:
            is_dynamic = True

        has_changed = (client_version != self.state_version) or is_dynamic

        # Build compact summary of jobs for the dropdown
        jobs_summary = [
            {
                "id": j["id"],
                "status": j.get("status", "unknown"),
                "prompt": (j.get("prompt") or "")[:40],
                "created_at": j.get("created_at", 0),
                "chunks_count": len(j.get("chunks", [])),
                "total_chunks": j.get("total_chunks", 3)
            }
            for j in jobs_list
        ]

        return {
            "version": self.state_version,
            "changed": has_changed,
            "comfy": comfy_stat,
            "active_job_id": active_job.get("id") if active_job else None,
            "active_job": active_job,
            "jobs_summary": jobs_summary
        }
