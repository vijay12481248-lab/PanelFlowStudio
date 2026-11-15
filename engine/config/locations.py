"""Where each local tool / model lives, editable from Settings.

Order for every item: saved setting (app-data config/locations.json), then the environment variable,
then the built-in default. Most engine code still reads the environment variable, so a saved value is
copied into os.environ at start-up and when it is saved; resetting restores the variable the process
started with. Items marked ``restart`` are read once when their module is imported, so a saved change
only takes effect after the engine restarts.
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_COMFY_DIR = r"E:\VIJAY SEKAR\ComfyUI"
DEFAULT_TOOLS_ROOT = r"D:\Tools"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class Item:
    key: str
    label: str
    kind: str  # "dir" | "file" | "url"
    envs: tuple[str, ...]  # first is the one read by the resolver; all are written when saved
    default: str
    note: str = ""
    restart: bool = False


ITEMS: tuple[Item, ...] = (
    Item("comfyui_dir", "ComfyUI folder", "dir", ("PANELFLOW_COMFYUI_DIR",), DEFAULT_COMFY_DIR, "Folder with main.py. Used to find models and start ComfyUI.", True),
    Item("comfyui_workflow_dir", "ComfyUI workflow folder", "dir", ("PANELFLOW_COMFYUI_WORKFLOW_DIR",), DEFAULT_COMFY_DIR + r"\workflow", "Folder that holds the approved workflow files."),
    Item("comfyui_url", "ComfyUI address", "url", ("PANELFLOW_COMFYUI_URL",), "http://127.0.0.1:8188", "Where the running ComfyUI answers.", True),
    Item("ollama_url", "Ollama address", "url", ("OLLAMA_URL",), DEFAULT_OLLAMA_URL, "Where the running Ollama answers.", True),
    Item("tools_root", "Local tools folder", "dir", ("PANELFLOW_LOCAL_TOOLS_ROOT",), DEFAULT_TOOLS_ROOT, "Holds ACE-Step 1.5, Qwen3-TTS, ffmpeg and other tools.", True),
    Item("qwen3_tts_python", "Qwen3-TTS Python", "file", ("PANELFLOW_QWEN3_TTS_PYTHON",), DEFAULT_TOOLS_ROOT + r"\Qwen3-TTS\.venv\Scripts\python.exe", "python.exe of the Qwen3-TTS environment.", True),
    Item("qwen3_tts_runner", "Qwen3-TTS runner script", "file", ("PANELFLOW_QWEN3_TTS_RUNNER",), DEFAULT_TOOLS_ROOT + r"\Qwen3-TTS\runner.py", "runner.py next to the Qwen3-TTS install.", True),
    Item("qwen3_tts_model", "Qwen3-TTS model folder", "dir", ("PANELFLOW_QWEN3_TTS_DIR",), r"D:\models\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-Base", "The downloaded model weights.", True),
    Item("voice_refs", "Voice references folder", "dir", ("PANELFLOW_VOICE_REF_DIR", "PANELFLOW_VOICE_REFERENCE_DIR"), "", "Reference voice clips for cloning. Empty default means the app-data folder.", True),
)
BY_KEY = {i.key: i for i in ITEMS}

_started_with: dict[str, str | None] = {}  # env values before any saved value overwrote them


def _path(app_data: Path) -> Path:
    return app_data / "config" / "locations.json"


def load_saved(app_data: Path) -> dict[str, str]:
    try:
        data = json.loads(_path(app_data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in BY_KEY and isinstance(v, str) and v.strip()}


def _default(item: Item, app_data: Path) -> str:
    return item.default or str(app_data / "voice_references")


def apply_saved(app_data: Path) -> None:
    """Make os.environ match the saved settings; items without a saved value get their original env back."""
    saved = load_saved(app_data)
    for item in ITEMS:
        for env in item.envs:
            _started_with.setdefault(env, os.environ.get(env))
            if item.key in saved:
                os.environ[env] = saved[item.key]
            elif _started_with[env] is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = _started_with[env]  # type: ignore[assignment]


def resolve(key: str, app_data: Path) -> tuple[str, str]:
    """(value, source) where source is saved | env | default."""
    item = BY_KEY[key]
    saved = load_saved(app_data)
    if key in saved:
        return saved[key], "saved"
    env = _started_with.get(item.envs[0], os.environ.get(item.envs[0]))
    if env:
        return env, "env"
    return _default(item, app_data), "default"


def check(item: Item, value: str) -> bool:
    """Found / not found. Folders and files must exist; an address must accept a connection."""
    if item.kind == "url":
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return False
        try:
            with socket.create_connection((parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)), timeout=0.7):
                return True
        except OSError:
            return False
    p = Path(value).expanduser()
    return p.is_dir() if item.kind == "dir" else p.is_file()


def validate(item: Item, value: str) -> str | None:
    """Return a plain-words problem, or None if the value is acceptable to save."""
    if item.kind == "url":
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.fragment:
            return "Use a full address like http://127.0.0.1:8188"
    elif "\x00" in value or len(value) > 500:
        return "That is not a usable path"
    return None


def describe(app_data: Path) -> list[dict]:
    out = []
    for item in ITEMS:
        value, source = resolve(item.key, app_data)
        out.append({
            "key": item.key, "label": item.label, "kind": item.kind, "note": item.note,
            "value": value, "source": source, "default": _default(item, app_data),
            "found": check(item, value), "restart": item.restart,
        })
    return out


def save(app_data: Path, changes: dict[str, str | None]) -> None:
    """Set (string) or reset (None / empty) items, persist, and update os.environ."""
    for key, value in changes.items():
        if key not in BY_KEY:
            raise KeyError(key)
        if value and (problem := validate(BY_KEY[key], value.strip())):
            raise ValueError(f"{BY_KEY[key].label}: {problem}")
    saved = load_saved(app_data)
    for key, value in changes.items():
        if value and value.strip():
            saved[key] = value.strip()
        else:
            saved.pop(key, None)
    path = _path(app_data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    apply_saved(app_data)
