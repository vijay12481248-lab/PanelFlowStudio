import subprocess, sys, os
sys.path.insert(0, '.')
from pathlib import Path
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine

mp4_path = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\renders\demon_magic_emperor_-_chapter_926_-_real_and_fake_maps_standard_1080p_4d4df85f.mp4"
out_dir = Path(r"scratch\crop_inspection\sync_verified_frames")
out_dir.mkdir(exist_ok=True)

test_points = [
    (2.0, "Seq 02 (Opening Scene - I'm back)", ["back", "returns"]),
    (12.0, "Seq 04 (Hurry up / impatient)", ["impatient", "hurry"]),
    (106.0, "Seq 14 (Angry shouting face - not harem)", ["harem", "scouting", "supposed"]),
    (158.0, "Seq 23 (The Soaring Sword)", ["soaring", "sword", "weapon"]),
    (252.0, "Seq 35 (Not two Sword Kings, only Feiyun)", ["sword", "kings", "feiyun"]),
    (290.0, "Seq 40 (Congratulations Clan Head)", ["congratulations", "gift", "succeed"]),
]

engine = WindowsMediaOCREngine()

for ts, expected_scene, expected_keywords in test_points:
    frame_path = out_dir / f"sync_frame_{int(ts)}s.jpg"
    cmd = [
        "ffmpeg", "-y", "-ss", str(ts), "-i", mp4_path,
        "-vframes", "1", "-q:v", "2", str(frame_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    res = engine.extract_text(frame_path, f"sync_{ts}")
    all_texts = [r.detected_text for r in res.regions]
    combined_text = " ".join(all_texts).lower()
    
    matches = [k for k in expected_keywords if k in combined_text]
    print(f"\n[t={ts:.1f}s] Expected: {expected_scene}")
    print(f"  Detected Text (sample): {all_texts[:3]}")
    print(f"  Keyword Match: {matches} -> {'PERFECT SYNC!' if matches else 'Check'}")

print("\nVerification script complete!")
