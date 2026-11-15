"""Settings page: where each local tool / model lives (engine/config/locations.py)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.config import locations
from engine.config.settings import settings

router = APIRouter(prefix="/api/system/locations", tags=["system"])


class LocationChanges(BaseModel):
    # key -> new value; null or "" resets that item to the environment variable / built-in default
    values: dict[str, str | None]


@router.get("")
def list_locations() -> dict:
    return {"items": locations.describe(settings.app_data_dir)}


@router.put("")
def save_locations(body: LocationChanges) -> dict:
    try:
        locations.save(settings.app_data_dir, body.values)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown location: {exc.args[0]}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"items": locations.describe(settings.app_data_dir)}
