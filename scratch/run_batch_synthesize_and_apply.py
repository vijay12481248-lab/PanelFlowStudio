import sys
import json
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import soundfile as sf
from sqlalchemy.orm.attributes import flag_modified
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord
from engine.audio.synthesis import local_synthesizer
from engine.render.service import render_service
from engine.render.compiler import timeline_compiler

project_id = 'a4e8115d-1e24-4a23-88b5-ecc72941bc8f'

script_lines = [
    # Scene 1 (Panel 1)
    "We kick off deep inside the underground labyrinth, where an ominous, ancient aura suddenly begins to pulse violently through the stone corridors.",
    # Scene 2 (Panel 2)
    "The guards are sweating bullets, utterly bewildered why a legendary Sacred Weapon from the higher domains is reacting to a mortal citizen!",
    # Scene 3 (Panel 3)
    "Spiritual waves ripple across the grand pavilion, sending shockwaves through the air as everyone scrambles to secure their footing.",
    # Scene 4 (Panel 4)
    "Ancient defensive seals flicker along the pillars, struggling to contain the overwhelming pressure building at the chamber's core.",
    # Scene 5 (Panel 5)
    "The energy frequency destabilizes further, casting eerie shadows across the faces of the terrified Imperial sentries.",
    # Scene 6 (Panel 6)
    "From the depths of the hall, heavy footsteps echo—a presence so stifling that even veteran cultivators can barely breathe.",
    # Scene 7 (Panel 7)
    "And there he is! Shangguan Feiyun holding the legendary Soaring Sword, cackling like a classic villain who just found cheat codes!",
    # Scene 8 (Panel 8)
    "He sneers with ruthless confidence: 'With the Soaring Sword's location finally confirmed, our ultimate victory is guaranteed!'",
    # Scene 9 (Panel 9)
    "'All that's left now is for those naive fools to step right into the trap,' he gloats, his eyes gleaming with malicious intent.",
    # Scene 10 (Panel 10)
    "His subordinate nods nervously in agreement, knowing all too well how utterly merciless his master truly is.",
    # Scene 11 (Panel 11)
    "Meanwhile, right on cue, a grand VIP delegation arrives at the front gate, completely oblivious to the brewing storm.",
    # Scene 12 (Panel 12)
    "The gatekeeper blinks in bewilderment as a flamboyant carriage pulls up, flanked by formidable martial experts.",
    # Scene 13 (Panel 13)
    "The imperial guards immediately drop to one knee, trembling in reverence: 'Welcome, most honored and distinguished guests!'",
    # Scene 14 (Panel 14)
    "Stepping down from the carriage is none other than our favorite demonic schemer, Zhuo Fan, calmly masquerading as Grandmaster Gu!",
    # Scene 15 (Panel 15)
    "Suddenly, a loud commotion erupts! 'I told you to halt immediately! Did your ears stop working?!'",
    # Scene 16 (Panel 16)
    "A hot-headed warrior draws his steel, furious at being obstructed, but he clearly has no idea who he's messing with.",
    # Scene 17 (Panel 17)
    "Zhuo Fan doesn't even flinch. He just raises an eyebrow, silently judging the utter foolishness unfolding before him.",
    # Scene 18 (Panel 18)
    "The air temperature drops to freezing as the terrifying blade hums again, reminding everyone of the deadly stakes.",
    # Scene 19 (Panel 19)
    "Bystanders immediately scramble backwards against the courtyard walls, praying they don't get caught in the lethal crossfire.",
    # Scene 20 (Panel 20)
    "Spiritual energy spirals off the blade like violent crimson lightning, crackling across the marble tiles.",
    # Scene 21 (Panel 21)
    "One of the elders whispers in horror, realizing that the sacred weapon's killing intent has already locked onto its targets!",
    # Scene 22 (Panel 22)
    "Guards desperately shout orders to reinforce the perimeter barriers before the entire courtyard collapses.",
    # Scene 23 (Panel 23)
    "A heavy thud shakes the pavilion floor as the crimson aura billows outward, suffocating the atmosphere.",
    # Scene 24 (Panel 24)
    "Zhuo Fan calmly steps between the panicked factions, his poker face on absolute legendary mode.",
    # Scene 25 (Panel 25)
    "The surrounding experts stare in stunned disbelief, wondering why this young grandmaster isn't cowering like everyone else.",
    # Scene 26 (Panel 26)
    "The courtyard leader hastily bows in embarrassment: 'Grandmaster Gu, esteemed guests, I sincerely apologize for this disgraceful display!'",
    # Scene 27 (Panel 27)
    "Zhuo Fan casually waves his hand like it's no big deal, already analyzing every single energy fluctuation in the room.",
    # Scene 28 (Panel 28)
    "Beside him, Old Dan narrows his eyes, keeping his divine senses razor sharp on the twitching imperial blades.",
    # Scene 29 (Panel 29)
    "The tension remains thick enough to cut with a dagger, as subtle spiritual probes bounce between both sides.",
    # Scene 30 (Panel 30)
    "Even the haughty royal bodyguards swallow hard, sweating profusely under Zhuo Fan's deceptively calm gaze.",
    # Scene 31 (Panel 31)
    "A deep rumble vibrates through the flagstones, signaling that the sacred artifact's spirit has grown dangerously restless.",
    # Scene 32 (Panel 32)
    "Crimson mist coalesces around the sword's hilt, looking like a ravenous beast demanding a fresh sacrifice.",
    # Scene 33 (Panel 33)
    "The wielder grunts in strain, desperately channeling spiritual Qi into the hilt to regain control.",
    # Scene 34 (Panel 34)
    "His veins bulge across his forearm as the cursed sword violently fights against his every mental directive!",
    # Scene 35 (Panel 35)
    "With a sharp hiss, the blade's murderous aura nearly breaks free, shocking every high-level cultivator present.",
    # Scene 36 (Panel 36)
    "Finally, with a tremendous burst of suppression force, the wild crimson radiance is slammed back into the scabbard.",
    # Scene 37 (Panel 37)
    "The swordsman wipes cold sweat from his brow, panting in shock: 'That bloodlust was so overwhelming, it completely overrode my commands!'",
    # Scene 38 (Panel 38)
    "Watching this, Zhuo Fan secretly connects with Danqing Shen through sound transmission: 'Old Dan, did you catch that?'",
    # Scene 39 (Panel 39)
    "'How on earth does Shangguan Feiyun wield the Soaring Sword so effortlessly when everyone else nearly gets devoured by it?'",
    # Scene 40 (Panel 40)
    "'Remember back at Double Dragon Manor, the Vaulting Sword almost wrecked me good! Its divine power isn't something normal mortals can block!'",
    # Scene 41 (Panel 41)
    "Danqing Shen chuckles softly through their mental link: 'Can't you tell, kid? Feiyun literally grew up alongside that sword—he understands its very soul!'",
    # Scene 42 (Panel 42)
    "'Why do you think the great sects covet the Five Divine Weapons so desperately? They are revered as Guardian Divine Weapons for a reason!'",
    # Scene 43 (Panel 43)
    "'They cut through all defenses, let the wielder battle ten masters at once, and can even slaughter experts an entire realm above them!'",
]

def main():
    db = SessionLocal()
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        print("Project not found!")
        return

    ws = Path(project.workspace_path)
    dialogue_dir = ws / "audio" / "dialogue"
    dialogue_dir.mkdir(parents=True, exist_ok=True)

    print("Step 1: Preparing 43 batch synthesis tasks...")
    tasks = []
    for idx, text in enumerate(script_lines, 1):
        tasks.append({
            "id": f"scene_narration_{idx:02d}",
            "directory": str(dialogue_dir),
            "text": text,
            "voice": "Narrator",
            "emotion": "Engaging",
            "intensity": 0.7,
            "speed": 1.05,
            "force": False, # Reuse already existing files!
        })

    print("Step 2: Executing batch synthesis with Chatterbox Turbo...")
    synth_start = time.time()
    batch_results = local_synthesizer.synthesize_batch(tasks)
    print(f"Batch synthesis completed in {time.time() - synth_start:.2f}s! ({len(batch_results)} results)")

    # Build map of id -> result
    res_map = {r["id"]: r for r in batch_results if r.get("success")}

    print("Step 3: Loading and updating Story Editor State...")
    state = project.settings.get("story_editor_state", {})
    scenes = state.get("scenes", [])
    if len(scenes) < 43:
        print(f"Warning: project has {len(scenes)} scenes, expected 43!")

    narration_clips = []
    running_time = 0.0

    for idx, sc in enumerate(scenes[:43]):
        task_id = f"scene_narration_{idx+1:02d}"
        res = res_map.get(task_id)
        if not res:
            # Fallback direct synthesize if missing
            print(f"Generating fallback for line {idx+1}...")
            wav_p = local_synthesizer.synthesize(
                directory=dialogue_dir,
                text=script_lines[idx],
                voice="Narrator",
                emotion="Engaging",
            )
            dur = round(float(sf.info(str(wav_p)).duration), 2)
            wav_name = wav_p.name
        else:
            wav_path = Path(res["audio_path"])
            dur = round(float(res.get("duration") or sf.info(str(wav_path)).duration), 2)
            wav_name = wav_path.name

        # Exact scene duration: speech length + 0.35s breathing room
        scene_dur = round(max(3.0, dur + 0.35), 2)
        sc["start_time_sec"] = running_time
        sc["duration_sec"] = scene_dur

        # Remove shakiness: rock-solid static camera and layers
        sc["camera"] = {
            "preset": "static",
            "zoom_start": 1.0,
            "zoom_end": 1.0,
            "pan_x_start": 0.0,
            "pan_x_end": 0.0,
            "pan_y_start": 0.0,
            "pan_y_end": 0.0,
            "easing": "ease_in_out",
            "duration_sec": scene_dur,
        }
        sc["transition_in"] = "none"
        sc["transition_duration_sec"] = 0.0

        if "background" in sc and isinstance(sc["background"], dict):
            sc["background"]["motion"] = "none"
            sc["background"]["motion_amount"] = 0.0

        for ly in sc.get("layers", []):
            ly["motion_preset"] = "none"
            ly["start_offset_sec"] = 0.0
            ly["duration_sec"] = scene_dur
            ly["transform"] = {"x": 0, "y": 0, "scale": 1, "rotation": 0, "opacity": 1, "z_index": 1}

        # Build synced narration clip
        clip_id = f"narration_clip_{idx+1:02d}"
        narration_clips.append({
            "id": clip_id,
            "scene_id": sc["id"],
            "linked_to_scene": True,
            "scene_offset_sec": 0.0,
            "start_time_sec": running_time,
            "duration_sec": dur,
            "text": script_lines[idx],
            "speaker": "Narrator",
            "voice": "Narrator",
            "volume": 1.0,
            "status": "APPROVED",
            "review_status": "APPROVED",
            "audio_url": f"/api/projects/{project_id}/audio/dialogue/{wav_name}",
        })

        running_time = round(running_time + scene_dur, 2)

    state["scenes"] = scenes[:43]
    state["narration_clips"] = narration_clips
    state["bgm_tracks"] = [
        {
            "id": "bgm_default",
            "audio_url": "/assets/demo/crystal_resonance_bgm.mp3",
            "volume": 0.35,
            "ducking": -14.0,
        }
    ]

    project.settings["story_editor_state"] = state
    flag_modified(project, "settings")
    db.commit()

    print(f"Updated project settings with {len(scenes[:43])} synced scenes and {len(narration_clips)} continuous clips.")
    print(f"Total video planned duration: {running_time:.2f}s ({running_time/60.0:.2f} mins)")

    # Preflight validate
    val = timeline_compiler.preflight_validate(state, project_id, ws)
    print("Preflight validation status:", val.get("is_valid"))
    print("Preflight stats:", json.dumps(val.get("stats"), indent=2))

    # Trigger render
    print("Step 4: Starting production 1080p render with continuous narration...")
    job = render_service.create_and_start_render_job(
        db=db,
        project_id=project_id,
        profile_name="standard_1080p",
        timeline_data=state,
        subtitle_enabled=False,
    )
    job_id = job.get("render_id") or job.get("id")
    print(f"Render job started: {job_id}")

    # Monitor render
    last_p = -1
    while True:
        time.sleep(2.0)
        db.expire_all()
        info = render_service.get_render_job(db, job_id)
        if not info:
            continue
        status = info.get("status")
        prog = info.get("progress", 0.0)
        done = info.get("frames_done", 0)
        total = info.get("frames_total", 0)
        if int(prog * 10) != last_p:
            print(f"[{status}] Progress: {prog:.1f}% ({done}/{total} frames)")
            last_p = int(prog * 10)
        if status in ("COMPLETE", "FAILED", "CANCELLED"):
            print(f"Render job finished with status: {status}")
            if status == "COMPLETE":
                out_path = info.get("output_path")
                print(f"Success! Output MP4: {out_path}")
            else:
                print(f"Error: {info.get('error_message')}")
            break

if __name__ == "__main__":
    main()
