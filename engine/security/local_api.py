"""Authentication and browser-boundary checks for the loopback API."""

from __future__ import annotations

import hmac
import os
from collections.abc import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

ENGINE_TOKEN_ENV = "PANELFLOW_ENGINE_TOKEN"
INSECURE_LOCAL_API_ENV = "PANELFLOW_ALLOW_INSECURE_LOCAL_API"
TOKEN_HEADER = "X-PanelFlow-Token"
RESOURCE_TOKEN_MARKER = ";pf-token="

_DEFAULT_DESKTOP_ORIGINS = frozenset(
    {
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    }
)


def configured_origins() -> set[str]:
    origins = set(_DEFAULT_DESKTOP_ORIGINS)
    extra = os.getenv("PANELFLOW_ALLOWED_ORIGINS", "")
    origins.update(origin.strip() for origin in extra.split(",") if origin.strip())
    return origins


def insecure_local_api_enabled() -> bool:
    return os.getenv(INSECURE_LOCAL_API_ENV, "").strip().lower() in {"1", "true", "yes"}


class LocalApiSecurityMiddleware(BaseHTTPMiddleware):
    """Fail closed on DNS rebinding, hostile browser origins, and missing tokens."""

    def __init__(
        self,
        app,
        *,
        engine_token: str,
        allowed_origins: Iterable[str],
        api_port: int,
        allow_insecure: bool = False,
    ) -> None:
        super().__init__(app)
        self.engine_token = engine_token
        self.allowed_origins = frozenset(allowed_origins)
        self.allowed_hosts = frozenset(
            {
                f"127.0.0.1:{api_port}",
                f"localhost:{api_port}",
                f"[::1]:{api_port}",
            }
        )
        self.allow_insecure = allow_insecure

    async def dispatch(self, request: Request, call_next):
        if self.allow_insecure:
            return await call_next(request)

        if request.headers.get("host", "").lower() not in self.allowed_hosts:
            return JSONResponse({"detail": "Invalid Host header."}, status_code=400)

        origin = request.headers.get("origin")
        if origin is not None and origin not in self.allowed_origins:
            return JSONResponse({"detail": "Origin is not allowed."}, status_code=403)

        path = request.url.path
        resource_token = ""
        if request.method in {"GET", "HEAD"} and RESOURCE_TOKEN_MARKER in path:
            clean_path, resource_token = path.rsplit(RESOURCE_TOKEN_MARKER, 1)
            if "/" not in resource_token and self._is_resource_path(clean_path):
                request.scope["path"] = clean_path
                request.scope["raw_path"] = clean_path.encode("ascii")
                path = clean_path

        if path == "/api/system/health":
            response = await call_next(request)
            response.headers["Referrer-Policy"] = "no-referrer"
            return response

        # Browsers do not send application headers on the CORS preflight itself.
        if request.method == "OPTIONS" and origin in self.allowed_origins:
            return await call_next(request)

        supplied = request.headers.get(TOKEN_HEADER, "") or resource_token
        if not self.engine_token or not hmac.compare_digest(supplied, self.engine_token):
            return JSONResponse(
                {"detail": "Missing or invalid local engine token."},
                status_code=401,
                headers={"WWW-Authenticate": "PanelFlowToken"},
            )

        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @staticmethod
    def _is_resource_path(path: str) -> bool:
        return (
            path.endswith(("/file", "/normalized-file", "/output", "/contact-sheet"))
            or "/samples/" in path
            or path == "/api/render/events"
        )
