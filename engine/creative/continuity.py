"""Scene Continuity, Environmental Landmark Locking, and Cinematic Directing Engine.

Solves the core visual & audio consistency problems in manhua video generation:
1. Environment Continuity: Locks persistent geographic landmarks across all shots in a scene.
2. Character & Faction Uniformity: Locks armor, face, and weapon profiles for side characters & squads.
3. Cinematic Direction: Enforces the 180-degree rule, spatial eye-lines, and professional shot progression.
4. Human Storyteller Cadence: Assembles continuous narration with dynamic emotional pacing and zero dead silence.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import subprocess
from typing import Any, Dict, List, Optional

import edge_tts

logger = logging.getLogger("panelflow.creative.continuity")

ANCHORS_CHAR_DIR = Path("output/series_1000/character_anchors")
ANCHORS_ENV_DIR = Path("output/series_1000/environment_anchors")


@dataclass
class EnvironmentalLandmarks:
    location_name: str
    geology: str
    crystal_features: str
    ground_surface: str
    sky_and_weather: str
    lighting_sources: str

    def compile_background_tokens(self) -> str:
        """Returns the immutable environmental tokens that MUST be present in all scene shots."""
        return (
            f"in {self.location_name}, {self.geology}, {self.crystal_features}, "
            f"{self.ground_surface}, {self.sky_and_weather}, {self.lighting_sources}"
        )


@dataclass
class CharacterVisualProfile:
    id: str
    name: str
    role: str  # protagonist | antagonist | side_character | faction_squad
    visual_tags: str
    negative_tags: str
    anchor_image_path: Optional[Path] = None
    default_screen_side: str = "left"  # "left" for protagonist, "right" for antagonists


@dataclass
class CinematicShotSpec:
    shot_index: int
    scene_name: str
    shot_type: str  # EWS, MLS, OTS, MCU, Action_Dutch, Macro_Insert, Climax_Hero
    screen_axis: str  # e.g., "protagonist facing right, enforcers facing left"
    subject_entity: str  # chen_ye | lingxiao_enforcer | commander_meng | li_ming | environment | prop | action_clash
    subject_action: str
    camera_movement: str  # slow_push_in | slow_pan_down | lateral_track | zoom_burst
    narration_line: str
    emotion_tone: str  # mystery | tension | confrontation | battle_explosive | triumph_awe
    opponent_entity: Optional[str] = None  # Explicit opponent entity ID for clash & aftermath continuity
    weapon_in_hand: Optional[str] = None  # None if weapon was destroyed or unarmed
    damage_state: Optional[str] = None  # e.g. "caved inward breastplate, cracked armor, void smoke"
    forbidden_props: Optional[str] = None  # e.g. "sword, blade, weapon in hand"
    tts_rate: str = "-6%"
    tts_pitch: str = "-2Hz"
    intentional_pause_after_seconds: float = 0.15  # Natural breath buffer; higher only at cliffhangers


class SceneContinuityDirector:
    """Master director enforcing environmental, character, and cinematographic continuity."""

    def __init__(self):
        # 1. Register Default Locked Environment: Abyssal Basalt Quarry
        self.active_environment = EnvironmentalLandmarks(
            location_name="Abyssal Basalt Quarry",
            geology="towering vertical hexagonal black basalt cliff walls with sharp geometric fissures",
            crystal_features="glowing luminescent violet crystal ore veins running vertically through wet black stone",
            ground_surface="rain-slicked dark obsidian terraces and crushed black gravel with shallow water puddles reflecting purple light",
            sky_and_weather="cold driving torrential rain, heavy rolling fog, dark stormy twilight with a faint purple eclipse halo in the turbulent sky",
            lighting_sources="flickering warm amber torchlight from rusted iron braziers on stone ledges, volumetric rain haze",
        )
        self.env_anchor = ANCHORS_ENV_DIR / "abyssal_quarry_anchor.png"

        # 2. Register Locked Entity Profiles
        self.entities: Dict[str, CharacterVisualProfile] = {
            "chen_ye": CharacterVisualProfile(
                id="chen_ye",
                name="Chen Ye",
                role="protagonist",
                visual_tags=(
                    "young martial artist, pitch-black hair with stark snow-white streaks, "
                    "piercing glowing amethyst-purple eyes, jagged battle scar across left eyebrow, "
                    "pale skin with light coal dust, tattered dark gray linen tunic"
                ),
                negative_tags="blurry, low quality, distorted anatomy, text artifacts, static chained arms pose",
                anchor_image_path=ANCHORS_CHAR_DIR / "chen_ye_anchor.png",
                default_screen_side="left",
            ),
            "lingxiao_enforcer": CharacterVisualProfile(
                id="lingxiao_enforcer",
                name="Lingxiao Iron Enforcer",
                role="faction_squad",
                visual_tags=(
                    "imperial soldier clad in uniform matte-black spiked segmented iron plate armor, "
                    "full-face iron barbute helmet with single narrow horizontal glowing crimson visor slit, "
                    "heavy spiked iron pauldrons, wielding matching double-edged serrated black steel polearm halberd, "
                    "black iron combat boots"
                ),
                negative_tags="silver armor, gold armor, open visor, bare face, human skin, modern clothes, colorful",
                anchor_image_path=ANCHORS_CHAR_DIR / "lingxiao_enforcer_anchor.png",
                default_screen_side="right",
            ),
            "commander_meng": CharacterVisualProfile(
                id="commander_meng",
                name="Commander Meng",
                role="antagonist",
                visual_tags=(
                    "towering lead enforcer commander, massive muscular build, ruthless scowl, "
                    "jagged battle scar across lower jaw, heavy black-and-crimson spiked plate armor "
                    "with silver dragon embossed on left pauldron, spiked right pauldron, hair in warrior topknot"
                ),
                negative_tags="blonde hair, clean face, slender build, friendly expression, modern clothes",
                anchor_image_path=ANCHORS_CHAR_DIR / "commander_meng_anchor.png",
                default_screen_side="right",
            ),
            "li_ming": CharacterVisualProfile(
                id="li_ming",
                name="Li Ming",
                role="side_character",
                visual_tags=(
                    "elderly dust-covered quarry slave, gaunt hollow cheeks, deep-set tired dark eyes, "
                    "scraggly gray beard stubble, frayed dark brown burlap mining vest over tattered linen rags, "
                    "rope belt around waist, holding flickering rusted iron torch"
                ),
                negative_tags="young, muscular, armor, clean clothes, smooth face, modern",
                anchor_image_path=ANCHORS_CHAR_DIR / "li_ming_anchor.png",
                default_screen_side="left",
            ),
        }

    def compile_shot_prompt(self, shot: CinematicShotSpec) -> tuple[str, str, Optional[Path]]:
        """Compiles an ArtEngine prompt preserving environmental landmarks, character profile, and camera optics."""
        env_tokens = self.active_environment.compile_background_tokens()
        subject_id = shot.subject_entity.lower()

        # Case A: Environmental Establishing Shot (No Characters)
        if subject_id == "environment":
            prompt = (
                f"Masterpiece cinematic manhua environment key visual, {shot.shot_type}, "
                f"{shot.subject_action}. {env_tokens}. "
                f"Atmospheric depth, volumetric rain lighting, hyper-detailed digital matte painting, 8k key visual."
            )
            neg_prompt = "people, human, face, hands, body, character, crowd, modern structures, blurry, low quality"
            ref_image = self.env_anchor if self.env_anchor.exists() else None
            return prompt, neg_prompt, ref_image

        # Case B: Prop / Weapon Macro Insert
        if subject_id == "prop":
            prompt = (
                f"Masterpiece cinematic macro insert, {shot.shot_type}, {shot.subject_action}, "
                f"resting on the rain-slick dark basalt quarry stone with puddles and glowing violet crystal reflections. "
                f"Dramatic chiaroscuro, volumetric rain, hyper-detailed textures, 8k."
            )
            neg_prompt = "full body, face, character, people, blurry, low quality, cartoon"
            return prompt, neg_prompt, None

        # Case C: Character-Focused Shots (Chen Ye, Enforcer, Commander, Li Ming)
        entity = self.entities.get(subject_id)
        if entity:
            # Enforce 180-degree screen axis framing
            facing_dir = "facing screen-right" if entity.default_screen_side == "left" else "facing screen-left"
            weapon_clause = f", wielding {shot.weapon_in_hand}" if shot.weapon_in_hand else ""
            damage_clause = f", physical state: {shot.damage_state}" if shot.damage_state else ""
            
            prompt = (
                f"Cinematic manhua illustration, {shot.shot_type}, dramatic composition. "
                f"[CHARACTER: {entity.name}: {entity.visual_tags}{weapon_clause}{damage_clause}]. "
                f"{shot.subject_action}, positioned {entity.default_screen_side} of frame, {facing_dir}. "
                f"Background: {env_tokens}. "
                f"High-contrast ink chiaroscuro, volumetric rain haze, dynamic cel-shading, masterpiece, 8k."
            )
            extra_neg = f", {shot.forbidden_props}" if shot.forbidden_props else ""
            if shot.damage_state:
                extra_neg += ", clean undamaged armor, smooth pristine chestplate"
            neg_prompt = f"{entity.negative_tags}, blurry, distorted limbs, bad anatomy, inconsistent armor{extra_neg}"
            ref_image = entity.anchor_image_path if (entity.anchor_image_path and entity.anchor_image_path.exists()) else None
            return prompt, neg_prompt, ref_image

        # Case D: Multi-character or Action Clash
        opponent_id = (shot.opponent_entity or "commander_meng").lower()
        opponent = self.entities.get(opponent_id, self.entities["commander_meng"])
        chen = self.entities["chen_ye"]

        opponent_weapon = f", wielding {shot.weapon_in_hand}" if shot.weapon_in_hand else ""
        opponent_damage = f", {shot.damage_state}" if shot.damage_state else ""

        prompt = (
            f"Cinematic manhua action illustration, {shot.shot_type}, {shot.subject_action}. "
            f"Protagonist Chen Ye on screen-left [CHARACTER: {chen.name}: {chen.visual_tags}] "
            f"clashing against {opponent.name} on screen-right [CHARACTER: {opponent.name}: {opponent.visual_tags}{opponent_weapon}{opponent_damage}]. "
            f"Background: {env_tokens}. "
            f"Volumetric sparks, dynamic ink splash effects, high contrast lighting, masterpiece, 8k."
        )
        extra_neg = f", {shot.forbidden_props}" if shot.forbidden_props else ""
        neg_prompt = f"blurry, low quality, distorted anatomy, modern clothes, text artifacts{extra_neg}"
        ref_image = chen.anchor_image_path
        return prompt, neg_prompt, ref_image

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

            # Measure exact duration via ffprobe
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
