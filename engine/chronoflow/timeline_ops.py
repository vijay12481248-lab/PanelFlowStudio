"""ChronoFlow timelines on the server, so agents (MCP) and the studio UI edit the same thing.

The studio used to keep the timeline (cuts, colour grades, Fusion effects) only in the browser's localStorage, so no agent could
see or change a grade. Now the UI mirrors every edit here (versioned) and adopts newer versions written by agents; agents change it
through the small, validated operations below. Value ranges, looks and node shapes match the Color/Fusion pages
(static/nle/color.js, grade.js, fusion-graph.js) so an agent grade looks exactly like a hand-made one.
"""
from __future__ import annotations

import copy
import json
import math
import re
import secrets
import time
from pathlib import Path
from typing import Any

from engine.config.settings import settings

TIMELINE_DIR = settings.app_data_dir / "chronoflow" / "timelines"
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TimelineError(ValueError):
    """A request an agent can fix (bad clip, unknown control, value out of range)."""


# ---------- storage ----------
def _path(job_id: str) -> Path:
    if not _JOB_ID.match(job_id or ""):
        raise TimelineError("job_id may only contain letters, digits, '-' and '_'")
    return TIMELINE_DIR / f"{job_id}.json"


def load(job_id: str) -> dict[str, Any] | None:
    p = _path(job_id)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def version(job_id: str) -> int:
    rec = load(job_id)
    return int(rec["version"]) if rec else 0


def save(job_id: str, timeline: dict[str, Any], source: str) -> dict[str, Any]:
    if not isinstance(timeline, dict) or not isinstance(timeline.get("clips"), list):
        raise TimelineError("timeline must be an object with a 'clips' list")
    p = _path(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"version": version(job_id) + 1, "updated_at": time.time(), "source": source, "timeline": timeline}
    tmp = p.with_suffix(f".tmp{secrets.token_hex(3)}")
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    tmp.replace(p)
    return rec


# ---------- addressing clips ----------
def _clip(tl: dict[str, Any], clip: int | str) -> dict[str, Any]:
    clips = tl.get("clips") or []
    if not clips:
        raise TimelineError("this timeline has no clips yet")
    if isinstance(clip, str) and not clip.isdigit():
        for c in clips:
            if c.get("id") == clip:
                return c
        raise TimelineError(f"no clip with id {clip!r}")
    i = int(clip)
    if not 1 <= i <= len(clips):
        raise TimelineError(f"clip must be 1..{len(clips)} (timeline order) or a clip id")
    return clips[i - 1]


def _targets(tl: dict[str, Any], clip: int | str | None) -> list[dict[str, Any]]:
    """`clip` = 1-based position or id; 'all' / None = every clip."""
    if clip in (None, "all", "*"):
        if not tl.get("clips"):
            raise TimelineError("this timeline has no clips yet")
        return list(tl["clips"])
    return [_clip(tl, clip)]


# ---------- colour (matches grade.js newNode and the Color page sliders) ----------
SCALARS = {  # name: (min, max, neutral, what it does)
    "contrast": (0.0, 2.0, 1.0, "tonal contrast around the pivot"),
    "pivot": (0.0, 1.0, 0.435, "the grey level contrast turns around"),
    "saturation": (0.0, 2.0, 1.0, "0 = black and white, 1 = unchanged"),
    "hue": (-180.0, 180.0, 0.0, "rotates every hue (degrees)"),
    "temp": (-100.0, 100.0, 0.0, "+ warmer (orange), - cooler (blue)"),
    "tint": (-100.0, 100.0, 0.0, "+ magenta, - green"),
    "boost": (0.0, 100.0, 0.0, "colour boost: lifts dull colours more than vivid ones"),
    "shadows": (-100.0, 100.0, 0.0, "brightens (+) or deepens (-) the dark areas"),
    "highlights": (-100.0, 100.0, 0.0, "recovers (-) or pushes (+) the bright areas"),
}
WHEELS = ("lift", "gamma", "gain", "offset")  # shadows, midtones, highlights, whole picture
NAMED_HUES = {"red": 0, "orange": 30, "yellow": 60, "green": 120, "teal": 170, "cyan": 180, "blue": 230, "purple": 275, "magenta": 300, "pink": 330}


def new_node(label: str = "") -> dict[str, Any]:
    tone = [[0, 0], [1, 1]]
    return {
        "id": f"n{secrets.token_hex(3)}", "label": label, "enabled": True,
        "cdl": {"slope": [1, 1, 1], "offset": [0, 0, 0], "power": [1, 1, 1]},
        **{w: {"x": 0, "y": 0, "m": 0} for w in WHEELS},
        "contrast": 1, "pivot": 0.435, "saturation": 1, "hue": 0, "temp": 0, "tint": 0, "boost": 0, "shadows": 0, "highlights": 0,
        "curves": {k: copy.deepcopy(tone) for k in "yrgb"}, "hueVsHue": [], "hueVsSat": [], "hueVsLum": [], "lumVsSat": [], "lut": None,
    }


def new_grade() -> dict[str, Any]:
    return {"v": 1, "on": True, "nodes": [new_node("")]}


LOOKS: dict[str, dict[str, Any]] = {  # same names and numbers as the LOOKS on the Color page
    "Teal & Orange": {"lift": {"x": -0.8, "y": -0.15, "m": 0}, "gain": {"x": 0.6, "y": 0.35, "m": 0.02}, "contrast": 1.12, "saturation": 1.12},
    "Warm film": {"temp": 18, "tint": 4, "contrast": 1.08, "saturation": 1.05, "lift": {"x": 0.2, "y": 0.15, "m": 0.02}, "curves.y": [[0, 0.03], [0.5, 0.52], [1, 0.97]]},
    "Cold night": {"temp": -22, "gamma": {"x": -0.5, "y": -0.4, "m": -0.08}, "contrast": 1.1, "saturation": 0.9, "highlights": -10},
    "Bleach bypass": {"saturation": 0.55, "contrast": 1.3, "pivot": 0.45, "highlights": -6},
    "Faded matte": {"lift": {"x": 0, "y": 0, "m": 0.12}, "contrast": 0.92, "saturation": 0.9, "curves.y": [[0, 0.06], [1, 0.94]]},
    "Vivid pop": {"boost": 40, "saturation": 1.2, "contrast": 1.1},
    "Noir": {"saturation": 0, "contrast": 1.32, "curves.y": [[0, 0], [0.3, 0.2], [0.7, 0.8], [1, 1]]},
}


def _wheel(spec: Any) -> dict[str, float]:
    """A wheel as {x, y, m} (puck in the unit disc + master -1..1) or {color: 'orange'|degrees, amount: 0..1, master: -1..1}."""
    if not isinstance(spec, dict):
        raise TimelineError("a wheel is an object: {color, amount, master} or {x, y, m}")
    if "color" in spec or "amount" in spec:
        col = spec.get("color", 0)
        deg = NAMED_HUES.get(str(col).lower()) if not isinstance(col, (int, float)) else float(col)
        if deg is None:
            raise TimelineError(f"unknown colour {col!r}; use degrees or one of {', '.join(NAMED_HUES)}")
        amt = float(spec.get("amount", 0.3))
        if not 0 <= amt <= 1:
            raise TimelineError("amount must be 0..1")
        x, y = amt * math.cos(math.radians(deg)), amt * math.sin(math.radians(deg))   # same angle convention as the wheel ring (0 = red)
        m = float(spec.get("master", 0))
    else:
        x, y, m = float(spec.get("x", 0)), float(spec.get("y", 0)), float(spec.get("m", 0))
        r = math.hypot(x, y)
        if r > 1:
            x, y = x / r, y / r
    if not -1 <= m <= 1:
        raise TimelineError("a wheel master must be -1..1")
    return {"x": round(x, 3), "y": round(y, 3), "m": round(m, 3)}


def _apply_controls(node: dict[str, Any], controls: dict[str, Any]) -> list[str]:
    changed = []
    for k, v in controls.items():
        if k in SCALARS:
            lo, hi, _, _ = SCALARS[k]
            v = float(v)
            if not lo <= v <= hi:
                raise TimelineError(f"{k} must be {lo}..{hi} (got {v})")
            node[k] = v
        elif k in WHEELS:
            node[k] = _wheel(v)
        elif k == "curves.y":
            node["curves"]["y"] = [[float(a), float(b)] for a, b in v]
        else:
            raise TimelineError(f"unknown colour control {k!r}; controls are {', '.join([*SCALARS, *WHEELS])}")
        changed.append(k)
    return changed


def color_set(tl: dict[str, Any], clip: int | str | None, controls: dict[str, Any], node: int = 1, look: str | None = None) -> dict[str, Any]:
    """Set colour controls (and/or a named look) on node `node` (1-based; node count+1 adds a new serial node) of one clip or all."""
    if look and look not in LOOKS:
        raise TimelineError(f"unknown look {look!r}; looks are {', '.join(LOOKS)}")
    if not controls and not look:
        raise TimelineError("give some controls and/or a look")
    done = []
    for c in _targets(tl, clip):
        g = c.get("grade") or new_grade()
        nodes = g["nodes"]
        if not 1 <= node <= len(nodes) + 1:
            raise TimelineError(f"node must be 1..{len(nodes) + 1} (the last value adds a new node)")
        if node == len(nodes) + 1:
            nodes.append(new_node(look or ""))
        n = nodes[node - 1]
        changed = _apply_controls(n, LOOKS[look]) if look else []
        changed += _apply_controls(n, controls or {})
        g["on"] = True
        c["grade"] = g
        done.append({"clip": c.get("id"), "label": c.get("label"), "node": node, "changed": sorted(set(changed))})
    return {"graded": done}


def color_reset(tl: dict[str, Any], clip: int | str | None) -> dict[str, Any]:
    targets = _targets(tl, clip)
    for c in targets:
        c.pop("grade", None)
    return {"reset": [c.get("id") for c in targets]}


def color_copy(tl: dict[str, Any], from_clip: int | str, to_clip: int | str | None) -> dict[str, Any]:
    src = _clip(tl, from_clip)
    if not src.get("grade"):
        raise TimelineError("the source clip has no grade to copy")
    targets = [c for c in _targets(tl, to_clip) if c is not src]
    for c in targets:
        c["grade"] = copy.deepcopy(src["grade"])
    return {"copied_to": [c.get("id") for c in targets]}


# ---------- Fusion effects (node types/params mirror fusion-graph.js NODE_DEFS; the UI fills missing params with its defaults) ----------
EFFECTS: dict[str, str] = {
    "vignette": "radius 0..1.5, softness 0..1, opacity 0..1, color '#000000'",
    "film_grain": "intensity 0..1, size 0.5..4, roughness 0..1, animated bool",
    "glow": "threshold 0..1, size px, color, intensity 0..3",
    "blur": "radius px, blurType 'gaussian'|'directional', angle deg",
    "text_plus": "text, fontSize px, color, posX/posY 0..1, align, box bool, strokeWidth, glowSize",
    "color_corrector": "saturation, contrast, brightness, hue, tint color, tintStrength",
    "transform": "posX/posY px, scale, rotation deg, flipH/flipV",
    "camera_shake": "frequency, amplitude px, rotShake deg, decay",
    "chroma_keyer": "keyColor, tolerance, softness, despill",
}


def _new_graph() -> dict[str, Any]:
    return {"version": 1, "enabled": True,
            "nodes": [{"id": "media_in", "type": "mediain", "label": "MediaIn1", "pos": {"x": 80, "y": 140}, "params": {"enabled": True}},
                      {"id": "media_out", "type": "mediaout", "label": "MediaOut1", "pos": {"x": 520, "y": 140}, "params": {"enabled": True}}],
            "connections": [{"from": {"nodeId": "media_in", "socket": "output"}, "to": {"nodeId": "media_out", "socket": "input"}}]}


def fusion_add(tl: dict[str, Any], clip: int | str | None, effect: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Insert an effect just before MediaOut on one clip or all (the same as the Fusion page's '+ Effect' buttons)."""
    if effect not in EFFECTS:
        raise TimelineError(f"unknown effect {effect!r}; effects are {', '.join(EFFECTS)}")
    out = []
    for c in _targets(tl, clip):
        g = c.get("fusion") or _new_graph()
        count = sum(1 for n in g["nodes"] if n["type"] == effect) + 1
        nid = f"{effect}_{secrets.token_hex(3)}"
        g["nodes"].append({"id": nid, "type": effect, "label": f"{effect}{count}", "pos": {"x": 280 + 30 * count, "y": 140},
                           "params": {**(params or {}), "enabled": True}})
        conns = g["connections"]
        into_out = next((x for x in conns if x["to"]["nodeId"] == "media_out"), None)
        prev = into_out["from"] if into_out else {"nodeId": "media_in", "socket": "output"}
        g["connections"] = [x for x in conns if x["to"]["nodeId"] != "media_out"]
        g["connections"] += [{"from": prev, "to": {"nodeId": nid, "socket": "input"}},
                             {"from": {"nodeId": nid, "socket": "output"}, "to": {"nodeId": "media_out", "socket": "input"}}]
        c["fusion"] = g
        out.append({"clip": c.get("id"), "node": nid})
    return {"added": out}


def fusion_clear(tl: dict[str, Any], clip: int | str | None) -> dict[str, Any]:
    targets = _targets(tl, clip)
    for c in targets:
        c.pop("fusion", None)
    return {"cleared": [c.get("id") for c in targets]}


# ---------- what an agent reads first ----------
def summary(tl: dict[str, Any]) -> list[dict[str, Any]]:
    rows, t = [], 0.0
    for i, c in enumerate(tl.get("clips") or [], 1):
        dur = (float(c.get("out", 0)) - float(c.get("in", 0))) / float(c.get("speed") or 1)
        g = c.get("grade")
        rows.append({"clip": i, "id": c.get("id"), "label": c.get("label"), "src": c.get("src"), "start": round(t, 2), "duration": round(dur, 2),
                     "grade": None if not g else [{k: n[k] for k in [*SCALARS, *WHEELS] if n.get(k) != new_node()[k]} for n in g.get("nodes", [])],
                     "effects": [n["type"] for n in (c.get("fusion") or {}).get("nodes", []) if n["type"] not in ("mediain", "mediaout")]})
        t += dur
    return rows


def describe() -> dict[str, Any]:
    return {
        "how": "Read the timeline (clips are 1-based in timeline order), then change it with color_set / color_copy / fusion_add. "
               "The studio picks the change up within ~2 s and shows it on the monitor; the export renders exactly the same grade and effects.",
        "scalars": {k: {"min": lo, "max": hi, "neutral": d, "does": why} for k, (lo, hi, d, why) in SCALARS.items()},
        "wheels": {"lift": "shadows", "gamma": "midtones", "gain": "highlights", "offset": "whole picture",
                   "value": "{color: name|degrees, amount: 0..1, master: -1..1} - master is the brightness of that range; or raw {x, y, m}",
                   "colors": NAMED_HUES},
        "looks": list(LOOKS),
        "nodes": "a grade is a serial stack of nodes; node N+1 adds a new node on top (good for a look over a correction)",
        "effects": EFFECTS,
    }


OPS = {"color_set", "color_reset", "color_copy", "fusion_add", "fusion_clear"}


def apply_op(tl: dict[str, Any], op: str, args: dict[str, Any]) -> dict[str, Any]:
    if op == "color_set":
        return color_set(tl, args.get("clip"), args.get("controls") or {}, int(args.get("node", 1)), args.get("look"))
    if op == "color_reset":
        return color_reset(tl, args.get("clip"))
    if op == "color_copy":
        return color_copy(tl, args["from_clip"], args.get("to_clip"))
    if op == "fusion_add":
        return fusion_add(tl, args.get("clip"), args["effect"], args.get("params"))
    if op == "fusion_clear":
        return fusion_clear(tl, args.get("clip"))
    raise TimelineError(f"unknown op {op!r}; ops are {', '.join(sorted(OPS))}")
