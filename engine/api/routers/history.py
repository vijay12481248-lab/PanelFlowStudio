"""Authenticated by the same local API middleware as every project endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from engine.database.session import get_db
from engine.history.contracts import HistoryFault
from engine.history.service import project_history

router = APIRouter(prefix="/api/projects/{project_id}/history", tags=["history"])


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=36, max_length=36)
    expected_revision: int = Field(ge=0, strict=True)


class Command(Operation):
    type: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1, strict=True)
    label: str = Field(min_length=1, max_length=120)
    input: dict


class Reset(Operation):
    fingerprint: str = Field(min_length=64, max_length=64)


def respond(operation):
    try:
        return operation()
    except HistoryFault as error:
        raise HTTPException(status_code=error.status, detail={"code": error.code, "message": str(error)}) from error


@router.get("")
def read_history(project_id: str, db: Session = Depends(get_db)):
    return respond(lambda: project_history.read(db, project_id))


@router.post("/commands")
def execute_history(project_id: str, request: Command, db: Session = Depends(get_db)):
    return respond(lambda: project_history.execute(db, project_id, operation_id=request.operation_id,
        expected_revision=request.expected_revision, command_type=request.type, version=request.version,
        label=request.label, input=request.input))


@router.post("/undo")
def undo_history(project_id: str, request: Operation, db: Session = Depends(get_db)):
    return respond(lambda: project_history.move(db, project_id, direction="undo", **request.model_dump()))


@router.post("/redo")
def redo_history(project_id: str, request: Operation, db: Session = Depends(get_db)):
    return respond(lambda: project_history.move(db, project_id, direction="redo", **request.model_dump()))


@router.post("/reset")
def reset_history(project_id: str, request: Reset, db: Session = Depends(get_db)):
    return respond(lambda: project_history.reset(db, project_id, **request.model_dump()))
