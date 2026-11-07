"""Source of the anime short "The Dawn Gate": writes output/Original_Stories/<slug>/story.json.

The story, dialogue and per-shot motion are authored here; the system still writes every picture prompt (shot director -> prompt composer)
and every motion prompt (film.py). One action per shot, no repeated beats, one speaker per shot so the voice can be anchored to that face.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene  # noqa: E402

SLUG = "dawn_gate"

CHARS = [
    Character(id="mira", name="Mira", role="protagonist", age_group="teen", gender="female",
              look="teenage girl, short messy copper-red hair, big amber eyes, green scarf, brown leather jacket, brass compass pendant on a chain, flight goggles pushed up on her forehead",
              personality="reckless, warm, fiercely loyal"),
    Character(id="pip", name="Pip", role="companion", age_group="child", species="sky-fox kit", gender="neutral",
              look="tiny round pure white fluffy sky-fox kit like a puffball, white fur only and never orange, the size of a cat, floats in the air, huge blue eyes, fluffy cloud-like tail, small brass bell on a blue ribbon collar",
              personality="brave, comic, never speaks (squeaks)"),
    Character(id="rook", name="Rook", role="rival", age_group="teen", gender="male",
              look="teenage boy, spiky silver-white hair, cold grey eyes, long black coat with red lining, fingerless black gloves, silver flight goggles around his neck",
              personality="proud, guarded, secretly kind"),
    Character(id="oren", name="Oren", role="mentor", age_group="elder", gender="male",
              look="elderly man, white walrus mustache, round spectacles, patched blue coat, wooden cane with a small lantern",
              personality="gentle, wise, worried"),
    Character(id="guardian", name="Guardian", role="antagonist", age_group="adult", species="stone golem", gender="neutral",
              look="colossal moss-covered stone golem, glowing cyan rune eyes, massive stone fists, ancient carved body",
              personality="ancient protector of the ruins; does not speak"),
    Character(id="guardian_gold", name="Awakened", role="antagonist", age_group="adult", species="stone golem", gender="neutral",
              look="colossal moss-covered stone golem, bright warm gold glowing rune eyes, soft golden light on its mossy stone body, massive stone fists, ancient carved body",
              personality="the Guardian after the crystal woke: gentle, helpful; does not speak"),
    Character(id="crystal", name="Crystal", role="other", age_group="adult", species="living crystal", gender="female",
              look="huge radiant floating golden crystal, faceted, glowing warm light",
              personality="ancient, calm, speaks in echoing words"),
]

LOCS = [
    Location(id="sky", name="Sky above the Drift", look="open sky among floating rock islands with waterfalls pouring into clouds, golden hour light"),
    Location(id="isle", name="Lantern Isle", look="small floating village island, timber houses, hanging paper lanterns, clotheslines, rope bridges, cobblestone square, late afternoon warm golden sunlight"),
    Location(id="lamp", name="The Great Lantern", look="stone tower square holding a huge glowing blue crystal lantern, cobblestones, villagers, late afternoon warm golden sunlight, long soft shadows"),
    Location(id="dock", name="Sky dock", look="wooden sky dock at the island's edge, glider racks, rope rails, sunset sky, open clouds below"),
    Location(id="canyon", name="Storm canyon", look="canyon of towering floating rock pillars and stone arches inside black storm clouds, lightning, night"),
    Location(id="jungle", name="Jungle clearing", look="overgrown jungle clearing at night on a floating island, giant ferns, glowing fireflies, ruins on a cliff in the distance"),
    Location(id="gate", name="Skyfall Ruins", look="ancient moss-covered stone temple ruins with a huge sealed gate carved with sun symbols, vines, blue pre-dawn light"),
    Location(id="mirrors", name="Hall of Mirrors", look="ancient temple hall with tall polished bronze mirrors on stone pillars, dust motes, shafts of light"),
    Location(id="bridge", name="Chasm bridge", look="narrow ancient stone bridge across a bottomless chasm glowing orange from below, carved pillars"),
    Location(id="vault", name="Crystal vault", look="round stone chamber with a huge radiant golden crystal floating above a carved altar, god rays, warm golden light"),
    Location(id="gorge", name="Moth Gorge", look="misty gorge in blue pre-dawn light, giant ferns, a long old rope-and-plank bridge, tiny glowing blue-green lantern moths drifting in the air"),
    Location(id="lamp_gold", name="The Great Lantern relit", look="stone tower square holding a huge warm golden glowing crystal lantern, golden sunrise light, villagers cheering, lanterns glowing gold"),
    Location(id="flashback", name="Memory", look="warm soft-focus memory of the sky dock at golden hour"),
    Location(id="ruinsky", name="Above the ruins", look="open morning sky above collapsing stone ruins, sunrise, dust and golden sparks"),
]

PANELS: list[Panel] = []
SCENES: list[Scene] = []


SCORE = {
    's1': ('bright uplifting orchestral adventure theme, soaring strings, fast acoustic guitar, bouncing woodwinds, light percussion, joyful flying', 140, 'D Major'),
    's2': ('warm tender piano with gentle strings, worried and loving, simple melody, intimate', 72, 'A Minor'),
    's3': ('playful confident rivalry theme, pizzicato strings, snare rolls, rising tension with swagger, builds to a race start', 118, 'E Minor'),
    's4': ('epic fast action storm chase, driving taiko and orchestral percussion, urgent strings, heroic brass, lightning stabs, thrilling', 160, 'C Minor'),
    's5': ('quiet night campfire, soft acoustic guitar and flute, gentle humour, warm and healing', 80, 'G Major'),
    's6': ('mysterious wonder, harp, glockenspiel and soft choir pads, slow build of awe and discovery', 90, 'D Dorian'),
    's7': ('intense boss chase, heavy percussion, low brass, ostinato strings, thrilling with a playful twist', 150, 'F# Minor'),
    's8': ('emotional sacrifice, solo piano with swelling strings and soft choir, heartbreaking then radiant', 66, 'F Major'),
    's9': ('triumphant epic escape, full orchestra with choir, soaring brass, urgent then glorious', 130, 'Bb Major'),
    's10': ('heartfelt resolution, warm strings and uplifting piano, hopeful anthem, gentle fade-out ending', 90, 'D Major'),
}


def scene(sid, loc, chars, summary, mood):
    sc, bpm, key = SCORE[sid]
    SCENES.append(Scene(id=sid, location_id=loc, character_ids=chars, summary=summary, mood=mood, score=sc, bpm=bpm, key=key))


COUNT = [0]


def P(sid, shot, angle, loc, chars, action, motion, dlg=None, key=None, pid=None):
    if pid is None:  # numbered shots keep their ids whatever is inserted between them; inserted shots carry an explicit id
        COUNT[0] += 1
        pid = f"p{COUNT[0]:03d}"
    PANELS.append(Panel(id=pid, scene_id=sid, shot=shot, angle=angle, location_id=loc, character_ids=chars,
                        action=action, motion=motion,
                        dialogue=[Line(speaker_id=dlg[0], text=dlg[1])] if dlg else [], key_visuals=key or []))


def Q(pid, *args, **kw):
    P(*args, pid=pid, **kw)


# ---------------------------------------------------------------- S1 golden-hour flight (fun hook)
scene("s1", "sky", ["mira", "pip"], "Mira rockets home on her patched flying machine and crash-lands in the laundry.", "joyful, fast, funny")
P("s1", "wide", "low", "sky", ["mira", "pip"], "Mira crouched in her wooden flying machine with big patched canvas wings, flying fast between floating islands in golden afternoon light, scarf streaming behind her, Pip floating beside her.",
  "the flying machine streaks forward past the camera, scarf whipping, islands sliding by")
P("s1", "close", "eye_level", "sky", ["mira"], "Mira's face close-up, windblown, a huge excited grin, goggles on her forehead, golden sky behind.",
  "wind whips her hair, she laughs and turns her head, mouth moving as she speaks", ("mira", "Hold on, Pip! Lantern Isle is right ahead, and this time we're landing it!"))
P("s1", "extreme_close", "eye_level", "sky", ["pip"], "Close-up of Pip the white sky-fox kit floating in the rushing wind, ears pinned flat, cheeks flapping, eyes huge and terrified, blurred sky behind.",
  "ears flap wildly, cheeks ripple in the wind, Pip gulps and squeezes its eyes shut")
P("s1", "wide", "eye_level", "sky", ["mira", "pip"], "Mira in her wooden flying machine with big patched canvas wings, diving through a pouring waterfall, spray exploding around it, a small rainbow forming in the mist.",
  "the flying machine punches through the waterfall spray and a rainbow flares behind it")
P("s1", "medium", "low", "sky", ["mira", "pip"], "Mira banking the flying machine hard around a tall rock spire, leaning her whole body into the turn, patched wing cloth taut.",
  "the flying machine swings around the spire in a tight curve, Mira leaning, wing cloth snapping")
P("s1", "wide", "high", "isle", ["mira", "pip"], "Lantern Isle's wooden dock ahead with a long line of hanging laundry; Mira in her wooden flying machine with big patched canvas wings, coming in far too fast.",
  "the flying machine speeds toward the dock and the laundry line, getting bigger every moment")
P("s1", "medium", "eye_level", "sky", ["mira"], "Mira's face, panicked, eyes wide, one hand frantically feeling the flying machine's controls.",
  "she looks down at the controls, then up, eyes widening, mouth moving", ("mira", "Uh-oh. Brakes? Where are the... where are the brakes?"))
P("s1", "wide", "eye_level", "dock", ["mira", "pip"], "Mira in her wooden flying machine with big patched canvas wings ploughing through a line of white laundry sheets on the dock, sheets wrapping the flying machine and Mira.",
  "the flying machine tears through the hanging sheets, cloth flying everywhere, skidding along the dock boards")
P("s1", "medium", "eye_level", "dock", ["mira", "pip"], "Mira's head popping out of a pile of white sheets, a sheet draped over her head like a ghost, Pip sitting on top of it, wooden dock behind.",
  "she pops up from the sheets, blinks, then gives a proud thumbs-up", ("mira", "Landed! ...Technically."))

# ---------------------------------------------------------------- S2 Lantern Isle: the stakes
scene("s2", "lamp", ["mira", "oren", "pip"], "The Great Lantern is dying; Oren tells of the Dawn Crystal and Mira's lost father.", "worried, tender, determined")
P("s2", "wide", "low", "lamp", ["oren"], "The huge blue Great Lantern crystal in its stone tower flickering and dimming, villagers in the square looking up with worried faces.",
  "the blue light flickers and dims, villagers clasp their hands and look up")
P("s2", "medium", "eye_level", "lamp", ["oren"], "Grandpa Oren beside the dim Great Lantern, leaning on his cane, a worried face, speaking.",
  "he looks up at the crystal and then at the camera, speaking gravely, his mustache moving", ("oren", "Mira, can you feel it? Our Lantern is fading, and the island sinks lower every day."))
P("s2", "close", "eye_level", "lamp", ["mira"], "Mira close-up, her cheerful grin fading into a serious worried look, Pip floating beside her with drooping ears.",
  "her smile slowly falls, she swallows, Pip's ears droop")
P("s2", "wide", "eye_level", "isle", ["oren", "mira"], "The village square shaking, a crack splitting the cobblestones, hanging lanterns swinging wildly, a clay pot falling and shattering.",
  "the ground shudders, the crack races across the stones, lanterns swing, the pot falls and breaks")
P("s2", "close", "eye_level", "lamp", ["oren"], "Oren close-up, kind weathered face, serious eyes, speaking.",
  "he lifts one finger as he speaks, eyes steady, mustache moving", ("oren", "There is one hope: the Dawn Crystal, deep in the Skyfall Ruins."))
P("s2", "medium", "low", "lamp", ["oren"], "Oren medium shot beside the dim Great Lantern, leaning on his cane, looking toward the horizon, speaking solemnly.",
  "he turns toward the far sunset horizon, then back, speaking solemnly", ("oren", "Its gate opens at sunrise, once a year. And that sunrise is tomorrow."))
P("s2", "medium", "eye_level", "lamp", ["mira"], "Mira medium shot, eyes wide, stepping forward, fists clenched.",
  "she steps forward, fists tightening, speaking urgently", ("mira", "Tomorrow? Then I fly tonight!"))
P("s2", "close", "eye_level", "lamp", ["oren"], "Grandpa Oren close-up, eyes lowering sadly, soft warm light.",
  "his eyes drop, his voice trembles slightly as he speaks", ("oren", "Your father carried that compass to the ruins, Mira. He never came back."))
P("s2", "extreme_close", "eye_level", "lamp", ["mira"], "Extreme close-up of Mira's hand gripping the brass compass pendant on her chest, the needle trembling.",
  "her fingers tighten around the pendant, the needle shivers and swings")
P("s2", "close", "eye_level", "lamp", ["mira"], "Mira close-up, resolute amber eyes, a tear caught in her eyelashes, chin lifted.",
  "she blinks the tear away, lifts her chin, speaking firmly", ("mira", "Then I'll finish what he started. I'll bring the dawn home, Grandpa."))
P("s2", "medium", "eye_level", "lamp", ["oren"], "Grandpa Oren smiling through wet eyes, patting Mira's shoulder.",
  "he smiles with shining eyes and pats her shoulder, speaking softly", ("oren", "Then fly fast, little spark. And fly safe."))
P("s2", "close", "eye_level", "lamp", ["pip"], "Pip the white sky-fox kit floating in mid-air giving a tiny brave salute with one paw.",
  "Pip snaps a tiny salute, chest puffed out, tail wagging")
P("s2", "wide", "eye_level", "isle", ["mira", "pip"], "Mira running along a rope bridge toward the dock, Pip floating along beside her, villagers waving from their doorways, lanterns glowing.",
  "she sprints across the swaying bridge, Pip bouncing, villagers waving")

# ---------------------------------------------------------------- S3 the rival and the race
scene("s3", "dock", ["mira", "rook", "pip"], "Rook arrives; they bicker and launch into a race at sunset.", "competitive, witty")
P("s3", "wide", "low", "dock", ["rook"], "A sleek black flying machine with red trim landing softly on the sunset dock, Rook stepping off, his long black coat flaring.",
  "the black flying machine touches down, Rook steps off, coat swirling around him")
P("s3", "medium", "eye_level", "dock", ["rook"], "Rook standing coolly on the dock, arms crossed, a smirk, sunset sky behind him.",
  "he tilts his head with a smirk, speaking dryly", ("rook", "Nice landing. Was the laundry part of the plan?"))
P("s3", "medium", "eye_level", "dock", ["mira"], "Mira with a bedsheet still tangled in her hair, indignant, hands on hips.",
  "she pulls the sheet from her hair and jabs a finger, speaking sharply", ("mira", "Who are you? And nobody calls my glider scrap!"))
P("s3", "close", "eye_level", "dock", ["rook"], "Rook close-up, cold grey eyes, sunset rim light on his silver hair.",
  "he steps closer with a steady cold gaze, speaking quietly", ("rook", "Rook. The one who reaches the Dawn Gate first."))
P("s3", "close", "eye_level", "dock", ["mira"], "Mira close-up, a competitive grin, amber eyes bright.",
  "her grin widens, she pulls her goggles down over her eyes, speaking", ("mira", "Funny, I was about to say the same thing. Race you?"))
P("s3", "close", "eye_level", "dock", ["rook"], "Rook close-up with a tiny smirk, silver goggles at his neck.",
  "he lifts his goggles over his eyes with one hand, speaking low", ("rook", "Try to keep up."))
P("s3", "wide", "eye_level", "dock", ["mira", "rook", "pip"], "Mira and Rook climbing into the open cockpits of their two winged flying machines side by side at the dock's edge, sunset behind them.",
  "both riders grip their flying machines, wind lifts their hair and coats")
P("s3", "close", "eye_level", "dock", ["pip"], "Pip the white sky-fox kit floating in mid-air puffing its cheeks, a determined face, eyes narrowed.",
  "Pip puffs its cheeks and narrows its eyes, tail bristling")
P("s3", "extreme_close", "eye_level", "dock", ["rook"], "Extreme close-up of Rook's silver goggles snapping down over his grey eyes, sunset reflected in the lenses.",
  "the goggles snap down, sunset glints across the lenses")
P("s3", "wide", "high", "dock", ["mira", "rook"], "Mira and Rook leaping off the sky dock in the same instant, flying machines unfurling, speed lines in the sunset clouds.",
  "both flying machines drop, unfurl and catch the wind, shooting forward side by side")
P("s3", "wide", "low", "sky", ["mira", "rook"], "Mira's wooden flying machine with big patched canvas wings and Rook's sleek black flying machine with red trim rocketing side by side past floating islands into the dark clouds, sunset fading to dusk.",
  "the flying machines race neck and neck toward the storm wall, the light darkening")

# ---------------------------------------------------------------- S4 storm canyon race (action)
scene("s4", "canyon", ["mira", "rook", "pip"], "The race through the storm canyon; Rook is struck and Mira saves him.", "thrilling, then tender")
P("s4", "wide", "eye_level", "canyon", ["mira", "rook"], "Mira and Rook flying in their two winged flying machines with wide canvas wings spread, entering a canyon of tall floating rock pillars inside a black storm, lightning flickering across the clouds.",
  "the flying machines plunge into the canyon, lightning flashes across the pillars")
P("s4", "medium", "eye_level", "canyon", ["mira", "pip"], "Mira flying through the storm, rain streaming off her goggles, shouting over the wind, Pip floating beside her.",
  "rain streaks past, she shouts to the side, mouth moving", ("mira", "Pip, call the turns! Left pillar, now!"))
P("s4", "close", "eye_level", "canyon", ["pip"], "Pip the white sky-fox kit floating in the storm rain, soaked and wild-eyed, a tiny paw thrust pointing left, squeaking.",
  "Pip squeaks and jabs its paw to the left, ears streaming back")
P("s4", "wide", "eye_level", "canyon", ["mira"], "Mira in her wooden flying machine with big patched canvas wings banking left, slipping through a gap between two huge stone pillars by a hair's breadth.",
  "the flying machine squeezes through the gap between the pillars, wingtip scraping a shower of sparks")
P("s4", "medium", "eye_level", "canyon", ["rook"], "Rook flying alongside, rain-soaked, a confident smirk, silver goggles.",
  "he glances sideways with a smirk, shouting over the wind", ("rook", "Too slow!"))
P("s4", "wide", "low", "canyon", ["rook"], "Rook's sleek black flying machine with red trim surging ahead with a burst of red glowing thruster flame, pulling away between the pillars.",
  "the thruster bursts red and the black flying machine rockets ahead")
P("s4", "medium", "eye_level", "canyon", ["mira"], "Mira gritting her teeth, rain on her face, one hand yanking a lever on her flying machine.",
  "she yanks the lever, grinning fiercely, shouting", ("mira", "Not today!"))
P("s4", "wide", "low", "canyon", ["mira"], "Mira in her wooden flying machine with big patched canvas wings, folding its its wings back and diving under a huge stone arch while Rook flies over the top of the arch.",
  "Mira in her wooden flying machine with big patched canvas wings tucks its wings and darts under the arch, Rook sails over it")
P("s4", "close", "eye_level", "canyon", ["mira"], "Mira's face lit white by a lightning flash, a wild exhilarated grin, rain beading on her goggles.",
  "lightning flashes white across her face, she laughs, hair streaming")
P("s4", "wide", "eye_level", "canyon", ["mira", "rook"], "A lightning bolt striking a tall stone pillar, huge chunks of rock breaking loose and tumbling down toward Mira and Rook on their flying machines.",
  "the bolt cracks the pillar, boulders fall, the flying machines dive away")
P("s4", "medium", "high", "canyon", ["mira", "pip"], "Mira weaving the flying machine between falling boulders, Pip floating beside her with its fur standing on end from static.",
  "boulders crash past, she twists the flying machine through them, Pip's fur frizzed")
P("s4", "wide", "eye_level", "canyon", ["rook"], "Rook rolling his black flying machine elegantly between falling rocks, coat whipping.",
  "he barrel-rolls the flying machine around the tumbling rocks")
P("s4", "close", "eye_level", "canyon", ["rook"], "Rook's eyes widening behind his goggles as a white-blue lightning bolt races toward him.",
  "his eyes widen, a white-blue glow rises in the lenses")
P("s4", "wide", "eye_level", "canyon", ["rook"], "A lightning bolt striking Rook's sleek black flying machine with red trim, an explosion of red sparks, the flying machine spinning out of control and Rook thrown into the air.",
  "the bolt hits, sparks explode, the flying machine spins away and Rook tumbles out of it")
P("s4", "medium", "eye_level", "canyon", ["mira"], "Mira looking back over her shoulder, horrified, mouth open.",
  "she whips her head around, eyes wide, shouting his name", ("mira", "Rook!"))
P("s4", "wide", "high", "canyon", ["rook"], "Rook falling through dark clouds, coat flapping, arms and legs spread, lightning flickering around him.",
  "he tumbles downward through the cloud, coat flapping, lightning flickering")
P("s4", "wide", "low", "canyon", ["mira", "pip"], "Mira tucking her flying machine into a steep dive after Rook, Pip flattened against her back, rain streaming upward.",
  "the flying machine nose-dives, rain streaking upward, Mira flat against the frame")
P("s4", "medium", "eye_level", "canyon", ["mira"], "Mira flat against the flying machine in a dive, gritted teeth, wind tearing at her scarf.",
  "she pushes forward, scarf tearing in the wind, shouting", ("mira", "Come on, come on, faster!"))
P("s4", "close", "high", "canyon", ["rook"], "Rook falling, eyes squeezed shut, bracing for impact, rain in his silver hair.",
  "his coat whips upward as he falls, then his eyes open at a shadow rising below")
P("s4", "wide", "eye_level", "canyon", ["mira", "rook"], "Mira in her wooden flying machine with big patched canvas wings swooping under the falling Rook, Rook landing on the flying machine's wing and Mira grabbing his wrist.",
  "the flying machine slides under him, he thumps onto the wing, she catches his wrist")
P("s4", "medium", "eye_level", "canyon", ["rook"], "Rook clinging to the flying machine wing, wet hair in his eyes, stunned and disbelieving.",
  "he looks up at her, rain on his face, speaking in disbelief", ("rook", "Why did you come back for me?"))
P("s4", "close", "eye_level", "canyon", ["mira"], "Mira straining at the controls, rain on her face, fierce but caring eyes.",
  "she strains at the controls and snaps a look at him, speaking", ("mira", "Because you were falling, genius! Hold on!"))
P("s4", "wide", "high", "canyon", ["mira", "rook"], "The overloaded patched flying machine wobbling and trailing smoke as it drops toward a dark jungle island below, rain falling.",
  "the flying machine wobbles, smoke streams behind it, it sinks toward the treetops")
P("s4", "wide", "eye_level", "jungle", ["mira", "rook"], "The flying machine crash-landing, skidding through giant ferns and snapping branches, leaves and mud flying, sliding to a stop in a clearing.",
  "the flying machine ploughs through ferns, leaves explode upward, it grinds to a stop")

# ---------------------------------------------------------------- S5 truce
scene("s5", "jungle", ["mira", "rook", "pip"], "In the wreck they share what they have lost and make a truce.", "quiet, funny, warm")
P("s5", "wide", "eye_level", "jungle", ["mira", "rook"], "Smoke rising from the wrecked flying machine in a night jungle clearing, Mira and Rook small beside it, fireflies drifting, distant ruins on a cliff under the stars.",
  "smoke curls upward, fireflies drift, the camera slowly pushes toward the distant ruins")
P("s5", "medium", "eye_level", "jungle", ["mira"], "Mira sitting up in the ferns with leaves in her hair, dazed, coughing.",
  "she sits up, coughs, plucks a leaf from her hair, speaking", ("mira", "Everyone... alive?"))
P("s5", "close", "eye_level", "jungle", ["pip"], "Pip the white sky-fox kit floating up out of the ferns, dizzy, little stars circling its head.",
  "Pip shakes its head, stumbles sideways, stars spin around its head")
P("s5", "medium", "eye_level", "jungle", ["rook"], "Rook standing and looking down at the shattered pieces of his black flying machine, jaw tight, firelight on his face.",
  "he stares at the broken flying machine, hands curling into fists")
P("s5", "close", "eye_level", "jungle", ["rook"], "Rook close-up, firelight on his face, eyes glassy and hurt, looking away.",
  "he looks away, jaw working, then speaks quietly", ("rook", "That glider was all I had left. My island sank last spring."))
P("s5", "close", "eye_level", "jungle", ["mira"], "Mira close-up, her expression softening with understanding, firefly light in her eyes.",
  "her face softens, she speaks gently", ("mira", "So that's why you need the crystal."))
P("s5", "close", "eye_level", "jungle", ["rook"], "Rook close-up, bitter, eyes shining in the firelight.",
  "he shakes his head slowly, speaking bitterly", ("rook", "An island without a Lantern is just a rock waiting to fall."))
P("s5", "medium", "eye_level", "jungle", ["mira"], "Mira stepping forward and holding out her hand with a friendly determined smile.",
  "she steps toward him and holds out her hand, speaking warmly", ("mira", "Then we do this together. Truce, until the gate?"))
P("s5", "extreme_close", "eye_level", "jungle", ["mira", "rook"], "Extreme close-up of Mira's hand and Rook's gloved hand meeting in a handshake, firefly light.",
  "his gloved hand hesitates, then clasps hers and they shake")
P("s5", "medium", "eye_level", "jungle", ["rook"], "Rook with a very small reluctant smile.",
  "a small smile tugs at his mouth, he speaks dryly", ("rook", "Truce. But I'm not carrying the fox."))
P("s5", "medium", "eye_level", "jungle", ["rook", "pip"], "Pip sitting on Rook's head wearing his silver goggles crookedly over its eyes, Rook frozen in place.",
  "Pip adjusts the oversized goggles proudly, Rook doesn't move")
P("s5", "close", "eye_level", "jungle", ["rook"], "Rook close-up, totally deadpan, a small fox's tail hanging across his forehead.",
  "he stays perfectly still, one eye twitching, speaking flatly", ("rook", "...Get it off."))
P("s5", "wide", "eye_level", "jungle", ["mira", "rook", "pip"], "Mira laughing while she and Rook walk up a mossy stone path toward the ruins, Rook scowling, blue pre-dawn light.",
  "they walk up the path, Mira laughing, Rook scowling, the blue light growing")

# ---- Moth Gorge (added so the film runs about nine and a half minutes): fun, a chase, and Rook returns the rescue. Explicit ids keep every other shot's id.
Q("q01", "s5", "wide", "eye_level", "gorge", ["mira", "rook"], "Mira and Rook walking single file along a mossy path through giant ferns toward the glowing ruins, tiny blue-green lights drifting in the blue pre-dawn air.",
  "they walk along the path, the camera follows behind them, glowing specks drift past")
Q("q02", "s5", "close", "eye_level", "gorge", ["pip"], "Close-up of Pip the white fluffy sky-fox kit floating in the pre-dawn mist, nose twitching, huge blue eyes reflecting a tiny glowing light.",
  "Pip's nose twitches, its eyes grow wide and follow a drifting glowing light, ears perking up")
Q("q03", "s5", "wide", "low", "gorge", [], "A huge swirling cloud of dinner-plate-sized glowing blue-green moths rising out of giant ferns in a misty gorge in blue pre-dawn light.",
  "the moths rise in a glowing swirl, wings beating, light rippling through the cloud")
Q("q04", "s5", "medium", "eye_level", "gorge", ["mira"], "Mira looking up with a delighted open mouth, blue-green moth light glowing on her face.",
  "she turns slowly, awestruck, moth light flickering on her face, speaking softly", ("mira", "Whoa. They're beautiful."))
Q("q05", "s5", "medium", "eye_level", "gorge", ["rook"], "Rook wary, one hand raised in warning, moth light on his silver hair.",
  "he lifts his hand in warning and glances at the swarm, speaking low", ("rook", "Don't touch them. Lantern moths follow any light."))
Q("q06", "s5", "close", "eye_level", "gorge", ["pip"], "Pip the white fluffy sky-fox kit mid-leap toward a glowing moth, eyes sparkling, mouth open in a happy squeak.",
  "Pip dives eagerly toward a glowing moth, tail wagging, squeaking happily")
Q("q07", "s5", "medium", "eye_level", "gorge", ["mira"], "Mira reaching out in alarm, eyes wide, glowing moths swirling behind her.",
  "she reaches out and shouts, moths swirling past her", ("mira", "Pip, no! Come back!"))
Q("q08", "s5", "wide", "high", "gorge", ["pip"], "Pip the white fluffy sky-fox kit carried upward in a spiral of glowing moths over a misty gorge, kicking its little legs.",
  "the moths lift Pip in a glowing spiral and carry it across the gorge, its legs kicking")
Q("q09", "s5", "wide", "eye_level", "gorge", ["mira", "rook"], "Mira and Rook sprinting onto a long rope-and-plank bridge across a misty gorge, chasing the glowing swarm.",
  "they run onto the swaying rope bridge, planks bouncing under their boots")
Q("q10", "s5", "medium", "eye_level", "gorge", ["rook"], "Rook running on the rope bridge, glancing down at the cracked old planks, alarmed.",
  "he runs, glances down at the cracking planks and shouts a warning", ("rook", "This bridge is rotten! Slow down!"))
Q("q11", "s5", "wide", "high", "gorge", ["mira"], "Old wooden planks snapping and dropping away under Mira's boots on a rope bridge over a deep misty gorge.",
  "plank after plank cracks and falls into the mist as Mira runs, the bridge sagging")
Q("q12", "s5", "close", "eye_level", "gorge", ["mira"], "Mira close-up, terror on her face as she slips, one hand grabbing a rope, mist below.",
  "she slips, grabs the rope and cries out", ("mira", "Rook!"))
Q("q13", "s5", "wide", "low", "gorge", ["mira", "rook"], "The rope bridge snapping at one end and swinging against the cliff, Mira dangling from a plank while Rook grabs her wrist from the cliff edge.",
  "the bridge whips against the cliff, Mira dangles, Rook lunges and catches her wrist")
Q("q14", "s5", "close", "eye_level", "gorge", ["rook"], "Rook close-up, straining with both hands gripping, sweat on his face, fierce and gentle at once.",
  "he strains and holds on, then speaks through his teeth", ("rook", "I've got you. You caught me once, remember?"))
Q("q15", "s5", "wide", "eye_level", "gorge", ["mira", "rook"], "Rook hauling Mira up over the edge of the cliff ledge, both landing in the ferns gasping, the broken bridge hanging below.",
  "he heaves her up over the edge and they collapse in the ferns, panting")
Q("q16", "s5", "close", "eye_level", "gorge", ["mira"], "Mira close-up lying in the ferns, out of breath, a grateful grin, blue light on her face.",
  "she catches her breath and grins, speaking warmly", ("mira", "Now we're even."))
Q("q17", "s5", "medium", "eye_level", "gorge", ["pip"], "Pip the white fluffy sky-fox kit floating gently down on a halo of glowing moths, landing proudly, looking very pleased.",
  "the moths set Pip down gently and drift away, Pip looks proud and wags its tail")
Q("q18", "s5", "wide", "low", "gorge", ["mira", "rook"], "Mira and Rook standing side by side on the cliff, looking up toward the ruins as the first golden light touches the highest tower, glowing moths drifting around them.",
  "they stand shoulder to shoulder, golden light spreading over the tower, moths drifting upward")


# ---------------------------------------------------------------- S6 ruins and the mirror puzzle
scene("s6", "gate", ["mira", "rook", "pip"], "The gate is sealed; the compass reveals a side way and the mirrors open the path.", "wonder, teamwork, comic")
P("s6", "wide", "low", "gate", ["mira", "rook"], "The huge sealed stone gate of the Skyfall Ruins carved with a giant sun, vines hanging, the three tiny figures before it in blue pre-dawn light.",
  "the camera cranes up the vast sun-carved gate as the tiny figures look up")
P("s6", "medium", "eye_level", "gate", ["mira", "rook"], "Mira and Rook pushing with all their strength against the huge stone gate, veins showing, it does not budge.",
  "they heave against the gate, boots sliding, the stone does not move")
P("s6", "close", "eye_level", "gate", ["rook"], "Rook close-up reading the sun inscription on the stone, a frown.",
  "he runs his fingers over the carving, then speaks", ("rook", "Sealed. The carving says it opens only at first light."))
P("s6", "close", "eye_level", "gate", ["mira"], "Mira looking at her brass compass pendant in her hand, the needle spinning toward a side tunnel, blue light.",
  "the needle swings and locks to one side, she looks that way, speaking", ("mira", "The compass is pointing somewhere else."))
P("s6", "wide", "eye_level", "gate", ["mira", "rook", "pip"], "A hidden side entrance behind a curtain of vines, Mira pushing the vines aside and the three stepping into the dark opening.",
  "Mira sweeps the vines aside and they duck into the dark entrance")
P("s6", "wide", "eye_level", "mirrors", ["mira", "rook"], "The Hall of Mirrors, tall polished bronze mirrors on stone pillars, dust motes floating, a thin crack of sunrise light entering high above.",
  "dust motes drift, the camera glides forward past the mirrors, the first thin light creeps in")
P("s6", "medium", "eye_level", "mirrors", ["rook"], "Rook studying a bronze mirror, reflecting his thoughtful face.",
  "he touches the mirror's frame, looks up at the light, speaking", ("rook", "Mirrors. They must carry the dawn light to the crystal chamber."))
P("s6", "medium", "eye_level", "mirrors", ["mira", "pip"], "Mira heaving a heavy bronze mirror around on its stand, Pip hanging from the handle trying to help.",
  "she turns the heavy mirror, Pip dangling from the handle swings with it")
P("s6", "close", "eye_level", "mirrors", ["mira"], "Mira directing with one finger, sweat on her forehead, half-laughing.",
  "she points with one finger and wobbles her hand, speaking", ("mira", "Pip, left a bit! No, your other left!"))
P("s6", "close", "eye_level", "mirrors", ["pip"], "Pip with its tongue sticking out in concentration, both paws tilting a small bronze mirror.",
  "Pip tilts the small mirror with both paws, tongue out, then freezes proudly")
P("s6", "wide", "eye_level", "mirrors", ["mira", "rook"], "Sunrise light slicing through a high window and bouncing from mirror to mirror down the hall while Mira and Rook watch, a glowing path of golden beams forming.",
  "the light hits the first mirror and jumps from mirror to mirror down the hall in a blaze of gold")
P("s6", "wide", "eye_level", "mirrors", ["mira", "rook"], "The final golden beam striking a sun-carved stone door at the end of the hall, the door grinding open and dust falling.",
  "the beam hits the sun carving, the stone door grinds open, dust pours down")
P("s6", "medium", "eye_level", "mirrors", ["mira"], "Mira turning to Rook with an astonished grin, golden light on her face.",
  "she turns with a huge grin, speaking breathlessly", ("mira", "It's working! It's actually working!"))
P("s6", "close", "eye_level", "mirrors", ["rook"], "Rook close-up, golden light on his face, wary eyes looking toward the dark doorway.",
  "his smile vanishes, he stares into the dark doorway, speaking low", ("rook", "Don't celebrate yet. Something in there is breathing."))

# ---------------------------------------------------------------- S7 the guardian (big action)
scene("s7", "bridge", ["mira", "rook", "pip", "guardian"], "A stone Guardian wakes on the bridge; the heroes outwit it with a mirror flash.", "tense, thrilling, comic payoff")
P("s7", "wide", "eye_level", "bridge", ["mira", "rook", "pip"], "Mira, Rook and Pip crossing a narrow ancient stone bridge over a glowing orange chasm toward a golden glow in the distance.",
  "the three cross the long bridge, the camera pulls back to show the chasm glowing below")
P("s7", "medium", "eye_level", "bridge", ["mira"], "Mira walking carefully along the narrow bridge, arms out for balance, eyes darting.",
  "she tiptoes along the narrow bridge, arms out, whispering", ("mira", "Just a bridge. Nothing scary about a bridge."))
P("s7", "wide", "low", "bridge", ["guardian", "mira", "rook"], "A colossal moss-covered stone Guardian rising out of the glowing chasm in front of Mira and Rook on the bridge, rock and dust cascading off it, cyan rune eyes lighting up.",
  "the Guardian heaves up out of the chasm, stones tumbling off its shoulders, its eyes flare cyan")
P("s7", "extreme_close", "eye_level", "bridge", ["guardian"], "Extreme close-up of the Guardian's cyan rune eyes igniting in a dark stone face.",
  "the cyan eyes flare to life with a hum and focus")
P("s7", "medium", "eye_level", "bridge", ["rook"], "Rook shouting in alarm, eyes wide, pointing back along the bridge.",
  "he spins and shouts, pointing back", ("rook", "Run!"))
P("s7", "wide", "eye_level", "bridge", ["guardian", "mira", "rook"], "The Guardian's giant stone fist smashing down onto the bridge where they stood a heartbeat ago, stone slabs flying.",
  "the fist crashes down, slabs fly, the bridge cracks")
P("s7", "wide", "eye_level", "bridge", ["mira", "rook", "pip"], "Mira and Rook sprinting along the cracking bridge as slabs break off and fall behind them.",
  "they sprint, slabs crumbling and dropping away right behind their heels")
P("s7", "medium", "eye_level", "bridge", ["pip"], "Pip the white sky-fox kit floating in mid-air, ears flapping back, mouth wide open in a silent scream.",
  "Pip's ears flap, mouth wide, bouncing with each stride")
P("s7", "wide", "eye_level", "bridge", ["rook", "mira"], "Rook leaping over a wide gap in the broken bridge, Mira leaping right behind him, her scarf trailing in the air.",
  "Rook clears the gap and Mira jumps after him, scarf streaming")
P("s7", "close", "eye_level", "bridge", ["rook"], "Rook gripping Mira's wrist and hauling her up over the edge of the broken bridge, straining.",
  "he pulls her up over the edge, straining, then speaks", ("rook", "Got you!"))
P("s7", "wide", "low", "bridge", ["guardian", "mira", "rook"], "The Guardian swinging a huge arm sideways across the bridge, shattering a carved pillar as the two heroes duck below it.",
  "the arm sweeps, the pillar explodes in stone, they drop flat beneath it")
P("s7", "medium", "eye_level", "bridge", ["mira"], "Mira crouched behind a broken pillar, eyes bright with an idea, pointing at the Guardian's glowing eyes.",
  "she peeks out, points at the glowing eyes, speaking fast", ("mira", "It follows light! Rook, throw me your goggles!"))
P("s7", "close", "eye_level", "bridge", ["rook"], "Rook incredulous, pulling his silver goggles off over his head.",
  "he pulls the goggles off, aghast, speaking", ("rook", "My goggles?! Why my goggles?!"))
P("s7", "medium", "eye_level", "bridge", ["mira"], "Mira catching the silver goggles out of the air, grinning.",
  "the goggles arc through the air and she catches them, speaking", ("mira", "Because they shine!"))
P("s7", "wide", "high", "bridge", ["mira"], "Mira climbing a broken pillar toward a crack in the ceiling where a beam of sunrise light falls, holding the silver goggles up.",
  "she scrambles up the pillar to the beam and lifts the goggles into the light")
P("s7", "extreme_close", "eye_level", "bridge", ["mira"], "Extreme close-up of the silver goggle lens Mira holds up, catching a brilliant sunbeam in a hard bright flare.",
  "the lens catches the beam and bursts into a dazzling flare")
P("s7", "wide", "eye_level", "bridge", ["guardian", "mira"], "A dazzling beam reflected from Mira's goggles hitting the Guardian's glowing eyes, the colossal golem roaring and staggering backward, swatting blindly.",
  "the beam sweeps across its eyes, it roars and staggers, swatting at the air")
P("s7", "medium", "eye_level", "bridge", ["rook"], "Rook shouting as stone chunks fall from the ceiling.",
  "stones rain around him, he shouts", ("rook", "It's blind, and now it's furious!"))
P("s7", "wide", "eye_level", "bridge", ["mira", "rook", "pip"], "The three dashing across the last stretch of the bridge toward a golden arch as the bridge collapses behind them into the glowing chasm.",
  "they sprint through the golden arch as the bridge falls away behind them")

# ---------------------------------------------------------------- S8 the price of the crystal
scene("s8", "vault", ["mira", "rook", "pip", "crystal"], "The Dawn Crystal asks for what Mira holds most dear; she gives her father's compass.", "awe, sacrifice, emotion")
P("s8", "wide", "low", "vault", ["mira", "rook", "pip", "crystal"], "A round stone vault with the huge radiant golden Crystal floating over a carved altar, god rays flooding the room, Mira, Rook and Pip tiny at the arch.",
  "the crystal hums and rotates slowly, light rays sweep the vault, the camera pushes in")
P("s8", "close", "eye_level", "vault", ["mira"], "Mira close-up, golden light on her awed face, lips parted.",
  "golden light fills her eyes, she whispers", ("mira", "The Dawn Crystal."))
P("s8", "wide", "eye_level", "vault", ["crystal"], "The huge golden Crystal pulsing with light, waves of golden glow rippling outward through the vault.",
  "the crystal pulses, rings of golden light ripple outward", ("crystal", "Child of the falling sky. I will wake only for one who gives what she holds most dear."))
P("s8", "close", "eye_level", "vault", ["rook"], "Rook close-up, golden light reflected on his face, wary and puzzled.",
  "he glances from the crystal to Mira, speaking", ("rook", "What does it want?"))
P("s8", "medium", "eye_level", "vault", ["mira"], "Mira looking down at the brass compass pendant in her hands, golden light on it.",
  "she lifts the compass, her thumb tracing its edge, eyes shining")
P("s8", "medium", "eye_level", "flashback", ["mira"], "A soft-focus memory: a tall man in a flight coat lifting a laughing small copper-haired girl onto his shoulders on the sky dock at golden hour.",
  "the man lifts the little girl high, she laughs, warm light flares, the image softens and fades")
P("s8", "close", "eye_level", "vault", ["mira"], "Mira close-up, tears gathering, whispering to the compass.",
  "a tear rolls down her cheek as she whispers", ("mira", "Dad's compass."))
P("s8", "close", "eye_level", "vault", ["rook"], "Rook close-up, serious and concerned, golden light on his face.",
  "he steps toward her, speaking urgently and gently", ("rook", "Mira, don't. It's the last thing you have of him."))
P("s8", "close", "eye_level", "vault", ["mira"], "Mira close-up, a tear on her cheek and a brave smile, golden light.",
  "she wipes the tear and smiles bravely, speaking", ("mira", "It's only a compass. Everyone I love is on that island. People matter more than things."))
P("s8", "extreme_close", "eye_level", "vault", ["mira"], "Extreme close-up of Mira lifting the compass chain over her head, the brass compass glowing gold.",
  "she lifts the chain over her head, the compass glows brighter")
P("s8", "medium", "eye_level", "vault", ["mira"], "Mira at the carved altar placing the glowing compass into a small socket beneath the crystal, golden light.",
  "she sets the compass in the socket and steps back, whispering", ("mira", "Please. Wake up."))
P("s8", "wide", "eye_level", "vault", ["mira", "rook", "pip", "crystal"], "The Dawn Crystal erupting in blinding golden light, a wave of warm brilliance sweeping across the vault and out through the arch.",
  "the crystal flares, a golden shockwave rolls outward, the whole frame blooms to white-gold")
P("s8", "close", "eye_level", "vault", ["pip"], "Pip's huge blue eyes full of golden light, a tiny awestruck open mouth.",
  "the golden light floods across Pip's wide eyes, ears rising")
P("s8", "close", "eye_level", "vault", ["rook"], "Rook close-up, stunned, a slow astonished smile in the golden light.",
  "the stunned look becomes a slow smile, speaking quietly", ("rook", "You did it."))

# ---------------------------------------------------------------- S9 collapse and escape
scene("s9", "vault", ["mira", "rook", "pip", "guardian"], "The ruins collapse; the Guardian, freed, carries them to the sky.", "urgent, then awe")
P("s9", "wide", "eye_level", "vault", ["mira", "rook"], "The vault shaking violently, cracks racing across the ceiling, golden light spilling through them, dust and rubble falling.",
  "the ceiling cracks and rubble rains down around them while the golden Crystal stays whole and glowing, golden light streaming through the cracks")
P("s9", "medium", "eye_level", "vault", ["rook"], "Rook shielding his head from falling stones, shouting.",
  "stones fall around him, he shouts", ("rook", "The whole place is coming down!"))
P("s9", "wide", "low", "vault", ["guardian", "mira"], "The Guardian rising in the arch, its rune eyes now warm gold instead of cyan, Mira bracing in front of it.",
  "the Guardian looms in the arch, its eyes glowing gold, Mira steps back and braces")
P("s9", "medium", "eye_level", "vault", ["guardian", "mira"], "The Guardian kneeling and opening one giant stone palm toward Mira, Mira staring up in wonder.",
  "the huge hand lowers gently toward her, she stares up and speaks", ("mira", "It's... helping us?"))
P("s9", "wide", "eye_level", "vault", ["guardian", "mira", "rook", "pip"], "Mira, Rook and Pip leaping onto the Guardian's giant palm and the Guardian lifting them toward the crumbling ceiling.",
  "they jump onto the palm, the Guardian rises, stones crashing around them")
P("s9", "wide", "eye_level", "vault", ["guardian", "mira", "rook"], "The Guardian shielding them with its other arm as massive stones crash against it, dust and golden light swirling.",
  "stones hammer its raised arm, it holds firm, dust swirls")
P("s9", "wide", "low", "ruinsky", ["guardian", "mira", "rook"], "The Guardian bursting up through the ruined roof into the open sunrise sky, lifting the three heroes on its palm, a huge golden sun rising.",
  "the Guardian bursts upward through the roof into dazzling sunrise, debris spraying")
P("s9", "wide", "eye_level", "ruinsky", ["guardian"], "The Skyfall Ruins collapsing into golden dust below while the Guardian stands among the rubble, its stone body turning to golden sparks.",
  "the ruins fold into dust, the Guardian's body dissolves into rising golden sparks")
P("s9", "close", "eye_level", "ruinsky", ["mira"], "Mira close-up, tears and a grateful smile, golden sparks drifting past her face.",
  "golden sparks drift past her face, she whispers", ("mira", "Thank you."))

# ---------------------------------------------------------------- S10 return and ending
scene("s10", "isle", ["mira", "rook", "pip", "oren"], "Home: the Lantern relit, a new friend, and the compass returns.", "joyful, emotional, hopeful")
P("s10", "wide", "eye_level", "ruinsky", ["mira", "rook", "pip"], "Mira holding the glowing Dawn Crystal in her arms on a cliff edge above a sea of sunrise clouds, Rook and Pip beside her.",
  "the crystal glows in her arms, sunrise light sweeps across the clouds, wind lifts their hair")
P("s10", "wide", "low", "ruinsky", ["oren"], "A patched-sail sky skiff rising through the sunrise clouds with villagers on deck waving, Grandpa Oren at the bow.",
  "the skiff rises through the clouds, villagers wave, sail billowing")
P("s10", "close", "eye_level", "ruinsky", ["oren"], "Grandpa Oren at the skiff's bow, joyful, tears in his eyes, cupping a hand to shout.",
  "he waves and shouts down across the sky, beaming", ("oren", "Mira! The whole island saw the golden light!"))
P("s10", "medium", "eye_level", "ruinsky", ["oren", "mira"], "Mira running to Grandpa Oren on the skiff deck and hugging him tightly, his arms around her.",
  "she runs into his arms, he lifts her slightly in a hug, speaking", ("oren", "You brought the dawn home."))
P("s10", "wide", "high", "lamp", ["mira", "oren"], "Mira lifting the Dawn Crystal into the Great Lantern's stone cradle, the whole island glowing gold, lanterns lighting up one by one, villagers cheering.",
  "the crystal slots in, golden light blooms across the island, lanterns ignite, the island rises gently")
P("s10", "close", "eye_level", "lamp", ["mira"], "Mira close-up, tearful and radiant, golden light on her face, looking down at the village.",
  "she laughs through tears, looking down, speaking", ("mira", "Look, Grandpa. We're floating again."))
P("s10", "medium", "eye_level", "lamp", ["oren", "rook"], "Rook standing apart at the island's edge with his hands in his coat pockets, Grandpa Oren walking up to him with a kind smile.",
  "Oren walks up to Rook with a gentle smile, speaking", ("oren", "Young man, there is a spare room on this island."))
P("s10", "close", "eye_level", "lamp", ["mira"], "Mira close-up, grinning warmly.",
  "she grins warmly at Rook, speaking", ("mira", "Rival is a good start. Stay, Rook."))
P("s10", "close", "eye_level", "lamp", ["rook"], "Rook close-up, a slow real smile, eyes shining in golden light.",
  "a slow smile spreads on his face, he speaks softly", ("rook", "Fine. But I'm winning the next race."))
P("s10", "medium", "eye_level", "lamp", ["oren"], "Grandpa Oren placing the brass compass into Mira's open palm, warm lantern glow.",
  "he lays the compass in her palm and closes her fingers around it, speaking", ("oren", "The Dawn gave it back. Look at the needle."))
P("s10", "extreme_close", "eye_level", "lamp", ["mira"], "Extreme close-up of the brass compass in Mira's palm, the needle swinging and settling pointing straight up at her friends.",
  "the needle spins, slows and settles pointing up toward them, glowing warmly")
P("s10", "close", "eye_level", "lamp", ["mira"], "Mira close-up looking at the compass, then up, a happy tearful smile.",
  "she looks up from the compass to her friends, smiling, speaking softly", ("mira", "It points to home. It always did."))
P("s10", "wide", "low", "sky", ["mira", "rook", "pip", "oren"], "Mira and Rook racing their flying machines again into the golden sunrise side by side, Lantern Isle glowing far below.",
  "the two flying machines streak toward the sun, Pip's ears streaming, the glowing island shrinking below")
P("s10", "wide", "eye_level", "sky", [], "A breathtaking wide landscape of golden sunrise over the floating islands of the Drift, glowing clouds, waterfalls and, very small in the distance, two tiny flying machines flying toward the sun.",
  "the camera slowly rises over the glowing islands as the two tiny flying machines shrink into sparks in the sun")

# ---- post-processing (generic rules, applied to every shot)
ONLY = {"p109": [], "p068": ["rook"]}
NAMES = {"mira": "Mira", "pip": "Pip", "rook": "Rook", "oren": "Oren", "guardian": "Guardian", "crystal": "Crystal"}
for p in PANELS:
    if p.id in ONLY:  # shots drawn better with an explicit cast (a flashback has no present-day Mira; Pip drawn twice when also on Rook's head)
        p.character_ids = ONLY[p.id]
        continue
    for cid, nm in NAMES.items():  # whoever the description names is in the frame (an unlisted name is drawn as a stranger)
        if nm in p.action and cid not in p.character_ids and len(p.character_ids) < 3:
            p.character_ids.append(cid)
    if p.scene_id == "s9":  # after the crystal wakes the Guardian's eyes are gold
        p.character_ids = ["guardian_gold" if c == "guardian" else c for c in p.character_ids]
    if p.scene_id == "s10" and p.location_id == "lamp":  # and the Great Lantern glows gold once the Dawn Crystal is set
        p.location_id = "lamp_gold"

bible = Bible(
    premise=Premise(title="The Dawn Gate", genre="anime_adventure",
                    logline="A reckless teenage glider pilot races a proud rival through a storm to the Dawn Gate, where the crystal that can save her sinking home asks for her father's compass.",
                    tone="adventurous, funny, thrilling and heartfelt", setting="the Drift, an archipelago of floating islands held aloft by lantern crystals"),
    characters=CHARS, locations=LOCS,
    rules=["Pip never speaks; it only squeaks", "Rook's goggles are silver; Mira's goggles are on her forehead",
           "The Guardian's eyes are cyan until the crystal wakes, then gold",
           "Time of day: golden afternoon, sunset, storm night, blue pre-dawn, sunrise"])
story = OriginalStory(bible=bible, scenes=SCENES, panels=PANELS)

if __name__ == "__main__":
    ws = ROOT / "output" / "Original_Stories" / SLUG
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "story.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")
    spoken = sum(len(p.dialogue[0].text) for p in PANELS if p.dialogue)
    print(f"{len(PANELS)} panels, {len(SCENES)} scenes, {sum(1 for p in PANELS if p.dialogue)} spoken, {spoken} chars of dialogue -> {ws}")
