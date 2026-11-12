"""Somatic Emotion & Kinetic Intensity Guider Agent for Qwen Image 2.1.

Translates abstract narrative emotions into micro-anatomical, physiological,
and biomechanical visual tokens that force diffusion models out of static,
stoic "handsome mannequin" poses into visceral, high-stakes human reality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("panelflow.creative.emotion_guider")


class SomaticArchetype(str, Enum):
    VISCERAL_TRAUMA = "visceral_trauma"  # Taking heavy blow: open scream, blood spittle, whiplash, arched spine
    LETHAL_WRATH = "lethal_wrath"        # Attacking: ferocious snarl, bulging veins, flaring iris aura
    PARALYZING_DREAD = "paralyzing_dread"# Terror: pinpoint pupils, cold sweat beads, trembling, recoiling
    CRUEL_ARROGANCE = "cruel_arrogance"  # Antagonist mockery: asymmetrical sneer, tilted chin, cold slit eyes
    DESPERATE_EXHAUSTION = "desperate_exhaustion" # Heavy panting, sweat dripping, blood in eyes, slumped
    SOVEREIGN_AWE = "sovereign_awe"      # Epiphany/Divine: wide eyes lit by celestial beam, reverent parted lips
    TENSION_STANDOFF = "tension_standoff"# Piercing steely gaze, clenched jaw, ozone/lightning crackle around fingers


@dataclass
class SomaticDescriptor:
    archetype: SomaticArchetype
    cranial_micro_anatomy: str
    oral_and_dental: str
    vascular_tension: str
    biomechanical_posture: str
    kinetic_fx: str
    mandatory_negative_tokens: str = (
        "calm face, peaceful expression, handsome model pose, gentle expression, closed mouth, polite frown, "
        "stoic, emotionless, stiff posture, relaxed body, smiling, friendly, blank stare, unbothered"
    )

    def compile_somatic_clause(self) -> str:
        """Returns the assembled somatic description for prompt injection."""
        return (
            f"{self.cranial_micro_anatomy}, {self.oral_and_dental}, "
            f"{self.vascular_tension}, {self.biomechanical_posture}, {self.kinetic_fx}"
        )


# Canonical Micro-Anatomical Lexicon for Qwen Image 2.1
SOMATIC_LEXICON: Dict[SomaticArchetype, SomaticDescriptor] = {
    SomaticArchetype.VISCERAL_TRAUMA: SomaticDescriptor(
        archetype=SomaticArchetype.VISCERAL_TRAUMA,
        cranial_micro_anatomy="eyes wide in agonizing shock with exposed white sclera and dilated pupils, head violently snapped backward by concussive whiplash",
        oral_and_dental="mouth stretched wide in an agonizing breathless scream of sheer trauma, teeth bared with crimson blood spittle and saliva spraying into the air",
        vascular_tension="neck tendons straining taut under kinetic force, veins bulging across forehead and temples",
        biomechanical_posture="spine arched violently backward under the devastating impact, knees buckling, hands trembling in mid-air",
        kinetic_fx="concussive air distortion rings shattering raindrops, radial ink-black shockwave bursting with sparks, frozen droplets of blood mist in flight",
    ),
    SomaticArchetype.LETHAL_WRATH: SomaticDescriptor(
        archetype=SomaticArchetype.LETHAL_WRATH,
        cranial_micro_anatomy="brows deeply furrowed casting pitch-black shadows over the eyes, piercing glowing amethyst iris blazing with lethal warrior fury",
        oral_and_dental="teeth bared in a fierce animalistic warrior snarl with exposed canines",
        vascular_tension="corded neck muscles bulging with explosive kinetic power, pulsating temple vein",
        biomechanical_posture="body lunging violently forward driving all mass into the strike, knuckles white with crushing pressure",
        kinetic_fx="directional ink-splash kinetic lines, spiraling vacuum vortex around the fist, electric sparks",
    ),
    SomaticArchetype.PARALYZING_DREAD: SomaticDescriptor(
        archetype=SomaticArchetype.PARALYZING_DREAD,
        cranial_micro_anatomy="pupils contracted to terrified pinpoints, ash-pale skin drained of color, cold sweat beads dripping down cheeks",
        oral_and_dental="jaw slack and dropped open in breathless speechless shock",
        vascular_tension="throat muscles constricted, rapid shallow breathing visible in chest",
        biomechanical_posture="body recoiling backward involuntarily, trembling shaking hands clutching weapon weakly, hunched shoulders",
        kinetic_fx="heavy dark shadows engulfing upper face, trembling atmospheric aura",
    ),
    SomaticArchetype.CRUEL_ARROGANCE: SomaticDescriptor(
        archetype=SomaticArchetype.CRUEL_ARROGANCE,
        cranial_micro_anatomy="one eyebrow raised with heavy-lidded downward gaze, ruthless contemptuous smirk",
        oral_and_dental="corner of lip curled upward in a mocking sneer revealing a sharp canine tooth",
        vascular_tension="completely relaxed dominant posture with effortless breathing",
        biomechanical_posture="chin tilted upward looking down at opponent like an insect, chest pushed forward, dominant stance",
        kinetic_fx="sharp high-contrast chiaroscuro, wind whipping cape in majestic arrogance",
    ),
    SomaticArchetype.DESPERATE_EXHAUSTION: SomaticDescriptor(
        archetype=SomaticArchetype.DESPERATE_EXHAUSTION,
        cranial_micro_anatomy="heavy-lidded bloodshot eyes straining to remain open, streak of blood dripping down brow into eye",
        oral_and_dental="mouth parted gasping for oxygen, dry cracked lips, chest heaving violently",
        vascular_tension="muscles trembling with lactic acid failure, ragged breath mist",
        biomechanical_posture="torso bent forward, hand pressed against bruised ribs or knee to stay upright, unsteady footing",
        kinetic_fx="steam rising from rain-soaked exhausted skin, splashing mud on trembling boots",
    ),
    SomaticArchetype.SOVEREIGN_AWE: SomaticDescriptor(
        archetype=SomaticArchetype.SOVEREIGN_AWE,
        cranial_micro_anatomy="wide luminous eyes illuminated by celestial violet radiance, looking upward toward the heavens",
        oral_and_dental="lips parted in quiet awe and resolute transcendent determination",
        vascular_tension="calm unshakeable divine serenity, sovereign presence",
        biomechanical_posture="standing tall with perfect spine alignment, arms relaxed at sides, chest open to the heavens",
        kinetic_fx="radiant vertical beam of cosmic energy, raindrops instantly evaporating into glowing violet mist",
    ),
    SomaticArchetype.TENSION_STANDOFF: SomaticDescriptor(
        archetype=SomaticArchetype.TENSION_STANDOFF,
        cranial_micro_anatomy="steely unblinking amethyst gaze locked onto target, sharp furrow in brow",
        oral_and_dental="jaw clenched tight grinding molars, lips pressed into a hard resolute line",
        vascular_tension="subtle electric crackle around knuckles, muscles primed like a coiled spring",
        biomechanical_posture="low balanced martial stance, weight centered on ball of foot, fingers twitching with lethal intent",
        kinetic_fx="subtle violet lightning arcs crackling off fingertips, rain sizzling against warm skin",
    ),
}


class SomaticEmotionGuiderAgent:
    """Prompt Guider Agent that enhances prompts with visceral somatic micro-anatomy."""

    def __init__(self):
        self.lexicon = SOMATIC_LEXICON

    def infer_archetype(
        self,
        emotion_tone: str,
        is_victim_receiving_strike: bool = False,
        is_striker_attacking: bool = False,
    ) -> SomaticArchetype:
        """Determines the exact somatic archetype based on dramatic context."""
        tone_lower = emotion_tone.lower()

        if is_victim_receiving_strike or any(k in tone_lower for k in ["trauma", "agony", "pain", "struck", "smashed", "reeling"]):
            return SomaticArchetype.VISCERAL_TRAUMA

        if is_striker_attacking or any(k in tone_lower for k in ["wrath", "fury", "strike", "explosive", "battle_explosive", "clash"]):
            return SomaticArchetype.LETHAL_WRATH

        if any(k in tone_lower for k in ["dread", "terror", "fear", "trembling", "panic"]):
            return SomaticArchetype.PARALYZING_DREAD

        if any(k in tone_lower for k in ["arrogance", "confrontation", "mockery", "taunt"]):
            return SomaticArchetype.CRUEL_ARROGANCE

        if any(k in tone_lower for k in ["exhaustion", "desperate", "fatigue", "wounded"]):
            return SomaticArchetype.DESPERATE_EXHAUSTION

        if any(k in tone_lower for k in ["triumph_awe", "awe", "sovereign", "epiphany", "divine", "climax"]):
            return SomaticArchetype.SOVEREIGN_AWE

        return SomaticArchetype.TENSION_STANDOFF

    def guide_prompt(
        self,
        base_prompt: str,
        base_negative_prompt: str,
        emotion_tone: str,
        is_victim_receiving_strike: bool = False,
        is_striker_attacking: bool = False,
    ) -> Tuple[str, str]:
        """Injects somatic micro-anatomy tokens into positive prompt and anti-stoic tokens into negative prompt."""
        archetype = self.infer_archetype(
            emotion_tone=emotion_tone,
            is_victim_receiving_strike=is_victim_receiving_strike,
            is_striker_attacking=is_striker_attacking,
        )
        desc = self.lexicon[archetype]
        somatic_clause = desc.compile_somatic_clause()

        # Inject somatic details into prompt
        enhanced_prompt = f"{base_prompt}. [SOMATIC EMOTION & INTENSITY: {somatic_clause}]."

        # Inject anti-stoic negative tokens
        enhanced_neg = f"{base_negative_prompt}, {desc.mandatory_negative_tokens}"

        logger.debug(f"Guided prompt with archetype: {archetype.value}")
        return enhanced_prompt, enhanced_neg
