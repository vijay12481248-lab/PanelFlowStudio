"""Google OAuth 2.0 for a desktop app: loopback redirect + PKCE, refresh-token storage, nothing sent anywhere but Google.

The user supplies their own OAuth client (Google Cloud project with the YouTube Data API enabled). The client id/secret and the
tokens live in the app-data config folder; the API never returns them, and they are never logged.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
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
SCOPE = "https://www.googleapis.com/auth/youtube.upload"  # upload only: the app cannot read or delete anything on the channel
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


class OAuthStore:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or _config_dir()
        self.client_file = self.dir / "youtube_client.json"
        self.token_file = self.dir / "youtube_tokens.json"

    def set_client(self, client_id: str, client_secret: str) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise AuthError("client id and client secret are both required")
        _write_private(self.client_file, {"client_id": client_id.strip(), "client_secret": client_secret.strip()})

    def client(self) -> dict | None:
        return json.loads(self.client_file.read_text(encoding="utf-8")) if self.client_file.exists() else None

    def save_tokens(self, tokens: dict) -> None:
        old = self.tokens() or {}
        keep = {"refresh_token": tokens.get("refresh_token") or old.get("refresh_token"),
                "access_token": tokens["access_token"], "expires_at": time.time() + int(tokens.get("expires_in", 3600)),
                "scope": tokens.get("scope", SCOPE)}
        _write_private(self.token_file, keep)

    def tokens(self) -> dict | None:
        return json.loads(self.token_file.read_text(encoding="utf-8")) if self.token_file.exists() else None

    def clear_tokens(self) -> None:
        self.token_file.unlink(missing_ok=True)


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
    def status(self) -> dict:
        t = self.store.tokens()
        return {"configured": self.store.client() is not None, "connected": bool(t and t.get("refresh_token")),
                "pending": bool(self._pending and not self._pending.get("done")), "error": (self._pending or {}).get("error")}

    # ---- authorisation flow -------------------------------------------------------------------------------------------
    def begin(self) -> str:
        """Start a loopback listener and return the Google consent URL for the user to open."""
        client = self.store.client()
        if client is None:
            raise AuthError("save the OAuth client id and secret first")
        if self._pending and not self._pending.get("done"):
            self._pending["server"].shutdown()
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        flow: dict = {"state": state, "verifier": verifier, "done": False, "error": None}
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
                        auth._exchange(q["code"][0], flow["verifier"], flow["redirect_uri"])
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
            "state": state, "code_challenge": challenge, "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent"})

    def _exchange(self, code: str, verifier: str, redirect_uri: str) -> None:
        c = self.store.client()
        r = self.http.post(TOKEN_URL, data={"code": code, "client_id": c["client_id"], "client_secret": c["client_secret"],
                                            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier})
        if r.status_code != 200:
            raise AuthError(f"token exchange failed ({r.status_code}): {r.json().get('error_description', r.json().get('error', ''))}")
        body = r.json()
        if not body.get("refresh_token"):
            raise AuthError("Google returned no refresh token; remove the app's access in your Google account and connect again")
        self.store.save_tokens(body)

    # ---- tokens ---------------------------------------------------------------------------------------------------------
    def access_token(self) -> str:
        t = self.store.tokens()
        if not t or not t.get("refresh_token"):
            raise AuthError("YouTube is not connected")
        if t.get("access_token") and t.get("expires_at", 0) - 60 > time.time():
            return t["access_token"]
        c = self.store.client()
        if c is None:
            raise AuthError("OAuth client is not configured")
        r = self.http.post(TOKEN_URL, data={"client_id": c["client_id"], "client_secret": c["client_secret"],
                                            "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise AuthError(f"token refresh failed ({r.status_code}): {r.json().get('error', '')}; connect YouTube again")
        self.store.save_tokens(r.json())
        return r.json()["access_token"]

    def disconnect(self) -> None:
        t = self.store.tokens()
        if t and t.get("refresh_token"):
            try:
                self.http.post(REVOKE_URL, data={"token": t["refresh_token"]})
            except httpx.HTTPError:
                pass  # revoking is best effort; the local tokens are removed either way
        self.store.clear_tokens()
