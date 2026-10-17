from fastapi import APIRouter, HTTPException, status
from engine.jobs.manager import job_manager
from engine.api.schemas import JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

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

@router.get("/project/{project_id}", response_model=list[JobResponse])
def list_project_jobs(project_id: str):
    return job_manager.list_project_jobs(project_id)
