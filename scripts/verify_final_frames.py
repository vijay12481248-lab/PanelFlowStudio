import subprocess, sys, os
sys.path.insert(0, '.')
from pathlib import Path
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine

mp4_path = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\renders\demon_magic_emperor_-_chapter_926_-_real_and_fake_maps_standard_1080p_8d705608.mp4"
out_dir = Path(r"scratch\crop_inspection\final_video_frames")
out_dir.mkdir(exist_ok=True)

timestamps = [3.0, 40.0, 95.0, 150.0, 275.0, 320.0]
engine = WindowsMediaOCREngine()

keywords = ['manhuaplus', 'discord', 'patreon', 'paypal', 'faster release', 'read on', 'read first']

for ts in timestamps:
    frame_path = out_dir / f"frame_{int(ts)}s.jpg"
    cmd = [
        "ffmpeg", "-y", "-ss", str(ts), "-i", mp4_path,
        "-vframes", "1", "-q:v", "2", str(frame_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    res = engine.extract_text(frame_path, f"f_{ts}")
    all_texts = [r.detected_text for r in res.regions]
    found_promo = [t for t in all_texts if any(k in t.lower() for k in keywords)]
    print(f"Frame at {ts}s: {len(all_texts)} text blocks found.")
    if found_promo:
        print(f"  WARNING PROMO DETECTED: {found_promo}")
    else:
        print(f"  Clean: No promo text! Sample text: {all_texts[:2]}")

print("Verification complete!")
