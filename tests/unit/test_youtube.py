import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from engine.original import upload as up
from engine.original.series import Episode, SeriesStore
from engine.youtube import auth as ya
from engine.youtube.client import CHUNK, UploadMeta, YouTubeClient, YouTubeError, fit_tags
from tests.unit.test_original_story import full_bible


def make_auth(tmp_path, handler):
    store = ya.OAuthStore(tmp_path / "cfg")
    store.dir.mkdir()
    store.set_client("client-id-123456", "secret-xyz")
    a = ya.YouTubeAuth(store, httpx.Client(transport=httpx.MockTransport(handler)))
    return a, store


# ---- OAuth ----------------------------------------------------------------------------------------------------------------
def test_pkce_pair_is_s256_of_verifier():
    import base64, hashlib
    v, c = ya.pkce_pair()
    assert c == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode() and len(v) >= 43


def test_begin_needs_client_then_builds_pkce_url_and_status_never_leaks_secrets(tmp_path):
    a = ya.YouTubeAuth(ya.OAuthStore(tmp_path))
    with pytest.raises(ya.AuthError):
        a.begin()
    a.store.set_client("client-id-123456", "secret-xyz")
    url = a.begin()
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == [ya.SCOPE] and q["code_challenge_method"] == ["S256"] and q["access_type"] == ["offline"]
    assert q["redirect_uri"][0].startswith("http://127.0.0.1:") and "secret" not in url
    assert a.status() == {"configured": True, "connected": False, "pending": True, "error": None}
    a._pending["server"].shutdown()


def test_callback_exchanges_code_with_verifier_and_stores_tokens(tmp_path):
    seen = {}

    def handler(req):
        seen.update(parse_qs(req.content.decode()))
        return httpx.Response(200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})

    a, store = make_auth(tmp_path, handler)
    url = a.begin()
    state = parse_qs(urlparse(url).query)["state"][0]
    redirect = parse_qs(urlparse(url).query)["redirect_uri"][0]
    r = httpx.get(redirect, params={"code": "CODE", "state": state})
    assert r.status_code == 200
    for _ in range(50):
        if a.status()["connected"]:
            break
        time.sleep(0.05)
    assert a.status()["connected"] and seen["code"] == ["CODE"] and seen["code_verifier"][0] == a._pending["verifier"]
    assert store.tokens()["refresh_token"] == "RT"


def test_callback_with_wrong_state_is_rejected(tmp_path):
    a, store = make_auth(tmp_path, lambda r: httpx.Response(500))
    url = a.begin()
    redirect = parse_qs(urlparse(url).query)["redirect_uri"][0]
    httpx.get(redirect, params={"code": "CODE", "state": "forged"})
    time.sleep(0.2)
    assert store.tokens() is None and a.status()["error"] == "state mismatch"


def test_access_token_refreshes_when_expired_and_keeps_refresh_token(tmp_path):
    calls = []

    def handler(req):
        calls.append(parse_qs(req.content.decode())["grant_type"][0])
        return httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600})

    a, store = make_auth(tmp_path, handler)
    store.save_tokens({"access_token": "OLD", "refresh_token": "RT", "expires_in": -100})
    assert a.access_token() == "NEW" and calls == ["refresh_token"]
    assert store.tokens()["refresh_token"] == "RT"  # a refresh response has no refresh token: the old one must survive
    assert a.access_token() == "NEW" and len(calls) == 1  # still valid: no second call


# ---- metadata ---------------------------------------------------------------------------------------------------------------
def test_metadata_validation_and_scheduling_rules():
    with pytest.raises(ValueError):
        UploadMeta(title="x" * 101, made_for_kids=False)
    with pytest.raises(ValueError):
        UploadMeta(title="ok <b>", made_for_kids=False)
    with pytest.raises(ValueError):
        UploadMeta(title="ok", privacy="secret", made_for_kids=False)
    with pytest.raises(Exception):
        UploadMeta(title="ok")  # made_for_kids is mandatory
    when = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(ValueError):
        UploadMeta(title="ok", made_for_kids=False, privacy="public", publish_at=when).body()
    b = UploadMeta(title="ok", made_for_kids=True, publish_at=when).body()
    assert b["status"]["publishAt"].endswith("Z") and b["status"]["privacyStatus"] == "private"
    assert b["status"]["selfDeclaredMadeForKids"] is True and b["status"]["containsSyntheticMedia"] is True


def test_fit_tags_dedupes_and_respects_the_500_character_budget():
    tags = ["story time", "story time"] + [f"tag{i:03d}" * 3 for i in range(100)]
    out = fit_tags(tags)
    assert out[0] == "story time" and out.count("story time") == 1
    assert sum(len(t) + (2 if " " in t else 0) for t in out) + len(out) - 1 <= 500


# ---- resumable upload -------------------------------------------------------------------------------------------------------
class FakeYouTube:
    """Speaks just enough of the resumable protocol: init, chunk PUTs (308/200), status probes, injected failures."""

    def __init__(self, fail_chunks=0, init_status=200):
        self.received, self.fail_chunks, self.init_status, self.log, self.thumb = 0, fail_chunks, init_status, [], None
        self.total = 0
        self.body = None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.startswith("https://www.googleapis.com/upload/youtube/v3/videos"):
            self.total = int(req.headers["x-upload-content-length"])
            self.body = json.loads(req.content)
            if self.init_status != 200:
                return httpx.Response(self.init_status, json={"error": {"message": "quota", "errors": [{"reason": "quotaExceeded"}]}})
            return httpx.Response(200, headers={"location": "https://upload.example/session1"})
        if url.startswith("https://upload.example/session1"):
            cr = req.headers["content-range"]
            self.log.append(cr)
            if cr.startswith("bytes */"):
                return self._progress()
            if self.fail_chunks:
                self.fail_chunks -= 1
                self.received += len(req.content) // 2  # the server kept half of that chunk before dying
                return httpx.Response(503)
            start = int(cr.split()[1].split("-")[0])
            assert start == self.received, f"chunk starts at {start} but server has {self.received}"
            self.received += len(req.content)
            return self._progress()
        if url.startswith("https://www.googleapis.com/upload/youtube/v3/thumbnails/set"):
            self.thumb = (parse_qs(urlparse(url).query)["videoId"][0], len(req.content))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def _progress(self):
        if self.received >= self.total:
            return httpx.Response(200, json={"id": "VID123"})
        return httpx.Response(308, headers={"range": f"bytes=0-{self.received - 1}"} if self.received else {})


def client(tmp_path, fake):
    a, _ = make_auth(tmp_path, lambda r: httpx.Response(500))
    a.store.save_tokens({"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
    return YouTubeClient(a, httpx.Client(transport=httpx.MockTransport(fake)), sleep=lambda s: None)


def video(tmp_path, size):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x" * size)
    return f


def test_upload_in_chunks_returns_id_and_sends_the_right_metadata(tmp_path):
    fake = FakeYouTube()
    res = client(tmp_path, fake).upload(video(tmp_path, CHUNK * 2 + 123), UploadMeta(title="T", made_for_kids=False))
    assert res["id"] == "VID123" and res["url"].endswith("VID123") and res["privacy"] == "private"
    assert len(fake.log) == 3 and fake.log[0] == f"bytes 0-{CHUNK - 1}/{CHUNK * 2 + 123}"
    assert fake.body["status"]["privacyStatus"] == "private" and fake.body["snippet"]["title"] == "T"


def test_upload_resumes_after_a_server_error_from_the_byte_the_server_has(tmp_path):
    fake = FakeYouTube(fail_chunks=2)
    res = client(tmp_path, fake).upload(video(tmp_path, CHUNK + 500), UploadMeta(title="T", made_for_kids=False))
    assert res["id"] == "VID123" and any(c.startswith("bytes */") for c in fake.log)  # it asked how much was received


def test_upload_gives_up_after_repeated_failures(tmp_path):
    fake = FakeYouTube(fail_chunks=100)
    with pytest.raises(YouTubeError, match="resume"):
        client(tmp_path, fake).upload(video(tmp_path, 1000), UploadMeta(title="T", made_for_kids=False))


def test_quota_error_is_explained(tmp_path):
    with pytest.raises(YouTubeError, match="quota"):
        client(tmp_path, FakeYouTube(init_status=403)).upload(video(tmp_path, 10), UploadMeta(title="T", made_for_kids=False))


def test_thumbnail_is_sent_and_size_limited(tmp_path):
    fake = FakeYouTube()
    c = client(tmp_path, fake)
    img = tmp_path / "t.jpg"
    img.write_bytes(b"j" * 1000)
    c.set_thumbnail("VID123", img)
    assert fake.thumb == ("VID123", 1000)
    img.write_bytes(b"j" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError):
        c.set_thumbnail("VID123", img)


# ---- episode upload rules ---------------------------------------------------------------------------------------------------
def finished_series(tmp_path, publish_in=timedelta(days=1)):
    store = SeriesStore(tmp_path / "series")
    s = store.create("Moon Tales", "bedtime", full_bible())
    ws = store.episode_dir(s.id, 1)
    ws.mkdir(parents=True)
    (ws / "v.mp4").write_bytes(b"x" * 2000)
    (ws / "t.jpg").write_bytes(b"j" * 100)
    (ws / "youtube_package.json").write_text(json.dumps({"title": "Ep 1", "description": "d", "tags": ["a"], "thumbnail_path": str(ws / "t.jpg")}))
    pub = (datetime.now() + publish_in).isoformat(timespec="seconds")
    store.update_episode(s.id, Episode(number=1, status="done", video=str(ws / "v.mp4"), workspace=str(ws), publish_at=pub))
    return store, s.id


def test_default_upload_is_private_and_recorded(tmp_path):
    store, sid = finished_series(tmp_path)
    fake = FakeYouTube()
    out = up.upload_episode(store, sid, 1, client(tmp_path, fake), made_for_kids=True)
    ep = store.get(sid).episodes[0]
    assert fake.body["status"]["privacyStatus"] == "private" and "publishAt" not in fake.body["status"]
    assert ep.upload_status == "uploaded" and ep.youtube_id == "VID123" and ep.youtube_privacy == "private" and fake.thumb[0] == "VID123"
    assert out["warning"] == ""


def test_public_and_scheduled_releases_need_explicit_confirmation(tmp_path):
    store, sid = finished_series(tmp_path)
    with pytest.raises(up.UploadRefused, match="confirm_public"):
        up.plan_upload(store, sid, 1, made_for_kids=False, privacy="public")
    with pytest.raises(up.UploadRefused, match="confirm_public"):
        up.plan_upload(store, sid, 1, made_for_kids=False, schedule=True)
    meta, _, _ = up.plan_upload(store, sid, 1, made_for_kids=False, schedule=True, confirm_public=True)
    assert meta.privacy == "private" and meta.publish_at is not None  # YouTube flips it public at the slot


def test_slot_in_the_past_and_double_upload_are_refused(tmp_path):
    store, sid = finished_series(tmp_path, publish_in=timedelta(minutes=5))
    with pytest.raises(up.UploadRefused, match="past or less than 20"):
        up.plan_upload(store, sid, 1, made_for_kids=False, schedule=True, confirm_public=True)
    up.upload_episode(store, sid, 1, client(tmp_path, FakeYouTube()), made_for_kids=False)
    with pytest.raises(up.UploadRefused, match="already on YouTube"):
        up.plan_upload(store, sid, 1, made_for_kids=False)
    up.plan_upload(store, sid, 1, made_for_kids=False, force=True)  # an explicit re-upload is allowed


def test_unfinished_episode_is_refused_and_failures_are_recorded(tmp_path):
    store, sid = finished_series(tmp_path)
    store.update_episode(sid, store.get(sid).episodes[0].model_copy(update={"status": "running"}))
    with pytest.raises(up.UploadRefused, match="not finished"):
        up.plan_upload(store, sid, 1, made_for_kids=False)
    store.update_episode(sid, store.get(sid).episodes[0].model_copy(update={"status": "done"}))
    with pytest.raises(YouTubeError):
        up.upload_episode(store, sid, 1, client(tmp_path, FakeYouTube(init_status=403)), made_for_kids=False)
    ep = store.get(sid).episodes[0]
    assert ep.upload_status == "failed" and "quota" in ep.upload_error and ep.youtube_id is None


def test_thumbnail_failure_does_not_undo_the_upload(tmp_path):
    store, sid = finished_series(tmp_path)

    class NoThumb(FakeYouTube):
        def __call__(self, req):
            return httpx.Response(400, json={"error": {"message": "needs verified phone", "errors": []}}) if "thumbnails" in str(req.url) else super().__call__(req)

    out = up.upload_episode(store, sid, 1, client(tmp_path, NoThumb()), made_for_kids=False)
    ep = store.get(sid).episodes[0]
    assert ep.youtube_id == "VID123" and "thumbnail not set" in ep.upload_error and "thumbnail" in out["warning"]


# ---- HTTP routes ------------------------------------------------------------------------------------------------------------
@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from engine.api.app import create_app
    import engine.api.routers.original as orig
    import engine.api.routers.youtube as yr

    monkeypatch.setattr(orig, "SERIES_ROOT", tmp_path / "series")
    store = ya.OAuthStore(tmp_path / "cfg")
    store.dir.mkdir()
    monkeypatch.setattr(yr, "auth", ya.YouTubeAuth(store))
    return TestClient(create_app(allow_insecure=True), base_url="http://localhost"), store, tmp_path, yr


def test_client_secret_is_stored_but_never_returned(api):
    c, store, _, _ = api
    r = c.put("/api/youtube/client", json={"client_id": "client-id-123456", "client_secret": "super-secret-value"})
    assert r.status_code == 200 and r.json() == {"configured": True, "connected": False, "pending": False, "error": None}
    assert "super-secret-value" not in r.text and "super-secret-value" not in c.get("/api/youtube/status").text
    assert store.client()["client_secret"] == "super-secret-value"


def test_upload_route_requires_connection_and_refuses_unconfirmed_public(api):
    c, store, tmp, yr = api
    s = SeriesStore(tmp / "series")
    series = s.create("Moon Tales", "bedtime", full_bible())
    ws = s.episode_dir(series.id, 1)
    ws.mkdir(parents=True)
    (ws / "v.mp4").write_bytes(b"x" * 100)
    (ws / "youtube_package.json").write_text(json.dumps({"title": "T", "description": "d", "tags": []}))
    s.update_episode(series.id, Episode(number=1, status="done", video=str(ws / "v.mp4"), workspace=str(ws)))
    url = f"/api/original/series/{series.id}/episodes/1/upload"
    assert c.post(url, json={"made_for_kids": True}).status_code == 409  # not connected
    store.save_tokens({"access_token": "a", "refresh_token": "r", "expires_in": 3600})
    assert c.post(url, json={}).status_code == 422  # made_for_kids is mandatory
    bad = c.post(url, json={"made_for_kids": True, "privacy": "public"})
    assert bad.status_code == 422 and "confirm_public" in bad.json()["detail"]
    assert c.post("/api/original/series/none/episodes/1/upload", json={"made_for_kids": True}).status_code == 404
