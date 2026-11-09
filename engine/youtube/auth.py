"""Google OAuth 2.0 for a desktop app: loopback redirect + PKCE, refresh-token storage, nothing sent anywhere but Google.

The user supplies their own OAuth client (Google Cloud project with the YouTube Data API enabled). The client id/secret and the
tokens live in the app-data config folder; the API never returns them, and they are never logged.
Supports multiple YouTube channels with an active channel concept, scheduler slot times, and agent upload permissions.
Credentials and tokens are encoded when persisted to protect secrets from being stored as plain text.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from engine.config.settings import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPE = "https://www.googleapis.com/auth/youtube"  # upload + edit own videos (release time of scheduled releases); was youtube.upload, which cannot change a video after upload
FLOW_TIMEOUT_SEC = 300


class AuthError(RuntimeError):
    pass


def _config_dir() -> Path:
    d = settings.app_data_dir / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_private(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)  # no-op on Windows, where the profile folder's ACL already limits access
    except OSError:
        pass
    tmp.replace(path)


def _encode_secret(val: str | None) -> str:
    """Encodes a secret string so it is not stored in plain text."""
    if not val:
        return ""
    if val.startswith("enc:v1:"):
        return val
    b64 = base64.b64encode(val.encode("utf-8")).decode("ascii")
    return f"enc:v1:{b64}"


def _decode_secret(val: str | None) -> str:
    """Decodes an encoded secret string transparently; supports legacy plain text."""
    if not val:
        return ""
    if val.startswith("enc:v1:"):
        raw = val[len("enc:v1:"):]
        try:
            return base64.b64decode(raw.encode("ascii")).decode("utf-8")
        except Exception:
            return val
    return val


def parse_client_file(raw: dict | str) -> tuple[str, str]:
    """Extracts client_id and client_secret from a Google Cloud OAuth client JSON file or dict."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception as e:
            raise AuthError(f"invalid JSON file: {e}")
    elif isinstance(raw, dict):
        data = raw
    else:
        raise AuthError("expected JSON string or dictionary")

    source = data.get("installed") or data.get("web") or data
    client_id = source.get("client_id") or ""
    client_secret = source.get("client_secret") or ""
    if not isinstance(client_id, str) or not isinstance(client_secret, str) or not client_id.strip() or not client_secret.strip():
        raise AuthError("Google OAuth JSON must contain non-empty 'client_id' and 'client_secret'")
    return client_id.strip(), client_secret.strip()


class OAuthStore:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or _config_dir()
        self.client_file = self.dir / "youtube_client.json"
        self.token_file = self.dir / "youtube_tokens.json"
        self.registry_file = self.dir / "youtube_channels.json"

    def _channel_key(self, channel_id: str | None) -> str:
        key = (channel_id or self.get_active_channel_id()).strip()
        return key or "default"

    def _token_path(self, channel_id: str | None = None) -> Path:
        key = self._channel_key(channel_id)
        if key == "default":
            return self.token_file
        return self.dir / f"youtube_tokens_{key}.json"

    def _client_path(self, channel_id: str | None = None) -> Path:
        key = self._channel_key(channel_id)
        if key == "default":
            return self.client_file
        custom = self.dir / f"youtube_client_{key}.json"
        return custom if custom.exists() else self.client_file

    def _read_registry(self) -> dict:
        if self.registry_file.exists():
            try:
                return json.loads(self.registry_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "active_channel_id": "default",
            "channels": {
                "default": {"id": "default", "name": "Primary Channel", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            },
            "agent_settings": {
                "enabled": True,
                "default_privacy": "private",
                "publish_time": "18:00",
                "lead_time_min": 20,
            }
        }

    def _save_registry(self, reg: dict) -> None:
        _write_private(self.registry_file, reg)

    def get_active_channel_id(self) -> str:
        reg = self._read_registry()
        active = reg.get("active_channel_id", "default")
        channels = reg.get("channels", {})
        if active not in channels and channels:
            active = next(iter(channels))
        return active or "default"

    def set_active_channel(self, channel_id: str) -> None:
        reg = self._read_registry()
        cid = channel_id.strip()
        if cid not in reg.get("channels", {}):
            raise AuthError(f"channel '{cid}' not found")
        reg["active_channel_id"] = cid
        self._save_registry(reg)

    def list_channels(self) -> list[dict]:
        reg = self._read_registry()
        active_id = self.get_active_channel_id()
        out = []
        for cid, info in reg.get("channels", {}).items():
            t_path = self._token_path(cid)
            c_path = self._client_path(cid)
            tokens = self.tokens(channel_id=cid) if t_path.exists() else None
            client = self.client(channel_id=cid) if c_path.exists() else None
            out.append({
                "id": cid,
                "name": info.get("name", cid),
                "is_active": cid == active_id,
                "connected": bool(tokens and tokens.get("refresh_token")),
                "configured": client is not None,
                "created_at": info.get("created_at"),
            })
        return out

    def create_channel(self, name: str, channel_id: str | None = None) -> dict:
        name = name.strip()
        if not name:
            raise AuthError("channel name is required")
        reg = self._read_registry()
        cid = (channel_id or re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower())).strip()
        if not cid:
            cid = f"ch_{int(time.time())}"
        reg.setdefault("channels", {})
        item = {
            "id": cid,
            "name": name,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        reg["channels"][cid] = item
        self._save_registry(reg)
        return item

    def delete_channel(self, channel_id: str) -> None:
        cid = channel_id.strip()
        reg = self._read_registry()
        if cid not in reg.get("channels", {}):
            return
        if len(reg.get("channels", {})) <= 1:
            raise AuthError("cannot delete the only configured channel")
        del reg["channels"][cid]
        if reg.get("active_channel_id") == cid:
            reg["active_channel_id"] = next(iter(reg["channels"]))
        self._save_registry(reg)
        self._token_path(cid).unlink(missing_ok=True)
        if cid != "default":
            (self.dir / f"youtube_client_{cid}.json").unlink(missing_ok=True)

    def get_agent_settings(self) -> dict:
        reg = self._read_registry()
        return reg.get("agent_settings", {
            "enabled": True,
            "default_privacy": "private",
            "publish_time": "18:00",
            "lead_time_min": 20,
        })

    def update_agent_settings(
        self,
        enabled: bool,
        default_privacy: str = "private",
        publish_time: str = "18:00",
        lead_time_min: int = 20,
    ) -> dict:
        if default_privacy not in {"private", "unlisted", "public"}:
            raise AuthError("invalid default privacy for agents")
        reg = self._read_registry()
        reg["agent_settings"] = {
            "enabled": bool(enabled),
            "default_privacy": default_privacy,
            "publish_time": (publish_time or "18:00").strip(),
            "lead_time_min": max(20, int(lead_time_min or 20)),
        }
        self._save_registry(reg)
        return reg["agent_settings"]

    def set_client(self, client_id: str, client_secret: str, channel_id: str | None = None) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise AuthError("client id and client secret are both required")
        key = self._channel_key(channel_id)
        path = self.client_file if key == "default" else (self.dir / f"youtube_client_{key}.json")
        _write_private(path, {"client_id": client_id.strip(), "client_secret": _encode_secret(client_secret.strip())})

    def client(self, channel_id: str | None = None) -> dict | None:
        path = self._client_path(channel_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if "client_secret" in data:
            data["client_secret"] = _decode_secret(data["client_secret"])
        return data

    def save_tokens(self, tokens: dict, channel_id: str | None = None) -> None:
        old = self.tokens(channel_id=channel_id) or {}
        ref = tokens.get("refresh_token") or old.get("refresh_token")
        keep = {
            "refresh_token": _encode_secret(ref) if ref else None,
            "access_token": _encode_secret(tokens["access_token"]),
            "expires_at": time.time() + int(tokens.get("expires_in", 3600)),
            "scope": tokens.get("scope", SCOPE)
        }
        _write_private(self._token_path(channel_id), keep)

    def tokens(self, channel_id: str | None = None) -> dict | None:
        path = self._token_path(channel_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("refresh_token"):
            data["refresh_token"] = _decode_secret(data["refresh_token"])
        if data.get("access_token"):
            data["access_token"] = _decode_secret(data["access_token"])
        return data

    def clear_tokens(self, channel_id: str | None = None) -> None:
        self._token_path(channel_id).unlink(missing_ok=True)


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


class YouTubeAuth:
    def __init__(self, store: OAuthStore | None = None, http: httpx.Client | None = None):
        self.store = store or OAuthStore()
        self.http = http or httpx.Client(timeout=30)
        self._pending: dict | None = None

    # ---- status -------------------------------------------------------------------------------------------------------
    def status(self, channel_id: str | None = None) -> dict:
        t = self.store.tokens(channel_id=channel_id)
        active_id = channel_id or self.store.get_active_channel_id()
        is_pending = bool(self._pending and not self._pending.get("done") and self._pending.get("channel_id") == active_id)
        err = (self._pending or {}).get("error") if (self._pending and self._pending.get("channel_id") == active_id) else None
        return {"configured": self.store.client(channel_id=channel_id) is not None, "connected": bool(t and t.get("refresh_token")),
                "pending": is_pending, "error": err}

    def masked_client_id(self, channel_id: str | None = None) -> str:
        c = self.store.client(channel_id=channel_id)
        if not c or not c.get("client_id"):
            return ""
        cid = c["client_id"]
        if len(cid) > 16:
            return f"{cid[:8]}...{cid[-8:]}"
        return cid

    def full_status(self, channel_id: str | None = None) -> dict:
        base = self.status(channel_id=channel_id)
        base["active_channel_id"] = self.store.get_active_channel_id()
        base["masked_client_id"] = self.masked_client_id(channel_id=channel_id)
        base["channels"] = self.store.list_channels()
        base["agent_settings"] = self.store.get_agent_settings()
        return base

    # ---- authorisation flow -------------------------------------------------------------------------------------------
    def begin(self, channel_id: str | None = None) -> str:
        """Start a loopback listener and return the Google consent URL for the user to open."""
        target_channel = channel_id or self.store.get_active_channel_id()
        client = self.store.client(channel_id=target_channel)
        if client is None:
            raise AuthError("save the OAuth client id and secret first")
        if self._pending and not self._pending.get("done"):
            self._pending["server"].shutdown()
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        flow: dict = {"state": state, "verifier": verifier, "done": False, "error": None, "channel_id": target_channel}
        auth = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                q = parse_qs(urlparse(self.path).query)
                if urlparse(self.path).path != "/oauth2callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                msg = "You can close this window and return to PanelFlow Studio."
                if q.get("state", [""])[0] != flow["state"]:
                    flow["error"], msg = "state mismatch", "Authorisation failed (state mismatch)."
                elif "error" in q:
                    flow["error"], msg = q["error"][0], f"Authorisation failed: {q['error'][0]}"
                else:
                    try:
                        auth._exchange(q["code"][0], flow["verifier"], flow["redirect_uri"], channel_id=flow["channel_id"])
                    except Exception as e:  # shown in status(), never the secret
                        flow["error"], msg = str(e)[:200], "Authorisation failed."
                flow["done"] = True
                flow["timer"].cancel()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(msg.encode())
                threading.Thread(target=flow["server"].shutdown, daemon=True).start()

            def log_message(self, *a):  # keep the one-time code out of logs
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        flow["server"], flow["redirect_uri"] = server, f"http://127.0.0.1:{server.server_port}/oauth2callback"
        self._pending = flow
        threading.Thread(target=server.serve_forever, daemon=True).start()
        timer = threading.Timer(FLOW_TIMEOUT_SEC, lambda: (flow.update(done=True, error=flow["error"] or "timed out"), server.shutdown()))
        timer.daemon = True  # must not keep the process alive for the whole timeout
        flow["timer"] = timer
        timer.start()
        return AUTH_URL + "?" + urlencode({
            "client_id": client["client_id"], "redirect_uri": flow["redirect_uri"], "response_type": "code", "scope": SCOPE,
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent select_account"})

    def _exchange(self, code: str, verifier: str, redirect_uri: str, channel_id: str | None = None) -> None:
        c = self.store.client(channel_id=channel_id)
        r = self.http.post(TOKEN_URL, data={"code": code, "client_id": c["client_id"], "client_secret": c["client_secret"],
                                            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier})
        if r.status_code != 200:
            raise AuthError(f"token exchange failed ({r.status_code}): {r.json().get('error_description', r.json().get('error', ''))}")
        body = r.json()
        if not body.get("refresh_token"):
            raise AuthError("Google returned no refresh token; remove the app's access in your Google account and connect again")
        self.store.save_tokens(body, channel_id=channel_id)

    # ---- tokens ---------------------------------------------------------------------------------------------------------
    def access_token(self, channel_id: str | None = None) -> str:
        t = self.store.tokens(channel_id=channel_id)
        if not t or not t.get("refresh_token"):
            raise AuthError("YouTube is not connected")
        if t.get("access_token") and t.get("expires_at", 0) - 60 > time.time():
            return t["access_token"]
        c = self.store.client(channel_id=channel_id)
        if c is None:
            raise AuthError("OAuth client is not configured")
        r = self.http.post(TOKEN_URL, data={"client_id": c["client_id"], "client_secret": c["client_secret"],
                                            "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise AuthError(f"token refresh failed ({r.status_code}): {r.json().get('error', '')}; connect YouTube again")
        self.store.save_tokens(r.json(), channel_id=channel_id)
        return r.json()["access_token"]

    def disconnect(self, channel_id: str | None = None) -> None:
        t = self.store.tokens(channel_id=channel_id)
        if t and t.get("refresh_token"):
            try:
                self.http.post(REVOKE_URL, data={"token": t["refresh_token"]})
            except httpx.HTTPError:
                pass  # revoking is best effort; the local tokens are removed either way
        self.store.clear_tokens(channel_id=channel_id)
