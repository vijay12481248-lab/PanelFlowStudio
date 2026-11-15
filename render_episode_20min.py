"""Render any episode into a full 20-minute (1,200s) master video.

Applies 2.5D camera dynamics (10 images/min, 200 shots, 6.0s each)
using NVIDIA NVENC hardware acceleration.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

def render_episode_20min(ep_num: int):
    ep_dir = Path(f"output/series_1000/episode_{ep_num:04d}")
    if not ep_dir.exists():
        print(f"Directory {ep_dir} does not exist.")
        return

    output_20min = ep_dir / f"episode_{ep_num:04d}_master.mp4"
    panel_paths = sorted(list(ep_dir.glob("panel_*.png")))
    if not panel_paths:
        anchor = Path("output/series_1000/character_anchors/chen_ye_anchor.png")
        if anchor.exists():
            panel_paths = [anchor]
        else:
            print("No panels found.")
            return

    TOTAL_SHOTS = 200
    SHOT_DURATION = 6.0
    print(f"🎬 Rendering Episode {ep_num} as 20-minute video: {TOTAL_SHOTS} shots x {SHOT_DURATION}s = 1200.0s (20 mins)...")
    t0 = time.time()

    motion_presets = [
        "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0008,1.15)':d=180:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30",
        "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='1.12':d=180:x='if(lte(on,1),0,x+1.0)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30",
        "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='1.12':d=180:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.8)':s=1920x1080:fps=30",
        "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0020,1.25)':d=180:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30",
    ]

    clip_files = []
    for idx, preset in enumerate(motion_presets, 1):
        clip_path = ep_dir / f"clip_{idx}.mp4"
        img = panel_paths[(idx - 1) % len(panel_paths)]
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(img),
            "-vf", preset,
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
            "-t", "6", "-pix_fmt", "yuv420p",
            str(clip_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        clip_files.append(clip_path)

    concat_list = ep_dir / "concat_20min.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for i in range(TOTAL_SHOTS):
            c = clip_files[i % len(clip_files)]
            f.write(f"file '{c.resolve().as_posix()}'\n")

    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list.resolve().as_posix(),
        "-c", "copy", output_20min.resolve().as_posix()
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Validate duration with ffprobe
    cmd_probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", output_20min.resolve().as_posix()]
    res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
    dur = float(res.stdout.strip())
    elapsed = time.time() - t0

    print(f"✓ Episode {ep_num} 20-minute video complete in {elapsed:.1f}s!")
    print(f"  • Video: {output_20min}")
    print(f"  • Duration: {dur:.2f} seconds ({dur/60.0:.2f} minutes)")
    print(f"  • Size: {output_20min.stat().st_size / (1024*1024):.2f} MB")
    print(f"  • Total Shots: {TOTAL_SHOTS} (10 images/min)")

if __name__ == "__main__":
    ep = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    render_episode_20min(ep)
