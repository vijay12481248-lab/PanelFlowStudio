"""Frost Monarch Scene Continuity and Cinematic Directing Engine for Video 2.
Universe: Deep Frost Abyss / SSS-Rank Dungeon Sovereign Arc.
Enforces:
1. Environmental Landmark Locking (Glacial Frost Citadel)
2. Character Profiles & Faction Armor Locking (Kang Jin-Woo, Vice-Leader Drake, Apex Strike Squad, Shadow General)
3. 180-degree Cinematographic Axis and Camera Choreography
4. Emotional Voiceover Cadence & Exact Time Matching (Edge-TTS)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

import edge_tts

from engine.creative.continuity import (
    EnvironmentalLandmarks,
    CharacterVisualProfile,
    CinematicShotSpec,
)
from engine.creative.emotion_guider import SomaticEmotionGuiderAgent

logger = logging.getLogger("panelflow.creative.frost_continuity")

ANCHORS_CHAR_DIR = Path("output/series_2000/character_anchors")
ANCHORS_ENV_DIR = Path("output/series_2000/environment_anchors")
ANCHORS_CHAR_DIR.mkdir(parents=True, exist_ok=True)
ANCHORS_ENV_DIR.mkdir(parents=True, exist_ok=True)


class FrostSceneContinuityDirector:
    """Master director enforcing environmental, character, and cinematographic continuity for the Frost Abyss universe."""

    def __init__(self):
        # 1. Locked Environment: Glacial Frost Abyss
        self.active_environment = EnvironmentalLandmarks(
            location_name="Deep Frost Abyss Subterranean Citadel",
            geology="towering hexagonal translucent blue glacial ice spires, ancient colossal frost dragon ribcage embedded into cavern walls",
            crystal_features="glowing neon-cyan runic frost fissures pulsing through frozen blue ice floors and monolithic obsidian pillars",
            ground_surface="permafrost stone terraces covered in crystalline hoarfrost and shallow icy pools reflecting glowing blue starlight",
            sky_and_weather="swirling icy blizzard flurries, ethereal cyan mist rising from crevasses, volumetric frozen haze",
            lighting_sources="luminescent cyan crystal clusters glowing along cavern walls, cold high-contrast volumetric blue rim lighting",
        )
        self.env_anchor = ANCHORS_ENV_DIR / "glacial_abyss_anchor.png"
        self.emotion_guider = SomaticEmotionGuiderAgent()

        # 2. Locked Character Profiles
        self.entities: Dict[str, CharacterVisualProfile] = {
            "kang_jinwoo": CharacterVisualProfile(
                id="kang_jinwoo",
                name="Kang Jin-Woo",
                role="protagonist",
                visual_tags=(
                    "athletic handsome young Korean hunter, piercing glowing icy-cyan sovereign eyes, "
                    "jet-black hair with frosted silver tips, calm deadly expression, "
                    "wearing a torn dark charcoal tactical hooded trench coat over high-tech carbon weave undersuit, "
                    "holding twin curved obsidian-and-cyan spectral daggers"
                ),
                negative_tags="blurry, distorted limbs, smiling, blonde, modern casual clothes, medieval armor, weak",
                anchor_image_path=ANCHORS_CHAR_DIR / "kang_jinwoo_anchor.png",
                default_screen_side="left",
            ),
            "vice_leader_drake": CharacterVisualProfile(
                id="vice_leader_drake",
                name="Vice-Leader Drake",
                role="supreme_antagonist",
                visual_tags=(
                    "towering muscular arrogant elite hunter, slicked-back blonde hair, cruel sneer, "
                    "gleaming high-tech white-and-gold adamantine exoskeleton power armor, glowing golden energy pauldrons, "
                    "wielding a massive six-foot glowing golden plasma broadsword"
                ),
                negative_tags="friendly, soft face, ragged clothes, black hair, dark armor, peasant",
                anchor_image_path=ANCHORS_CHAR_DIR / "vice_leader_drake_anchor.png",
                default_screen_side="right",
            ),
            "apex_strike_squad": CharacterVisualProfile(
                id="apex_strike_squad",
                name="Apex Strike Squad",
                role="faction_squad",
                visual_tags=(
                    "high-tech combat soldiers clad in uniform heavy cobalt-and-silver tactical power armor, "
                    "full-face enclosed combat helmets with glowing orange visor arrays, "
                    "holding matching heavy plasma railgun rifles and hexagonal energy tower shields"
                ),
                negative_tags="bare face, medieval armor, cloth robes, colorful, gold armor",
                anchor_image_path=ANCHORS_CHAR_DIR / "strike_squad_anchor.png",
                default_screen_side="right",
            ),
            "shadow_general": CharacterVisualProfile(
                id="shadow_general",
                name="Frost Shadow General",
                role="summon_familiar",
                visual_tags=(
                    "colossal ten-foot tall ethereal shadow monarch knight, clad in dark translucent midnight-blue plate armor, "
                    "glowing bright cyan flame eyes inside a horned shadowy helm, billowing icy phantom mist, "
                    "wielding a massive six-foot curved frost executioner greatsword radiating freezing vapors"
                ),
                negative_tags="human face, flesh, colorful, white armor, modern clothes",
                anchor_image_path=ANCHORS_CHAR_DIR / "frost_shadow_general_anchor.png",
                default_screen_side="left",
            ),
        }

    def compile_shot_prompt(self, shot: CinematicShotSpec) -> tuple[str, str, Optional[List[Path]]]:
        """Compiles an ArtEngine prompt preserving environmental landmarks, character profile, and camera optics."""
        env_tokens = self.active_environment.compile_background_tokens()
        subject_id = shot.subject_entity.lower()

        # Case A: Environmental Establishing Shot (No Characters)
        if subject_id == "environment":
            prompt = (
                f"Masterpiece cinematic webtoon key visual, {shot.shot_type}, "
                f"{shot.subject_action}. {env_tokens}. "
                f"Volumetric blizzard lighting, ethereal cyan glow, hyper-detailed digital matte painting, 8k key visual."
            )
            neg_prompt = "people, human, face, hands, body, character, crowd, modern cars, blurry, low quality"
            ref_images = [self.env_anchor] if self.env_anchor.exists() else None
            return prompt, neg_prompt, ref_images

        # Case B: Prop / System Screen Macro Insert
        if subject_id == "prop":
            prompt = (
                f"Masterpiece cinematic macro insert, {shot.shot_type}, {shot.subject_action}, "
                f"set against the glowing icy blue translucent frost stone of the abyss. "
                f"Holographic glowing neon-gold and cyan system UI glyphs, hyper-detailed textures, 8k."
            )
            neg_prompt = "full body, face, character, people, blurry, low quality"
            return prompt, neg_prompt, None

        # Case C: Action Clash Between Two Characters
        if subject_id == "action_clash":
            opponent_id = shot.opponent_entity.lower() if shot.opponent_entity else "vice_leader_drake"
            opponent = self.entities.get(opponent_id, self.entities["vice_leader_drake"])
            protag = self.entities["kang_jinwoo"]
            
            prompt = (
                f"Cinematic manhua dynamic action clash, {shot.shot_type}, intense battle impact. "
                f"[FIGHTER 1 LEFT: {protag.name}: {protag.visual_tags}]. "
                f"[FIGHTER 2 RIGHT: {opponent.name}: {opponent.visual_tags}]. "
                f"{shot.subject_action}. "
                f"Background: {env_tokens}. "
                f"Blinding energy shockwave, exploding ice crystals, cyan and gold sparks flying, high contrast, 8k."
            )
            neg_prompt = "blurry, distorted limbs, extra limbs, bad anatomy, calm expressions"
            ref_images = []
            if protag.anchor_image_path and protag.anchor_image_path.exists():
                ref_images.append(protag.anchor_image_path)
            if opponent.anchor_image_path and opponent.anchor_image_path.exists():
                ref_images.append(opponent.anchor_image_path)
            return prompt, neg_prompt, ref_images or None

        # Case D: Single Character-Focused Shots
        entity = self.entities.get(subject_id)
        if entity:
            facing_dir = "facing screen-right" if entity.default_screen_side == "left" else "facing screen-left"
            weapon_clause = f", wielding {shot.weapon_in_hand}" if shot.weapon_in_hand else ""
            damage_clause = f", physical state: {shot.damage_state}" if shot.damage_state else ""
            
            prompt = (
                f"Cinematic manhwa illustration, {shot.shot_type}, dramatic composition. "
                f"[CHARACTER: {entity.name}: {entity.visual_tags}{weapon_clause}{damage_clause}]. "
                f"{shot.subject_action}, positioned {entity.default_screen_side} of frame, {facing_dir}. "
                f"Background: {env_tokens}. "
                f"High-contrast ink chiaroscuro, volumetric cyan blizzard haze, glowing eyes, masterpiece, 8k."
            )
            extra_neg = f", {shot.forbidden_props}" if shot.forbidden_props else ""
            if shot.damage_state:
                extra_neg += ", clean undamaged armor, smooth pristine chestplate"
            neg_prompt = f"{entity.negative_tags}, blurry, distorted limbs, bad anatomy{extra_neg}"
            
            # Somatic Emotion Guider
            is_victim = bool(shot.damage_state and any(k in shot.damage_state.lower() for k in ["caved", "cracked", "pain", "shock", "blood"]))
            is_striker = bool(any(k in shot.emotion_tone.lower() for k in ["strike", "wrath", "battle", "clash"]))
            prompt, neg_prompt = self.emotion_guider.guide_prompt(
                base_prompt=prompt,
                base_negative_prompt=neg_prompt,
                emotion_tone=shot.emotion_tone,
                is_victim_receiving_strike=is_victim,
                is_striker_attacking=is_striker,
            )
            ref_images = [entity.anchor_image_path] if entity.anchor_image_path and entity.anchor_image_path.exists() else None
            return prompt, neg_prompt, ref_images

        # Default fallback
        prompt = f"Cinematic manhwa illustration, {shot.shot_type}, {shot.subject_action}. Background: {env_tokens}. 8k."
        neg_prompt = "blurry, low quality, bad anatomy"
        return prompt, neg_prompt, None

    async def synthesize_continuous_storyteller_audio(
        self,
        shots: List[CinematicShotSpec],
        output_dir: Path,
    ) -> List[tuple[Path, float]]:
        """Synthesizes individual speech segments with dynamic emotional cadence and measures exact durations."""
        output_dir.mkdir(parents=True, exist_ok=True)
        results: List[tuple[Path, float]] = []

        for shot in shots:
            audio_path = output_dir / f"audio_{shot.shot_index:03d}.mp3"
            if not audio_path.exists():
                comm = edge_tts.Communicate(
                    text=shot.narration_line,
                    voice="en-US-ChristopherNeural",
                    rate=shot.tts_rate,
                    pitch=shot.tts_pitch,
                )
                await comm.save(str(audio_path))

            dur = self._get_audio_duration(audio_path)
            results.append((audio_path, dur))

        return results

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Measures exact audio stream duration in seconds using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 5.0
