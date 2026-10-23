/**
 * PanelFlow Studio — Chapter 5A: Mock Chapter Data & Voice Profiles
 *
 * Representative manga chapter: "Chapter 14: Whispers in the Obsidian Vault"
 * Demonstrating multi-character dialogue, narrator exposition, 4-tier storytelling
 * quality review (OCR vs Visual vs Context vs Script), smart scene binding, and
 * audio take revision tracking.
 */

import {
  type NarrationChapter,
  type CharacterProfile,
  type VoiceProfile,
  type NarrationSegment,
  type PageScriptRecord,
  computeContentHash,
} from "./NarrationStudio.types.ts";

export const MOCK_PAGE_SCRIPTS: Record<string, PageScriptRecord> = {
  "page_01": {
    page_id: "page_01",
    page_sequence: 1,
    full_script: "Page 1 welcomes us to the depths with dramatic flair and questionable dungeon exploration choices. The narrator opens like we are entering a cathedral of doom, but Elena Vance immediately ruins the eerie silence by yelling at Kaelen for waving his lantern like a festival sparkler. Kaelen's face is pure bewildered regret, wondering why he signed up for this quest in the first place. You have to love the classic trope: ancient unspeakable horrors lurk ahead, yet our squad is busy bickering over flashlight etiquette. The shadows stretch ominously, but Elena refuses to let darkness stop her sarcastic lecture. By the bottom panel, the banter abruptly halts as a faint click in the floor stones reminds them both that traps don't care about their feelings.",
    lines: [
      "Page 1 welcomes us to the depths with dramatic flair and questionable dungeon exploration choices.",
      "The narrator opens like we are entering a cathedral of doom, but Elena Vance immediately ruins the eerie silence by yelling at Kaelen for waving his lantern like a festival sparkler.",
      "Kaelen's face is pure bewildered regret, wondering why he signed up for this quest in the first place.",
      "You have to love the classic trope: ancient unspeakable horrors lurk ahead, yet our squad is busy bickering over flashlight etiquette.",
      "The shadows stretch ominously, but Elena refuses to let darkness stop her sarcastic lecture.",
      "By the bottom panel, the banter abruptly halts as a faint click in the floor stones reminds them both that traps don't care about their feelings."
    ],
    tone: "Humorous, Sarcastic & Suspenseful",
    panels_count: 4,
    humor_and_emotional_notes: "Comedic contrast between ancient doom and lantern bickering, pivoting into sudden trap suspense."
  },
  "page_02": {
    page_id: "page_02",
    page_sequence: 2,
    full_script: "Moving onto Page 2, and the tension spikes from zero to a hundred in four frantic panels. Scholar Caelum is visibly hyperventilating over an ancient seal, rambling like a terrified graduate student whose thesis just caught fire. Meanwhile, Elena is already drawing her daggers, totally unfazed and clearly unimpressed by the glowing runes of guaranteed obliteration. Kaelen is clutching his talisman like a lucky rabbit's foot, praying to deities that probably retired two centuries ago. The facial expressions here are absolute comedy gold: sheer panic on the left, icy annoyance on the right. And of course, the seal isn't just a decoration—it's a countdown timer that just hit zero!",
    lines: [
      "Moving onto Page 2, and the tension spikes from zero to a hundred in four frantic panels.",
      "Scholar Caelum is visibly hyperventilating over an ancient seal, rambling like a terrified graduate student whose thesis just caught fire.",
      "Meanwhile, Elena is already drawing her daggers, totally unfazed and clearly unimpressed by the glowing runes of guaranteed obliteration.",
      "Kaelen is clutching his talisman like a lucky rabbit's foot, praying to deities that probably retired two centuries ago.",
      "The facial expressions here are absolute comedy gold: sheer panic on the left, icy annoyance on the right.",
      "And of course, the seal isn't just a decoration—it's a countdown timer that just hit zero!"
    ],
    tone: "Comedic Disbelief, Fast-Paced & Tense",
    panels_count: 4,
    humor_and_emotional_notes: "Scholar panic roasts vs stoic assassin energy, ending on countdown cliffhanger."
  }
};


export const MOCK_VOICE_PROFILES: VoiceProfile[] = [
  {
    id: "voice_aria",
    name: "Aria — Velvet Narrator",
    gender: "Female",
    age_group: "Adult",
    timbre: "Deep, resonant, measured storytelling tone with acoustic warmth",
    recommended_emotions: ["Mysterious", "Serious", "Neutral", "Suspenseful"],
    sample_quote: "Beyond the shattered archway, the shadows seemed to inhale with ancient malice.",
    sample_audio_available: true,
    sample_audio_uri: "/assets/demo/aria_narration_sample.mp3",
    model_family: "F5-TTS",
    is_mock: true,
  },
  {
    id: "voice_vespera",
    name: "Vespera — Shadow Whisperer",
    gender: "Female",
    age_group: "Young",
    timbre: "Tense, breathy, focused, intimate rogue cadence with crisp diction",
    recommended_emotions: ["Whispering", "Fearful", "Determined", "Suspenseful"],
    sample_quote: "Keep your lantern hooded, Kaelen. Something down here is awake.",
    sample_audio_available: true,
    sample_audio_uri: "/assets/demo/vespera_sample.mp3",
    model_family: "Chatterbox",
    is_mock: true,
  },
  {
    id: "voice_caelum",
    name: "Caelum — Anxious Scholar",
    gender: "Male",
    age_group: "Young",
    timbre: "Articulate, slightly elevated pitch, stammering hesitation under stress",
    recommended_emotions: ["Fearful", "Sad", "Neutral", "Excited"],
    sample_quote: "These glyphs aren't a warning... they're a containment tether, and it's breaking!",
    sample_audio_available: false,
    model_family: "F5-TTS",
    is_mock: true,
  },
  {
    id: "voice_corvus",
    name: "Corvus — Grim Herald",
    gender: "Male",
    age_group: "Elderly",
    timbre: "Gravelly, echoing low register, chilling metallic resonance",
    recommended_emotions: ["Whispering", "Angry", "Serious", "Mysterious"],
    sample_quote: "Mortals tread where the stars themselves feared to look.",
    sample_audio_available: false,
    model_family: "Dia",
    is_mock: true,
  },
  {
    id: "voice_torin",
    name: "Torin — Heroic Resonant",
    gender: "Male",
    age_group: "Adult",
    timbre: "Bold, grounded, commanding baritone with unwavering resolve",
    recommended_emotions: ["Determined", "Angry", "Serious", "Excited"],
    sample_quote: "Stand your ground. We do not turn back until the core is secured.",
    sample_audio_available: true,
    sample_audio_uri: "/assets/demo/torin_sample.mp3",
    model_family: "F5-TTS",
    is_mock: true,
  },
  {
    id: "voice_lyra",
    name: "Lyra — Bright Inquisitor",
    gender: "Female",
    age_group: "Young",
    timbre: "Energetic, perceptive, clear and dynamic delivery with sharp turns",
    recommended_emotions: ["Excited", "Happy", "Determined", "Neutral"],
    sample_quote: "Look at the refraction in this prism! It's reacting to our footsteps!",
    sample_audio_available: false,
    model_family: "Chatterbox",
    is_mock: true,
  },
];

export const MOCK_CHARACTERS: CharacterProfile[] = [
  {
    id: "char_narrator",
    name: "The Narrator",
    role: "NARRATOR",
    color_accent: "#6366f1", // Indigo
    avatar_initials: "NR",
    default_voice_profile_id: "voice_aria",
    default_emotion: "Mysterious",
    default_speed: 1.0,
    notes: "Main storyteller. Delivers world-building, camera perspective, and psychological subtext.",
    segment_count: 3,
  },
  {
    id: "char_elena",
    name: "Elena Vance",
    role: "PROTAGONIST",
    color_accent: "#10b981", // Emerald
    avatar_initials: "EV",
    default_voice_profile_id: "voice_vespera",
    default_emotion: "Determined",
    default_speed: 1.05,
    notes: "Rogue-archaeologist investigating the Shattered Prism. Sharp, pragmatic, guarded.",
    segment_count: 2,
  },
  {
    id: "char_kaelen",
    name: "Kaelen Drake",
    role: "SUPPORTING",
    color_accent: "#f59e0b", // Amber
    avatar_initials: "KD",
    default_voice_profile_id: "voice_caelum",
    default_emotion: "Fearful",
    default_speed: 1.1,
    notes: "Arcane researcher companion. Brilliant scholar but physically out of his element.",
    segment_count: 2,
  },
  {
    id: "char_malakor",
    name: "Wraith of Malakor",
    role: "ANTAGONIST",
    color_accent: "#f43f5e", // Rose
    avatar_initials: "WM",
    default_voice_profile_id: "voice_corvus",
    default_emotion: "Whispering",
    default_speed: 0.85,
    notes: "Ancient entity sealed inside the obsidian chamber. Telepathic echo speaking to intruders.",
    segment_count: 1,
  },
];

// Helper to generate SVG manga panels for rich visual context
const makeMangaSvg = (title: string, subtitle: string, moodColor: string) => `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200" width="100%" height="100%" style="background:#09090b;">
  <defs>
    <linearGradient id="g_${title.replace(/\s+/g, "_")}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#18181b" />
      <stop offset="100%" stop-color="${moodColor}" stop-opacity="0.25" />
    </linearGradient>
    <pattern id="hatch" width="8" height="8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="0" y2="8" stroke="#27272a" stroke-width="1" />
    </pattern>
  </defs>
  <rect width="320" height="200" fill="url(#g_${title.replace(/\s+/g, "_")})" />
  <rect width="320" height="200" fill="url(#hatch)" opacity="0.4" />
  
  <!-- Stylized Manga Panel Border -->
  <rect x="6" y="6" width="308" height="188" fill="none" stroke="#3f3f46" stroke-width="2" />
  <rect x="9" y="9" width="302" height="182" fill="none" stroke="#27272a" stroke-width="1" />
  
  <!-- Screentone & Speedlines silhouette -->
  <path d="M10 10 L160 100 L310 10" stroke="#52525b" stroke-width="0.5" opacity="0.3" />
  <path d="M10 190 L160 100 L310 190" stroke="#52525b" stroke-width="0.5" opacity="0.3" />
  <circle cx="160" cy="100" r="42" fill="none" stroke="${moodColor}" stroke-width="2" stroke-dasharray="4 2" opacity="0.8" />
  
  <!-- Label text -->
  <text x="160" y="95" font-family="system-ui, sans-serif" font-weight="800" font-size="13" fill="#f4f4f5" text-anchor="middle" letter-spacing="1">${title}</text>
  <text x="160" y="115" font-family="system-ui, sans-serif" font-weight="500" font-size="10" fill="#a1a1aa" text-anchor="middle">${subtitle}</text>
  
  <!-- Manga Page Badge -->
  <rect x="14" y="14" width="70" height="18" rx="4" fill="#000000" opacity="0.75" />
  <text x="49" y="27" font-family="monospace" font-size="9" fill="${moodColor}" text-anchor="middle" font-weight="bold">PANEL REF</text>
</svg>
`.trim();

export const MOCK_SEGMENTS: NarrationSegment[] = [
  {
    id: "seg_001",
    sequence: 1,
    scene_id: "scene_01",
    scene_title: "The Subterranean Threshold",
    linked_to_scene: true,
    scene_offset_sec: 0.0,
    speaker_id: "char_narrator",
    speaker_name: "The Narrator",
    speaker_type: "NARRATOR",
    voice_profile_id: "voice_aria",
    has_custom_voice_override: false,
    narration_text:
      "Deep beneath the sunken ruins of Aethelgard, the air turned to ice. Here lay the Obsidian Vault, undisturbed for eight hundred years.",
    text_revision: 1,
    content_hash: computeContentHash(
      "Deep beneath the sunken ruins of Aethelgard, the air turned to ice. Here lay the Obsidian Vault, undisturbed for eight hundred years.",
      "Mysterious",
      0.95,
      "medium"
    ),
    source_context: {
      page_id: "page_01",
      page_number: 1,
      panel_ids: ["panel_1_1"],
      panel_labels: ["Page 1 • Panel 1 (Establishing Wide)"],
      svg_thumbnail: makeMangaSvg("SUNKEN VAULT", "Page 1 • Establishing Shot", "#6366f1"),
      raw_ocr_dialogue: "...",
      visual_description:
        "Wide establishing shot looking down a towering spiral staircase carved from black volcanic stone. Heavy mist curls around broken stone pillars.",
      story_context:
        "Sets the oppressive atmospheric mood of the chapter. Introduces the legendary ancient location before the protagonists arrive.",
    },
    delivery: {
      emotion: "Mysterious",
      intensity: 0.65,
      speech_speed: 0.95,
      pause: {
        preset: "medium",
        duration_ms: 600,
        placement: "after_first_sentence",
        instruction: "Pause after 'ice' to let the cold atmosphere settle before naming the vault.",
      },
      performance_notes:
        "Low, measured cadence. Emphasize the ancient weight of 'undisturbed for eight hundred years'.",
      pronunciation_guide: [
        { id: "pr_1", word: "Aethelgard", phonetic: "EYE-thel-gard", notes: "Hard initial vowel" },
        { id: "pr_2", word: "Obsidian", phonetic: "uhb-SID-ee-uhn", notes: "Short 'i'" },
      ],
    },
    continuity_notes: "Opening hook for Chapter 14. Leads directly into Elena's entrance in panel 2.",
    review_status: "APPROVED",
    generation_status: "READY",
    generation_progress: 100,
    generated_audio_revision: 1,
    audio_asset_uri: "/assets/demo/seg_001_audio.mp3",
    previous_audio_asset_uri: null,
    estimated_duration_sec: 7.2,
    measured_duration_sec: 7.4,
    updated_at: "2026-10-18T09:15:00Z",
  },
  {
    id: "seg_002",
    sequence: 2,
    scene_id: "scene_01",
    scene_title: "The Subterranean Threshold",
    linked_to_scene: true,
    scene_offset_sec: 0.5,
    speaker_id: "char_elena",
    speaker_name: "Elena Vance",
    speaker_type: "CHARACTER",
    voice_profile_id: "voice_vespera",
    has_custom_voice_override: false,
    narration_text:
      "Keep that lantern shuttered, Kaelen. Whatever is down here, it hunts by sound and spark.",
    text_revision: 1,
    content_hash: computeContentHash(
      "Keep that lantern shuttered, Kaelen. Whatever is down here, it hunts by sound and spark.",
      "Suspenseful",
      1.0,
      "short"
    ),
    source_context: {
      page_id: "page_01",
      page_number: 1,
      panel_ids: ["panel_1_2", "panel_1_3"],
      panel_labels: ["Page 1 • Panel 2-3 (Over-Shoulder / Reaction)"],
      svg_thumbnail: makeMangaSvg("ELENA STEPS FORWARD", "Page 1 • Panels 2-3", "#10b981"),
      raw_ocr_dialogue: "Shut the light! Don't let it see!",
      visual_description:
        "Over-the-shoulder angle: Elena holds up a leather-gloved hand to block Kaelen's brass lantern. Her eyes scan the shadowed hallway.",
      story_context:
        "Elena realizes the vault's guardian is active. The raw OCR was brief and rushed, so the narrative script expands her strategic caution.",
    },
    delivery: {
      emotion: "Suspenseful",
      intensity: 0.75,
      speech_speed: 1.0,
      pause: {
        preset: "short",
        duration_ms: 300,
        placement: "after_first_sentence",
        instruction: "Slight breath hesitation before 'Whatever is down here'.",
      },
      performance_notes:
        "Hushed whisper-toned command. Urgent yet disciplined, not screaming in panic.",
      pronunciation_guide: [
        { id: "pr_3", word: "Kaelen", phonetic: "KAY-len", notes: "Emphasis on first syllable" },
      ],
    },
    continuity_notes: "Contrasts with the solemn narrator opener by introducing immediate present tension.",
    review_status: "APPROVED",
    generation_status: "READY",
    generation_progress: 100,
    generated_audio_revision: 1,
    audio_asset_uri: "/assets/demo/seg_002_audio.mp3",
    previous_audio_asset_uri: null,
    estimated_duration_sec: 5.8,
    measured_duration_sec: 5.6,
    updated_at: "2026-10-18T09:18:00Z",
  },
  {
    id: "seg_003",
    sequence: 3,
    scene_id: "scene_01",
    scene_title: "The Subterranean Threshold",
    linked_to_scene: true,
    scene_offset_sec: 1.2,
    speaker_id: "char_kaelen",
    speaker_name: "Kaelen Drake",
    speaker_type: "CHARACTER",
    voice_profile_id: "voice_caelum",
    has_custom_voice_override: false,
    narration_text:
      "Elena, look at the doorframe... these aren't warding runes. They're containment seals—and three of them have already cracked!",
    text_revision: 1,
    content_hash: computeContentHash(
      "Elena, look at the doorframe... these aren't warding runes. They're containment seals—and three of them have already cracked!",
      "Fearful",
      1.15,
      "short"
    ),
    source_context: {
      page_id: "page_01",
      page_number: 1,
      panel_ids: ["panel_1_4"],
      panel_labels: ["Page 1 • Panel 4 (Macro Close-Up)"],
      svg_thumbnail: makeMangaSvg("CRACKED RUNES", "Page 1 • Panel 4 Close-Up", "#f59e0b"),
      raw_ocr_dialogue: "Look! The seal is broken! Three lines are gone!",
      visual_description:
        "Extreme close-up of Kaelen's trembling hand holding a parchment rubbing against glowing crimson hairline fractures on the obsidian arch.",
      story_context:
        "Scholarly realization that the danger is not sealed away—it has partially breached.",
    },
    delivery: {
      emotion: "Fearful",
      intensity: 0.85,
      speech_speed: 1.15,
      pause: {
        preset: "short",
        duration_ms: 250,
        placement: "after_first_sentence",
        instruction: "Gasp pause right after 'Elena, look at the doorframe'.",
      },
      performance_notes:
        "Nervous tremor in voice. Accelerates towards 'already cracked' as panic rises.",
      pronunciation_guide: [],
    },
    continuity_notes: "Heightens the stakes established in Segment 2. Kaelen's voice sounds brittle against Elena's calm.",
    review_status: "NEEDS_REVIEW",
    generation_status: "NEEDS_REVIEW",
    generation_progress: 100,
    generated_audio_revision: null,
    audio_asset_uri: null,
    previous_audio_asset_uri: null,
    estimated_duration_sec: 7.0,
    measured_duration_sec: null,
    updated_at: "2026-10-18T09:40:00Z",
  },
  {
    id: "seg_004",
    sequence: 4,
    scene_id: "scene_02",
    scene_title: "The Awakening of Malakor",
    linked_to_scene: true,
    scene_offset_sec: 0.0,
    speaker_id: "char_narrator",
    speaker_name: "The Narrator",
    speaker_type: "NARRATOR",
    voice_profile_id: "voice_aria",
    has_custom_voice_override: false,
    narration_text:
      "As if answering his words, the darkness stirred. A sound like shattered glass skittered across the vaulted ceiling above them.",
    text_revision: 1,
    content_hash: computeContentHash(
      "As if answering his words, the darkness stirred. A sound like shattered glass skittered across the vaulted ceiling above them.",
      "Suspenseful",
      0.9,
      "dramatic"
    ),
    source_context: {
      page_id: "page_02",
      page_number: 2,
      panel_ids: ["panel_2_1"],
      panel_labels: ["Page 2 • Panel 1 (Upward Low-Angle)"],
      svg_thumbnail: makeMangaSvg("THE VAULTED CEILING", "Page 2 • Low-Angle Tilt", "#6366f1"),
      raw_ocr_dialogue: "*SKRRR-CHH*",
      visual_description:
        "Low-angle camera tilted up at high vaulted ribbing. Black tendrils of shadow drift across ancient carving like spiderwebs.",
      story_context:
        "Transition from character interaction to ominous environmental reaction. The entity responds to Kaelen's voice.",
    },
    delivery: {
      emotion: "Suspenseful",
      intensity: 0.7,
      speech_speed: 0.9,
      pause: {
        preset: "dramatic",
        duration_ms: 800,
        placement: "after_first_sentence",
        instruction: "Hold dramatic silence between 'stirred' and the glass sound description.",
      },
      performance_notes:
        "Eerie, storytelling pause. Soften tone on 'shattered glass' to evoke tactile creepiness.",
      pronunciation_guide: [],
    },
    continuity_notes: "Seamlessly bridges scene 1 and 2. Responds directly to Kaelen's exclamation in segment 3.",
    review_status: "APPROVED",
    generation_status: "READY",
    generation_progress: 100,
    generated_audio_revision: 1,
    audio_asset_uri: "/assets/demo/seg_004_audio.mp3",
    previous_audio_asset_uri: null,
    estimated_duration_sec: 7.8,
    measured_duration_sec: 8.0,
    updated_at: "2026-10-18T09:45:00Z",
  },
  {
    id: "seg_005",
    sequence: 5,
    scene_id: "scene_02",
    scene_title: "The Awakening of Malakor",
    linked_to_scene: true,
    scene_offset_sec: 0.8,
    speaker_id: "char_malakor",
    speaker_name: "Wraith of Malakor",
    speaker_type: "CHARACTER",
    voice_profile_id: "voice_corvus",
    has_custom_voice_override: false,
    narration_text:
      "Another prism bearer... so small, so fragile. Did your elders not teach you what sleeps within the glass?",
    text_revision: 2, // Modified after initial generation!
    content_hash: computeContentHash(
      "Another prism bearer... so small, so fragile. Did your elders not teach you what sleeps within the glass?",
      "Whispering",
      0.85,
      "dramatic"
    ),
    source_context: {
      page_id: "page_02",
      page_number: 2,
      panel_ids: ["panel_2_2", "panel_2_3"],
      panel_labels: ["Page 2 • Panel 2-3 (Horror Inset / Manifestation)"],
      svg_thumbnail: makeMangaSvg("SHADOW MANIFESTATION", "Page 2 • Inset Panel", "#f43f5e"),
      raw_ocr_dialogue: "You came... little prism... why did you come?",
      visual_description:
        "Two hollow crimson eyes open within the blackness. Elena's hand flies to the crystal talisman resting against her collarbone.",
      story_context:
        "First appearance of Malakor's telepathic voice. Mock AI refined raw OCR into an ancient, mocking psychological taunt.",
    },
    delivery: {
      emotion: "Whispering",
      intensity: 0.9,
      speech_speed: 0.85,
      pause: {
        preset: "dramatic",
        duration_ms: 900,
        placement: "after_first_sentence",
        instruction: "Dramatic pause after 'fragile' to let the cold threat echo.",
      },
      performance_notes:
        "Chilling, breathy hiss with ancient arrogance. Every syllable should feel like frost on glass.",
      pronunciation_guide: [
        { id: "pr_4", word: "Malakor", phonetic: "MAL-uh-kor", notes: "Short 'a', rolling 'r'" },
      ],
    },
    continuity_notes: "Direct antagonist intrusion into the protagonists' minds. Sudden tone shift from cautious exploration to mortal danger.",
    review_status: "DRAFT",
    generation_status: "OUTDATED",
    generation_progress: 0,
    generated_audio_revision: 1, // Generated for revision 1, now on revision 2
    audio_asset_uri: null,
    // Decision 2: Preserved previous audio take!
    previous_audio_asset_uri: "/assets/demo/seg_005_take1_archived.mp3",
    estimated_duration_sec: 7.5,
    measured_duration_sec: 7.3,
    updated_at: "2026-10-18T10:02:00Z",
  },
  {
    id: "seg_006",
    sequence: 6,
    scene_id: "scene_02",
    scene_title: "The Awakening of Malakor",
    linked_to_scene: true,
    scene_offset_sec: 0.2,
    speaker_id: "char_elena",
    speaker_name: "Elena Vance",
    speaker_type: "CHARACTER",
    voice_profile_id: "voice_vespera",
    has_custom_voice_override: false,
    narration_text:
      "They taught me that even ancient nightmares can bleed when struck with consecrated steel.",
    text_revision: 1,
    content_hash: computeContentHash(
      "They taught me that even ancient nightmares can bleed when struck with consecrated steel.",
      "Determined",
      1.05,
      "short"
    ),
    source_context: {
      page_id: "page_02",
      page_number: 2,
      panel_ids: ["panel_2_4"],
      panel_labels: ["Page 2 • Panel 4 (Action Stance Dynamic)"],
      svg_thumbnail: makeMangaSvg("CONSECRATED BLADE", "Page 2 • Heroic Stance", "#10b981"),
      raw_ocr_dialogue: "I'm not afraid of you! My blade can cut you!",
      visual_description:
        "Dynamic diagonal panel: Elena unsheathes a curved dagger etched with silver prismatic runes. Light glints off the honed edge.",
      story_context:
        "Elena turns fear into resolute defiance. The rewritten script delivers protagonist agency and grit.",
    },
    delivery: {
      emotion: "Determined",
      intensity: 0.85,
      speech_speed: 1.05,
      pause: {
        preset: "short",
        duration_ms: 300,
        placement: "before",
        instruction: "Brief steadying breath before delivering the counter-threat.",
      },
      performance_notes:
        "Steely, unshakable conviction. Clear tonal projection that cuts through the shadow whisper.",
      pronunciation_guide: [
        { id: "pr_5", word: "consecrated", phonetic: "KON-suh-kray-tuhd", notes: "Standard 4-syllable" },
      ],
    },
    continuity_notes: "Direct heroic reply to Malakor's segment 5 taunt. High dramatic payoff.",
    review_status: "APPROVED",
    generation_status: "QUEUED",
    generation_progress: 25,
    generated_audio_revision: null,
    audio_asset_uri: null,
    previous_audio_asset_uri: null,
    estimated_duration_sec: 5.5,
    measured_duration_sec: null,
    updated_at: "2026-10-18T10:10:00Z",
  },
  {
    id: "seg_007",
    sequence: 7,
    scene_id: "scene_03",
    scene_title: "The Tremor of the Genesis Core",
    linked_to_scene: false, // User chose unlinked / floating narration
    scene_offset_sec: 0.0,
    speaker_id: "char_kaelen",
    speaker_name: "Kaelen Drake",
    speaker_type: "CHARACTER",
    voice_profile_id: "voice_caelum",
    has_custom_voice_override: false,
    narration_text:
      "Elena, don't engage! The frequency of your blade is synchronizing with the floor plates!",
    text_revision: 1,
    content_hash: computeContentHash(
      "Elena, don't engage! The frequency of your blade is synchronizing with the floor plates!",
      "Excited",
      1.25,
      "none"
    ),
    source_context: {
      page_id: "page_03",
      page_number: 3,
      panel_ids: ["panel_3_1", "panel_3_2"],
      panel_labels: ["Page 3 • Panel 1-2 (Alarm & Floor Tremor)"],
      svg_thumbnail: makeMangaSvg("RESONANCE WARNING", "Page 3 • Panels 1-2", "#f59e0b"),
      raw_ocr_dialogue: "Stop! The floor is shaking! Don't use magic!",
      visual_description:
        "Kaelen lunges forward with arms outstretched as cracks shoot across the hexagonal floor tiles. Luminescent blue dust rises from the seams.",
      story_context:
        "Unexpected mechanical complication. Combat magic risks collapsing the ancient vault floor.",
    },
    delivery: {
      emotion: "Excited",
      intensity: 0.9,
      speech_speed: 1.25,
      pause: {
        preset: "none",
        duration_ms: 0,
        placement: "before",
      },
      performance_notes:
        "Desperate, breathless warning shouted over rising rumble. Rapid cadence.",
      pronunciation_guide: [],
    },
    continuity_notes: "Interrupts Elena's battle stance. Introduces physical jeopardy beyond the wraith.",
    review_status: "NEEDS_REVIEW",
    generation_status: "UNQUEUED",
    generation_progress: 0,
    generated_audio_revision: null,
    audio_asset_uri: null,
    previous_audio_asset_uri: null,
    estimated_duration_sec: 5.0,
    measured_duration_sec: null,
    updated_at: "2026-10-18T10:15:00Z",
  },
  {
    id: "seg_008",
    sequence: 8,
    scene_id: "scene_03",
    scene_title: "The Tremor of the Genesis Core",
    linked_to_scene: true,
    scene_offset_sec: 1.5,
    speaker_id: "char_narrator",
    speaker_name: "The Narrator",
    speaker_type: "NARRATOR",
    voice_profile_id: "voice_aria",
    has_custom_voice_override: false,
    narration_text:
      "Too late. The subterranean floor gave way in a blinding cascade of shattered stone, plunging them both into the forgotten heart of the Genesis Core.",
    text_revision: 1,
    content_hash: computeContentHash(
      "Too late. The subterranean floor gave way in a blinding cascade of shattered stone, plunging them both into the forgotten heart of the Genesis Core.",
      "Serious",
      0.95,
      "medium"
    ),
    source_context: {
      page_id: "page_03",
      page_number: 3,
      panel_ids: ["panel_3_3", "panel_3_4"],
      panel_labels: ["Page 3 • Panel 3-4 (Full-Page Splash Climax)"],
      svg_thumbnail: makeMangaSvg("THE FALL INTO THE CORE", "Page 3 • Splash Climax", "#6366f1"),
      raw_ocr_dialogue: "*CRASHHHH*",
      visual_description:
        "Massive full-page splash: The floor collapses inward into a cavernous glowing chasm. Elena and Kaelen fall as radiant prismatic shards explode outward.",
      story_context:
        "Chapter climax and cliffhanger. Sets up the next chapter's exploration of the Genesis Core.",
    },
    delivery: {
      emotion: "Serious",
      intensity: 0.85,
      speech_speed: 0.95,
      pause: {
        preset: "medium",
        duration_ms: 500,
        placement: "after_first_sentence",
        instruction: "Deadpan, final pause after 'Too late.' before describing the catastrophic collapse.",
      },
      performance_notes:
        "Dramatic, cinematic weight. Start with quiet dread on 'Too late', then swell with epic resonance through 'Genesis Core'.",
      pronunciation_guide: [
        { id: "pr_6", word: "subterranean", phonetic: "suhb-tuh-RAY-nee-uhn", notes: "Four syllables" },
      ],
    },
    continuity_notes: "Climax of Chapter 14. Directly resolves Kaelen's tremor warning with the inevitable collapse.",
    review_status: "APPROVED",
    generation_status: "READY",
    generation_progress: 100,
    generated_audio_revision: 1,
    audio_asset_uri: "/assets/demo/seg_008_audio.mp3",
    previous_audio_asset_uri: null,
    estimated_duration_sec: 8.5,
    measured_duration_sec: 8.7,
    updated_at: "2026-10-18T10:20:00Z",
  },
];

export const MOCK_CHAPTER: NarrationChapter = {
  project_id: "proj_demo_manga_01",
  project_title: "Lumina: Chronicles of the Obsidian Realm",
  chapter_id: "chap_14_obsidian_vault",
  chapter_title: "Chapter 14: Whispers in the Obsidian Vault",
  chapter_number: 14,
  segments: MOCK_SEGMENTS,
  characters: MOCK_CHARACTERS,
  voice_profiles: MOCK_VOICE_PROFILES,
  page_scripts: MOCK_PAGE_SCRIPTS,
  created_at: "2026-10-18T08:00:00Z",
  updated_at: "2026-10-18T10:20:00Z",
};
