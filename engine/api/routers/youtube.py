"""YouTube connection endpoints. Secrets go in, only booleans come out."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.youtube.auth import AuthError, YouTubeAuth

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
auth = YouTubeAuth()


class ClientRequest(BaseModel):
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str = Field(min_length=4, max_length=300)


@router.put("/client")
def save_client(req: ClientRequest):
    try:
        auth.store.set_client(req.client_id, req.client_secret)
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return auth.status()


@router.get("/status")
def status():
    return auth.status()


@router.post("/connect")
def connect():
    """Returns the Google consent URL; open it in a browser, approve, and poll /status until connected."""
    try:
        return {"auth_url": auth.begin()}
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/disconnect")
def disconnect():
    auth.disconnect()
    return auth.status()
