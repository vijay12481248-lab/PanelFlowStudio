"""Production script for Video 2: 5-Minute Viral YouTube Manhwa Master Episode.
Title: "Betrayed E-Rank Porter Awakens SSS-Rank Undead Monarch In The Deep Frost Abyss"
Universe: Glacial Frost Citadel / Solo Hunter Apocalypse.
Total Shots: 36.
Target Duration: ~315 seconds (5+ minutes).
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
from engine.creative.frost_continuity import (
    FrostSceneContinuityDirector,
    ANCHORS_CHAR_DIR,
    ANCHORS_ENV_DIR,
)

OUTPUT_DIR = Path("output/series_2000/episode_0001_frost_monarch")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SHOT_SEQUENCE: List[CinematicShotSpec] = [
    CinematicShotSpec(
        shot_index=1,
        scene_name="Deep Frost Abyss",
        shot_type="Extreme Wide Shot (EWS) Subterranean Master",
        screen_axis="Panoramic landscape looking down into icy abyss",
        subject_entity="environment",
        subject_action="wide panoramic view of the vast subterranean glacial cavern, towering hexagonal blue ice spires, glowing cyan runic fissures, ancient colossal frost dragon skeleton half-buried in the permafrost wall",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Two miles beneath the permafrost, the catastrophic SSS-Rank dungeon known as the Deep Frost Abyss lay locked in eternal winter.",
        emotion_tone="mystery",
        tts_rate="-7%",
        tts_pitch="-3Hz",
    ),
    CinematicShotSpec(
        shot_index=2,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Long Shot (MLS) Gate Slam",
        screen_axis="Dungeon gate on screen-left, closing rightward",
        subject_entity="prop",
        subject_action="massive adamantine dungeon blast door slamming shut with crushing hydraulic force, sparks flying as heavy locking bolts engage, sealing the cavern in shadow",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.5)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="With a deafening mechanical crash, the heavy adamantine blast doors slammed shut, sealing the vault forever.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=3,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Desolate Porter",
        screen_axis="Protagonist centered, kneeling on frozen ground",
        subject_entity="kang_jinwoo",
        subject_action="kneeling in the deep snow with head bowed, worn tactical gear torn and blood-stained, cold breath steaming into the darkness, clenching frostbitten fists",
        forbidden_props="weapons, smiling, clean armor",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Left behind as bait by his own guild, E-Rank porter Kang Jin-Woo was abandoned to freeze in the dark.",
        emotion_tone="tension",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=4,
        scene_name="Deep Frost Abyss",
        shot_type="Wide Shot (WS) Stalking Horrors",
        screen_axis="Monsters advancing from right toward left",
        subject_entity="environment",
        subject_action="pack of monstrous feral frost ghoul beasts with glowing crimson eyes and razor-sharp crystal teeth emerging from jagged ice crevasses, creeping forward across the snow",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.4)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="From the icy fissures emerged dozens of ravenous Frost Horrors, their hollow shrieks echoing across the frozen waste.",
        emotion_tone="tension",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=5,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Defiance",
        screen_axis="Protagonist looking up screen-right",
        subject_entity="kang_jinwoo",
        subject_action="looking up with fierce determination burning through his eyes, bloody cheek, frost in his dark hair, refusing to surrender to death",
        forbidden_props="smiling, weapons",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'So this is how the strong discard the weak,' Jin-Woo rasped, his frozen fingers clenching into fists.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=6,
        scene_name="Deep Frost Abyss",
        shot_type="Macro Holographic System Awaken",
        screen_axis="Center macro holographic UI",
        subject_entity="prop",
        subject_action="macro close-up of a shattered glowing gold and neon-cyan holographic system status screen floating in the dark air with warning text: CRITICAL: LETHAL BETRAYAL DETECTED. HIDDEN QUEST: SOVEREIGN OF DEATH COMPLETED.",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0015,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Suddenly, a blinding system interface pierced the freezing blackness before his eyes.",
        emotion_tone="mystery",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=7,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Starlight Eyes",
        screen_axis="Protagonist centered, glowing cyan eyes",
        subject_entity="kang_jinwoo",
        subject_action="intense focus on Jin-Woo's face as his eyes burst into blinding cyan celestial flames, ancient runic monarch glyphs swirling across his irises, cold blizzard swirling around his face",
        forbidden_props="weapons, chains",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0012,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="A forbidden power, slumbering since the dawn of the Great Calamity, coursed through his frozen veins.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=8,
        scene_name="Deep Frost Abyss",
        shot_type="Full Shot (FS) Sovereign Transformation",
        screen_axis="Protagonist standing tall on left, facing right",
        subject_entity="kang_jinwoo",
        subject_action="standing completely tall amidst the howling blizzard, dark tactical trench coat billowing with ethereal cyan flames, frost-silver streaks rippling through his jet-black hair",
        forbidden_props="kneeling, scared expression",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.15)':d={frames}:x='if(lte(on,1),ih*0.1,x-0.4)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Standing tall amidst the howling blizzard, Jin-Woo's body underwent a complete biological metamorphosis.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=9,
        scene_name="Deep Frost Abyss",
        shot_type="Macro Dagger Materialization",
        screen_axis="Center macro hands and daggers",
        subject_entity="prop",
        subject_action="macro close-up of twin curved obsidian and luminescent cyan spectral daggers condensing out of swirling black shadow mist into gloved hands, cold frost vapors rising from blade edges",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0016,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="From the abyss of nothingness, the twin Sovereign Daggers answered his call, forged from distilled void ice.",
        emotion_tone="triumph_awe",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=10,
        scene_name="Deep Frost Abyss",
        shot_type="Dynamic Action Attack",
        screen_axis="Beast lunging from right toward left",
        subject_entity="environment",
        subject_action="feral alpha frost ghoul lunging forward mid-air with razor crystal fangs and glowing red eyes, claws outstretched to shred its prey",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0014,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The alpha Frost Horror lunged forward, claws poised to tear him limb from limb!",
        emotion_tone="battle_explosive",
        tts_rate="+3%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=11,
        scene_name="Deep Frost Abyss",
        shot_type="Cinematic Strike Impact (Action Clash)",
        screen_axis="Jin-Woo dashing past on right, severed beast on left",
        subject_entity="action_clash",
        subject_action="Jin-Woo flashing past in a high-speed azure blur, curved cyan spectral daggers cleanly slicing through the frost beast, exploding the monster into blue crystalline ice shards and dark mist",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0020,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Faster than thought, a flash of azure lightning bifurcated the beast before its claws could even graze his coat.",
        emotion_tone="battle_explosive",
        tts_rate="+4%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=12,
        scene_name="Deep Frost Abyss",
        shot_type="Wide Shot (WS) Terror in the Snow",
        screen_axis="Monsters backing away toward right",
        subject_entity="environment",
        subject_action="remaining horde of frost monsters trembling and taking frantic steps backward as a vast lake of inky-black shadow mist rapidly spreads across the frozen ground beneath Jin-Woo's boots",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.5)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The horde froze in terror as the permafrost beneath his boots transformed into a fathomless lake of shadows.",
        emotion_tone="tension",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=13,
        scene_name="Deep Frost Abyss",
        shot_type="Low-Angle Medium Shot (MLS) Command",
        screen_axis="Protagonist centered low angle, right hand reaching out",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo extending his right hand toward the frozen earth, glowing cyan eyes radiating supreme authority, uttering the sovereign command",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.18)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'Awaken from your frozen slumber,' Jin-Woo commanded softly. 'Arise.'",
        emotion_tone="triumph_awe",
        tts_rate="-7%",
        tts_pitch="-3Hz",
        intentional_pause_after_seconds=0.4,
    ),
    CinematicShotSpec(
        shot_index=14,
        scene_name="Deep Frost Abyss",
        shot_type="Low-Angle Epic Rise (WS)",
        screen_axis="Shadow knights erupting across entire frame",
        subject_entity="shadow_general",
        subject_action="dozens of towering ethereal shadow knights in translucent dark midnight-blue plate armor and burning cyan eyes rising majestically out of the frozen ice, kneeling in reverence to Jin-Woo",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.12':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.1,y-0.7)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="From the fractured bedrock rose an army of spectral shadow warriors, kneeling in absolute fealty to their new Monarch.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=15,
        scene_name="Deep Frost Abyss",
        shot_type="Wide Shot (WS) Explosive Breach",
        screen_axis="Blast door exploding on screen-left",
        subject_entity="prop",
        subject_action="the massive adamantine dungeon blast doors blowing violently inward with fiery orange explosive demolition charges, acrid smoke pouring into the blue ice cavern",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0012,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Six hours later, the blast doors were blown open as the White Tiger Strike Squad returned to claim the dungeon's divine core.",
        emotion_tone="tension",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=16,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Long Shot (MLS) Arrogant Strut",
        screen_axis="Antagonist squad advancing leftward through smoke",
        subject_entity="vice_leader_drake",
        subject_action="Vice-Leader Drake striding forward through explosive smoke in gleaming white-and-gold power armor, arrogant smirk on his face, flanked by armored strike soldiers with railguns",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.4)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Leading the vanguard was Vice-Leader Drake, confident that the abandoned porter had long been devoured to the bone.",
        emotion_tone="confrontation",
        tts_rate="-4%",
        tts_pitch="+0Hz",
    ),
    CinematicShotSpec(
        shot_index=17,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Smirk Fades",
        screen_axis="Antagonist headshot, screen-right",
        subject_entity="vice_leader_drake",
        subject_action="close-up of Drake's face as his arrogant smirk instantly drops into stunned bewilderment, tactical ocular HUD flashing red warnings over his eyes",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'What in the world...?' Drake muttered, his scanner sensors screeching with impossible energy readings.",
        emotion_tone="tension",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=18,
        scene_name="Deep Frost Abyss",
        shot_type="Master Hero Full Shot (FS)",
        screen_axis="Protagonist seated on throne, screen-left",
        subject_entity="kang_jinwoo",
        subject_action="Kang Jin-Woo sitting calmly upon an ancient throne carved from dark frost ice, dark trench coat draped over knees, glowing cyan eyes gazing down at the intruders, shadow sentinels standing at his flanks",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Sitting upon an ancient throne of frozen obsidian sat Kang Jin-Woo, calmly waiting for his betrayers.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=19,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Long Shot (MLS) Shaking Guns",
        screen_axis="Strike squad on screen-right, shaking",
        subject_entity="apex_strike_squad",
        subject_action="elite strike soldiers aiming heavy plasma railguns at Jin-Woo, their armored hands visibly trembling as cold phantom shadows pool around their boots",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.4)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'P-Porter Kang?!' stuttered the vanguard captain, his plasma rifle trembling against his chest.",
        emotion_tone="tension",
        tts_rate="-3%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=20,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Chilling Voice",
        screen_axis="Protagonist resting chin on hand, looking right",
        subject_entity="kang_jinwoo",
        subject_action="close-up of Jin-Woo resting his chin nonchalantly on his fist, glowing cyan eyes piercing through the dark, cold calm smile on his lips",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'You took longer than I expected, Drake,' Jin-Woo spoke, his voice carrying the chilling resonance of the abyss.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=21,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Enraged Antagonist",
        screen_axis="Antagonist on right, igniting weapon",
        subject_entity="vice_leader_drake",
        subject_action="Drake snarling with bared teeth, igniting a massive six-foot glowing golden plasma broadsword that casts furious amber light across the ice",
        weapon_in_hand="glowing golden plasma broadsword",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'I don't know what glitched artifact you found, trash,' Drake bellowed, 'but an E-Rank is still an E-Rank! Fire!'",
        emotion_tone="confrontation",
        tts_rate="+1%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=22,
        scene_name="Deep Frost Abyss",
        shot_type="Wide Action Shot (WS) Railgun Salvo",
        screen_axis="Barreling projectiles moving right to left",
        subject_entity="apex_strike_squad",
        subject_action="entire strike squad opening fire simultaneously, thirty blinding orange plasma railgun beams scorching across the frozen cavern, illuminating the ice with violent light",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0016,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Thirty heavy railguns fired in unison, turning the cavern into a raging inferno of superheated plasma!",
        emotion_tone="battle_explosive",
        tts_rate="+4%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=23,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Unmoved Shield",
        screen_axis="Protagonist centered behind shadow wall",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo sitting motionless without blinking as a towering wall of dense black shadow rises seamlessly in front of him, effortlessly absorbing every plasma blast into thin air",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Yet the barrage vanished like rain upon the ocean, swallowed whole by an impenetrable shroud of void darkness.",
        emotion_tone="triumph_awe",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=24,
        scene_name="Deep Frost Abyss",
        shot_type="Low-Angle Action Transition (MLS)",
        screen_axis="Protagonist standing up from throne",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo stepping down from the obsidian throne, twin cyan daggers spinning into his reverse grip, shadowy mist trailing his footsteps",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0012,1.18)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Jin-Woo tilted his head. 'Now... it is my turn.'",
        emotion_tone="tension",
        tts_rate="-6%",
        tts_pitch="-3Hz",
        intentional_pause_after_seconds=0.3,
    ),
    CinematicShotSpec(
        shot_index=25,
        scene_name="Deep Frost Abyss",
        shot_type="Dynamic Action Clash (WS)",
        screen_axis="Left shadow wave striking right squad",
        subject_entity="action_clash",
        opponent_entity="apex_strike_squad",
        subject_action="tidal wave of shadowy soldiers colliding violently with the strike squad phalanx, ripping apart heavy power armor and crushing plasma rifles under shadowy blades",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0020,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Like a tidal wave of living darkness, the shadow legion collided with the strike team, tearing through adamantine alloy like parchment.",
        emotion_tone="battle_explosive",
        tts_rate="+5%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=26,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Long Shot (MLS) Vanguard Neutralized",
        screen_axis="Armored soldiers disarmed on ground",
        subject_entity="apex_strike_squad",
        damage_state="power armor cracked, weapons shattered, held down by shadowy hands",
        subject_action="all thirty elite strike soldiers pinned helpless face-down in the ice by dark shadowy hands, their weapons shattered into scrap",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='if(lte(on,1),0,x+0.6)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Within three breaths, the entire elite vanguard lay disarmed and paralyzed upon the ice.",
        emotion_tone="triumph_awe",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=27,
        scene_name="Deep Frost Abyss",
        shot_type="Low-Angle Dynamic Leap (Dutch Tilt)",
        screen_axis="Antagonist airborne right to left",
        subject_entity="vice_leader_drake",
        weapon_in_hand="glowing golden plasma broadsword",
        subject_action="Drake igniting his rocket booster thrusters, soaring forward through the cavern with golden broadsword raised overhead in a desperate sonic-boom leap",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0016,1.24)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Desperate and enraged, Drake ignited his armor's overdrive cores, charging forward in a sonic-boom leap!",
        emotion_tone="battle_explosive",
        tts_rate="+3%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=28,
        scene_name="Deep Frost Abyss",
        shot_type="Macro Action Parrying Clash",
        screen_axis="Blade clash center frame",
        subject_entity="action_clash",
        opponent_entity="vice_leader_drake",
        subject_action="Jin-Woo parrying the massive descending golden plasma blade with a single reversed cyan spectral dagger, brilliant cyan and amber shockwave shattering ice crystals in all directions",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0018,1.26)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Clang! The deafening shockwave shattered the surrounding ice spires—yet Jin-Woo blocked the strike with a single hand.",
        emotion_tone="battle_explosive",
        tts_rate="+4%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=29,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Chilling Eye Contact",
        screen_axis="Protagonist looking right into enemy face",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo staring inches from Drake's horrified face, glowing cyan eyes searing into Drake's soul, completely effortless composure",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.18)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'You called me trash,' Jin-Woo whispered cold as permafrost. 'Yet look who is begging for breath.'",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=30,
        scene_name="Deep Frost Abyss",
        shot_type="Cinematic Strike Impact (MCU)",
        screen_axis="Jin-Woo thrusting left into Drake on right",
        subject_entity="kang_jinwoo",
        opponent_entity="vice_leader_drake",
        damage_state="white-and-gold chestplate caved inward, dark cyan shockwave explosion",
        subject_action="Jin-Woo driving an ink-black shadow palm into Drake's gold breastplate, concussive dark shockwave crushing the armor alloy inward like tin",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0016,1.22)':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="A burst of dark cyan kinetic force slammed into Drake's chest, caving the golden armor inward with a bone-jarring crunch.",
        emotion_tone="battle_explosive",
        tts_rate="+2%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=31,
        scene_name="Deep Frost Abyss",
        shot_type="Wide Impact Aftermath (WS)",
        screen_axis="Lateral wide tracking shot, victim on right",
        subject_entity="vice_leader_drake",
        damage_state="collapsed chestplate, fractured helmet visor, sparks spitting from power conduits",
        forbidden_props="clean armor, standing, weapon in hand",
        subject_action="Drake skidding fifty meters violently across the frozen ice, crashing into a glacial wall, his broken plasma broadsword sliding into a dark crevasse",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The mighty vice-leader crashed violently against the glacial wall, his pride and power reduced to shattered glass.",
        emotion_tone="triumph_awe",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=32,
        scene_name="Deep Frost Abyss",
        shot_type="Low-Angle Colossal Summon (WS)",
        screen_axis="Towering summon on left, victim on right",
        subject_entity="shadow_general",
        subject_action="ten-foot tall Frost Shadow General stepping forward out of the billowing darkness, brandishing a massive curved frost executioner greatsword over the fallen Drake",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="From the depths of the frozen vault stepped the Frost Shadow General, towering ten feet tall with blade poised.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-3Hz",
    ),
    CinematicShotSpec(
        shot_index=33,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Desperate Begging",
        screen_axis="Antagonist on knees on screen-right",
        subject_entity="vice_leader_drake",
        damage_state="coughing blood, crushed breastplate, crying in agony",
        subject_action="Drake on his knees in the snow, hands raised in frantic pleading, crying and trembling uncontrollably before the towering shadow knight",
        forbidden_props="weapons, standing, arrogant look",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'P-Please...' Drake pleaded, tears freezing on his cheeks. 'Spare me! I'll give you everything—money, ranks, the guild!'",
        emotion_tone="confrontation",
        tts_rate="-3%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=34,
        scene_name="Deep Frost Abyss",
        shot_type="Medium Close-Up (MCU) Sovereign Verdict",
        screen_axis="Protagonist looking down toward right",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo looking down with cold sovereign detachment, eyes ablaze with ethereal cyan starlight, utterly merciless and majestic",
        forbidden_props="smiling, fear",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'The debt you owe cannot be paid in gold,' Jin-Woo declared, his eyes burning with eternal cyan starlight.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=35,
        scene_name="Deep Frost Abyss",
        shot_type="Extreme Wide Shot (EWS) Ten Thousand Shadows",
        screen_axis="Expansive wide view of whole cavern",
        subject_entity="environment",
        subject_action="entire subterranean citadel illuminated by thousands of glowing cyan eyes as ten thousand spectral shadow soldiers emerge from every icy fissure and raise their weapons in unison",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.12':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.1,y-0.7)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Across the vast expanse of the subterranean citadel, ten thousand resurrected warriors raised their blades to the sky.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=36,
        scene_name="Deep Frost Abyss",
        shot_type="Master Climax Heroic Shot (WS)",
        screen_axis="Protagonist walking toward open gate",
        subject_entity="kang_jinwoo",
        subject_action="Jin-Woo walking slowly toward the open surface gate, his dark trench coat billowing with shadow mist and frost embers, looking back one final time with piercing cyan eyes",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The hunter who was left to die in the frost had conquered death itself. The world above was about to meet its new master.",
        emotion_tone="triumph_awe",
        tts_rate="-7%",
        tts_pitch="-3Hz",
        intentional_pause_after_seconds=1.2,
    ),
]


async def produce_video_2():
    print("==================================================================")
    print("❄️ COMMENCING PRODUCTION: VIDEO 2 (5-MINUTE VIRAL DUNGEON HUNTER MASTER)")
    print("Title: Betrayed E-Rank Porter Awakens SSS-Rank Undead Monarch")
    print(f"Total Shots: {len(SHOT_SEQUENCE)}")
    print("==================================================================")
    t_start = time.time()

    director = FrostSceneContinuityDirector()
    art = ArtEngine()

    # Step 0: Ensure Character & Environment Anchors are rendered
    print("\n--- Step 0: Establishing Series Anchors (Continuity Locks) ---")
    anchors = [
        ("env", ANCHORS_ENV_DIR / "glacial_abyss_anchor.png", 
         "Masterpiece cinematic webtoon key visual, wide panoramic view of deep subterranean glacial ice cavern, towering hexagonal blue ice spires, glowing cyan runic fissures, volumetric frozen haze, 8k key visual",
         "people, character, modern cars, low quality"),
        ("protag", ANCHORS_CHAR_DIR / "kang_jinwoo_anchor.png",
         "Cinematic webtoon portrait, athletic handsome young Korean hunter Kang Jin-Woo, glowing icy-cyan sovereign eyes, jet-black hair with frosted tips, dark charcoal tactical hooded trench coat, holding curved cyan spectral dagger, calm lethal expression, 8k",
         "blurry, smiling, blonde, armor, weak"),
        ("antag", ANCHORS_CHAR_DIR / "vice_leader_drake_anchor.png",
         "Cinematic webtoon portrait, muscular arrogant elite hunter Vice-Leader Drake, slicked-back blonde hair, cruel sneer, gleaming white-and-gold high-tech adamantine power armor, holding glowing golden plasma broadsword, 8k",
         "friendly, soft, dark hair, peasant"),
        ("squad", ANCHORS_CHAR_DIR / "strike_squad_anchor.png",
         "Cinematic webtoon squad portrait, high-tech strike soldiers in heavy cobalt-and-silver power armor, glowing orange tactical visors, holding plasma railguns and energy tower shields, 8k",
         "bare face, colorful, medieval armor"),
        ("general", ANCHORS_CHAR_DIR / "frost_shadow_general_anchor.png",
         "Cinematic webtoon monster portrait, colossal ten-foot tall ethereal shadow monarch knight, translucent midnight-blue plate armor, burning cyan flame eyes in horned helm, holding massive frost greatsword, 8k",
         "human face, flesh, white armor"),
    ]

    for a_name, a_path, a_prompt, a_neg in anchors:
        if not a_path.exists():
            print(f"Rendering anchor: {a_name} ({a_path.name})...")
            img = art.generate(prompt=a_prompt, negative_prompt=a_neg, width=1344, height=768, seed=888111, prefix=f"anchor_{a_name}")
            with open(a_path, "wb") as f:
                f.write(img.png)
            print(f"✓ Saved anchor: {a_path.name}")
        else:
            print(f"✓ Anchor exists: {a_path.name}")

    # Step 1: Synthesize all speech audio segments
    print("\n--- Step 1: Audio Narration Cadence & Durations ---")
    audio_data = await director.synthesize_continuous_storyteller_audio(SHOT_SEQUENCE, OUTPUT_DIR)
    total_audio_dur = sum(dur for _, dur in audio_data)
    total_expected_dur = sum(dur + s.intentional_pause_after_seconds for (_, dur), s in zip(audio_data, SHOT_SEQUENCE))
    print(f"Total Narration Speech: {total_audio_dur:.2f}s | Expected Video Length: {total_expected_dur:.2f}s (~{total_expected_dur/60:.2f} min)")

    # Step 2: Render All 36 Character- & Environment-Locked Panels
    print("\n--- Step 2: Panel Visual Generation (ComfyUI Qwen Image 2.1) ---")
    panel_images: List[Path] = []
    for idx, shot in enumerate(SHOT_SEQUENCE, 1):
        panel_path = OUTPUT_DIR / f"panel_{idx:03d}.png"
        if panel_path.exists():
            print(f"✓ Panel {idx:02d} already exists: {panel_path.name}")
            panel_images.append(panel_path)
            continue

        prompt, neg_prompt, ref_images = director.compile_shot_prompt(shot)
        ref_names = [p.name for p in ref_images] if ref_images else ["None"]
        print(f"Rendering Panel {idx:02d} [{shot.subject_entity}] (refs={ref_names})...")
        t_img = time.time()
        art_img = art.generate(
            prompt=prompt,
            negative_prompt=neg_prompt,
            width=1344,
            height=768,
            seed=200000 + idx * 317,
            prefix=f"vid2_p{idx:03d}",
            reference_images=ref_images,
        )
        with open(panel_path, "wb") as f:
            f.write(art_img.png)
        print(f"✓ Panel {idx:02d} rendered in {time.time() - t_img:.1f}s ({len(art_img.png)} bytes)")
        panel_images.append(panel_path)

    # Step 3: Encode Kinematic Video Shots
    print("\n--- Step 3: Encoding 4K Kinematic Video Shots (NVENC) ---")
    shot_video_paths: List[Path] = []
    for idx, (img_path, (audio_path, audio_dur)) in enumerate(zip(panel_images, audio_data), 1):
        shot_spec = SHOT_SEQUENCE[idx - 1]
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
        else:
            print(f"✓ Shot {idx:02d} already encoded")
        shot_video_paths.append(shot_video_path)

    # Step 4: Concatenate Raw Master
    print("\n--- Step 4: Concatenating Full 5-Minute Episode ---")
    raw_master = OUTPUT_DIR / "video_2_raw_concat.mp4"
    concat_manifest = OUTPUT_DIR / "shots_manifest.txt"
    with open(concat_manifest, "w", encoding="utf-8") as f:
        for p in shot_video_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_manifest.resolve().as_posix(),
        "-c", "copy",
        str(raw_master),
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Step 5: Add Master Cinematic Sound Design (Cold Atmospheric Pad + Sub Drone)
    print("\n--- Step 5: Master Audio Polish & Cinematic Sound Design ---")
    final_master = OUTPUT_DIR / "video_2_betrayed_necromancer_monarch_5min_master.mp4"
    
    filter_complex = (
        "[0:a]volume=1.0[voice];"
        "aevalsrc=exprs='0.025*sin(2*PI*48*t)+0.012*sin(2*PI*96*t)+0.008*sin(2*PI*144*t)':s=44100:d={total_dur}[synth];"
        "[synth]lowpass=f=220,volume=0.32[ambient];"
        "[voice][ambient]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    ).replace("{total_dur}", str(round(total_expected_dur + 2, 1)))

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

    # Step 6: Generate High CTR YouTube Thumbnail
    print("\n--- Step 6: Generating High CTR YouTube Thumbnail (16:9) ---")
    thumb_path = OUTPUT_DIR / "video_2_thumbnail_high_ctr.png"
    if not thumb_path.exists():
        thumb_prompt = (
            "Masterpiece YouTube thumbnail art, 16:9 widescreen composition, ultra-high contrast webtoon key visual. "
            "Handsome athletic young Korean hunter with blazing neon-cyan sovereign eyes, dark hair with frosted tips, "
            "standing triumphant in a frozen blue glacial cavern amidst howling blizzard. "
            "A colossal ten-foot dark spectral shadow monarch knight standing behind him with glowing cyan flame eyes. "
            "A shattered golden SSS-Rank holographic status window exploding into neon sparks in the foreground. "
            "Cinematic volumetric lighting, dynamic dramatic action pose, 8k resolution, artstation trending."
        )
        thumb_neg = "blurry, low quality, distorted anatomy, text artifacts, bad hands, cartoonish"
        thumb_img = art.generate(
            prompt=thumb_prompt,
            negative_prompt=thumb_neg,
            width=1344,
            height=768,
            seed=999222,
            prefix="vid2_thumb",
        )
        with open(thumb_path, "wb") as f:
            f.write(thumb_img.png)
        print(f"✓ Thumbnail generated: {thumb_path.name}")

    total_time = time.time() - t_start
    final_size_mb = final_master.stat().st_size / (1024 * 1024)
    print("\n==================================================================")
    print(f"🎉 VIDEO 2 PRODUCTION COMPLETE: {final_master.name}")
    print(f"Total Shots: {len(SHOT_SEQUENCE)}")
    print(f"Final Video Size: {final_size_mb:.2f} MB")
    print(f"Pipeline Runtime: {total_time / 60:.2f} minutes")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(produce_video_2())
