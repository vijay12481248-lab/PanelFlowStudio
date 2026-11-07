"""Source of the channel video "Why Do We Cry?": writes output/Original_Stories/<slug>/story.json.

The narration (`caption`) is authored here; the system still writes every picture prompt (shot director -> prompt composer) and every
motion prompt (animate.py). One narrated beat per panel (<= 24 words) so the shot director does not split them. Science claims are
kept hedged ("studies suggest", "one idea") and carry no invented numbers.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.original.models import Bible, Character, Location, OriginalStory, Panel, Premise, Scene  # noqa: E402

SLUG = "vox_why_we_cry"

CHARS = [
    Character(id="maya", name="Maya", role="protagonist", age_group="adult", gender="female",
              look="short black bob haircut, medium brown skin, dark brown eyes, round glasses, bright yellow hoodie, blue jeans",
              personality="warm, tired, easily startled, cries at everything"),
    Character(id="biscuit", name="Biscuit", role="companion", age_group="adult", species="cat", gender="male",
              look="chubby orange tabby fur, white front paws, big green eyes, pink nose, blue collar with a gold tag",
              personality="deadpan, patient, secretly a scientist"),
    Character(id="dev", name="Dev", role="other", age_group="adult", gender="male",
              look="tall young man, short curly dark hair, light brown skin, kind brown eyes, no glasses, forest green sweater, grey trousers",
              personality="shy, kind, bad at goodbyes"),
    Character(id="baby", name="Baby", role="other", age_group="child", gender="neutral",
              look="tiny newborn baby, round face, small tuft of black hair, white onesie",
              personality="loud, sleepy"),
]

LOCS = [
    Location(id="living_room", name="Cozy Living Room",
             look="cozy apartment living room in the evening, grey sofa, warm yellow lamp, television glowing blue, tissue box on a wooden coffee table"),
    Location(id="kitchen", name="Sunny Kitchen",
             look="small sunny apartment kitchen, wooden table, white walls, green plant on the window sill"),
    Location(id="diagram", name="Explainer Backdrop",
             look="plain deep navy blue explainer backdrop, clean empty space, simple bright canary yellow flat diagram shapes, no text"),
    Location(id="hallway", name="Apartment Hallway",
             look="apartment hallway outside a front door, warm yellow hallway light, a few cardboard moving boxes stacked against the wall"),
    Location(id="nursery", name="Nursery",
             look="small dim nursery at night, wooden crib, soft yellow night lamp, star mobile hanging above the crib"),
]

PANELS: list[Panel] = []
SCENES: list[Scene] = []
COUNT = [0]
BAD: list[str] = []


def scene(sid, loc, chars, summary, mood):
    SCENES.append(Scene(id=sid, location_id=loc, character_ids=chars, summary=summary, mood=mood))


def P(sid, shot, angle, loc, chars, action, caption, key=None, pid=None):
    if pid is None:  # numbered beats keep their ids whatever is inserted between them; inserted beats carry an explicit id
        COUNT[0] += 1
        pid = f"p{COUNT[0]:03d}"
    words = len(caption.split())
    if words > 24:
        BAD.append(f"{pid} has {words} words: {caption}")
    PANELS.append(Panel(id=pid, scene_id=sid, shot=shot, angle=angle, location_id=loc, character_ids=chars,
                        action=action, caption=caption, key_visuals=key or []))


# ------------------------------------------------------------- S1 the commercial (funny hook)
scene("s1", "living_room", ["maya", "biscuit"], "Maya sobs at a dog food commercial and wonders why.", "funny, warm")
P("s1", "wide", "eye_level", "living_room", ["maya", "biscuit"],
  "Maya sits on the grey sofa with big shiny clear light-blue tears running down both cheeks, clean white eyes, tears only and no redness, a wobbly sad mouth, a tissue in her fist, Biscuit the cat sitting beside her. The TV screen shows a sad cartoon golden retriever puppy sitting alone with drooping ears, big wet sorrowful eyes and a tear, looking up lonely beside a red dog food bowl.",
  "Maya is crying. Not at a funeral, not at a goodbye. At a dog food commercial. Thirty seconds long, and she is a mess.",
  ["tears on Maya's cheeks", "TV showing a sad lonely puppy beside a dog food bowl"])
P("s1", "close", "eye_level", "living_room", ["biscuit"],
  "Biscuit the cat staring straight ahead with a flat, unimpressed deadpan face, half his body turned toward Maya, the TV behind him showing a sad cartoon golden retriever puppy with drooping ears and big wet sorrowful eyes, sitting alone beside a red dog food bowl.",
  "Biscuit has watched this for years. He has seen her cry at a cartoon, a wedding speech, and a very good sandwich.",
  ["TV showing a sad lonely puppy beside a dog food bowl"])
P("s1", "close", "eye_level", "living_room", ["maya"],
  "Maya sniffling and wiping her nose with a tissue, puzzled and embarrassed, a single tear on her cheek.",
  "Maya has questions too. Why does salty water just leak out of her face, and why does nobody ask her permission?")
P("s1", "medium", "eye_level", "living_room", ["maya"],
  "Maya looking toward the viewer with a thoughtful raised eyebrow, tissue in hand, wiping her last tear.",
  "So here is today's question. Why do humans cry, and why does it feel so good and so embarrassing at the same time?")
P("s1", "close", "eye_level", "diagram", [],
  "One large glossy blue teardrop shape floating alone in the middle of the plain navy backdrop beside a bright yellow question mark, no people and no faces in the picture.",
  "Let's start with the tear itself, because it turns out you make three completely different kinds of tears.",
  ["one large teardrop"])

# ------------------------------------------------------------- S2 three kinds of tears
scene("s2", "diagram", ["maya", "biscuit"], "Basal, reflex and emotional tears.", "curious, informative")
P("s2", "extreme_close", "eye_level", "diagram", ["maya"],
  "Extreme close up of Maya's one open dark brown eye behind her round glasses, long lashes, a thin glossy wet shine along the lower lid, calm and relaxed.",
  "Kind one: basal tears. They are always there, a thin film that keeps your eyes wet and clean. Right now, you are making them.")
P("s2", "medium", "eye_level", "kitchen", ["maya"],
  "Maya chopping a big onion at the kitchen table with tears streaming down her face, eyes squeezed shut and mouth in a comic grimace.",
  "Kind two: reflex tears. Cut an onion, or get smoke in your eye, and your eyes flood to wash the irritant away.",
  ["a cut onion", "tears streaming"])
P("s2", "close", "eye_level", "living_room", ["maya"],
  "Maya on the sofa with a red runny nose and a tissue pressed under it, watery eyes, a comic little drip, looking annoyed.",
  "Why does your nose run? Tears drain through tiny channels at the corner of each eye into your nose. Basically, plumbing.",
  ["red runny nose", "tissue"], pid="p007a")
P("s2", "medium", "eye_level", "diagram", ["maya"],
  "Maya sitting very still in profile with sad eyes and one clear teardrop rolling down her cheek, nothing near her eyes, a glowing yellow thought-cloud shape beside her head.",
  "Kind three is the strange one: emotional tears. Nothing is in your eye. The trigger is entirely inside your head.",
  ["one tear", "nothing in her eye"])
P("s2", "wide", "eye_level", "diagram", [],
  "Two large glass droplets side by side on the navy backdrop, the left one plain and pale blue, the right one filled with swirling bright yellow shapes.",
  "Studies of tears suggest emotional tears carry more protein-based hormones than onion tears. A clue that crying has a job to do.",
  ["two droplets, one plain, one with yellow swirls"])
P("s2", "wide", "eye_level", "diagram", [],
  "A large glossy blue teardrop shape floating in the middle of the plain navy backdrop, surrounded by a glowing bright yellow ring, tiny grey dots bouncing away from the ring, an abstract science diagram.",
  "Tears are not just water. They also contain an enzyme called lysozyme, which helps fight germs. Your eyes ship their own tiny security guard.",
  ["a teardrop with a yellow shield", "germs bouncing off"], pid="p009a")
P("s2", "close", "eye_level", "living_room", ["biscuit"],
  "Biscuit the cat sitting next to Maya's feet, one eyebrow raised in smug deadpan, a tiny puppy toy on the floor beside him.",
  "Here is a fun fact. As far as scientists know, humans are the only animals that cry because of how they feel.")
P("s2", "medium", "eye_level", "living_room", ["maya"],
  "Maya on the sofa looking up and to the side, thinking hard with a finger on her chin, small question marks floating above her head.",
  "So that is what tears are. The real mystery is why humans evolved to do this at all.")

# ------------------------------------------------------------- S3 why evolution kept it
scene("s3", "living_room", ["maya", "biscuit", "baby"], "Crying as a signal: babies, tears and sympathy.", "curious, then tender")
P("s3", "close", "eye_level", "living_room", ["maya"],
  "Maya in a full ugly cry, eyes squeezed shut, tears streaming down both cheeks, mouth wide open sobbing, red runny nose, hair messy, comical and over-the-top.",
  "Think about it. Crying blurs your vision, makes your nose run, and your breathing goes wobbly. Honestly, a terrible survival move.")
P("s3", "medium", "eye_level", "living_room", ["maya"],
  "Maya crying softly in the middle of the room while bright yellow signal rings spread out from her like a beacon, Biscuit watching from the arm of the sofa.",
  "Unless that is the point. One leading idea is that crying is a signal. It tells everyone nearby: I am overwhelmed and need you.")
P("s3", "wide", "high", "nursery", ["baby"],
  "A tiny baby lying in a wooden crib with mouth wide open, crying loudly, eyes squeezed shut, the star mobile above, a long shadow of a person arriving at the doorway.",
  "You can see it at the start of life. A newborn cannot walk, talk or feed itself. But it can cry, and somebody comes.")
P("s3", "extreme_close", "eye_level", "nursery", ["baby"],
  "Extreme close up of the baby's face, mouth open mid-cry, and one single small tear just forming at the corner of the eye.",
  "Here is a detail that surprises people. Newborns cry loudly, but real tears usually take a few weeks to arrive. The signal comes first.")
P("s3", "medium", "eye_level", "living_room", ["maya", "biscuit"],
  "Maya crying quietly on the sofa, wet shining cheeks, while Biscuit across the room lifts his head and stares at her, ears up, noticing.",
  "Some researchers think tears add something a cry alone cannot: a visible sign that you really mean it. Faces are easy to read.")
P("s3", "medium", "eye_level", "living_room", ["maya", "biscuit"],
  "Biscuit climbing onto Maya's lap and curling up, Maya looking down at him with wet cheeks and a small surprised smile, warm lamp light.",
  "And it seems to work. In studies across many countries, people who see tears tend to feel warmer, and offer more support.")
P("s3", "wide", "eye_level", "diagram", [],
  "A row of simple round flat cartoon faces on the navy backdrop, some with one blue tear, some without, a few smiling, no text, no letters.",
  "Studies comparing countries find differences in how often people cry. So crying is partly built in, and partly learned from the people around you.",
  ["a row of round faces, some with tears"], pid="p017a")

# ------------------------------------------------------------- S4 does it help
scene("s4", "living_room", ["maya", "biscuit"], "Does crying actually make you feel better?", "honest, reflective")
P("s4", "medium", "eye_level", "living_room", ["maya"],
  "Maya holding a crumpled tissue and raising one skeptical eyebrow toward the viewer, a yellow question mark glowing beside her.",
  "Now the big question. Does crying actually make you feel better? Scientists asked, and the honest answer is: sometimes.")
P("s4", "wide", "eye_level", "diagram", ["maya"],
  "A simple bright yellow line that dips down then climbs gently upward across the navy backdrop, a small Maya figure at the low point looking sad and another at the high point looking calmer.",
  "In surveys, many people say a good cry helps. In lab studies, the mood boost often shows up later, not right away.",
  ["a line that dips then climbs"])
P("s4", "close", "eye_level", "living_room", ["maya"],
  "Maya with eyes closed, taking a slow deep breath out, shoulders dropping, face relaxing, soft warm light on her cheeks.",
  "Why? Crying seems to switch on the calming side of your nervous system. Breathing and heart rate can settle after the storm passes.")
P("s4", "wide", "high", "living_room", ["maya"],
  "Maya, small, sitting alone in the far corner of a big dim living room with the lamp off, shoulders hunched, head down.",
  "Context matters too. Studies suggest crying alone, in a bad mood, helps less. Crying with someone supportive nearby tends to help more.")
P("s4", "medium", "eye_level", "living_room", ["maya", "biscuit"],
  "Maya laughing and crying at the same time with a party hat on and confetti falling, tears of joy on her cheeks, Biscuit beside her wearing a squashed party hat looking annoyed.",
  "And sometimes you cry from joy. A wedding, a surprise, a finish line. Researchers think your body is balancing a feeling too big.")
P("s4", "close", "eye_level", "diagram", ["maya"],
  "Maya's head in profile on the navy backdrop with a small bright yellow valve on top of her head letting out a puff of steam, her face relieved.",
  "So crying is not weakness. It looks a lot more like a pressure valve for a body carrying too much.")
P("s4", "medium", "eye_level", "living_room", ["maya"],
  "Maya on the sofa holding a phone to her ear with a calm, gentle, honest expression, a soft warm lamp light, the tissue box beside her.",
  "One honest note. Crying is normal. But if sadness lingers for weeks, talk to someone you trust. That is a signal too.",
  ["a phone held to her ear"], pid="p023a")

# ------------------------------------------------------------- S5 the goodbye
scene("s5", "hallway", ["maya", "dev", "biscuit"], "Dev comes to say goodbye and Maya lets herself cry.", "tender, sad, warm")
P("s5", "medium", "eye_level", "hallway", ["maya", "dev"],
  "Maya opening the front door in her yellow hoodie, Dev standing in the hallway holding a cardboard box and a small sad smile.",
  "But the best proof is not in a lab. A few weeks later, Maya's best friend Dev knocked, holding a cardboard box.")
P("s5", "over_shoulder", "eye_level", "hallway", ["dev", "maya"],
  "Dev looking down at his shoes, mouth open mid-sentence, trying to speak, eyes glassy, Maya listening in front of him.",
  "He was moving to another city. He had practiced the speech on the bus. He got about four words in.")
P("s5", "close", "eye_level", "hallway", ["maya"],
  "Close up of Maya's face, eyebrows tilted up in the middle, chin wobbling, lower lip trembling, her eyes brimming with big shining tears about to spill over.",
  "Maya did not plan to cry. Her chin wobbled first, then her eyes, then everything.",
  ["eyes filling with tears"])
P("s5", "close", "eye_level", "hallway", ["maya"],
  "Maya crying openly, eyes shut, tears streaming down both cheeks, mouth open in a sob, no tissue, no hiding.",
  "This time she did not hide it. No tissue, no joke, no checking who was watching. She just let it out.",
  ["tears streaming down both cheeks"])
P("s5", "medium", "eye_level", "hallway", ["maya", "dev"],
  "Maya and Dev hugging tightly in the hallway, tears streaming down both their cheeks, Maya's face against his shoulder, the cardboard box at their feet, warm yellow light.",
  "And Dev, who was definitely not planning to cry, joined her. Two grown adults, sobbing in a hallway, surrounded by boxes.",
  ["both hugging", "both crying"])
P("s5", "medium", "eye_level", "hallway", ["maya", "dev"],
  "Maya laughing through happy tears with a wide smile and wet cheeks, Dev smiling warmly with wet eyes and holding up his phone, the moving boxes behind them.",
  "He promised to call every Sunday. Maya promised to answer every Sunday, even if she cries. Dev said that was the best deal.",
  ["both smiling with wet eyes", "a phone"], pid="p028a")
P("s5", "close", "eye_level", "hallway", ["dev"],
  "Close up of Dev's face, wet cheeks, eyes warm, a relieved gentle smile appearing, shoulders relaxing.",
  "A wet face tells the other person: this matters to me. Dev could see it, and his whole body relaxed.")
P("s5", "medium", "low", "hallway", ["biscuit", "dev"],
  "Biscuit the cat pressing his head against Dev's leg and purring with eyes half closed, Dev looking down in surprise with wet eyes.",
  "And Biscuit, who has ignored every cry for years, walked over and pressed his head against Dev's leg. Even he got it.")

# ------------------------------------------------------------- S6 the answer
scene("s6", "living_room", ["maya", "biscuit"], "The answer and the sign-off.", "warm, hopeful")
P("s6", "medium", "eye_level", "living_room", ["maya"],
  "Maya on the sofa with a gentle smile and slightly wet eyes, looking toward the viewer, warm lamp light, the TV off.",
  "So why do we cry? Because some feelings are too big for words, and your body already knows how to say them.")
P("s6", "close", "eye_level", "diagram", [],
  "Only one glowing blue teardrop shape in the middle of the navy backdrop with three bright yellow rays shining out of it, no people and no faces.",
  "It signals that you need someone, it calms your body down, and it shows people they matter. Three jobs, one drop of salty water.",
  ["one teardrop with three rays"])
P("s6", "wide", "eye_level", "living_room", ["maya", "biscuit"],
  "Maya on the sofa with Biscuit in her lap and a tissue box beside her, smiling and waving at the viewer, the TV behind them showing a sad cartoon golden retriever puppy with drooping ears and big wet sorrowful eyes, sitting alone beside a red dog food bowl.",
  "So next time a dog food commercial gets you, let it happen. Your face is just doing its job.",
  ["TV showing a sad lonely puppy beside a dog food bowl"])
P("s6", "medium", "eye_level", "living_room", ["maya", "biscuit"],
  "Maya laughing with a happy tear on her cheek and pointing toward the viewer, Biscuit beside her giving a tiny deadpan nod.",
  "Thanks for watching, and tell us in the comments: what was the last thing that made you cry?")

bible = Bible(
    premise=Premise(title="Why Do We Cry? The Science of Tears", genre="vox",
                    logline="Maya sobs at a dog food commercial and sets out to learn why humans cry, then discovers the answer herself when her best friend comes to say goodbye.",
                    tone="witty, warm, curious, ending tender", setting="Maya's apartment."),
    characters=CHARS, locations=LOCS,
    rules=["Maya always wears round glasses and a bright yellow hoodie", "Biscuit is an orange tabby cat with white front paws and a blue collar",
           "Dev has no glasses, short curly dark hair and a forest green sweater",
           "Flat 2D vector art, no text or letters inside any picture"])
story = OriginalStory(bible=bible, scenes=SCENES, panels=PANELS)

if __name__ == "__main__":
    if BAD:
        sys.exit("narration over 24 words:\n" + "\n".join(BAD))
    ws =ROOT / "output" / "Original_Stories" / SLUG
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "story.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    words = sum(len(p.caption.split()) for p in PANELS)
    print(f"{len(PANELS)} panels, {len(SCENES)} scenes, {words} narrated words (~{words / 2.6 / 60:.1f} min at 2.6 words/s) -> {ws}")
