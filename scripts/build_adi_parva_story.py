import json
import sys
from pathlib import Path
sys.path.insert(0, ".")

from engine.original.models import (
    Bible, Character, Location, Premise, OriginalStory, Panel, Scene, Line
)

ws = Path("output/Original_Stories/mahabharata_adi_parva")
ws.mkdir(parents=True, exist_ok=True)

# 1. Premise & Characters
premise = Premise(
    title="Mahabharata: Adi Parva — The Cosmic Prelude",
    genre="fantasy",
    logline="In the sacred forest of Naimisharanya, the wandering bard Sauti reveals to the gathered rishis the cosmic genesis of the Mahabharata, composed by sage Vyasa and inscribed by Lord Ganesha.",
    tone="epic, solemn, majestic, celestial, spiritual",
    setting="The sacred forest of Naimisharanya and the timeless peaks of the Himalayas"
)

sauti = Character(
    id="sauti",
    name="Ugrasrava Sauti",
    role="protagonist",
    age_group="adult",
    species="human",
    gender="male",
    look="wandering ascetic bard, copper-bronze skin, long dark hair tied neatly, rudraksha prayer beads, humble ochre linen robes, calm visionary eyes, holding wooden staff",
    personality="reverent, poetic, eloquent storyteller"
)

shaunaka = Character(
    id="shaunaka",
    name="Kulapati Shaunaka",
    role="mentor",
    age_group="elder",
    species="human",
    gender="male",
    look="venerable ancient rishi, long flowing silver-white beard, sacred white tripundra bhasma tilak on brow, glowing peaceful countenance, wrapped in bark garments",
    personality="wise, inquisitive, master of the sacred groves"
)

vyasa = Character(
    id="vyasa",
    name="Veda Vyasa",
    role="other",
    age_group="elder",
    species="human",
    gender="male",
    look="colossal ascetic sage, dark matted locks, piercing visionary eyes holding millennia of destiny, deep contemplative expression, wrapped in ascetic deer pelt",
    personality="profound, all-seeing composer of the cosmic epic"
)

ganesha = Character(
    id="ganesha",
    name="Lord Ganesha",
    role="other",
    age_group="adult",
    species="creature",
    gender="male",
    look="divine elephant-headed god of wisdom, glowing golden skin, ornate celestial crown, wise kind eyes, holding broken ivory tusk as sacred stylus",
    personality="omniscient divine scribe of the gods"
)

bhishma = Character(
    id="bhishma",
    name="Devavrata (Bhishma)",
    role="other",
    age_group="adult",
    species="human",
    gender="male",
    look="athletic young warrior prince, gleaming engraved silver armor, holding upright sword on war chariot, eyes set with unshakeable resolve",
    personality="fearless, steadfast, embodiment of sacrifice"
)

# 2. Locations
loc_naimisha = Location(
    id="naimisharanya",
    name="Sacred Forest of Naimisharanya",
    look="primeval dense forest, colossal banyan and sal trees, misty morning sunbeams cutting through green canopy, central circular hermitage with glowing yajna fire"
)

loc_himalayas = Location(
    id="himalayas",
    name="Mount Meru (Himalayan Hermitage)",
    look="towering snow-capped jagged Himalayan peaks, biting wind, high mountain cave carved into sheer granite, overlooking sea of clouds"
)

loc_ganga = Location(
    id="ganga",
    name="Banks of the River Ganga",
    look="wide torrential sacred river flowing with silver foam, ancient stone ghats, golden sunset lighting, billowing silk battle flags"
)

loc_kurukshetra = Location(
    id="kurukshetra",
    name="Plains of Kurukshetra",
    look="vast horizon under blood-red sunset, silhouetted armies with spears and standards, ominous dark war drums"
)

bible = Bible(
    premise=premise,
    characters=[sauti, shaunaka, vyasa, ganesha, bhishma],
    locations=[loc_naimisha, loc_himalayas, loc_ganga, loc_kurukshetra],
    rules=[
        "The language of narration and dialogue is classical, cinematic English.",
        "Character identities, traditional dress and sacred markers remain consistent across all shots.",
        "The Adi Parva begins in Naimisharanya, travels through the cosmic creation of Vyasa, and culminates in the prophecy of the Kuru dynasty."
    ]
)

# 3. Scenes
sc01 = Scene(
    id="sc01",
    location_id="naimisharanya",
    character_ids=["sauti", "shaunaka"],
    summary="In the sacred forest of Naimisharanya, the bard Sauti arrives during a twelve-year sacrifice and is welcomed by sage Shaunaka.",
    mood="sacred, reverent, mystical morning"
)

sc02 = Scene(
    id="sc02",
    location_id="himalayas",
    character_ids=["vyasa", "ganesha"],
    summary="Vyasa meditates in the Himalayan peaks and commands Lord Ganesha to inscribe the eternal verses of the Mahabharata.",
    mood="celestial, profound, cosmic, awe-inspiring"
)

sc03 = Scene(
    id="sc03",
    location_id="ganga",
    character_ids=["bhishma"],
    summary="The genesis of the dynasty: the celestial river Ganga, the terrible vow of Bhishma, and the dual nature of Dharma.",
    mood="epic, dramatic, tragic grandeur"
)

sc04 = Scene(
    id="sc04",
    location_id="naimisharanya",
    character_ids=["sauti", "shaunaka"],
    summary="Sauti proclaims the eternal nature of the Mahabharata: what is found here is everywhere, what is not found here is nowhere.",
    mood="monumental, transcendent climax"
)

# 4. Panels (18 Directed Cinematic Shots)
panels_data = [
    # Act I
    Panel(
        id="p001",
        scene_id="sc01",
        shot="wide",
        angle="eye_level",
        location_id="naimisharanya",
        character_ids=[],
        action="Sunbeams slice through towering ancient banyan canopies into the mystical morning fog of Naimisharanya forest.",
        caption="Before the great wars shook the earth, there lay the sacred forest of Naimisharanya, where time itself paused to listen.",
        dialogue=[]
    ),
    Panel(
        id="p002",
        scene_id="sc01",
        shot="wide",
        angle="low",
        location_id="naimisharanya",
        character_ids=["shaunaka"],
        action="Venerable rishis in ochre robes sit in a sacred circle around the glowing sacrificial fire, aromatic smoke spiraling skyward.",
        caption="Here, during a twelve-year sacrifice, the wisest sages of Aryavarta gathered to preserve the memory of the cosmos.",
        dialogue=[]
    ),
    Panel(
        id="p003",
        scene_id="sc01",
        shot="medium",
        angle="eye_level",
        location_id="naimisharanya",
        character_ids=["shaunaka"],
        action="Kulapati Shaunaka with flowing silver beard and glowing bhasma tilak raises his hands in gentle welcome.",
        caption="The venerable Kulapati Shaunaka raised his hand as a lone wanderer emerged from the misty trees.",
        dialogue=[]
    ),
    Panel(
        id="p004",
        scene_id="sc01",
        shot="medium",
        angle="eye_level",
        location_id="naimisharanya",
        character_ids=["sauti"],
        action="Ugrasrava Sauti steps into the firelight, bowing reverently with folded hands and his wooden staff.",
        caption="It was Ugrasrava Sauti, the wandering bard, whose voice held the memory of kings and gods.",
        dialogue=[]
    ),
    Panel(
        id="p005",
        scene_id="sc01",
        shot="medium",
        angle="eye_level",
        location_id="naimisharanya",
        character_ids=["shaunaka", "sauti"],
        action="Shaunaka leans forward, his wise eyes fixed intently upon the young traveler.",
        caption="The sage spoke with quiet majesty.",
        dialogue=[Line(speaker_id="shaunaka", text="From where do you journey, O Sauti, and what sacred history do you bring to this holy grove?")]
    ),
    Panel(
        id="p006",
        scene_id="sc01",
        shot="close",
        angle="eye_level",
        location_id="naimisharanya",
        character_ids=["sauti"],
        action="Sauti lifts his gaze, firelight reflecting in his inspired, visionary eyes.",
        caption="Sauti bowed his head, his voice ringing like temple bronze through the silent woods.",
        dialogue=[Line(speaker_id="sauti", text="I bring the supreme chronicle of the universe, conceived by Maharishi Krishna Dvaipayana Vyasa himself.")]
    ),

    # Act II
    Panel(
        id="p007",
        scene_id="sc02",
        shot="wide",
        angle="low",
        location_id="himalayas",
        character_ids=[],
        action="The colossal snow-capped peaks of Mount Meru pierce the twilight clouds in breathtaking panoramic majesty.",
        caption="High upon the frozen crags of the Himalayas, far beyond the realm of mortal men, the tale was first conceived.",
        dialogue=[]
    ),
    Panel(
        id="p008",
        scene_id="sc02",
        shot="medium",
        angle="low",
        location_id="himalayas",
        character_ids=["vyasa"],
        action="Maharishi Veda Vyasa sits in deep samadhi atop a granite precipice, matted locks whipping in mountain gale.",
        caption="Maharishi Vyasa sat in profound meditation, seeing the past, present, and all future ages unfold like an open scroll.",
        dialogue=[]
    ),
    Panel(
        id="p009",
        scene_id="sc02",
        shot="wide",
        angle="eye_level",
        location_id="himalayas",
        character_ids=["vyasa"],
        action="A blinding golden aura of celestial light illuminates the cave as Lord Brahma reveals the path to record the epic.",
        caption="To inscribe an epic that encompassed the entire universe, the creator commanded him to seek the scribe of the gods.",
        dialogue=[]
    ),
    Panel(
        id="p010",
        scene_id="sc02",
        shot="medium",
        angle="eye_level",
        location_id="himalayas",
        character_ids=["ganesha", "vyasa"],
        action="Lord Ganesha with divine golden countenance sits opposite Vyasa, his broken tusk held ready over palm leaf sheaves.",
        caption="Lord Ganesha himself descended, wielding his broken tusk as a sacred stylus upon one eternal condition.",
        dialogue=[Line(speaker_id="ganesha", text="My pen shall not halt for a single breath, unless your verse ceases to flow.")]
    ),
    Panel(
        id="p011",
        scene_id="sc02",
        shot="close",
        angle="eye_level",
        location_id="himalayas",
        character_ids=["ganesha"],
        action="Macro close up of Ganesha's broken ivory tusk carving glowing Sanskrit glyphs into birch bark as golden sparks float upward.",
        caption="And so the god inscribed, capturing the cosmic struggle between divine duty and human desire.",
        dialogue=[]
    ),
    Panel(
        id="p012",
        scene_id="sc02",
        shot="medium",
        angle="eye_level",
        location_id="himalayas",
        character_ids=["vyasa"],
        action="Vyasa chanting unbroken rhythmically with closed eyes, his breath weaving the tapestry of the Bharata lineage.",
        caption="A hundred thousand verses flowed forth, binding the destiny of gods, kings, and mortals together.",
        dialogue=[]
    ),

    # Act III
    Panel(
        id="p013",
        scene_id="sc03",
        shot="wide",
        angle="eye_level",
        location_id="ganga",
        character_ids=[],
        action="The raging sacred river Ganga flows with turbulent silver crests under a dramatic golden-orange dusk.",
        caption="From the celestial descent of Mother Ganga began the fated lineage of the lunar dynasty.",
        dialogue=[]
    ),
    Panel(
        id="p014",
        scene_id="sc03",
        shot="medium",
        angle="low",
        location_id="ganga",
        character_ids=["bhishma"],
        action="Young Devavrata in gleaming silver plate armor stands upon his war chariot, raising his sword to heaven.",
        caption="There stood young Devavrata, who for the love of his father swore the terrible, earth-shaking vow of eternal renunciation.",
        dialogue=[Line(speaker_id="bhishma", text="From this day forth, I renounce the crown, and take the vow of celibacy forever!")]
    ),
    Panel(
        id="p015",
        scene_id="sc03",
        shot="wide",
        angle="eye_level",
        location_id="ganga",
        character_ids=["bhishma"],
        action="The gods shower celestial flowers from heaven upon the prince as thunder cracks across the horizon.",
        caption="The heavens wept golden blossoms, proclaiming him Bhishma, the one of the Terrible Vow.",
        dialogue=[]
    ),
    Panel(
        id="p016",
        scene_id="sc03",
        shot="wide",
        angle="eye_level",
        location_id="kurukshetra",
        character_ids=[],
        action="A colossal mystical tree standing on a misty plain: one half blooming with white blossoms, the other consumed by thorny dark embers.",
        caption="Thus sprouted the tree of the Kuru dynasty: one branch rooted in Dharma, the other consumed by the bitter fires of envy.",
        dialogue=[]
    ),
    Panel(
        id="p017",
        scene_id="sc04",
        shot="wide",
        angle="eye_level",
        location_id="kurukshetra",
        character_ids=[],
        action="The blood-red horizon of Kurukshetra, thousands of battle banners fluttering in the silent wind awaiting the storm.",
        caption="A storm that would culminate upon the sacred dust of Kurukshetra, testing the very foundation of righteous action.",
        dialogue=[]
    ),
    Panel(
        id="p018",
        scene_id="sc04",
        shot="close",
        angle="eye_level",
        location_id="naimisharanya",
        character_ids=["sauti"],
        action="Sauti addresses the spellbound rishis of Naimisharanya with outstretched hands in dramatic theatrical climax.",
        caption="As the sacrificial flames flickered in the night, Sauti delivered the eternal declaration of the epic.",
        dialogue=[Line(speaker_id="sauti", text="What is found here may be found elsewhere. But what is not found here, is nowhere else in all the worlds.")]
    )
]

story = OriginalStory(
    bible=bible,
    scenes=[sc01, sc02, sc03, sc04],
    panels=panels_data
)

story_file = ws / "story.json"
story_file.write_text(story.model_dump_json(indent=2), encoding="utf-8")
print(f"[SUCCESS] Wrote {len(panels_data)} panels to {story_file}")
