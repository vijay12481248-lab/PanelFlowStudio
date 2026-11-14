"""ChronoFlow's Magic Brush / range editing and the story workbench, now served by the engine (they used to need the port 7860 server)."""
import base64
import io
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from engine.api.routers import chronoflow_nle as nle
from engine.api.routers import chronoflow_stories as stories
from engine.api.routers import original


def _png_bytes(size=(32, 24), color=(10, 120, 200)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


def _data_url(raw: bytes | None = None) -> str:
    return "data:image/png;base64," + base64.b64encode(raw or _png_bytes()).decode()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    inputs, outputs = tmp_path / "inputs", tmp_path / "outputs"
    inputs.mkdir(); outputs.mkdir()
    monkeypatch.setattr(nle, "COMFY_INPUT_DIR", inputs)
    monkeypatch.setattr(nle, "STUDIO_OUTPUT_DIR", outputs)
    return inputs, outputs


@pytest.fixture
def client(dirs):
    app = FastAPI()
    app.include_router(nle.router)
    return TestClient(app)


# ---------- helpers ----------
def test_a_client_file_name_can_never_leave_the_input_folder():
    assert nle.safe_name("../../evil.png") == "evil.png"
    assert nle.safe_name("C:\\Windows\\system32\\x.jpg") in ("x.jpg", "C:\\Windows\\system32\\x.jpg.png")
    assert nle.safe_name("a/b/c.webp") == "c.webp"
    assert nle.safe_name("notes.txt").endswith(".txt.png"), "a non-picture extension is not trusted"
    assert nle.safe_name(None).startswith("ref_") and nle.safe_name(".hidden").startswith("ref_")
    assert "/" not in nle.safe_name("x/../../y") and ".." not in nle.safe_name("x/../../y")


def test_a_data_url_must_be_a_real_picture_within_the_limit():
    assert nle.decode_data_url(_data_url()).startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="base64"):
        nle.decode_data_url("data:image/png;base64,!!!not base64!!!")
    with pytest.raises(ValueError, match="readable picture"):
        nle.decode_data_url("data:image/png;base64," + base64.b64encode(b"just text").decode())
    with pytest.raises(ValueError, match="larger"):
        nle.decode_data_url(_data_url(), limit=10)


def test_code_fences_frame_lengths_and_the_master_lookup(dirs):
    assert nle.strip_code_fence("```text\nhello\n```") == "hello"
    assert nle.strip_code_fence("  plain  ") == "plain"
    assert [nle.frame_length_for(d) for d in (1.0, 2.0, 3.0, 5.0)] == [22, 56, 73, 124]
    _, outputs = dirs
    assert nle.latest_master(None) is None
    older = outputs / "chronoflow_master_aaa.mp4"; older.write_bytes(b"x")
    newer = outputs / "chronoflow_master_bbb.mp4"; newer.write_bytes(b"y")
    import os, time
    os.utime(older, (time.time() - 100, time.time() - 100))
    assert nle.latest_master(None) == newer, "the newest master when no job is named"
    assert nle.latest_master("aaa") == older, "the job's own master first"
    assert nle.latest_master("../../etc/passwd") == newer, "a job id is reduced to a bare name"


def test_a_replacement_clip_is_rendered_at_the_size_of_the_video_it_joins(dirs, monkeypatch):
    _, outputs = dirs
    assert nle.render_size({"width": 1024, "height": 576}, "j") == (1024, 576), "the job's own size first"
    assert nle.render_size({}, None) == (1344, 768), "nothing known: the default"
    master = outputs / "chronoflow_master_j2.mp4"; master.write_bytes(b"m")
    monkeypatch.setattr(nle.media_tools, "probe", lambda p: {"width": 768, "height": 1344})
    assert nle.render_size({}, "j2") == (768, 1344), "a portrait master gets a portrait clip"
    monkeypatch.setattr(nle.media_tools, "probe", lambda p: (_ for _ in ()).throw(RuntimeError("no ffprobe")))
    assert nle.render_size({}, "j2") == (1344, 768), "an unreadable master falls back to the default"


# ---------- upload_ref ----------
def test_upload_ref_stores_a_picture_under_a_safe_name(client, dirs):
    inputs, _ = dirs
    res = client.post("/api/chronoflow/nle/upload_ref", json={"image": _data_url(), "filename": "../../outside.png"})
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "outside.png" and body["url"] == "/inputs/outside.png"
    assert (inputs / "outside.png").is_file() and not (inputs.parent.parent / "outside.png").exists()


def test_upload_ref_refuses_bad_data_urls_and_arbitrary_paths_and_urls(client, tmp_path):
    for image in ("data:image/png;base64,AAAA", "https://example.com/x.png", str(tmp_path / "secret.png"), "not-a-file.png"):
        (tmp_path / "secret.png").write_bytes(_png_bytes())
        assert client.post("/api/chronoflow/nle/upload_ref", json={"image": image}).status_code == 400, image


def test_upload_ref_can_reuse_a_picture_from_the_media_folders(client, dirs, monkeypatch, tmp_path):
    inputs, _ = dirs
    media = tmp_path / "media"; media.mkdir()
    (media / "shot.png").write_bytes(_png_bytes())
    monkeypatch.setattr(nle.media_tools, "resolve_media", lambda name: media / name if (media / name).exists() else None)
    res = client.post("/api/chronoflow/nle/upload_ref", json={"image": "shot.png", "filename": "kept.png"})
    assert res.status_code == 200 and (inputs / "kept.png").read_bytes() == _png_bytes()


# ---------- frame/generate ----------
def test_frame_generate_draws_with_the_real_art_engine_method(client, dirs, monkeypatch):
    inputs, _ = dirs
    (inputs / "anchor.png").write_bytes(_png_bytes())
    seen = {}

    class FakeArt:
        def generate(self, prompt, **kw):
            seen.update(prompt=prompt, **kw)
            return type("A", (), {"png": _png_bytes((64, 36))})()

    import engine.comfyui.art as art
    monkeypatch.setattr(art, "ArtEngine", FakeArt)
    res = client.post("/api/chronoflow/nle/frame/generate", json={"prompt": "a lantern in the rain", "time": 3.5, "reference_image": "../anchor.png"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] and body["time"] == 3.5 and body["image_url"] == f"/inputs/{body['id']}"
    assert (inputs / body["id"]).is_file()
    assert seen["prompt"] == "a lantern in the rain" and (seen["width"], seen["height"]) == (1024, 576)
    assert seen["reference_images"] == [_png_bytes()], "the chosen reference picture is passed to the art engine"
    assert client.post("/api/chronoflow/nle/frame/generate", json={"prompt": ""}).status_code == 422


def test_the_real_art_engine_has_the_method_the_route_calls():
    from engine.comfyui.art import ArtEngine
    assert callable(getattr(ArtEngine, "generate", None)) and not hasattr(ArtEngine, "generate_image")


# ---------- range routes ----------
def test_range_auto_prompt_writes_a_prompt_and_a_summary(client, dirs, monkeypatch):
    seen = {}

    async def fake_write(system, user, anchor):
        seen.update(system=system, user=user, anchor=anchor)
        return "summary:\nA slow push-in on the hero.\n\ndetailed_description:\nThe hero turns."

    monkeypatch.setattr(nle, "_write_prompt", fake_write)
    res = client.post("/api/chronoflow/nle/range/auto_prompt", json={"t_start": 1.0, "t_end": 3.0, "adjustments": "make him turn left"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] and body["summary"] == "A slow push-in on the hero." and body["duration"] == 2.0 and body["anchor_image"] is None
    assert "make him turn left" in seen["user"] and "[1.0s -> 3.0s]" in seen["system"]


def test_range_auto_prompt_reports_a_missing_local_model_as_a_bad_gateway(client, monkeypatch):
    async def down(*a):
        raise ConnectionError("ollama is not running")

    monkeypatch.setattr(nle, "_write_prompt", down)
    res = client.post("/api/chronoflow/nle/range/auto_prompt", json={"adjustments": "x"})
    assert res.status_code == 502 and "ollama" in res.json()["detail"]


def test_range_generate_needs_an_anchor_frame_and_a_prompt(client, dirs):
    res = client.post("/api/chronoflow/nle/range/generate", json={"prompt": "he runs"})
    assert res.status_code == 400 and "no frame to start from" in res.json()["detail"].lower()
    inputs, _ = dirs
    (inputs / "start.png").write_bytes(_png_bytes())
    assert client.post("/api/chronoflow/nle/range/generate", json={"reference_image": "start.png", "prompt": ""}).status_code == 400


def test_range_generate_renders_a_clip_from_the_anchor(client, dirs, monkeypatch):
    inputs, outputs = dirs
    (inputs / "start.png").write_bytes(_png_bytes())
    clip = outputs / "raw.mp4"; clip.write_bytes(b"clip")
    seen = {}

    class FakePipeline:
        def build_h3_prompt(self, **kw):
            seen.update(kw)
            return {"graph": True}

        async def execute_prompt(self, graph):
            return clip

    monkeypatch.setattr(nle.cf, "pipeline", FakePipeline())
    full = "summary:\nx\ndetailed_description:\nhe runs"
    res = client.post("/api/chronoflow/nle/range/generate", json={"t_start": 0, "t_end": 2.0, "prompt": full, "reference_image": "start.png"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] and body["clip_filename"].startswith("range_chunk_") and (outputs / body["clip_filename"]).read_bytes() == b"clip"
    assert seen["first_frame_filename"] == "start.png" and seen["length"] == 56 and seen["prompt"] == full
    assert (seen["width"], seen["height"]) == (1344, 768), "no job and no master: the default size"


def test_range_apply_splices_into_the_master_and_keeps_names_safe(client, dirs, monkeypatch):
    _, outputs = dirs
    (outputs / "chronoflow_master_j1.mp4").write_bytes(b"master")
    (outputs / "newclip.mp4").write_bytes(b"clip")
    updates = {}
    calls = {}

    def fake_splice(base, rep, t0, t1, out):
        calls.update(base=base.name, rep=rep.name, t=(t0, t1))
        out.write_bytes(b"spliced")
        return out

    monkeypatch.setattr(nle.media_tools, "splice_timeline_range", fake_splice)
    monkeypatch.setattr(nle.media_tools, "resolve_media", lambda name: None)
    monkeypatch.setattr(nle.cf.supervisor, "update_job", lambda job_id, **kw: updates.update(job_id=job_id, **kw))
    res = client.post("/api/chronoflow/nle/range/apply", json={"job_id": "j1", "clip_filename": "../../newclip.mp4", "t_start": 1.0, "t_end": 2.5})
    assert res.status_code == 200
    assert calls == {"base": "chronoflow_master_j1.mp4", "rep": "newclip.mp4", "t": (1.0, 2.5)}
    assert (outputs / "chronoflow_master_j1.mp4").read_bytes() == b"spliced", "the master now holds the spliced video"
    assert updates["job_id"] == "j1" and updates["master_video"] == "/outputs/chronoflow_master_j1.mp4"
    assert client.post("/api/chronoflow/nle/range/apply", json={"job_id": "j1", "clip_filename": "missing.mp4"}).status_code == 404


def test_range_apply_without_any_master_is_a_404(client):
    assert client.post("/api/chronoflow/nle/range/apply", json={"clip_filename": "x.mp4"}).status_code == 404


# ---------- the story workbench adapter ----------
@pytest.fixture
def story_client(tmp_path, monkeypatch):
    root = tmp_path / "Original_Stories"
    ws = root / "tale"
    (ws / "panels").mkdir(parents=True)
    (ws / "panels" / "p001.png").write_bytes(_png_bytes())
    (ws / "panels" / "_candidates" / "p001").mkdir(parents=True)
    (ws / "panels" / "_candidates" / "p001" / "c002.png").write_bytes(_png_bytes((8, 8)))
    (ws / "voice").mkdir()
    (ws / "voice" / "p001.wav").write_bytes(b"RIFFxxxxWAVE")
    (ws / "story.json").write_text(json.dumps({"bible": {"premise": {"title": "A Tale", "genre": "fantasy"}}, "panels": [{"id": "p001"}]}), encoding="utf-8")
    (ws / "art.json").write_text(json.dumps([{"panel_id": "p001", "score": 0.4, "status": "needs_review", "review": {"defects": ["extra finger"]}}]), encoding="utf-8")
    (root / "not_a_story").mkdir()
    monkeypatch.setattr(original, "STORY_ROOT", root)
    app = FastAPI()
    app.include_router(stories.router)
    return TestClient(app), ws


def test_the_story_list_shows_only_real_stories(story_client):
    c, _ = story_client
    body = c.get("/api/original_stories/list").json()
    assert body["success"] and body["stories"] == [
        {"slug": "tale", "title": "A Tale", "genre": "fantasy", "total_panels": 1, "has_art": True, "has_video": False}]


def test_panel_pictures_candidates_and_audio_are_served_and_ids_are_checked(story_client):
    c, _ = story_client
    assert c.get("/api/original_stories/tale/panel/p001").content == _png_bytes()
    assert c.get("/api/original_stories/tale/panel/p001?candidate=2").content == _png_bytes((8, 8))
    assert c.get("/api/original_stories/tale/panel/p001?candidate=oops").content == _png_bytes(), "a bad candidate number falls back to the panel"
    assert c.get("/api/original_stories/tale/panel/p404").status_code == 404
    assert c.get("/api/original_stories/tale/panel/..%2F..%2Fstory").status_code == 404
    assert c.get("/api/original_stories/tale/panel/bad.id").status_code == 404, "ids are letters, digits, - and _ only"
    assert c.get("/api/original_stories/tale/audio/p001").content.startswith(b"RIFF")
    assert c.get("/api/original_stories/tale/audio/p002").status_code == 404
    assert c.get("/api/original_stories/nosuch/panel/p001").status_code == 404


def test_agent_actions_give_somatic_cues_or_the_stored_audit(story_client):
    c, _ = story_client
    cues = c.post("/api/original_stories/tale/panel/p001/agent_action", json={"action": "somatic_emotion", "archetype": "dread_terror", "custom_cues": "rain"}).json()
    assert cues["success"] and cues["archetype_title"].startswith("Paralyzing Dread") and cues["somatic_prompt"].startswith("rain, ")
    default = c.post("/api/original_stories/tale/panel/p001/agent_action", json={}).json()
    assert default["archetype"] == "visceral_pain", "no body at all means the default action and archetype"
    audit = c.post("/api/original_stories/tale/panel/p001/agent_action", json={"action": "vision_audit"}).json()
    assert audit["score"] == 0.4 and audit["status"] == "needs_review" and audit["defects"] == ["extra finger"]
    assert c.post("/api/original_stories/tale/panel/p001/agent_action", json={"action": "nope"}).status_code == 400


def test_approve_reroll_and_open_call_the_original_story_functions(story_client, monkeypatch):
    c, _ = story_client
    seen = {}
    monkeypatch.setattr(original, "approve_panel", lambda slug, panel_id, req: seen.update(approve=(slug, panel_id, req.episode)) or {"ok": 1})

    async def fake_reroll(slug, panel_id, req):
        seen["reroll"] = (slug, panel_id, req.episode, req.seed, req.prompt)
        return {"ok": 2}

    monkeypatch.setattr(original, "reroll_panel", fake_reroll)
    monkeypatch.setattr(original, "open_story", lambda slug, req: f"opened {slug}")
    assert c.post("/api/original_stories/tale/panel/p001/approve", json={"episode": "e1"}).json() == {"ok": 1}
    assert c.post("/api/original_stories/tale/panel/p001/reroll", json={"seed": 7, "prompt": "brighter"}).json() == {"ok": 2}
    assert c.post("/api/original_stories/tale/open").json() == {"success": True, "detail": "opened tale"}
    assert seen == {"approve": ("tale", "p001", "e1"), "reroll": ("tale", "p001", None, 7, "brighter")}
    assert c.post("/api/original_stories/tale/panel/../approve").status_code in (404, 405)
