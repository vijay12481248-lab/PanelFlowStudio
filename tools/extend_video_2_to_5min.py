"""Extend Video 2 to exceed 5 minutes (300+ seconds).
Adds Shots 37 to 40 (Surface Gate, Association Obelisk Alarm, Shadow Throne, Epic Outro).
"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import List

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.comfyui.art import ArtEngine
from engine.creative.continuity import CinematicShotSpec
from engine.creative.frost_continuity import FrostSceneContinuityDirector

OUTPUT_DIR = Path("output/series_2000/episode_0001_frost_monarch")

EXTRA_SHOTS: List[CinematicShotSpec] = [
    CinematicShotSpec(
        shot_index=37,
        scene_name="Deep Frost Abyss",
        shot_type="Extreme Wide Shot (EWS) Mountain Summit Rupture",
        screen_axis="Panoramic snowy mountain landscape looking at surface rift",
        subject_entity="environment",
        subject_action="massive abyssal rift opening atop a frozen Himalayan mountain peak under turbulent twilight storm clouds, columns of dark cyan shadow energy erupting into the sky",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.1,y-0.6)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Emerging from the abyssal rift onto the storm-swept mountain peaks above, Jin-Woo stepped into the freezing twilight.",
        emotion_tone="mystery",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=38,
        scene_name="Deep Frost Abyss",
        shot_type="Macro Global Alarm Insert",
        screen_axis="Center macro holographic alarm screen",
        subject_entity="prop",
        subject_action="macro close-up of a massive glowing crimson and gold Hunter Association warning holographic terminal flashing in red alarm text: UNREGISTERED SSS-RANK CALAMITY MONARCH AWAKENED IN SECTOR ZERO.",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0015,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Across the globe, the Hunter Association's orbital arrays flashed into crimson panic as an unregistered calamity entity registered on radar.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=39,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Shadow Generals Assembled",
        screen_axis="Protagonist centered flanked by shadow generals",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo standing atop the mountain cliff, flanked by three towering shadow generals in translucent midnight-blue armor, twin cyan daggers bathed in ethereal starlight, cold wind whipping his trench coat",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Surrounded by immortal generals carved from pure darkness, Jin-Woo clenched his fist, feeling the boundless sovereign core roaring in his chest.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=40,
        scene_name="Deep Frost Abyss",
        shot_type="Master Hero Climax (Low-Angle Heroic)",
        screen_axis="Protagonist looking toward distant glowing city skyline",
        subject_entity="kang_jinwoo",
        subject_action="epic low-angle wide heroic shot of Kang Jin-Woo standing at the edge of the snowy precipice looking down at the glittering neon skyscrapers of the distant metropolis, dark shadow wings spreading behind him against the aurora sky",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The era of the corrupt guilds was over. The betrayed porter had become death itself, and the sovereign's hunt had only begun.",
        emotion_tone="triumph_awe",
        tts_rate="-7%",
        tts_pitch="-3Hz",
        intentional_pause_after_seconds=1.5,
    ),
]


async def main():
    print("=== Extending Video 2 to 5+ Minutes ===")
    director = FrostSceneContinuityDirector()
    art = ArtEngine()

    # Step 1: Synthesize Audio for Shots 37 to 40
    print("--- Synthesizing Narration for Shots 37-40 ---")
    audio_data = await director.synthesize_continuous_storyteller_audio(EXTRA_SHOTS, OUTPUT_DIR)

    # Step 2: Render Panels 37 to 40
    print("--- Rendering Panels 37-40 on ComfyUI ---")
    extra_panel_paths = []
    for idx, shot in enumerate(EXTRA_SHOTS, 37):
        panel_path = OUTPUT_DIR / f"panel_{idx:03d}.png"
        if not panel_path.exists():
            prompt, neg_prompt, ref_images = director.compile_shot_prompt(shot)
            print(f"Rendering Panel {idx:02d} [{shot.subject_entity}]...")
            img = art.generate(
                prompt=prompt,
                negative_prompt=neg_prompt,
                width=1344,
                height=768,
                seed=300000 + idx * 411,
                prefix=f"vid2_p{idx:03d}",
                reference_images=ref_images,
            )
            with open(panel_path, "wb") as f:
                f.write(img.png)
            print(f"✓ Panel {idx:02d} rendered ({panel_path.stat().st_size} bytes)")
        extra_panel_paths.append(panel_path)

    # Step 3: Encode Kinematic Video Shots 37 to 40
    print("--- Encoding Shots 37-40 (NVENC) ---")
    for idx, (img_path, (audio_path, audio_dur)) in enumerate(zip(extra_panel_paths, audio_data), 37):
        shot_spec = EXTRA_SHOTS[idx - 37]
        shot_video_path = OUTPUT_DIR / f"shot_{idx:03d}.mp4"
        exact_duration = round(audio_dur + shot_spec.intentional_pause_after_seconds, 2)
        total_frames = int(exact_duration * 30)
        vf_filter = shot_spec.camera_movement.replace("{frames}", str(total_frames))

        if not shot_video_path.exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(img_path),
                "-i", str(audio_path),
                "-vf", vf_filter,
                "-c:v", "h264_nvenc",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(exact_duration),
                "-pix_fmt", "yuv420p",
                "-shortest",
                str(shot_video_path),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✓ Encoded Shot {idx:02d}: {exact_duration:.2f}s")

    # Step 4: Re-concatenate all 40 Shots
    print("--- Re-concatenating all 40 Shots ---")
    raw_master = OUTPUT_DIR / "video_2_raw_concat_40shots.mp4"
    concat_manifest = OUTPUT_DIR / "shots_manifest_40.txt"
    all_shots = [OUTPUT_DIR / f"shot_{i:03d}.mp4" for i in range(1, 41)]
    with open(concat_manifest, "w", encoding="utf-8") as f:
        for p in all_shots:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_manifest.resolve().as_posix(),
        "-c", "copy",
        str(raw_master),
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step 5: Mix Master Audio with Atmospheric Sub Drone Bed
    print("--- Audio Mastering with Cinematic Sub Drone ---")
    final_master = OUTPUT_DIR / "video_2_betrayed_necromancer_monarch_5min_master.mp4"
    
    # Measure raw video duration
    probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(raw_master)]
    dur_str = subprocess.run(probe_cmd, capture_output=True, text=True, check=True).stdout.strip()
    total_dur = float(dur_str)

    filter_complex = (
        "[0:a]volume=1.0[voice];"
        "aevalsrc=exprs='0.025*sin(2*PI*48*t)+0.012*sin(2*PI*96*t)+0.008*sin(2*PI*144*t)':s=44100:d={total_dur}[synth];"
        "[synth]lowpass=f=220,volume=0.32[ambient];"
        "[voice][ambient]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    ).replace("{total_dur}", str(round(total_dur + 2, 1)))

    cmd_audio = [
        "ffmpeg", "-y",
        "-i", str(raw_master),
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "256k",
        str(final_master)
    ]
    subprocess.run(cmd_audio, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"🎉 Extended Video 2 Master Ready: {final_master.name} ({total_dur:.2f}s, {total_dur/60:.2f} min)")


if __name__ == "__main__":
    asyncio.run(main())
