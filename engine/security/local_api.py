"""Authentication and browser-boundary checks for the loopback API."""

from __future__ import annotations

import hmac
import os
import urllib.parse
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
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        "http://[::1]:8765",
        "http://localhost:7860",
        "http://127.0.0.1:7860",
        "http://[::1]:7860",
        "null",
    }
)


def is_allowed_local_origin(origin: str | None, allowed_origins: frozenset[str] | set[str] = _DEFAULT_DESKTOP_ORIGINS) -> bool:
    """Return True if the origin is a trusted local origin or explicitly allowed."""
    if not origin:
        return True
    if origin in allowed_origins or origin == "null":
        return True
    try:
        parsed = urllib.parse.urlparse(origin)
        if parsed.scheme in {"http", "https"}:
            host = parsed.hostname or ""
            if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
                return True
        elif parsed.scheme == "tauri":
            return True
    except Exception:
        pass
    return False


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

    def _is_origin_allowed(self, origin: str | None) -> bool:
        return is_allowed_local_origin(origin, self.allowed_origins)

    async def dispatch(self, request: Request, call_next):
        if self.allow_insecure:
            return await call_next(request)

        if request.headers.get("host", "").lower() not in self.allowed_hosts:
            return JSONResponse({"detail": "Invalid Host header."}, status_code=400)

        origin = request.headers.get("origin")
        if origin is not None and not self._is_origin_allowed(origin):
            return JSONResponse({"detail": "Origin is not allowed."}, status_code=403)

        path = request.url.path
        resource_token = ""
        if request.method in {"GET", "HEAD"} and RESOURCE_TOKEN_MARKER in path:
            clean_path, resource_token = path.rsplit(RESOURCE_TOKEN_MARKER, 1)
            if "/" not in resource_token and self._is_resource_path(clean_path):
                request.scope["path"] = clean_path
                request.scope["raw_path"] = clean_path.encode("ascii")
                path = clean_path

        if request.method in {"GET", "HEAD"} and path in {
            "/api/system/health",
            "/chronoflow/ui",
            "/chronoflow",
            "/api/chronoflow/ui",
        }:
            response = await call_next(request)
            response.headers["Referrer-Policy"] = "no-referrer"
            return response

        # Browsers do not send application headers on the CORS preflight itself.
        if request.method == "OPTIONS" and self._is_origin_allowed(origin):
            return await call_next(request)

        query_token = request.query_params.get("token") or request.query_params.get("pf-token") or ""
        supplied = request.headers.get(TOKEN_HEADER, "") or resource_token or query_token
        if not supplied and request.headers.get("Authorization", "").startswith("Bearer "):
            supplied = request.headers.get("Authorization", "").split(" ", 1)[1].strip()
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
            path.endswith(("/file", "/normalized-file", "/output", "/contact-sheet", "/cover", "/text-blur-preview"))
            or "/samples/" in path
            or "/chronoflow/" in path
            or path.startswith(("/outputs/", "/inputs/"))
            or path == "/api/render/events"
        )
