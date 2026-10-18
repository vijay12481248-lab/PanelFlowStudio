from typing import Optional
from fastapi import APIRouter, HTTPException, status, Query
from engine.jobs.manager import job_manager
from engine.api.schemas import JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("", response_model=list[JobResponse])
def list_all_jobs(
    status: Optional[str] = Query(None, description="Filter by status (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    limit: int = Query(50, ge=1, le=200, description="Max jobs to return"),
):
    """Lists jobs across all projects with optional status/project filters."""
    return job_manager.list_all_jobs(status=status, project_id=project_id, limit=limit)

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    cancelled = job_manager.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not active or could not be cancelled"
        )
    return {"status": "CANCELLED", "message": "Cancellation signal sent to job"}

@router.post("/{job_id}/retry")
def retry_job(job_id: str):
    """Re-queues a failed or cancelled job for execution."""
    retried = job_manager.retry_job(job_id)
    if not retried:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found or could not be re-queued"
        )
    return {"status": "QUEUED", "message": f"Job {job_id} re-queued for execution"}

@router.get("/project/{project_id}", response_model=list[JobResponse])
def list_project_jobs(project_id: str):
    return job_manager.list_project_jobs(project_id)

