"""Small, fail-closed ComfyUI API client used by PanelFlow diagnostics and jobs."""

from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from engine.security.paths import resolve_contained_path


class ComfyUIError(RuntimeError):
    """Raised when the configured ComfyUI endpoint cannot satisfy a request."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirect())
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ComfyUIClient:
    """Access only documented ComfyUI HTTP endpoints.

    The client deliberately does not infer model licenses or silently select a
    checkpoint. Workflow submission is exposed as a primitive for a future
    approved-workflow registry; the current API surface only exposes discovery.
    """

    def __init__(
        self,
        base_url: str | None = None,
        workflow_dir: str | Path | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        raw_url = base_url or os.environ.get("PANELFLOW_COMFYUI_URL", "http://127.0.0.1:8188")
        try:
            parsed = urlsplit(raw_url)
            valid_url = parsed.scheme in {"http", "https"} and bool(parsed.hostname)
        except ValueError as exc:
            raise ComfyUIError("PANELFLOW_COMFYUI_URL is malformed") from exc
        if not valid_url or parsed.username or parsed.password or parsed.fragment:
            raise ComfyUIError("PANELFLOW_COMFYUI_URL must be an http(s) URL without credentials or fragments")
        host = parsed.hostname.lower()
        allow_remote = os.environ.get("PANELFLOW_COMFYUI_ALLOW_REMOTE", "").lower() in {"1", "true", "yes"}
        allowed_remote_hosts = {
            item.strip().lower()
            for item in os.environ.get("PANELFLOW_COMFYUI_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        }
        if host not in _LOCAL_HOSTS:
            if not allow_remote or host not in allowed_remote_hosts:
                raise ComfyUIError("Remote ComfyUI endpoints require PANELFLOW_COMFYUI_ALLOW_REMOTE=true and an explicit PANELFLOW_COMFYUI_ALLOWED_HOSTS entry")
            try:
                remote_ip = ipaddress.ip_address(host)
            except ValueError as exc:
                raise ComfyUIError("Remote ComfyUI endpoints must use a public IP literal to prevent DNS rebinding") from exc
            if any((remote_ip.is_private, remote_ip.is_loopback, remote_ip.is_link_local, remote_ip.is_multicast, remote_ip.is_reserved, remote_ip.is_unspecified)):
                raise ComfyUIError("Remote ComfyUI endpoints must use a public IP address")
        self.base_url = raw_url.rstrip("/") + "/"
        self.timeout_s = timeout_s
        configured_workflow_dir = workflow_dir or os.environ.get("PANELFLOW_COMFYUI_WORKFLOW_DIR")
        self.workflow_dir = Path(configured_workflow_dir).expanduser() if configured_workflow_dir else None

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            request = Request(url, data=body, headers=headers, method=method)
            with _NO_REDIRECT_OPENER.open(request, timeout=self.timeout_s) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
                    raise ComfyUIError("ComfyUI response exceeded the configured size limit")
                chunks = []
                total = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise ComfyUIError("ComfyUI response exceeded the configured size limit")
                    chunks.append(chunk)
                raw = b"".join(chunks)
        except ComfyUIError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise ComfyUIError(f"ComfyUI request failed for {method} {path}: {exc}") from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ComfyUIError(f"ComfyUI returned non-JSON data for {method} {path}") from exc

    def system_stats(self) -> dict[str, Any]:
        result = self._request_json("/system_stats")
        return result if isinstance(result, dict) else {}

    def queue(self) -> dict[str, Any]:
        result = self._request_json("/queue")
        return result if isinstance(result, dict) else {}

    def node_catalog(self) -> dict[str, Any]:
        result = self._request_json("/object_info")
        return result if isinstance(result, dict) else {}

    def submit_prompt(self, workflow: Mapping[str, Any], client_id: str | None = None) -> str:
        """Submit an API-format workflow and return ComfyUI's prompt id.

        Callers must supply a workflow selected from PanelFlow's future approved
        registry; this method intentionally performs no model or node guessing.
        """
        if not workflow:
            raise ValueError("workflow must be a non-empty API-format mapping")
        payload: dict[str, Any] = {"prompt": dict(workflow)}
        if client_id:
            payload["client_id"] = client_id
        result = self._request_json("/prompt", method="POST", payload=payload)
        prompt_id = result.get("prompt_id") if isinstance(result, dict) else None
        if not prompt_id:
            raise ComfyUIError("ComfyUI accepted no prompt_id for the submitted workflow")
        return str(prompt_id)

    def history(self, prompt_id: str) -> dict[str, Any]:
        if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", prompt_id):
            raise ValueError("prompt_id must contain only letters, numbers, '_' or '-' and be at most 128 characters")
        result = self._request_json(f"/history/{prompt_id}")
        return result if isinstance(result, dict) else {}

    def _workflow_root(self) -> Path | None:
        if self.workflow_dir:
            return self.workflow_dir if self.workflow_dir.is_dir() and not self.workflow_dir.is_symlink() else None
        for candidate in (Path.home() / "ComfyUI" / "workflow", Path.home() / "claude" / "ComfyUI" / "workflow"):
            if candidate.is_dir() and not candidate.is_symlink():
                return candidate
        return None

    def api_workflow_root(self) -> Path | None:
        configured = os.environ.get("PANELFLOW_COMFYUI_API_WORKFLOW_DIR")
        if configured:
            root = Path(configured).expanduser()
            return root if root.is_dir() and not root.is_symlink() else None
        workflow_root = self._workflow_root()
        if workflow_root is None:
            return None
        candidate = workflow_root.parent / "workflows"
        return candidate if candidate.is_dir() and not candidate.is_symlink() else None

    def download_output(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ValueError("filename must be a single output filename")
        if not isinstance(subfolder, str):
            raise ValueError("subfolder must be a safe relative path")
        subfolder_path = Path(subfolder)
        if (subfolder_path.is_absolute() or PureWindowsPath(subfolder).drive
                or subfolder.startswith(("/", "\\"))
                or any(part in {"", ".", ".."} for part in subfolder_path.parts)):
            raise ValueError("subfolder must be a safe relative path")
        if folder_type != "output":
            raise ValueError("folder_type must be output")
        query = urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
        url = urljoin(self.base_url, "view") + "?" + query
        try:
            with _NO_REDIRECT_OPENER.open(Request(url, headers={"Accept": "image/*,application/octet-stream"}), timeout=self.timeout_s) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
                    raise ComfyUIError("ComfyUI output exceeded the configured size limit")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise ComfyUIError("ComfyUI output exceeded the configured size limit")
                    chunks.append(chunk)
                return b"".join(chunks)
        except ComfyUIError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise ComfyUIError(f"ComfyUI output retrieval failed for {filename}: {exc}") from exc

    def discover_workflows(self) -> list[str]:
        root = self._workflow_root()
        if root is None:
            return []
        try:
            return sorted(
                str(path.relative_to(root)).replace(os.sep, "/")
                for path in root.rglob("*.json")
                if self._is_discoverable_file(root, path)
            )[:500]
        except OSError:
            return []

    def discover_models(self) -> dict[str, list[str]]:
        root = self._workflow_root()
        if root is None:
            return {}
        models_root = root.parent / "models"
        if not models_root.is_dir() or models_root.is_symlink():
            return {}
        result: dict[str, list[str]] = {}
        for category in ("checkpoints", "diffusion_models", "unet", "vae", "loras", "controlnet", "clip", "text_encoders"):
            category_dir = models_root / category
            if category_dir.is_dir() and not category_dir.is_symlink():
                try:
                    result[category] = sorted(
                        str(path.relative_to(category_dir)).replace(os.sep, "/")
                        for path in category_dir.rglob("*")
                        if self._is_discoverable_file(category_dir, path)
                    )[:500]
                except OSError:
                    result[category] = []
        return result

    @staticmethod
    def _is_discoverable_file(root: Path, path: Path) -> bool:
        try:
            resolve_contained_path(root, path, must_be_file=True)
            return True
        except (ValueError, FileNotFoundError, OSError):
            return False

    def capabilities(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "available": False,
            "endpoint": self.base_url.rstrip("/"),
            "workflow_dir": str(self._workflow_root()) if self._workflow_root() else None,
            "workflow_files": self.discover_workflows(),
            "models": self.discover_models(),
            "errors": [],
        }
        try:
            stats = self.system_stats()
            result["system"] = stats
            result["available"] = True
            system = stats.get("system", {}) if isinstance(stats, dict) else {}
            result["version"] = system.get("comfyui_version")
            result["device"] = system.get("device")
        except ComfyUIError as exc:
            result["errors"].append(str(exc))

        if result["available"]:
            try:
                queue = self.queue()
                result["queue"] = {
                    "running": len(queue.get("queue_running", [])),
                    "pending": len(queue.get("queue_pending", [])),
                }
            except ComfyUIError as exc:
                result["errors"].append(str(exc))
            try:
                nodes = self.node_catalog()
                result["node_count"] = len(nodes)
                result["node_names"] = sorted(nodes)
            except ComfyUIError as exc:
                result["errors"].append(str(exc))
        return result
