"""Bridge between PanelFlow MCP tools and the local FastAPI engine."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import aiohttp

DEFAULT_ENGINE_URL = os.environ.get("PANELFLOW_API_URL", "http://127.0.0.1:8765")


def get_engine_token() -> str:
    # 1. Environment variable
    token = os.environ.get("PANELFLOW_ENGINE_TOKEN", "").strip()
    if token:
        return token

    # 2. Local AppData
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        token_path = Path(local_app_data) / "PanelFlow Studio" / "engine.token"
        if token_path.exists():
            try:
                t = token_path.read_text(encoding="utf-8").strip()
                if t:
                    return t
            except Exception:
                pass

    # 3. Project root file .engine_token
    root_token = Path(__file__).resolve().parents[2] / ".engine_token"
    if root_token.exists():
        try:
            t = root_token.read_text(encoding="utf-8").strip()
            if t:
                return t
        except Exception:
            pass

    return ""


class EngineBridge:
    def __init__(self, base_url: str = DEFAULT_ENGINE_URL):
        self.base_url = base_url.rstrip("/")

    def get_headers(self) -> dict[str, str]:
        token = get_engine_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token:
            headers["X-PanelFlow-Token"] = token
            headers["X-PanelFlow-Control"] = "1"
        return headers

    async def get(self, endpoint: str, timeout_s: float = 30.0) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"Engine GET {endpoint} returned {resp.status}: {text}")
                return await resp.json()

    async def post(self, endpoint: str, json_data: dict[str, Any] | None = None, timeout_s: float = 60.0) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            async with session.post(url, json=json_data or {}, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"Engine POST {endpoint} returned {resp.status}: {text}")
                return await resp.json()

    async def put(self, endpoint: str, json_data: dict[str, Any] | None = None, timeout_s: float = 60.0) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            async with session.put(url, json=json_data or {}, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"Engine PUT {endpoint} returned {resp.status}: {text}")
                return await resp.json()

    async def delete(self, endpoint: str, timeout_s: float = 30.0) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            async with session.delete(url, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise RuntimeError(f"Engine DELETE {endpoint} returned {resp.status}: {text}")
                return await resp.json()


bridge = EngineBridge()
