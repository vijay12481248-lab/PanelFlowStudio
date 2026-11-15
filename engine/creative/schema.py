"""Data contracts and schemas for the Creative Multi-Agent Studio.

Defines Pydantic models for Story Bible, Characters, Novel Chapters,
Cinematic Scenes, Shots, and Generative Tool Instructions.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StoryGenre(str, Enum):
    MYTHOLOGICAL_EPIC = "mythological_epic"
    SCI_FI = "sci_fi"
    FANTASY = "fantasy"
    HISTORICAL_DRAMA = "historical_drama"
    CYBERPUNK = "cyberpunk"
    SUPERNATURAL_THRILLER = "supernatural_thriller"
    SLICE_OF_LIFE = "slice_of_life"
    CUSTOM = "custom"


class VisualStyle(str, Enum):
    CINEMATIC_PHOTO = "cinematic_photorealistic"
    ANIME_EPIC = "anime_epic"
    DARK_FANTASY_OIL = "dark_fantasy_oil"
    VINTAGE_MANGA = "vintage_manga"
    SOLARPUNK = "solarpunk"
    CUSTOM = "custom"


class StorySeed(BaseModel):
    """Initial user prompt and creative steering parameters."""
    prompt: str = Field(description="Abstract seed or story concept (e.g. 'Mahabharata: Fall of Bhishma' or sci-fi exploration)")
    genre: StoryGenre = Field(default=StoryGenre.MYTHOLOGICAL_EPIC, description="Primary narrative genre")
    visual_style: VisualStyle = Field(default=VisualStyle.CINEMATIC_PHOTO, description="Visual aesthetic style")
    tone: str = Field(default="Epic, sorrowful, philosophically profound", description="Emotional tone")
    target_chapters: int = Field(default=1, ge=1, le=10, description="Number of chapters to synthesize")
    parent_folder: Optional[str] = Field(default=None, description="Custom disk directory for scenes and shots")


class CharacterProfile(BaseModel):
    """Detailed character specification maintaining visual and psychological identity."""
    id: str = Field(description="Unique slug identifier (e.g. 'bhishma', 'arjuna')")
    name: str = Field(description="Full character name")
    role: str = Field(description="Protagonist, Antagonist, Mentor, Companion, etc.")
    visual_tags: str = Field(description="Strict comma-separated visual tags reused in art prompts")
    personality: str = Field(description="Core psychology, temperament, and speech cadence")
    signature_item: str = Field(default="", description="Iconic weapon, talisman, armor, or artifact")
    facial_features: str = Field(default="", description="Distinct facial characteristics, eye color, scars, age markers")
    emotional_arc: str = Field(default="", description="Trauma, motivation, and emotional evolution")
    anchor_image: Optional[str] = Field(default=None, description="Reference keyframe image filename")
    tag: str = Field(default="<Picture 1>", description="Storyboard picture tag for prompt chaining")


class WorldLore(BaseModel):
    """World-building principles, setting, factions, and immutable rules."""
    world_name: str
    era_or_timeline: str
    setting_overview: str
    rules: List[str] = Field(default_factory=list, description="Immutable physical or cosmological rules that cannot be violated")
    key_factions: List[str] = Field(default_factory=list)


class ChapterBeat(BaseModel):
    """Narrative beat within a chapter roadmap."""
    beat_index: int
    title: str
    narrative_summary: str
    emotional_shift: str
    characters_present: List[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    """Structural blueprint for an individual novel chapter."""
    chapter_number: int
    title: str
    epigraph: str = Field(default="", description="Opening philosophical quote or poetic epigraph")
    dramatic_premise: str
    beats: List[ChapterBeat] = Field(default_factory=list)


class StoryBible(BaseModel):
    """Comprehensive narrative and visual canon synthesized by the Showrunner."""
    title: str
    logline: str
    thematic_core: str
    emotional_arc: str
    lore: WorldLore
    characters: List[CharacterProfile] = Field(default_factory=list)
    chapter_outlines: List[ChapterOutline] = Field(default_factory=list)


class NovelChapter(BaseModel):
    """Full-length novel chapter drafted with literary depth."""
    chapter_number: int
    title: str
    epigraph: str = ""
    prose: str = Field(description="Complete rich narrative text including internal monologue and dialogue")
    summary: str
    word_count: int = 0
    emotional_peak: str = ""


class EditorialCritique(BaseModel):
    """Auditing and refinement verdict from the Story Editor agent."""
    score: float = Field(default=8.0, ge=1.0, le=10.0, description="Overall narrative quality score out of 10")
    continuity_pass: bool = Field(description="True if lore, items, and character descriptions remain consistent")
    critique_notes: List[str] = Field(default_factory=list, description="Editorial feedback on pacing, emotion, and voice")
    polished_prose: Optional[str] = Field(default=None, description="Polished version of the chapter prose if revisions were made")


class CinematicShot(BaseModel):
    """A single visual shot specification for visual art and video generation."""
    shot_index: int
    scene_index: int = 1
    title: str
    shot_type: str = Field(default="Medium Tracking", description="Wide Establishing, Medium Tracking, Macro Close-Up, Low-Angle Hero, etc.")
    duration: float = Field(default=5.2, description="Shot duration in seconds")
    workflow: str = Field(default="sliding_window", description="'reference' for first shot, 'sliding_window' for chained shots")
    camera_movement: str = Field(description="Exact camera vector, speed, angle, and optical movement")
    subject_description: str = Field(description="Subject pose, actions, and micro-facial expressions")
    environmental_details: str = Field(description="Atmospheric conditions, architecture, particle effects, ground textures")
    lighting_and_atmosphere: str = Field(description="Chiaroscuro, volumetric rays, color temperatures, shadows")
    soundscape: str = Field(description="Diegetic audio, foley, footsteps, suit hum, wind, strictly no speech")
    non_diegetic_music: str = Field(description="Musical texture, tempo, instruments, and emotional chord")
    prompt: str = Field(default="", description="Compiled 6-heading MiniMax H3 prompt string")
    art_prompt: str = Field(default="", description="Compiled Qwen Image 2.1 art prompt")
    first_frame: Optional[str] = Field(default=None, description="Anchor image or tail frame input")
    last_frame: Optional[str] = Field(default=None)
    rendered_video: Optional[str] = Field(default=None, description="Path to rendered .mp4 file")
    rendered_video_filename: Optional[str] = Field(default=None)
    folder_id: Optional[str] = Field(default=None)


class CinematicScene(BaseModel):
    """A thematic sequence of cinematic shots grouped within a scene folder."""
    scene_index: int
    id: str
    name: str
    description: str
    path: str = Field(default="", description="Disk directory path for this scene's assets")
    shot_indices: List[int] = Field(default_factory=list)
    shots: List[CinematicShot] = Field(default_factory=list)


class SelfCritiqueVerdict(BaseModel):
    """Metacognitive self-evaluation verdict generated by an agent reflecting on its own work."""
    quality_score: float = Field(ge=1.0, le=10.0, description="Self-assessed quality score from 1.0 to 10.0")
    passed_rubric: bool = Field(description="True if artifact meets all strict aesthetic and lore criteria")
    detected_weaknesses: List[str] = Field(default_factory=list, description="Specific flaws, clichés, or continuity lapses found")
    continuity_violations: List[str] = Field(default_factory=list, description="Violations of world lore, character traits, or physical rules")
    actionable_improvements: List[str] = Field(default_factory=list, description="Concrete revisions needed to elevate quality")
    learned_principles: List[str] = Field(default_factory=list, description="Generalizable heuristics learned to store in permanent memory")


class LearnedHeuristic(BaseModel):
    """A self-learned heuristic or rule discovered through reflection and critique."""
    id: str
    domain: str = Field(description="Domain: character_lore, novel_prose, cinematography, h3_prompting, art_engine")
    rule: str = Field(description="The actionable lesson or constraint learned")
    source_project: str = Field(default="", description="The project or context where this was learned")
    confidence_score: float = Field(default=1.0, description="Confidence rating")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SelfImprovementReport(BaseModel):
    """Audit trail of autonomous self-refinement iterations."""
    agent_name: str
    target_artifact: str
    initial_score: float
    final_score: float
    iterations: int = 1
    critique_history: List[SelfCritiqueVerdict] = Field(default_factory=list)
    new_heuristics_stored: List[str] = Field(default_factory=list)


class MistakeSeverity(str, Enum):
    CRITICAL = "critical"  # Lore breaks, tool crashes, soundscape dialogue leaks
    HIGH = "high"          # Flat writing, repetitive camera moves, visual drift
    MEDIUM = "medium"      # Minor pacing lag or stylistic cliches


class MistakeRecord(BaseModel):
    """Cataloged failure pattern or regression anti-pattern to permanently avoid."""
    mistake_id: str = Field(description="Unique slug for the mistake, e.g. 'err_h3_soundscape_speech'")
    domain: str = Field(description="Domain: novel_prose, character_lore, cinematography, h3_prompting, art_engine")
    category: str = Field(default="general", description="Category: continuity, tool_syntax, sensory_immersion, camera_optics")
    flawed_pattern: str = Field(description="The exact flaw, bad habit, or anti-pattern that failed previously")
    prevention_rule: str = Field(description="Mandatory imperative instruction agents must follow to avoid this mistake")
    example_bad: str = Field(default="", description="Concrete example illustrating the mistake")
    example_good: str = Field(default="", description="Concrete example illustrating the corrected approach")
    recurrence_count: int = Field(default=1, description="Number of times this mistake was detected or flagged")
    last_detected: str = Field(default_factory=lambda: datetime.now().isoformat())
    severity: MistakeSeverity = Field(default=MistakeSeverity.HIGH)


class RegressionAuditVerdict(BaseModel):
    """Result of automated post-execution audit checking whether any known mistakes were repeated."""
    passed: bool = Field(description="True if zero recurring mistakes or regressions were detected")
    detected_mistakes: List[MistakeRecord] = Field(default_factory=list, description="Known mistakes detected in the output")
    regression_warnings: List[str] = Field(default_factory=list, description="Human-readable warning messages")
    remediation_instructions: List[str] = Field(default_factory=list, description="Explicit rewrite instructions to fix the regression")


class AgentPostmortem(BaseModel):
    """Autonomous post-mortem analysis performed when an error or rejection occurs."""
    trigger_event: str = Field(description="What triggered the failure or rejection")
    root_cause: str = Field(description="Underlying reason the mistake occurred")
    preventative_rule: str = Field(description="The newly synthesized rule to avoid this in all future runs")
    new_anti_pattern: Optional[MistakeRecord] = Field(default=None)


class CreativeProject(BaseModel):
    """Root model representing an end-to-end creative novel and visual storyboard project."""
    project_id: str
    title: str
    seed: StorySeed
    bible: StoryBible
    chapters: List[NovelChapter] = Field(default_factory=list)
    scenes: List[CinematicScene] = Field(default_factory=list)
    parent_path: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "completed"
    self_improvement_reports: List[SelfImprovementReport] = Field(default_factory=list)
    regression_audits: List[RegressionAuditVerdict] = Field(default_factory=list)
    postmortems: List[AgentPostmortem] = Field(default_factory=list)


# =====================================================================
# KNOWLEDGE BASE, MANHUA STRUCTURAL ANALYSIS, & DYNAMIC FORGE SCHEMAS
# =====================================================================

class KnowledgeCategory(str, Enum):
    PANEL_COMPOSITION = "panel_composition"
    PACING_AND_RHYTHM = "pacing_and_rhythm"
    COLOR_SCRIPTING = "color_scripting"
    DIALOGUE_AND_SFX = "dialogue_and_sfx"
    CULTIVATION_XIANXIA = "cultivation_xianxia"
    ACTION_CHOREOGRAPHY = "action_choreography"
    CLIFFHANGERS = "cliffhangers"
    CHARACTER_ARCHETYPES = "character_archetypes"
    GENERAL = "general"


class KnowledgeEntry(BaseModel):
    """Atomic knowledge unit stored in the persistent hybrid RAG database."""
    entry_id: str
    category: KnowledgeCategory = KnowledgeCategory.GENERAL
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    source: str = "curated_wisdom"
    confidence_score: float = Field(default=0.9, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class PanelLayoutType(str, Enum):
    VERTICAL_SCROLL_FULL = "vertical_scroll_full"      # 100% width dramatic impact panel
    VERTICAL_SPLIT_STACK = "vertical_split_stack"      # Two vertical stacked panels
    HORIZONTAL_SPLIT = "horizontal_split"              # Left / Right dual focus
    DIAGONAL_ACTION = "diagonal_action"                # Dynamic action diagonal cut
    GUTTER_TRANSITION = "gutter_transition"            # Wide empty gutter for dramatic silence
    BORDERLESS_INSET = "borderless_inset"              # Borderless character headshot over background


class ManhuaPanel(BaseModel):
    """Single panel inside a continuous vertical-scroll Manhua or traditional Manga page."""
    panel_index: int
    layout_type: PanelLayoutType = PanelLayoutType.VERTICAL_SCROLL_FULL
    aspect_ratio: str = Field(default="16:9", description="e.g. 9:16 vertical, 16:9 cinematic, 1:1 square")
    gutter_spacing_px: int = Field(default=80, description="Vertical gap height representing temporal delay")
    visual_description: str = Field(description="Visual art composition and subject action")
    art_prompt: str = Field(description="Compiled Qwen Image 2.1 art prompt (unnamed tags)")
    dialogue_balloons: List[Dict[str, str]] = Field(default_factory=list, description="[{'character': 'Lin Feng', 'text': '...', 'style': 'shout'}]")
    sfx_onomatopoeia: List[Dict[str, str]] = Field(default_factory=list, description="[{'text': 'BOOM', 'meaning': 'shockwave', 'color': 'gold'}]")
    camera_angle: str = Field(default="eye-level", description="low-angle heroic, birds-eye, Dutch tilt")
    lighting_color: str = Field(default="warm ambient", description="Dominant atmospheric aura")
    narration_text: str = Field(default="", description="The dramatic story narration spoken while this panel is on screen")


class ManhuaEpisode(BaseModel):
    """Complete episodic script for an original Manhua/Manga episode."""
    episode_number: int
    title: str
    reading_flow: str = "vertical_scroll"  # "vertical_scroll" (webtoon/manhua) or "traditional_rtl" (manga)
    summary: str
    cliffhanger_hook: str
    panels: List[ManhuaPanel] = Field(default_factory=list)
    estimated_scroll_length_px: int = 12000
    theme_palette: List[str] = Field(default_factory=lambda: ["#0f172a", "#38bdf8", "#f59e0b"])


class ManhuaDeconstructionReport(BaseModel):
    """Clean-room structural analysis report extracted from a manga/manhua chapter."""
    source_title: str
    chapter_identifier: str
    total_panels: int
    average_aspect_ratio: str
    average_gutter_spacing: int
    color_temperature: str
    dialogue_density: float = Field(default=12.0, description="Average words per panel")
    pacing_profile: str = Field(default="Kinetic Action Escalation", description="Fast action / Atmospheric slow build / Dialogue heavy")
    cliffhanger_type: str = Field(default="Arrival of Powerhouse", description="Arrival, Sudden Strike, Secret Revealed, Impending Doom")
    extracted_heuristics: List[str] = Field(default_factory=list)
    action_flow_patterns: List[str] = Field(default_factory=list)


class DynamicAgentSpec(BaseModel):
    """Specification used by AgentForge to synthesize and register a new agent."""
    role_name: str
    domain: str
    description: str
    system_prompt: str
    required_capabilities: List[str] = Field(default_factory=lambda: ["reasoning", "knowledge_retrieval"])
    anti_patterns_to_enforce: List[str] = Field(default_factory=list)
    created_by: str = "AgentForge"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class DynamicSkillSpec(BaseModel):
    """Specification for an agent-synthesized skill module."""
    skill_name: str
    domain: str
    description: str
    instructions_markdown: str
    heuristics: List[str] = Field(default_factory=list)
    anti_patterns: List[str] = Field(default_factory=list)
    examples_bad: List[str] = Field(default_factory=list)
    examples_good: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
