import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import soundfile as sf
from engine.audio.synthesis import local_synthesizer

script_lines = [
    "We kick off deep inside the underground labyrinth, where an ominous, ancient aura suddenly begins to pulse violently through the stone corridors.",
    "The guards are sweating bullets, utterly bewildered why a legendary Sacred Weapon from the higher domains is reacting to a mortal citizen!",
    "Spiritual waves ripple across the grand pavilion, sending shockwaves through the air as everyone scrambles to secure their footing.",
    "Ancient defensive seals flicker along the pillars, struggling to contain the overwhelming pressure building at the chamber's core.",
    "The energy frequency destabilizes further, casting eerie shadows across the faces of the terrified Imperial sentries.",
    "From the depths of the hall, heavy footsteps echo—a presence so stifling that even veteran cultivators can barely breathe.",
    "And there he is! Shangguan Feiyun holding the legendary Soaring Sword, cackling like a classic villain who just found cheat codes!",
    "He sneers with ruthless confidence: 'With the Soaring Sword's location finally confirmed, our ultimate victory is guaranteed!'",
    "'All that's left now is for those naive fools to step right into the trap,' he gloats, his eyes gleaming with malicious intent.",
    "His subordinate nods nervously in agreement, knowing all too well how utterly merciless his master truly is.",
    "Meanwhile, right on cue, a grand VIP delegation arrives at the front gate, completely oblivious to the brewing storm.",
    "The gatekeeper blinks in bewilderment as a flamboyant carriage pulls up, flanked by formidable martial experts.",
    "The imperial guards immediately drop to one knee, trembling in reverence: 'Welcome, most honored and distinguished guests!'",
    "Stepping down from the carriage is none other than our favorite demonic schemer, Zhuo Fan, calmly masquerading as Grandmaster Gu!",
    "Suddenly, a loud commotion erupts! 'I told you to halt immediately! Did your ears stop working?!'",
    "A hot-headed warrior draws his steel, furious at being obstructed, but he clearly has no idea who he's messing with.",
    "Zhuo Fan doesn't even flinch. He just raises an eyebrow, silently judging the utter foolishness unfolding before him.",
    "The air temperature drops to freezing as the terrifying blade hums again, reminding everyone of the deadly stakes.",
    "Bystanders immediately scramble backwards against the courtyard walls, praying they don't get caught in the lethal crossfire.",
    "Spiritual energy spirals off the blade like violent crimson lightning, crackling across the marble tiles.",
    "One of the elders whispers in horror, realizing that the sacred weapon's killing intent has already locked onto its targets!",
    "Guards desperately shout orders to reinforce the perimeter barriers before the entire courtyard collapses.",
    "A heavy thud shakes the pavilion floor as the crimson aura billows outward, suffocating the atmosphere.",
    "Zhuo Fan calmly steps between the panicked factions, his poker face on absolute legendary mode.",
    "The surrounding experts stare in stunned disbelief, wondering why this young grandmaster isn't cowering like everyone else.",
    "The courtyard leader hastily bows in embarrassment: 'Grandmaster Gu, esteemed guests, I sincerely apologize for this disgraceful display!'",
    "Zhuo Fan casually waves his hand like it's no big deal, already analyzing every single energy fluctuation in the room.",
    "Beside him, Old Dan narrows his eyes, keeping his divine senses razor sharp on the twitching imperial blades.",
    "The tension remains thick enough to cut with a dagger, as subtle spiritual probes bounce between both sides.",
    "Even the haughty royal bodyguards swallow hard, sweating profusely under Zhuo Fan's deceptively calm gaze.",
    "A deep rumble vibrates through the flagstones, signaling that the sacred artifact's spirit has grown dangerously restless.",
    "Crimson mist coalesces around the sword's hilt, looking like a ravenous beast demanding a fresh sacrifice.",
    "The wielder grunts in strain, desperately channeling spiritual Qi into the hilt to regain control.",
    "His veins bulge across his forearm as the cursed sword violently fights against his every mental directive!",
    "With a sharp hiss, the blade's murderous aura nearly breaks free, shocking every high-level cultivator present.",
    "Finally, with a tremendous burst of suppression force, the wild crimson radiance is slammed back into the scabbard.",
    "The swordsman wipes cold sweat from his brow, panting in shock: 'That bloodlust was so overwhelming, it completely overrode my commands!'",
    "Watching this, Zhuo Fan secretly connects with Danqing Shen through sound transmission: 'Old Dan, did you catch that?'",
    "'How on earth does Shangguan Feiyun wield the Soaring Sword so effortlessly when everyone else nearly gets devoured by it?'",
    "'Remember back at Double Dragon Manor, the Vaulting Sword almost wrecked me good! Its divine power isn't something normal mortals can block!'",
    "Danqing Shen chuckles softly through their mental link: 'Can't you tell, kid? Feiyun literally grew up alongside that sword—he understands its very soul!'",
    "'Why do you think the great sects covet the Five Divine Weapons so desperately? They are revered as Guardian Divine Weapons for a reason!'",
    "'They cut through all defenses, let the wielder battle ten masters at once, and can even slaughter experts an entire realm above them!'",
]

project_id = 'a4e8115d-1e24-4a23-88b5-ecc72941bc8f'
dialogue_dir = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects") / project_id / "audio" / "dialogue"
dialogue_dir.mkdir(parents=True, exist_ok=True)

print(f"Synthesizing {len(script_lines)} continuous narration lines...")
results = []
for i, text in enumerate(script_lines, 1):
    wav_p = local_synthesizer.synthesize(
        directory=dialogue_dir,
        text=text,
        voice="Narrator",
        emotion="Engaging",
        intensity=0.7,
        pace=1.05,
        force=True,
    )
    dur = round(float(sf.info(str(wav_p)).duration), 2)
    print(f"Line {i:02d}: {dur}s -> {wav_p.name} ('{text[:40]}...')")
    results.append({
        "index": i,
        "text": text,
        "wav_path": str(wav_p),
        "wav_name": wav_p.name,
        "duration": dur,
    })

with open("scratch/synthesized_43_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

total_spoken_time = sum(r["duration"] for r in results)
print(f"Done! Synthesized {len(results)} lines. Total spoken duration: {total_spoken_time:.1f}s")
