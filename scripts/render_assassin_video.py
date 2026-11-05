import json
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageFilter, ImageDraw, ImageFont

PROJECT_DIR = Path("output/Regressed_Assassin_Duke")
AUDIO_DIR = PROJECT_DIR / "audio"
FRAMES_DIR = PROJECT_DIR / "render_frames"
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
SHORTS_DIR = PROJECT_DIR / "viral_shorts"
SHORTS_DIR.mkdir(parents=True, exist_ok=True)

MASTER_AUDIO = AUDIO_DIR / "master_narration.wav"
FINAL_VIDEO = PROJECT_DIR / "The_Regressed_Son_Of_A_Duke_Is_An_Assassin_Ep1_1080p.mp4"

WIDTH = 1920
HEIGHT = 1080

def build_composite_frame(shot: dict, out_path: Path):
    im_path = Path(shot["image_path"])
    with Image.open(im_path) as src:
        im = src.convert("RGB")
    
    # 1. Background: resized & blurred
    bg = im.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(35))
    dark = Image.new("RGB", (WIDTH, HEIGHT), (12, 12, 18))
    bg = Image.blend(bg, dark, 0.65)
    
    # 2. Foreground: fit nicely
    max_w = int(WIDTH * 0.82)
    max_h = int(HEIGHT * 0.88)
    fg = im.copy()
    fg.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    
    # Border
    border_w = 4
    bordered_fg = Image.new("RGB", (fg.width + border_w * 2, fg.height + border_w * 2), (218, 165, 32)) # Gold border
    bordered_fg.paste(fg, (border_w, border_w))
    
    ox = (WIDTH - bordered_fg.width) // 2
    oy = (HEIGHT - bordered_fg.height) // 2 - 15
    bg.paste(bordered_fg, (ox, oy))
    
    # 3. Lower Third Banner
    draw = ImageDraw.Draw(bg)
    bar_h = 50
    bar_y = HEIGHT - 70
    draw.rectangle([ox, bar_y, ox + bordered_fg.width, bar_y + bar_h], fill=(10, 10, 15, 220))
    # Border line for banner
    draw.line([ox, bar_y, ox + bordered_fg.width, bar_y], fill=(218, 165, 32), width=2)
    
    # Text
    act_label = f"ACT {shot['act']} | {shot['title'].upper()}"
    series_label = "THE REGRESSED SON OF A DUKE IS AN ASSASSIN (CH 1-5)"
    
    draw.text((ox + 25, bar_y + 8), act_label, fill=(255, 215, 0))
    draw.text((ox + 25, bar_y + 28), series_label, fill=(180, 180, 195))
    
    bg.save(str(out_path), quality=92)

def generate_all_frames(shots: list):
    print(f"Generating {len(shots)} composite 1080p frames...", flush=True)
    t0 = time.time()
    concat_lines = []
    
    for idx, shot in enumerate(shots):
        f_name = f"frame_{idx:04d}.jpg"
        f_path = FRAMES_DIR / f_name
        build_composite_frame(shot, f_path)
        
        # Concat demuxer format:
        # file 'path'
        # duration X.XX
        concat_lines.append(f"file '{f_path.resolve()}'")
        concat_lines.append(f"duration {shot['duration']:.3f}")
        
        if (idx + 1) % 25 == 0 or idx == len(shots) - 1:
            print(f"  Processed {idx + 1}/{len(shots)} frames...", flush=True)
            
    # Concat demuxer requires repeating the last file
    if shots:
        last_f = FRAMES_DIR / f"frame_{len(shots)-1:04d}.jpg"
        concat_lines.append(f"file '{last_f.resolve()}'")
        
    concat_file = FRAMES_DIR / "concat_list.txt"
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    print(f"Frames generated in {time.time() - t0:.1f}s. Concat file written.", flush=True)
    return concat_file

def render_master_video(concat_file: Path):
    print("\n=== Encoding 1080p Master Video with NVENC ===", flush=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file.resolve()),
        "-i", str(MASTER_AUDIO.resolve()),
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-b:v", "4500k",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(FINAL_VIDEO.resolve())
    ]
    t0 = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("NVENC failed, falling back to libx264...", flush=True)
        cmd[cmd.index("h264_nvenc")] = "libx264"
        cmd[cmd.index("-preset") + 1] = "fast"
        res = subprocess.run(cmd, capture_output=True, text=True)
        
    if res.returncode == 0 and FINAL_VIDEO.exists():
        size_mb = FINAL_VIDEO.stat().st_size / (1024 * 1024)
        print(f"[SUCCESS] Final Video Created: {FINAL_VIDEO}")
        print(f"  Size: {size_mb:.2f} MB")
        print(f"  Render time: {time.time() - t0:.1f}s")
    else:
        print("Error during video render:")
        print(res.stderr[-500:])

def extract_viral_shorts():
    print("\n=== Extracting 3 High-Hook Viral Shorts (9:16 Vertical) ===", flush=True)
    # Short 1: Rebirth Hook (Act 1 climax into Act 2)
    # Short 2: Training Ground Duel (Act 4)
    # Short 3: The Hit List Vow (Act 5)
    
    shorts_config = [
        {
            "name": "Short_1_The_Execution_and_Rebirth.mp4",
            "start": "02:00",
            "duration": "58",
            "title": "Killed by his family after 30 years... and regressed as a child!"
        },
        {
            "name": "Short_2_Training_Ground_Bloodlust.mp4",
            "start": "13:30",
            "duration": "59",
            "title": "A 10-year-old child unleashes the bloodlust of a veteran assassin!"
        },
        {
            "name": "Short_3_The_Hit_List_Vow.mp4",
            "start": "16:30",
            "duration": "55",
            "title": "I am no longer your hunting dog. I am the hunter."
        }
    ]
    
    for s in shorts_config:
        out_short = SHORTS_DIR / s["name"]
        print(f"Rendering {s['name']} (from {s['start']} for {s['duration']}s)...", flush=True)
        # Crop 1920x1080 horizontal into centered 607x1080, then scale to 1080x1920 with top/bottom bars or 9:16 fit
        # Standard 9:16 crop filter: crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920
        cmd = [
            "ffmpeg", "-y",
            "-ss", s["start"],
            "-i", str(FINAL_VIDEO.resolve()),
            "-t", s["duration"],
            "-vf", "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920",
            "-c:v", "h264_nvenc",
            "-b:v", "3500k",
            "-c:a", "aac",
            str(out_short.resolve())
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and out_short.exists():
            print(f"  [OK] Created {s['name']} ({out_short.stat().st_size / (1024*1024):.2f} MB)")
        else:
            print(f"  Failed: {res.stderr[-200:]}")

def generate_youtube_package():
    with open(AUDIO_DIR / "timing_manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    lines = [
        "# YouTube Monetization & Packaging Suite",
        "## The Regressed Son Of A Duke Is An Assassin (Chapters 1 - 5 Recap)",
        "",
        "### 🎯 High-CTR YouTube Title Options (Copy & Paste):",
        "1. He Spent 30 Years As The Family's Disposable Assassin, Then Woke Up As A 10-Year-Old Prodigy! (Ch 1-5)",
        "2. Betrayed And Executed By His Father, He Regresses Into His Childhood Body With Full Bloodlust Intact",
        "3. (Manhwa Recap) The Duke Raised Him As A Hunting Dog, But He Reborn To Destroy Them All (Part 1)",
        "",
        "### ⏱️ Video Timestamps (Chapters):"
    ]
    
    # Add chapter timestamps
    for b in manifest["beats"]:
        m = int(b["start_sec"] // 60)
        s = int(b["start_sec"] % 60)
        lines.append(f"{m:02d}:{s:02d} - {b['title']}")
        
    lines.extend([
        "",
        "### 📝 YouTube Video Description:",
        "Welcome to today's manhwa recap! Today we dive into the epic regression story 'The Regressed Son Of A Duke Is An Assassin' covering Chapters 1 to 5.",
        "",
        "Cyan Vert spent thirty agonizing years living as House Vert's secret shadow dog—carrying out assassinations, drinking poisons, and securing their glory. But once his brother inherited the duchy, Cyan was rewarded with a guillotine blade in the snow.",
        "",
        "Opening his eyes, Cyan finds himself back in his fragile 10-year-old body before his nightmare ever began. With thirty years of apex killing instincts and a pure, unblemished mana core, Cyan vows to never be their hunting dog again.",
        "",
        "🔔 Subscribe and turn on notifications for Part 2!",
        "💬 Comment below: Would you spare the Duke or eliminate everyone on the hit list?",
        "",
        "### 🏷️ High-Ranking SEO Tags (Comma-Separated for YouTube Studio):",
        "The Regressed Son Of A Duke Is An Assassin, The Regressed Son Of A Duke Is An Assassin recap, manhwa recap, anime recap, regression manhwa, assassin manhwa, overpowered mc, manhwa explained, manhua recap, best manhwa, webtoon recap, Cyan Vert, panel flow studio",
        "",
        "### 📱 Viral Shorts Packaged:",
        "1. Short_1_The_Execution_and_Rebirth.mp4 (TikTok / Shorts hook)",
        "2. Short_2_Training_Ground_Bloodlust.mp4 (Action duel climax)",
        "3. Short_3_The_Hit_List_Vow.mp4 (Vengeance declaration)"
    ])
    
    pkg_file = PROJECT_DIR / "YOUTUBE_PACKAGE.md"
    pkg_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nYouTube Packaging Suite saved to: {pkg_file}")

def main():
    with open(PROJECT_DIR / "shots_plan.json", "r", encoding="utf-8") as f:
        shots = json.load(f)
    
    concat_file = generate_all_frames(shots)
    render_master_video(concat_file)
    extract_viral_shorts()
    generate_youtube_package()

if __name__ == "__main__":
    main()
