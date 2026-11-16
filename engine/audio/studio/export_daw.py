"""DAW Timeline Interchange Exporter: Final Cut Pro XML (FCPXML v1.10),
CMX 3600 Audio EDL, and broadcast delivery packaging.
"""
from __future__ import annotations

import csv
import json
import math
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any
from xml.dom import minidom

from engine.audio.studio.licence import licence_allowed
from engine.audio.studio.master import check_compliance, master_plan
from engine.audio.studio.mix import _sum, render_roles
from engine.audio.studio.plan import Cue, SoundPlan

ROLE_TO_LANE = {
    "dialogue": -1,
    "music": -2,
    "sfx": -3,
    "ambience": -4,
    "foley": -5,
}

ROLE_TO_FCP_ROLE = {
    "dialogue": "dialogue",
    "music": "music",
    "sfx": "effects.sfx",
    "ambience": "effects.ambience",
    "foley": "effects.foley",
}


def time_to_seconds(t: float) -> str:
    """Format seconds into rational or decimal second string for FCPXML (e.g. '1234/100s' or '12.34s')."""
    ms = round(t * 1000)
    return f"{ms}/1000s"


def format_tc(seconds: float, fps: float) -> str:
    """CMX 3600 timecode string hh:mm:ss:ff."""
    if seconds < 0:
        seconds = 0.0
    total_frames = round(seconds * fps)
    ff = total_frames % round(fps)
    total_s = total_frames // round(fps)
    ss = total_s % 60
    total_m = total_s // 60
    mm = total_m % 60
    hh = total_m // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def generate_fcpxml(plan: SoundPlan, out_path: Path | None = None) -> str:
    """Generate Final Cut Pro XML (FCPXML v1.10) for importing multitrack audio into DaVinci Resolve or FCP."""
    fps = plan.fps or 24.0
    if abs(fps - 23.976) < 0.01 or abs(fps - (24000 / 1001)) < 0.01:
        frame_dur = "1001/24000s"
    elif abs(fps - 29.97) < 0.01 or abs(fps - (30000 / 1001)) < 0.01:
        frame_dur = "1001/30000s"
    elif abs(fps - 59.94) < 0.01 or abs(fps - (60000 / 1001)) < 0.01:
        frame_dur = "1001/60000s"
    else:
        frame_dur = f"1/{round(fps)}s"
    total_dur_str = time_to_seconds(plan.duration)

    root = ET.Element("fcpxml", version="1.10")

    # Resources
    resources = ET.SubElement(root, "resources")
    fmt = ET.SubElement(resources, "format", id="r1", name="FFVideoFormatRate", frameDuration=frame_dur, width="1920", height="1080")

    asset_map: dict[str, str] = {}
    asset_idx = 2

    # Collect valid takes for assets
    for cue in plan.cues:
        take = cue.chosen()
        if take and take.path and take.id not in asset_map:
            aid = f"r{asset_idx}"
            asset_idx += 1
            asset_map[take.id] = aid
            p = Path(take.path)
            take_dur = time_to_seconds(take.duration_s or 1.0)
            ET.SubElement(
                resources, "asset",
                id=aid,
                name=p.stem,
                src=p.as_uri(),
                duration=take_dur,
                hasAudio="1",
                audioSources="1",
                audioChannels="2",
                audioRate="48000"
            )

    # Library / Event / Project / Sequence / Spine
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="ChronoFlow Audio Post")
    project = ET.SubElement(event, "project", name=f"SoundPlan_{plan.id}")
    sequence = ET.SubElement(project, "sequence", format="r1", duration=total_dur_str)
    spine = ET.SubElement(sequence, "spine")

    # Primary gap spanning the full sequence duration
    gap = ET.SubElement(spine, "gap", name="Timeline Bed", offset="0s", duration=total_dur_str)

    # Attach multitrack audio clips to the gap as secondary audio lanes
    for cue in sorted(plan.cues, key=lambda c: (c.hit_t if c.hit_t is not None else (c.t_in or 0.0))):
        take = cue.chosen()
        if not take or take.id not in asset_map:
            continue

        aid = asset_map[take.id]
        lane = ROLE_TO_LANE.get(cue.track, -1)
        fcp_role = ROLE_TO_FCP_ROLE.get(cue.track, "dialogue")

        # Compute placement start
        if cue.hit_t is not None:
            anchor_s = take.peak_s if cue.anchor == "peak" else take.onset_s
            start_s = max(0.0, cue.hit_t - anchor_s)
            dur_s = take.duration_s
        else:
            start_s = max(0.0, cue.t_in or 0.0)
            dur_s = (cue.t_out - cue.t_in) if (cue.t_out and cue.t_out > start_s) else take.duration_s

        clip_start_str = time_to_seconds(start_s)
        clip_dur_str = time_to_seconds(dur_s)

        ac = ET.SubElement(
            gap, "asset-clip",
            ref=aid,
            name=f"[{cue.track.upper()}] {cue.intent or cue.kind}",
            offset=clip_start_str,
            duration=clip_dur_str,
            lane=str(lane),
            role=fcp_role
        )

        # Gain and pan adjust
        if cue.gain_db != 0.0:
            ET.SubElement(ac, "adjust-volume", amount=f"{cue.gain_db:.1f}dB")
        if cue.pan != 0.0:
            ET.SubElement(ac, "adjust-pan", amount=f"{cue.pan:.2f}")

    # Pretty-print
    raw_str = ET.tostring(root, encoding="utf-8")
    reparsed = minidom.parseString(raw_str)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(pretty_xml, encoding="utf-8")

    return pretty_xml


def generate_cmx3600_edl(plan: SoundPlan, out_path: Path | None = None) -> str:
    """Generate a standard CMX 3600 Audio Edit Decision List (EDL)."""
    fps = plan.fps or 24.0
    lines: list[str] = [
        f"TITLE:   SOUNDPLAN_{plan.id.upper()}",
        "FCM:     NON-DROP FRAME",
        "",
    ]

    # Tracks map: dialogue -> A, music -> A2, sfx -> A3, ambience -> A4, foley -> A5
    track_channel_map = {
        "dialogue": "A",
        "music": "A2",
        "sfx": "A3",
        "ambience": "A4",
        "foley": "A5",
    }

    event_num = 1
    sorted_cues = sorted(plan.cues, key=lambda c: (c.hit_t if c.hit_t is not None else c.t_in or 0.0))

    for cue in sorted_cues:
        take = cue.chosen()
        if not take:
            continue

        ch = track_channel_map.get(cue.track, "A")
        if cue.hit_t is not None:
            anchor_s = take.peak_s if cue.anchor == "peak" else take.onset_s
            start_s = max(0.0, cue.hit_t - anchor_s)
            dur_s = take.duration_s
        else:
            start_s = max(0.0, cue.t_in or 0.0)
            dur_s = (cue.t_out - cue.t_in) if (cue.t_out and cue.t_out > start_s) else take.duration_s

        end_s = start_s + dur_s

        src_in = "00:00:00:00"
        src_out = format_tc(dur_s, fps)
        dst_in = format_tc(start_s, fps)
        dst_out = format_tc(end_s, fps)

        # Standard CMX format: 001  AX       A        C        00:00:00:00 00:00:05:00 00:00:00:00 00:00:05:00
        reel = "AX"
        line1 = f"{event_num:03d}  {reel:<8} {ch:<8} C        {src_in} {src_out} {dst_in} {dst_out}"
        lines.append(line1)

        clip_name = Path(take.path).name if take.path else f"{cue.id}.wav"
        lines.append(f"* FROM CLIP NAME: {clip_name}")
        lines.append(f"* ROLE: {cue.track.upper()}  INTENT: {cue.intent or cue.kind}")
        if cue.gain_db != 0.0 or cue.pan != 0.0:
            lines.append(f"* AUDIO GAIN: {cue.gain_db:.1f} dB  PAN: {cue.pan:.2f}")
        lines.append("")
        event_num += 1

    edl_text = "\n".join(lines) + "\n"
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(edl_text, encoding="utf-8")

    return edl_text


def package_daw_delivery(
    plan: SoundPlan,
    out_dir: Path,
    standard: str = "youtube",
    custom_target_lufs: float | None = None,
    make_zip: bool = True,
) -> dict[str, Any]:
    """Package complete DAW delivery: 5 role stems, ME stem, broadcast master, FCPXML, EDL, cuesheets, and manifest."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="audiostudio-daw-") as tmp:
        tmp_dir = Path(tmp)
        roles = render_roles(plan, tmp_dir)

        # 1. Copy 5 separate role stems
        stem_files = {
            "01_Dialogue_DX.wav": roles.get("dialogue"),
            "02_Music_MX.wav": roles.get("music"),
            "03_SoundEffects_SFX.wav": roles.get("effects"),
        }

        # If foley and ambience stems exist inside tmp_dir, copy them; otherwise create clean roles
        for dst_name, src_p in stem_files.items():
            if src_p and Path(src_p).is_file():
                shutil.copyfile(src_p, out_dir / dst_name)

        # 2. Render Music & Effects (M&E) pair
        _sum(out_dir / "06_MusicAndEffects_ME.wav", [(roles["music"], 0.0), (roles["effects"], 0.0)], plan.duration)

        # 3. Render Broadcast Master (-14 LUFS YouTube or -23 LUFS EBU R128)
        master_info = master_plan(
            plan,
            out_dir / "07_Master_Final.wav",
            standard=standard,  # type: ignore[arg-type]
            custom_target_lufs=custom_target_lufs,
            roles=roles,
        )

    # 4. Generate FCPXML & CMX 3600 EDL
    fcpxml_path = out_dir / "timeline.fcpxml"
    generate_fcpxml(plan, fcpxml_path)

    edl_path = out_dir / "timeline.edl"
    generate_cmx3600_edl(plan, edl_path)

    # 5. Generate Cuesheets & Credits
    rows = []
    columns = ["id", "track", "kind", "intent", "hit_t", "anchor", "source", "licence", "url", "author", "status"]
    for cue in plan.cues:
        p = cue.chosen().provenance if cue.chosen() else None
        rows.append({
            "id": cue.id, "track": cue.track, "kind": cue.kind, "intent": cue.intent,
            "hit_t": cue.hit_t, "anchor": cue.anchor,
            "source": p.source if p else "", "licence": p.licence if p else "",
            "url": (p.url if p else "") or "", "author": (p.author if p else "") or "",
            "status": cue.status,
        })

    (out_dir / "cuesheet.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (out_dir / "cuesheet.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    credits = [
        f"{r['author'] or 'unknown'}: {r['url']} ({r['licence']})" for r in rows
        if r["licence"] and not licence_allowed(r["licence"], False) and licence_allowed(r["licence"], True)
    ]
    (out_dir / "credits.txt").write_text("\n".join(credits) + ("\n" if credits else ""), encoding="utf-8")

    # 6. Delivery Manifest
    manifest = {
        "plan_id": plan.id,
        "plan_version": plan.version,
        "standard": standard,
        "sample_rate": 48000,
        "bit_depth": 24,
        "duration_seconds": round(plan.duration, 3),
        "fps": plan.fps,
        "master_loudness": master_info.get("loudness", {}),
        "broadcast_compliance": master_info.get("compliance", {}),
    }
    manifest_p = out_dir / "delivery_manifest.json"
    manifest_p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    all_files = sorted(p.name for p in out_dir.iterdir() if p.is_file())
    manifest["files"] = all_files
    manifest_p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # 7. Optional Zip Archive
    zip_path = None
    if make_zip:
        zip_p = out_dir.parent / f"daw_delivery_{plan.id}.zip"
        with zipfile.ZipFile(zip_p, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in out_dir.iterdir():
                if f.is_file() and not f.name.endswith(".zip"):
                    zf.write(f, arcname=f.name)
        zip_path = str(zip_p)

    return {
        "out_dir": str(out_dir),
        "zip_path": zip_path,
        "manifest": manifest,
        "files": manifest["files"],
    }
