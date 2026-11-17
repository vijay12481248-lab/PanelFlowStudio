"""r13: 'The Ghost Who Went Viral' - a haunted-house comedy for tools/reels (stages tts/music/clips), tools/reels/hidream_art.py (pictures) and
tools/reels/cine.py (assembly). Keys as in spec_mosquito.py, plus: style (the picture style sentence, replaces the doodle STYLE for hidream_art.py)
and clip_style (the sentence that keeps H3 in that look). Concept: spooky + funny + pop culture, so almost anyone enjoys it; the ghost is the
underdog, the twist is positive (the scare fails, the ghost becomes a star), the closing question invites comments."""

STYLE = ("high quality 3D animated feature film still, Pixar-style character design, expressive faces, soft cinematic lighting with rim light, "
         "rich saturated colors, shallow depth of field, vertical 9:16 composition, no text, no letters, no numbers, no words, no logos")
CLIP_STYLE = "Keep the same polished 3D animated film look, soft cinematic lighting, no new objects appear."

GERALD = ("Gerald, a chubby cute white bedsheet ghost with big round black eyes, rosy cheeks, a small blue bow tie and tiny stubby arms, softly glowing")
MIA = ("Mia, a young woman with curly black hair, big headphones around her neck and an orange hoodie")
PLACE = "inside an old Victorian haunted mansion with cobwebs, flickering candles and blue moonlight through tall windows"

GHOST = dict(
    slug="r13_ghost_viral", cine=True, title="The Ghost Who Went Viral", hook="HE HAUNTED 200 YEARS. NOBODY CARED.", voice="marcus_male",
    music=("playful spooky comedic instrumental, mischievous pizzicato strings, harpsichord, soft theremin, light bouncy percussion, "
           "haunted house cartoon score that turns triumphant, instrumental"),
    bpm=112, key="A Minor", music_sec=48,
    palette="blue moonlight and warm candle glow", chars=f"{GERALD}; {MIA}",
    style=STYLE, clip_style=CLIP_STYLE,
    tags="#shorts #ghost #haunted #funny #animation #comedy #spooky #viral #storytime",
    scenes=[
        dict(img=f"{GERALD}, floating alone in a dark grand hall {PLACE}, rubbing his stubby hands together with a mischievous grin, headlights of a car shining through the window across the floor",
             act="Gerald rubs his stubby hands with a mischievous grin and glances at the window as car headlights sweep across the hall",
             line="Gerald has haunted this mansion for two hundred years. Tonight, new tenants arrive.",
             cam=[("push", 0.0, (0.5, 0.55)), ("punch", 0.8, (0.5, 0.5))], tr="dip", grade="night", sfx=[("stinger", 0.0), ("heart", 3.0)]),
        dict(img=f"{MIA} walking into the dark grand hall {PLACE} dragging a suitcase, looking down at her phone, in the background {GERALD} peeks from behind a curtain with sparkling excited eyes",
             act="Mia walks across the hall looking at her phone with headphones on while Gerald peeks from behind the curtain and giggles",
             line="He rehearsed his big scare for weeks. Candles. Chains. Spooky moaning.",
             cam=[("drift", 0.0, (0.35, 0.5)), ("push", 0.5, (0.6, 0.5))], tr="cut", grade="night", sfx=[("click", 0.4)]),
        dict(still=True, dur=0.9, img=f"extreme close-up of {GERALD} with a terrifying scary face, glowing white eyes, huge open mouth, dark background with dramatic green light, horror movie lighting",
             cam=[("punch", 0.0, (0.5, 0.45))], tr="flash", grade="alarm", sfx=[("stinger", 0.0), ("boom", 0.05)]),
        dict(img=f"{GERALD} bursting out with arms spread wide and chains flying and candles flaring {PLACE}, while {MIA} stands calmly in the foreground still looking at her phone with bored half-closed eyes, completely unbothered",
             act="Gerald bursts out with arms wide, chains flying and candles flaring while Mia keeps scrolling her phone completely unbothered",
             line="She didn't even look up. She thought it was a smart home.",
             cam=[("shake", 0.0, (0.5, 0.5)), ("push", 0.5, (0.6, 0.55))], tr="whip", grade="night", sfx=[("whoosh", 0.1), ("crash", 0.5), ("scratch", 2.4)]),
        dict(img=f"{MIA} holding up her phone filming {GERALD} with a huge delighted smile and sparkling eyes, a small glowing ring light on her phone, {GERALD} frozen with shocked wide eyes and floating plates around him, warm light",
             act="Mia films Gerald with a delighted smile while Gerald stares at her in shock and plates float around him",
             line="Then she smiled. Wow, amazing special effects! Let's go live!",
             cam=[("push", 0.0, (0.5, 0.5)), ("punch", 0.85, (0.45, 0.5))], tr="cut", grade="warm", sfx=[("ding", 0.2), ("crowd", 2.4)]),
        dict(still=True, dur=1.0, img=f"a giant glowing smartphone floating in a dark mansion hall surrounded by a swirling cloud of pink hearts, thumbs up icons and sparkling stars, no text, magical light",
             cam=[("push", 0.0, (0.5, 0.5))], tr="flash", grade="day", sfx=[("ding", 0.0), ("ding", 0.25), ("tada", 0.5)]),
        dict(img=f"{GERALD} wearing tiny sunglasses and posing like a famous influencer in front of a glowing ring light, sparkles around him, {MIA} beside him holding a phone and giving a thumbs up, the mansion decorated with colorful party lights",
             act="Gerald poses and winks with sparkles around him while Mia gives a thumbs up beside him",
             line="Ten million followers later, Gerald is the most famous ghost on Earth.",
             cam=[("pull", 0.0, (0.5, 0.5)), ("push", 0.6, (0.5, 0.45))], tr="zoom", grade="day", sfx=[("tada", 0.2), ("crowd", 0.4)]),
        dict(img=f"{GERALD} waving cheerfully at the camera from the open front door of the haunted mansion at night, behind him a long line of excited tourists with suitcases and cameras waiting at the gate in blue moonlight, warm glow from the doorway",
             act="Gerald waves cheerfully at the camera while the long line of tourists waits at the gate and some wave back",
             line="Now there's a waiting list. Would you rent this haunted house?",
             cam=[("pull", 0.0, (0.5, 0.55)), ("punch", 0.88, (0.5, 0.5))], tr="cut", grade="warm", sfx=[("whistle", 3.0)]),
    ])
