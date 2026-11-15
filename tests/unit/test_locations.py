"""Tool / model locations: saved setting > environment variable > default, and the found check."""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engine.config import locations
from engine.api.routers import locations as router_mod


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    for item in locations.ITEMS:
        for env in item.envs:
            monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(locations, "_started_with", {})
    yield tmp_path
    for item in locations.ITEMS:  # nothing saved here may leak into other tests
        for env in item.envs:
            os.environ.pop(env, None)


def test_default_then_env_then_saved(app_data, monkeypatch):
    assert locations.resolve("tools_root", app_data) == (r"D:\Tools", "default")
    monkeypatch.setenv("PANELFLOW_LOCAL_TOOLS_ROOT", str(app_data / "env"))
    assert locations.resolve("tools_root", app_data) == (str(app_data / "env"), "env")
    locations.save(app_data, {"tools_root": str(app_data / "saved")})
    assert locations.resolve("tools_root", app_data) == (str(app_data / "saved"), "saved")
    assert os.environ["PANELFLOW_LOCAL_TOOLS_ROOT"] == str(app_data / "saved")  # existing readers see it
    locations.save(app_data, {"tools_root": None})  # reset: back to the env value the process started with
    assert locations.resolve("tools_root", app_data) == (str(app_data / "env"), "env")
    assert os.environ["PANELFLOW_LOCAL_TOOLS_ROOT"] == str(app_data / "env")


def test_reset_without_env_removes_variable(app_data):
    locations.save(app_data, {"comfyui_dir": str(app_data)})
    assert os.environ["PANELFLOW_COMFYUI_DIR"] == str(app_data)
    locations.save(app_data, {"comfyui_dir": ""})
    assert "PANELFLOW_COMFYUI_DIR" not in os.environ


def test_voice_refs_sets_both_env_names(app_data):
    locations.save(app_data, {"voice_refs": str(app_data)})
    assert os.environ["PANELFLOW_VOICE_REF_DIR"] == os.environ["PANELFLOW_VOICE_REFERENCE_DIR"] == str(app_data)


def test_found_check_for_dir_file_and_url(app_data):
    (app_data / "runner.py").write_text("x")
    by = locations.BY_KEY
    assert locations.check(by["tools_root"], str(app_data))
    assert not locations.check(by["tools_root"], str(app_data / "missing"))
    assert locations.check(by["qwen3_tts_runner"], str(app_data / "runner.py"))
    assert not locations.check(by["qwen3_tts_runner"], str(app_data))  # a folder is not a file
    assert not locations.check(by["comfyui_url"], "http://127.0.0.1:1")  # nothing listens
    assert not locations.check(by["comfyui_url"], "not a url")


def test_bad_url_and_unknown_key_are_rejected(app_data):
    with pytest.raises(ValueError):
        locations.save(app_data, {"ollama_url": "ftp://x"})
    with pytest.raises(KeyError):
        locations.save(app_data, {"nope": "x"})
    assert locations.load_saved(app_data) == {}


def test_api_round_trip(app_data, monkeypatch):
    monkeypatch.setattr(router_mod.settings, "app_data_dir", app_data)
    app = FastAPI()
    app.include_router(router_mod.router)
    client = TestClient(app)
    r = client.put("/api/system/locations", json={"values": {"tools_root": str(app_data)}})
    assert r.status_code == 200
    row = next(i for i in r.json()["items"] if i["key"] == "tools_root")
    assert (row["source"], row["found"]) == ("saved", True)
    assert client.put("/api/system/locations", json={"values": {"comfyui_url": "x"}}).status_code == 422
    assert client.put("/api/system/locations", json={"values": {"zzz": "x"}}).status_code == 422
    assert len(client.get("/api/system/locations").json()["items"]) == len(locations.ITEMS)
