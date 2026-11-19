"""r16: 'Who Stole My Lunch' - the test build for the narrated twist/karma Short chosen from the audience research (docs/AUDIENCE_INTEL.md).
Original premise, anime cel-shaded style (r17; r16 was the stickman doodle version). Hook -> plan -> the thief strikes -> karma -> twist (it was the boss) + comment bait.
Registered by tools/reels/run_lunch.py so tools/reels/specs.py (other work in progress) is not touched."""
from specs import COMEDY

HERO = "a tall adult anime man in his late twenties with spiky black hair, a lean adult face and adult body proportions (not a child), a blue t-shirt and jeans, no beard"
BOSS = "a chubby completely bald anime middle-aged boss in a light green shirt and a darker green tie with a gold watch, no hair, no glasses"

STYLE_ANIME = ("high quality modern anime key visual, cel shaded, clean line art, vibrant saturated colors, soft glow and rim light, expressive characters with big shiny eyes, "
               "cinematic composition, vertical 9:16, no text, no letters, no numbers, no words, no speech bubbles")
CLIP_ANIME = "Keep the same anime cel-shaded look and line art, expressive anime acting with squash and stretch, no text, no new objects appear."

LUNCH = dict(
    style=STYLE_ANIME, clip_style=CLIP_ANIME,
    slug="r17_lunch_anime", title="Who Keeps Eating My Lunch?", hook="WHO STOLE MY LUNCH?", voice="marcus_male", music=COMEDY, bpm=118,
    palette="pale blue office background", chars=f"the hero is {HERO}; the boss is {BOSS}",
    tags="#shorts #funny #office #karma #animation #storytime #comedy",
    scenes=[
        dict(img="stands at an open office fridge looking at an empty lunchbox with crumbs, eyes huge and mouth open in shock, sweat drops, empty shelves",
             act="the hero gasps, his eyes widen and he shakes the empty lunchbox upside down while crumbs fall out",
             line="Someone kept eating my lunch from the office fridge. Every. Single. Day."),
        dict(img="grinning evilly at his desk packing a sandwich with one giant glowing red chili pepper sticking out of it, tiny flames around the chili",
             act="the hero chuckles, tucks the giant red chili into the sandwich and rubs his hands together",
             line="So I packed a sandwich with the hottest chili on Earth."),
        dict(img=f"{BOSS} tiptoeing at the open office fridge on his toes, one finger on his lips, holding the sandwich and taking a huge bite with cheeks full (the boss is the one eating), the spiky-haired adult hero stands far behind in the background, half hidden by a big plant with only his head peeking out, and he is NOT eating",
             act="the boss tiptoes to the fridge, grabs the sandwich and takes a huge happy bite while the hero peeks from behind the plant",
             line="Right on time, a hungry thief tiptoed in and took a huge bite."),
        dict(img=f"{BOSS} with his whole face bright red and steam shooting out of both ears, tongue sticking out, running toward a water cooler, coworkers at desks staring with wide eyes",
             act="the boss's face turns bright red, steam blasts from his ears and he sprints to the water cooler flailing his arms",
             line="Ten seconds later, his whole face turned red and he ran screaming."),
        dict(img=f"{BOSS} (the same boss as before) sitting sadly with a pile of lunch bags in front of him, smiling coworkers cheering around him, the adult hero giving a thumbs up and a wink, bright office, exactly one bald boss in the picture",
             act="the coworkers cheer and clap, the boss slumps and the hero winks and gives a thumbs up",
             line="It was the boss. Now he buys everyone lunch, every day. Your move?"),
    ],
)
