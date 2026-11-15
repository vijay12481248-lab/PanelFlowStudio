"""Production script for Video 1: 5-Minute Viral YouTube Manhua Master Episode.
Title: "Betrayed Slave Awakens Forbidden Dragon Monarch Core" (Episode 1 Full Arc)
Total Shots: 38 (Shots 1-16 established, Shots 17-38 new narrative climax).
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
from engine.creative.continuity import (
    SceneContinuityDirector,
    CinematicShotSpec,
)
from produce_perfect_continuity_manhua import SHOT_SEQUENCE as SHOTS_1_TO_16

OUTPUT_DIR = Path("output/series_1000/episode_0001_5min_master")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 22 New Cinematic Shots (Shots 17 to 38)
NEW_SHOTS: List[CinematicShotSpec] = [
    CinematicShotSpec(
        shot_index=17,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Low-Angle Cosmic Rupture Master",
        screen_axis="Vertical composition looking up from quarry floor",
        subject_entity="environment",
        subject_action="ancient obsidian altar on the basalt quarry floor splitting completely in half, erupting a colossal vertical pillar of blinding violet celestial energy piercing through dark storm clouds",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.14)':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),ih*0.1,y-0.6)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="As the ten-thousand-year celestial seal shattered, a blinding torrent of primordial void energy erupted from the basalt floor, tearing through the storm-laden skies.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=18,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Close-Up (MCU) Metamorphosis",
        screen_axis="Protagonist centered, facing forward",
        subject_entity="chen_ye",
        subject_action="Chen Ye bathed in the roaring celestial violet pillar, iridescent dark violet dragon scales crystallizing over his neck and arms, amethyst eyes burning with sovereign starlight, long wet black and white hair billowing wildly upward",
        forbidden_props="chains, handcuffs, holding weapon, fists raised",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.18)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Within his dantian, the dormant Dragon Sovereign Core ignited, purging the slave marks from his flesh as ancient celestial scales coiled around his arms.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=19,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Extreme Wide Shot (EWS) Vanguard Entrance",
        screen_axis="Antagonist army arriving on upper screen-right cliff terrace",
        subject_entity="overseer_gu",
        subject_action="High Overseer Lord Gu in ornamental black-and-gold spiked armor mounted on a massive horned black warbeast arriving at the quarry overlook, flanked by fifty heavy black-armored halberdier enforcers with banners flapping in the storm",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='if(lte(on,1),0,x+0.5)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The tremor echoed across the peaks, summoning High Overseer Lord Gu himself—a merciless cultivator whose iron rule had drowned entire clans in blood.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=20,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Close-Up (MCU) Threat",
        screen_axis="Antagonist on screen-right, sneering toward screen-left",
        subject_entity="overseer_gu",
        subject_action="close-up of High Overseer Lord Gu with a cruel sneer on his aristocratic face, unsheathing a massive five-foot serrated crimson blood-glaive crackling with savage red lightning, cold rain washing over his gold-trimmed pauldron",
        weapon_in_hand="serrated crimson blood-glaive",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'A lowly mining slave daring to touch ancestral divine treasures?' Lord Gu scoffed, drawing his blood-drenched glaive as crimson lightning cracked through the downpour.",
        emotion_tone="confrontation",
        tts_rate="-3%",
        tts_pitch="+0Hz",
    ),
    CinematicShotSpec(
        shot_index=21,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Long Shot (MLS) Desperation",
        screen_axis="Side character on screen-left, kneeling in mud",
        subject_entity="li_ming",
        subject_action="elderly miner Li Ming kneeling on rain-slick basalt gravel, hands raised desperately pleading, torch knocked into a puddle as armored enforcer boots advance menacingly toward him",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.4)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'Lord Gu, have mercy!' cried old Li Ming. 'The mine collapsed on its own—the boy knows nothing!' But his cries were met only with cold, unsheathed steel.",
        emotion_tone="confrontation",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=22,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Full Shot (FS) Sovereign Interception",
        screen_axis="Protagonist on screen-left, facing screen-right line of enemies",
        subject_entity="chen_ye",
        subject_action="Chen Ye stepping calmly between old Li Ming and the advancing enforcers, a translucent dome of boiling violet qi flaring around him that instantly vaporizes the falling raindrops into rising white steam",
        forbidden_props="chains, handcuffs, holding weapon",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="In a single breath, Chen Ye stood before the old miner, his radiating aura so intense that torrential rain vaporized into billowing steam before touching his skin.",
        emotion_tone="tension",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=23,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Close-Up (MCU) Execution Order",
        screen_axis="Antagonist pointing weapon screen-left",
        subject_entity="overseer_gu",
        subject_action="High Overseer Lord Gu snarling with bared teeth, pointing his crimson blood-glaive forward toward Chen Ye, spittle flying as he orders the total slaughter of the rebels",
        weapon_in_hand="serrated crimson blood-glaive",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0012,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'Butcher them both!' Lord Gu roared, his voice booming over the gale. 'Grind their bones into dust and secure the celestial altar!'",
        emotion_tone="confrontation",
        tts_rate="+0%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=24,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Wide Action Charge (EWS)",
        screen_axis="Enforcer phalanx moving right to left",
        subject_entity="lingxiao_enforcer",
        subject_action="a massive phalanx of thirty identical matte-black armored enforcers with glowing crimson visors locking heavy tower shields and lowering serrated black halberds, charging forward across the dark quarry mud",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.6)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Thirty heavy iron enforcers locked shields in flawless imperial formation, their serrated halberds lowered like a bristling forest of black steel.",
        emotion_tone="tension",
        tts_rate="-2%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=25,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Low-Angle Medium Close-Up (MCU) Void Gathering",
        screen_axis="Protagonist low angle, right palm forward",
        subject_entity="chen_ye",
        subject_action="Chen Ye extending his right palm outward, space distorting around his fingers into a swirling pitch-black gravitational sphere rimmed with crackling amethyst lightning",
        forbidden_props="weapons, swords, chains",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Unmoved by the charging wall of steel, Chen Ye raised a single hand. In his palm, gravitational void energy coalesced into a spinning sphere of pure annihilation.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=26,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Apocalyptic Impact Clash (Wide Action)",
        screen_axis="Center dynamic explosion impact",
        subject_entity="action_clash",
        opponent_entity="lingxiao_enforcer",
        subject_action="the pitch-black void singularity detonating against the enforcer phalanx, blinding violet shockwave blasting iron tower shields into twisted metal shards, crushing basalt bedrock in all directions",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0020,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Release! The void singularity struck the vanguard, detonating with the fury of a dying star and obliterating their impenetrable shields in a microsecond.",
        emotion_tone="battle_explosive",
        tts_rate="+5%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=27,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Wide Aftermath of Impact",
        screen_axis="Lateral wide tracking shot",
        subject_entity="lingxiao_enforcer",
        subject_action="black-armored enforcer soldiers sent flying helplessly through the stormy air, crashing into jagged basalt cliff terraces, glowing crimson helmet visors flickering out into darkness",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Dozens of elite enforcers were launched like ragdolls through the violent storm, their heavy armor caving inward as they smashed against the jagged cliffs.",
        emotion_tone="battle_explosive",
        tts_rate="-2%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=28,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Low-Angle Mid-Air Leap Strike",
        screen_axis="Antagonist high in air, descending toward screen-left",
        subject_entity="overseer_gu",
        subject_action="High Overseer Lord Gu leaping thirty feet into the stormy air above the quarry, gripping his serrated crimson blood-glaive with both hands, a towering crimson dragon phantom roaring behind him",
        weapon_in_hand="serrated crimson blood-glaive",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0014,1.22)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Enraged by the slaughter of his vanguard, Lord Gu launched himself into the storm, igniting the nine blood-veins of his ancestral cultivation for a decapitating strike.",
        emotion_tone="battle_explosive",
        tts_rate="+3%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=29,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Dynamic Mid-Air Clash (Dutch Tilt)",
        screen_axis="Lord Gu leaping from upper right down to lower left",
        subject_entity="action_clash",
        opponent_entity="overseer_gu",
        weapon_in_hand="serrated crimson blood-glaive",
        subject_action="High Overseer Lord Gu descending with maximum downward momentum, swinging the glowing red blood-glaive downward straight toward Chen Ye's head amidst driving rain and lightning",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0016,1.24)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'Die, dog!' Gu screamed, bringing the colossal blade down with the force to cleave a mountain peak in two.",
        emotion_tone="battle_explosive",
        tts_rate="+4%",
        tts_pitch="+2Hz",
    ),
    CinematicShotSpec(
        shot_index=30,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Extreme Close-Up (MCU) Impossible Parrying",
        screen_axis="Chen Ye on left, parrying blade on right",
        subject_entity="chen_ye",
        opponent_entity="overseer_gu",
        subject_action="Chen Ye catching the massive descending crimson blood-glaive blade between his index and middle fingers, amethyst dragon scales shimmering on his fingertips, a massive shockwave crater carving the ground beneath",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0012,1.20)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="A deafening boom reverberated across the canyon—yet Chen Ye had not moved an inch. The mountain-shattering blade was locked firmly between two bare fingers.",
        emotion_tone="tension",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=31,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Extreme Close-Up (ECU) Horror Reaction",
        screen_axis="Antagonist headshot, screen-right",
        subject_entity="overseer_gu",
        subject_action="extreme close-up of High Overseer Lord Gu's face, eyes wide with manic disbelief and sweating profusely under torrential rain, trembling as hairline fractures spread across his ancestral blade",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0010,1.18)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Lord Gu's blood ran ice-cold. For the first time in his merciless life, he saw not a slave, but a sovereign god looking through him.",
        emotion_tone="tension",
        tts_rate="-6%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=32,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Macro High-Speed Freeze Frame",
        screen_axis="Center macro weapon shatter",
        subject_entity="prop",
        subject_action="macro close-up of the ancient serrated crimson blood-glaive shattering into dozens of glowing red crystal shards under the pinch of Chen Ye's scale-covered fingers, sparks showering through rain",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0018,1.26)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="With a sharp twist of his wrist, Chen Ye snapped the ancestral weapon like brittle sugar glass, crimson fragments scattering into the rain.",
        emotion_tone="battle_explosive",
        tts_rate="+2%",
        tts_pitch="+1Hz",
    ),
    CinematicShotSpec(
        shot_index=33,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Cinematic Palm Strike Impact (Medium Shot)",
        screen_axis="Chen Ye striking from left into Lord Gu on right",
        subject_entity="chen_ye",
        opponent_entity="overseer_gu",
        damage_state="gold-and-black breastplate caving inward, violet dragon runes searing through iron",
        subject_action="Chen Ye thrusting his open palm into Lord Gu's ornate gold-and-black breastplate, an intricate mandala of glowing violet dragon runes burning into the metal, shockwave blowing the rain backward",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0015,1.22)':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="'Your debt to this pit is paid in full,' Chen Ye whispered, driving his open palm directly into the Overseer's golden core.",
        emotion_tone="battle_explosive",
        tts_rate="-2%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=34,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Wide Impact Aftermath Crater",
        screen_axis="Lateral wide aftermath, body on right",
        subject_entity="overseer_gu",
        damage_state="gold breastplate completely collapsed inward, golden blood coughing from mouth, silk cape in tatters, void smoke rising from chest",
        forbidden_props="weapon, glaive, clean armor",
        subject_action="High Overseer Lord Gu embedded in a deep shattered crater at the base of the massive basalt obelisk, coughing golden blood, his gold breastplate crushed, eyes rolled back in defeat",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.10':d={frames}:x='if(lte(on,1),0,x+0.8)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="The blast hurled the aristocratic lord fifty paces into the great obelisk, his golden core pulverized, his cultivation extinguished forever.",
        emotion_tone="triumph_awe",
        tts_rate="-5%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=35,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Long Shot (MLS) Rout and Panic",
        screen_axis="Enforcers scrambling from right to left toward exits",
        subject_entity="lingxiao_enforcer",
        subject_action="remaining terrified black-armored enforcer soldiers throwing down their halberds and shields, desperately scrambling over rain-slick mud and rocks, fleeing out of the quarry pit into the dark night",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='1.08':d={frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,y+0.4)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Witnessing their invincible commander broken in an instant, the surviving enforcers cast their weapons aside and fled in utter terror into the black night.",
        emotion_tone="tension",
        tts_rate="-4%",
        tts_pitch="-1Hz",
    ),
    CinematicShotSpec(
        shot_index=36,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Long Shot (MLS) Awe and Reverence",
        screen_axis="Slaves kneeling in reverence looking toward right",
        subject_entity="li_ming",
        subject_action="old Li Ming and dozens of freed emaciated quarry slaves emerging from dark cavern entrances, gazing in breathless wonder and falling to their knees in reverence toward Chen Ye",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0006,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="From the shadows of the slave tunnels, hundreds of weary eyes looked upon the ruined quarry, realizing the nightmare of their bondage was broken.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=37,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Medium Close-Up (MCU) Claiming the Artifact",
        screen_axis="Protagonist low angle, holding artifact",
        subject_entity="chen_ye",
        subject_action="Chen Ye picking up an ancient glowing black-and-gold sovereign dragon jade token from the cracked altar pedestal, ancient celestial runes swirling into his palm",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Beneath the fractured altar lay the Primordial Dragon Seal, pulsating in sync with his newly awakened heart.",
        emotion_tone="triumph_awe",
        tts_rate="-6%",
        tts_pitch="-2Hz",
    ),
    CinematicShotSpec(
        shot_index=38,
        scene_name="Abyssal Basalt Quarry",
        shot_type="Master Climax Low-Angle Heroic Panoramic",
        screen_axis="Chen Ye centered, gazing toward distant horizon",
        subject_entity="chen_ye",
        subject_action="Chen Ye standing atop the highest basalt promontory overlooking the vast storm-swept mountain range, glowing amethyst eyes gazing toward the distant glowing towers of the Imperial Capital on the horizon, dragon aura swirling proudly around him",
        forbidden_props="chains, handcuffs, kneeling",
        camera_movement="scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,zoompan=z='min(zoom+0.0008,1.16)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30,scale=1920:1080:flags=bicubic",
        narration_line="Standing high above the abyss, the young sovereign turned his gaze toward the distant imperial throne. The slave had died; the Dragon Monarch had returned.",
        emotion_tone="triumph_awe",
        tts_rate="-7%",
        tts_pitch="-3Hz",
        intentional_pause_after_seconds=1.2,  # Dramatic final outro pause
    ),
]

FULL_SEQUENCE = SHOTS_1_TO_16 + NEW_SHOTS


async def produce_video_1():
    print("==================================================================")
    print("🔥 COMMENCING PRODUCTION: VIDEO 1 (5-MINUTE VIRAL MANHUA MASTER)")
    print("Title: Betrayed Slave Awakens Forbidden Dragon Monarch Core")
    print(f"Total Shots: {len(FULL_SEQUENCE)} (1-16 established, 17-38 new)")
    print("==================================================================")
    t_start = time.time()

    director = SceneContinuityDirector()
    art = ArtEngine()

    # Step 1: Synthesize all speech audio segments for shots 1 to 38
    print("\n--- Step 1: Audio Narration Cadence & Durations ---")
    audio_data = await director.synthesize_continuous_storyteller_audio(FULL_SEQUENCE, OUTPUT_DIR)
    total_audio_dur = sum(dur for _, dur in audio_data)
    total_expected_dur = sum(dur + s.intentional_pause_after_seconds for (_, dur), s in zip(audio_data, FULL_SEQUENCE))
    print(f"Total Narration Speech: {total_audio_dur:.2f}s | Expected Video Length: {total_expected_dur:.2f}s (~{total_expected_dur/60:.2f} min)")

    # Step 2: Render Panels
    # Copy existing approved panels 1-16 from output/series_1000/episode_0001_perfect_continuity
    prev_dir = Path("output/series_1000/episode_0001_perfect_continuity")
    panel_images: List[Path] = []

    print("\n--- Step 2: Panel Visual Generation (ComfyUI Qwen Image 2.1) ---")
    for idx, shot in enumerate(FULL_SEQUENCE, 1):
        panel_path = OUTPUT_DIR / f"panel_{idx:03d}.png"
        
        # Check if shot 1-16 already exists in previous directory
        prev_panel = prev_dir / f"panel_{idx:03d}.png"
        if idx <= 16 and prev_panel.exists() and not panel_path.exists():
            import shutil
            shutil.copy2(prev_panel, panel_path)
            print(f"✓ Reused established Panel {idx:02d}: {panel_path.name}")
            panel_images.append(panel_path)
            continue
            
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
            seed=100000 + idx * 237,
            prefix=f"vid1_p{idx:03d}",
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
        shot_spec = FULL_SEQUENCE[idx - 1]
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
    raw_master = OUTPUT_DIR / "video_1_raw_concat.mp4"
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

    # Step 5: Add Master Cinematic Sound Design (Ambient Drone & Orchestral Bed)
    print("\n--- Step 5: Master Audio Polish & Cinematic Sound Design ---")
    final_master = OUTPUT_DIR / "video_1_betrayed_slave_dragon_monarch_5min_master.mp4"
    
    # Generate atmospheric cinematic audio bed mixed with narration
    # Using ffmpeg complex filter to generate a subtle dark ambient pad + low-end rumble ducked at -22dB
    filter_complex = (
        "[0:a]volume=1.0[voice];"
        "aevalsrc=exprs='0.03*sin(2*PI*55*t)+0.015*sin(2*PI*110*t)+0.01*sin(2*PI*165*t)':s=44100:d={total_dur}[synth];"
        "[synth]lowpass=f=250,volume=0.35[ambient];"
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
    thumb_path = OUTPUT_DIR / "video_1_thumbnail_high_ctr.png"
    if not thumb_path.exists():
        thumb_prompt = (
            "Masterpiece YouTube thumbnail art, 16:9 widescreen composition, ultra-high contrast manhua key visual. "
            "Young handsome martial artist with glowing fierce amethyst purple eyes, scar over left eyebrow, dark hair with white streak, "
            "standing triumphant in an ancient dark basalt cavern under torrential rain. "
            "A massive ethereal purple celestial dragon coiled behind him roaring into the stormy sky. "
            "Shattered black iron chains flying apart, dazzling violet lightning and sparks exploding everywhere. "
            "Cinematic volumetric lighting, dynamic dramatic action pose, 8k resolution, artstation trending."
        )
        thumb_neg = "blurry, low quality, distorted anatomy, text artifacts, bad hands, cartoonish"
        thumb_img = art.generate(
            prompt=thumb_prompt,
            negative_prompt=thumb_neg,
            width=1344,
            height=768,
            seed=777888,
            prefix="vid1_thumb",
        )
        with open(thumb_path, "wb") as f:
            f.write(thumb_img.png)
        print(f"✓ Thumbnail generated: {thumb_path.name}")

    total_time = time.time() - t_start
    final_size_mb = final_master.stat().st_size / (1024 * 1024)
    print("\n==================================================================")
    print(f"🎉 VIDEO 1 PRODUCTION COMPLETE: {final_master.name}")
    print(f"Total Shots: {len(FULL_SEQUENCE)}")
    print(f"Final Video Size: {final_size_mb:.2f} MB")
    print(f"Pipeline Runtime: {total_time / 60:.2f} minutes")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(produce_video_1())
