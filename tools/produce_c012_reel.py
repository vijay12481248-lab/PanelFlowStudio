"""Production script for C012 The Quiet Backup Reel.

1. Generates 6 still frames using Z-Image Turbo (ArtEngine).
2. Generates 6 video clips using ChronoFlow MiniMax H3 Turbo.
3. Generates neural narration voiceover using Edge TTS.
4. Synthesizes synchronized foley sound effects & rhythmic music bed.
5. Applies dynamic camera angles (push-in, tracking, punch-in, wide reveal).
6. Assembles the final 40-second master Reel with styled captions.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import edge_tts
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.comfyui.art import ArtEngine
from engine.chronoflow.pipeline import ChronoFlowPipeline, COMFY_INPUT_DIR

OUT_DIR = ROOT / "output" / "c012_quiet_backup"
IMG_DIR = OUT_DIR / "images"
CLIP_DIR = OUT_DIR / "clips"
SEG_DIR = OUT_DIR / "seg"
AUDIO_DIR = OUT_DIR / "audio"
FINAL_DIR = OUT_DIR / "final"

for d in (IMG_DIR, CLIP_DIR, SEG_DIR, AUDIO_DIR, FINAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

SR = 48000
W, H = 1080, 1920
NEGATIVE = "extra limbs, duplicated characters, inconsistent clothes, changed head/body proportions, malformed hands, random text, logos, watermark, unwanted objects, style drift, 3d render, photo"
LORA4 = "minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors"
CLIP_W, CLIP_H = 480, 832

SHOTS = [
    {
        "id": "s1",
        "dur": 3.0,
        "seed_img": 3011,
        "seed_clip": 4011,
        "camera": "push_in",
        "scale_start": 1.0,
        "scale_end": 1.15,
        "line": "At the party, a friend freezes, mortified after an awkward dance move.",
        "img_prompt": (
            "Single still frame, vertical 9:16. Minimalist warm dance floor. A stickman dancer with round white head and orange beanie "
            "freezes in an awkward, silly dance pose with one arm up and knees bent, looking mortified. On the side, stickman Pip with teal scarf watches. "
            "Tight close-up, slight push-in. Crisp flat 2D line art, clean silhouette, awkward tension, soft consistent lighting."
        ),
        "video_prompt": (
            "A stickman dancer with an orange beanie freezes in a goofy dance pose, trembling slightly with embarrassment. "
            "Pip in a teal scarf watches with concern from the side. The camera does a slight push-in. "
            "Only the characters move slightly; everything else stays exactly as drawn in the same flat doodle style, no text, no speech bubbles."
        ),
    },
    {
        "id": "s2",
        "dur": 6.0,
        "seed_img": 3012,
        "seed_clip": 4012,
        "camera": "medium_drift",
        "scale_start": 1.0,
        "scale_end": 1.07,
        "line": "Everyone is staring. But Pip refuses to let their friend stand alone.",
        "img_prompt": (
            "Single still frame, vertical 9:16. Medium shot. Pip in teal scarf steps forward toward the dance floor with a determined, friendly look, "
            "ready to back up his frozen friend in the orange beanie. Minimalist warm hall background. Crisp flat 2D line art, clean silhouette."
        ),
        "video_prompt": (
            "Stickman Pip in a teal scarf steps forward decisively toward the frozen friend in the orange beanie, nodding with friendly determination. "
            "Clear anticipation in movement. The camera is a static medium shot. "
            "Only the characters move; flat 2D doodle style, no text, no speech bubbles."
        ),
    },
    {
        "id": "s3",
        "dur": 7.0,
        "seed_img": 3013,
        "seed_clip": 4013,
        "camera": "reaction_punch",
        "scale_start": 1.0,
        "scale_end": 1.18,
        "line": "Without hesitation, Pip jumps right in, copying the exact same silly pose.",
        "img_prompt": (
            "Single still frame, vertical 9:16. Wide shot. Pip in teal scarf stands right beside his friend in orange beanie, "
            "proudly striking the exact same ridiculous goofy dance pose with a huge grin, committing completely. Comic relief. "
            "Crisp flat 2D line art, clean silhouette, soft warm lighting."
        ),
        "video_prompt": (
            "Two stick-figure friends: Pip in a teal scarf and friend in an orange beanie, doing the same goofy dance move side by side. "
            "Pip grooves energetically with full confidence. Lively comedic dance motion. Static camera shot. "
            "Flat 2D doodle style, no text, no speech bubbles."
        ),
    },
    {
        "id": "s4",
        "dur": 7.0,
        "seed_img": 3014,
        "seed_clip": 4014,
        "camera": "over_shoulder_push",
        "scale_start": 1.04,
        "scale_end": 1.14,
        "line": "Suddenly, the awkward silence breaks into genuine smiles.",
        "img_prompt": (
            "Single still frame, vertical 9:16. Over-shoulder view of onlookers watching Pip and his friend dancing goofily. "
            "The onlookers smile and start nodding their heads to the rhythm, appreciating the fun. "
            "Crisp flat 2D line art, clean silhouette, soft warm lighting."
        ),
        "video_prompt": (
            "Onlookers watch the two dancing stickmen, their heads bobbing to the beat with bright smiles, clapping their hands gently. "
            "Warm surprise and amusement in movement. The camera does a slow subtle push. "
            "Flat 2D doodle style, no text, no speech bubbles."
        ),
    },
    {
        "id": "s5",
        "dur": 11.0,
        "seed_img": 3015,
        "seed_clip": 4015,
        "camera": "restrained_push",
        "scale_start": 1.0,
        "scale_end": 1.12,
        "line": "One by one, the whole room joins in, turning embarrassment into celebration.",
        "img_prompt": (
            "Single still frame, vertical 9:16. A whole group of stick-figure friends dancing together in a row across the floor, "
            "all copying the goofy move with arms waving and joyful smiles, Pip and his friend at the center celebrating. "
            "Crisp flat 2D line art, clean silhouette, soft warm lighting."
        ),
        "video_prompt": (
            "A group of stick figures dances joyfully together in rhythm, waving their arms in the goofy dance move, celebrating. "
            "Pip in teal scarf and friend in orange beanie smile happily in the middle. Restrained slow push-in. "
            "Flat 2D doodle style, no text, no speech bubbles."
        ),
    },
    {
        "id": "s6",
        "dur": 6.0,
        "seed_img": 3016,
        "seed_clip": 4016,
        "camera": "static_close",
        "scale_start": 1.06,
        "scale_end": 1.06,
        "line": "A true friend never leaves you to be weird by yourself.",
        "img_prompt": (
            "Single still frame, vertical 9:16. Static close-up. Pip in teal scarf and his friend in orange beanie stand side by side, "
            "striking a confident, happy final pose with thumbs up and huge smiles. Mutual belonging and joy. "
            "Crisp flat 2D line art, clean silhouette, soft consistent lighting."
        ),
        "video_prompt": (
            "Pip in teal scarf and his friend in orange beanie hold their final proud dance pose side by side, smiling warmly at each other with thumbs up. "
            "Subtle gentle breathing and celebration. Static close-up shot. "
            "Flat 2D doodle style, no text, no speech bubbles."
        ),
    },
]

# 1. Images
def stage_images():
    print("--- C012 STAGE 1: IMAGES ---")
    engine = ArtEngine()
    for s in SHOTS:
        p = IMG_DIR / f"{s['id']}.png"
        if p.exists() and p.stat().st_size > 0:
            print(f"Image {s['id']} already exists, skipping.")
            continue
        print(f"Generating image {s['id']}...")
        art = engine.generate(
            prompt=s["img_prompt"],
            negative_prompt=NEGATIVE,
            width=768,
            height=1344,
            seed=s["seed_img"],
            prefix=f"c012_{s['id']}",
            workflow_id="zimage_turbo"
        )
        p.write_bytes(art.png)
        print(f"Saved {p.name}")

# 2. Clips
def stage_clips():
    print("--- C012 STAGE 2: CHRONOFLOW CLIPS ---")
    pipe = ChronoFlowPipeline()
    for s in SHOTS:
        clip_p = CLIP_DIR / f"{s['id']}.mp4"
        if clip_p.exists() and clip_p.stat().st_size > 0:
            print(f"Clip {s['id']} already exists, skipping.")
            continue
        img_p = IMG_DIR / f"{s['id']}.png"
        inp_name = f"c012_{s['id']}.png"
        shutil.copy2(img_p, COMFY_INPUT_DIR / inp_name)
        print(f"Rendering clip {s['id']}...")
        t0 = time.time()
        graph = pipe.build_h3_prompt(
            prompt=s["video_prompt"],
            width=CLIP_W,
            height=CLIP_H,
            length=124,
            steps=4,
            lora_name=LORA4,
            workflow_mode="sliding_window",
            first_frame_filename=inp_name,
            seed=s["seed_clip"],
            fast_h3=False
        )
        res = asyncio.run(pipe.execute_prompt(graph))
        shutil.copy2(res, clip_p)
        print(f"Clip {s['id']} generated in {time.time()-t0:.1f}s ({clip_p.stat().st_size} bytes)")

# 3. Narration
async def stage_narration():
    print("--- C012 STAGE 3: NARRATION ---")
    voice = "en-US-ChristopherNeural"
    for s in SHOTS:
        mp3 = AUDIO_DIR / f"{s['id']}_voice.mp3"
        if not mp3.exists():
            c = edge_tts.Communicate(s["line"], voice, rate="-3%", pitch="+1Hz")
            await c.save(str(mp3))
        wav = AUDIO_DIR / f"{s['id']}_voice.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", str(SR), "-ac", "2", str(wav)], check=True)
    print("Narration ready.")

# 4. Camera & Foley Assembly
def apply_camera_motion(src_clip: Path, dst_clip: Path, target_dur: float, scale_start: float, scale_end: float):
    cap = cv2.VideoCapture(str(src_clip))
    total_frames = int(target_dur * 30.0)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_out = dst_clip.with_suffix(".tmp.mp4")
    out = cv2.VideoWriter(str(tmp_out), fourcc, 30.0, (W, H))

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()

    n_in = len(frames)
    for i in range(total_frames):
        prog = i / max(1, total_frames - 1)
        scale = scale_start + (scale_end - scale_start) * prog
        src_idx = min(n_in - 1, int(prog * n_in))
        base_frame = frames[src_idx]
        up = cv2.resize(base_frame, (W, H), interpolation=cv2.INTER_LANCZOS4)
        if abs(scale - 1.0) > 0.001:
            cw, ch = int(W / scale), int(H / scale)
            x1 = (W - cw) // 2
            y1 = (H - ch) // 2
            crop = up[y1:y1 + ch, x1:x1 + cw]
            final_frame = cv2.resize(crop, (W, H), interpolation=cv2.INTER_LINEAR)
        else:
            final_frame = up
        out.write(final_frame)
    out.release()

    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(tmp_out),
        "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p",
        str(dst_clip)
    ], check=True)
    if tmp_out.exists():
        tmp_out.unlink()

def build_soundscape(total_dur: float = 40.0) -> np.ndarray:
    n_samples = int(total_dur * SR)
    audio = np.zeros((n_samples, 2), dtype=np.float32)
    rng = np.random.default_rng(12)

    # Upbeat, quirky, playful groove (acoustic pizzicato + marimba feel)
    # Bass / kick groove starting from shot 3
    t = np.arange(n_samples) / SR
    bpm = 112
    beat_dur = 60.0 / bpm

    # Rhythmic beats starting at t=9.0s (s3)
    for beat_idx in range(int(9.0 / beat_dur), int(39.0 / beat_dur)):
        bt = beat_idx * beat_dur
        i0 = int(bt * SR)
        i1 = min(n_samples, i0 + int(0.15 * SR))
        ct = np.arange(i1 - i0) / SR
        kick = np.sin(2 * np.pi * 90 * np.exp(-ct * 30) * ct) * np.exp(-ct * 20) * 0.12
        audio[i0:i1, 0] += kick
        audio[i0:i1, 1] += kick
        # Clap on every 2nd beat
        if beat_idx % 2 == 1 and bt > 23.0:  # group claps in s5
            clap_n = rng.standard_normal(i1 - i0).astype(np.float32)
            sos_c = butter(2, [1000, 4500], "band", fs=SR, output="sos")
            clap = sosfilt(sos_c, clap_n) * np.exp(-ct * 35) * 0.14
            audio[i0:i1, 0] += clap
            audio[i0:i1, 1] += clap

    # Foley accents
    def add_boing(at_sec: float, vol: float = 0.20):
        i0 = int(at_sec * SR)
        i1 = min(n_samples, i0 + int(0.4 * SR))
        tt = np.arange(i1 - i0) / SR
        freq = 300 + 400 * np.sin(2 * np.pi * 12 * tt)
        boing = np.sin(2 * np.pi * freq * tt) * np.exp(-tt * 7) * vol
        audio[i0:i1, 0] += boing
        audio[i0:i1, 1] += boing

    def add_chime(at_sec: float, vol: float = 0.18):
        i0 = int(at_sec * SR)
        i1 = min(n_samples, i0 + int(2.0 * SR))
        tt = np.arange(i1 - i0) / SR
        for pf in [1046.5, 1318.5, 1567.98, 2093.0]:
            ch = np.sin(2 * np.pi * pf * tt) * np.exp(-tt * 2.2) * (vol / 4)
            audio[i0:i1, 0] += ch
            audio[i0:i1, 1] += ch

    add_boing(9.4, vol=0.18)   # Pip strikes the goofy pose
    add_chime(23.2, vol=0.20)  # Room joins in celebration
    add_chime(34.5, vol=0.15)  # Ending pride

    # Add Voice tracks
    t_cursor = 0.0
    for s in SHOTS:
        wav_p = AUDIO_DIR / f"{s['id']}_voice.wav"
        if wav_p.exists():
            vdata, vsr = sf.read(str(wav_p), dtype="float32")
            if vdata.ndim == 1:
                vdata = np.stack([vdata, vdata], axis=1)
            i0 = int((t_cursor + 0.25) * SR)
            i1 = min(n_samples, i0 + vdata.shape[0])
            audio[i0:i1] += vdata[:i1 - i0] * 0.95
        t_cursor += s["dur"]

    fade_len = int(1.5 * SR)
    fade_c = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    audio[-fade_len:, 0] *= fade_c
    audio[-fade_len:, 1] *= fade_c

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (10 ** (-1.0 / 20) / peak)
    return audio

def build_subtitles(ass_path: Path):
    def ass_time(t: float) -> str:
        cs = round(t * 100)
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Default,Impact,74,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,6,2,2,60,60,340,1\n"
        "Style: Hook,Impact,86,&H0000E5FF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,7,3,2,60,60,340,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = []
    t_cursor = 0.0
    for i, s in enumerate(SHOTS):
        st = t_cursor + 0.25
        et = t_cursor + s["dur"] - 0.2
        style = "Hook" if i == 0 else "Default"
        text = s["line"].upper()
        lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(et)},{style},,0,0,0,,{text}")
        t_cursor += s["dur"]

    ass_path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")

def main():
    stage_images()
    stage_clips()
    asyncio.run(stage_narration())

    seg_files = []
    for s in SHOTS:
        src = CLIP_DIR / f"{s['id']}.mp4"
        dst = SEG_DIR / f"{s['id']}.mp4"
        print(f"Applying camera motion ({s['camera']}) to {s['id']}...")
        apply_camera_motion(src, dst, s["dur"], s["scale_start"], s["scale_end"])
        seg_files.append(f"file '{dst.as_posix()}'")

    seg_list_file = OUT_DIR / "seg.txt"
    seg_list_file.write_text("\n".join(seg_files), encoding="utf-8")

    audio_path = AUDIO_DIR / "master_audio.wav"
    audio_arr = build_soundscape(40.0)
    sf.write(str(audio_path), audio_arr, SR)

    ass_path = OUT_DIR / "c012_subtitles.ass"
    build_subtitles(ass_path)

    concat_video = OUT_DIR / "concat.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(seg_list_file), "-c", "copy", str(concat_video)], check=True)

    final_video = FINAL_DIR / "C012_The_Quiet_Backup_Reel_Master.mp4"
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
    cmd_mux = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(concat_video),
        "-i", str(audio_path),
        "-vf", f"subtitles='{ass_escaped}'",
        "-c:v", "libx264", "-crf", "17", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-t", "40.000",
        "-movflags", "+faststart",
        str(final_video)
    ]
    subprocess.run(cmd_mux, check=True)
    print(f"\n=======================================================")
    print(f"REEL COMPLETE: {final_video}")
    print(f"Size: {final_video.stat().st_size / (1024*1024):.2f} MB")
    print(f"Duration: 40.00s")
    print(f"=======================================================")

if __name__ == "__main__":
    main()
