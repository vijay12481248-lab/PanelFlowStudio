"""YouTube connection endpoints. Secrets go in, only booleans and channel profiles come out."""
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engine.youtube.auth import AuthError, YouTubeAuth, parse_client_file

router = APIRouter(prefix="/api/youtube", tags=["youtube"])
auth = YouTubeAuth()


class ClientRequest(BaseModel):
    client_id: str = Field(min_length=10, max_length=300)
    client_secret: str = Field(min_length=4, max_length=300)
    channel_id: str | None = None


class ClientFileRequest(BaseModel):
    content: Any  # JSON string or parsed dictionary
    channel_id: str | None = None


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    channel_id: str | None = None


class DisconnectRequest(BaseModel):
    channel_id: str | None = None


class AgentSettingsRequest(BaseModel):
    enabled: bool
    default_privacy: str = "private"
    publish_time: str = "18:00"
    lead_time_min: int = 20


@router.put("/client")
def save_client(req: ClientRequest):
    try:
        auth.store.set_client(req.client_id, req.client_secret, channel_id=req.channel_id)
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return auth.status(channel_id=req.channel_id)


@router.post("/client/file")
def upload_client_file(req: ClientFileRequest):
    """Parses a Google Cloud OAuth client_secret_*.json file and stores the credentials."""
    try:
        client_id, client_secret = parse_client_file(req.content)
        auth.store.set_client(client_id, client_secret, channel_id=req.channel_id)
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return auth.full_status(channel_id=req.channel_id)


@router.get("/status")
def status(channel_id: str | None = Query(default=None)):
    return auth.full_status(channel_id=channel_id)


@router.post("/connect")
def connect(channel_id: str | None = Query(default=None)):
    """Returns the Google consent URL; open it in a browser, approve, and poll /status until connected."""
    try:
        return {"auth_url": auth.begin(channel_id=channel_id)}
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/disconnect")
def disconnect(req: DisconnectRequest | None = None, channel_id: str | None = Query(default=None)):
    target_channel = (req.channel_id if req else None) or channel_id
    auth.disconnect(channel_id=target_channel)
    return auth.full_status(channel_id=target_channel)


@router.get("/channels")
def list_channels():
    """Lists all configured YouTube channels and which is active."""
    return {
        "channels": auth.store.list_channels(),
        "active_channel_id": auth.store.get_active_channel_id(),
    }


@router.post("/channels")
def create_channel(req: CreateChannelRequest):
    """Adds a new channel profile (e.g. 'Anime Reviews', 'Manga Recaps')."""
    try:
        created = auth.store.create_channel(req.name, channel_id=req.channel_id)
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"created": created, "status": auth.full_status(channel_id=created["id"])}


@router.post("/channels/{channel_id}/activate")
def activate_channel(channel_id: str):
    """Sets this channel profile as the active channel for uploads and agent tasks."""
    try:
        auth.store.set_active_channel(channel_id)
    except AuthError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return auth.full_status(channel_id=channel_id)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str):
    """Deletes a channel profile and removes its stored credentials."""
    try:
        auth.store.delete_channel(channel_id)
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return auth.full_status()


@router.get("/agent-settings")
def get_agent_settings():
    """Returns agent upload permissions and default privacy settings."""
    return auth.store.get_agent_settings()


@router.put("/agent-settings")
def update_agent_settings(req: AgentSettingsRequest):
    """Updates whether agents are permitted to upload and their default privacy."""
    try:
        updated = auth.store.update_agent_settings(
            req.enabled,
            default_privacy=req.default_privacy,
            publish_time=req.publish_time,
            lead_time_min=req.lead_time_min,
        )
    except AuthError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return updated
