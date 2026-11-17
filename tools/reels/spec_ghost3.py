"""r15: 'Yuki vs Mochi' - a WORDLESS anime comedy (no narration, no captions): the story is told by pictures, acting, camera, sound effects and music only.
A tiny chibi ghost tries to scare a fat sleepy cat; the cat does not care, then wakes up to hunt the ghost's trailing sheet; the ghost ends up as the cat's blanket.
Everything reads without a word: every beat is one clear visual idea (sneak, inflate, deadpan eye, flail, tail-twitch, huge pupils, pounce, chase, hide, defeat).
Pictures: HiDream (tools/reels/hidream_art.py); clips: MiniMax H3; assembly: tools/reels/cine.py. Scenes have `dur` (no `line`), so cine.py cuts them on the music grid."""

STYLE = ("high quality modern anime key visual, cel shaded, clean line art, vibrant saturated colors, soft glow and rim light, expressive chibi characters with big shiny eyes, "
         "cinematic composition, vertical 9:16, no text, no letters, no numbers, no words, no speech bubbles, no sound effect lettering")
CLIP_STYLE = "Keep the same anime cel-shaded look and line art, expressive anime acting with squash and stretch, no text, no new objects appear."

YUKI = ("a tiny cute chibi ghost girl, a round white sheet body with big sparkling anime eyes, rosy cheeks and a small pink ribbon bow on top, softly glowing")
MOCHI = ("a very fat round sleepy orange tabby cat with half-closed bored green eyes and a white belly")
ROOM = "a cozy Japanese apartment living room at night with blue moonlight through the window, a small sofa, a potted plant, warm lamp glow and city lights outside"

GHOSTCAT = dict(
    slug="r15_yuki_vs_mochi", cine=True, title="Tiny Ghost vs Fat Cat", hook="", voice="marcus_male",
    music=("quirky playful Japanese anime comedy instrumental, pizzicato strings, koto plucks, light taiko and woodblock, sneaky tiptoe groove that "
           "turns into an energetic chase with bright brass stabs, cute and mischievous, instrumental"),
    bpm=120, key="D Minor", music_sec=50,
    palette="cool blue night with warm orange lamp light", chars=f"Yuki is {YUKI}; Mochi is {MOCHI}",
    style=STYLE, clip_style=CLIP_STYLE,
    tags="#shorts #anime #cat #ghost #funny #animation #cute #comedy #nodialogue",
    scenes=[
        dict(img=f"{MOCHI} fast asleep stretched on a sofa with his belly up in {ROOM}, and {YUKI} peeking out from behind the potted plant with sparkling mischievous eyes, rubbing her tiny hands together",
             act="Yuki peeks out from behind the plant rubbing her hands with a mischievous smile while Mochi's round belly slowly rises and falls as he sleeps",
             dur=4.0, cam=[("push", 0.0, (0.5, 0.55)), ("drift", 0.6, (0.6, 0.5))], tr="dip", grade="night", sfx=[("snore", 0.2), ("sparkle", 2.4)]),
        dict(img=f"{YUKI} transformed into a huge terrifying white ghost monster, still a white sheet shape with her pink ribbon bow, glowing yellow eyes and a jagged wide mouth, looming over a small sofa where {MOCHI} sleeps peacefully, giant shadow on the wall, low angle dramatic horror lighting, in {ROOM}",
             act="Yuki inflates into a huge scary ghost with glowing yellow eyes and a giant shadow while Mochi keeps sleeping peacefully",
             dur=3.4, cam=[("shake", 0.0, (0.5, 0.5)), ("push", 0.5, (0.5, 0.45))], tr="whip", grade="alarm", sfx=[("riser", 0.0), ("wail", 0.9)]),
        dict(still=True, dur=1.3, autosfx=False, music="drop",
             img=f"extreme close-up of the cat's face, one green eye half open looking completely bored and unimpressed, flat deadpan expression, soft moonlight, a tiny glowing ghost blurred in the far background",
             cam=[("push", 0.0, (0.5, 0.5))], tr="cut", grade="cold", sfx=[("cricket", 0.0), ("pop", 0.9)]),
        dict(img=f"chaos in {ROOM}: {YUKI} spinning wildly in the air flicking the lamp on and off and throwing sofa cushions with a desperate effort face, cushions flying everywhere, while {MOCHI} calmly licks his paw on the sofa with a cushion landing on his head",
             act="Yuki spins wildly throwing cushions while the lamp flickers and Mochi calmly licks his paw as a cushion lands on his head",
             dur=4.2, cam=[("dutch", 0.0, (0.5, 0.5)), ("shake", 0.55, (0.5, 0.5))], tr="cut", grade="warm", sfx=[("whoosh", 0.2), ("thud", 1.6), ("boing", 3.0)]),
        dict(img=f"{YUKI} flopped flat and exhausted on the floor with swirly spiral eyes and sweat drops, her little sheet tail trailing across the floor, and behind her {MOCHI} sitting up on the sofa slowly turning his head toward the twitching tail with eyes getting wide, in {ROOM}",
             act="Yuki lies exhausted with swirly eyes while her sheet tail twitches and Mochi slowly sits up and turns his head toward the tail with eyes widening",
             dur=4.0, cam=[("pull", 0.0, (0.5, 0.55)), ("push", 0.6, (0.6, 0.55))], tr="cut", grade="cold", sfx=[("sadtrombone", 0.0), ("heart", 3.0)]),
        dict(still=True, dur=1.0, autosfx=False,
             img=f"extreme close-up of the cat's eyes with huge round black dilated pupils filling his eyes and sparkling highlights, intense predator stare, dramatic dark background, anime close-up",
             cam=[("punch", 0.0, (0.5, 0.5))], tr="flash", grade="alarm", sfx=[("stinger", 0.0), ("hiss", 0.1)]),
        dict(img=f"{MOCHI} leaping through the air toward the camera with claws out and mouth open in a dramatic pounce with speed lines, {YUKI} in front of him with a terrified scream face, huge eyes and her sheet flying, in {ROOM}",
             act="Mochi pounces through the air with claws out as Yuki screams in terror with her sheet flying back",
             dur=3.2, cam=[("punchout", 0.0, (0.5, 0.5)), ("shake", 0.4, (0.5, 0.5))], tr="cut", grade="alarm", sfx=[("whoosh", 0.0), ("scream", 0.3), ("meow", 1.2)]),
        dict(img=f"a wide chase through {ROOM}: {YUKI} fleeing in panic zooming across the room with a trail of speed lines and sweat drops, {MOCHI} chasing right behind her with his belly bouncing, a knocked over plant and flying cushions, dynamic anime action composition",
             act="Yuki zooms across the room in panic with Mochi chasing right behind, his belly bouncing, a plant tipping over and cushions flying",
             dur=4.2, cam=[("drift", 0.0, (0.3, 0.5)), ("dutch", 0.5, (0.6, 0.5))], tr="zoom", grade="day", sfx=[("whoosh", 0.0), ("crash", 1.6), ("scream", 2.2), ("boing", 3.4)]),
        dict(img=f"{YUKI} hiding by pretending to be a plain white bedsheet draped over a chair with only two tiny trembling eyes peeking out, and only one cat, {MOCHI}, creeping toward the chair on tiptoe with a suspicious squinting face, tension, warm lamp light, in {ROOM}",
             act="Yuki trembles under the bedsheet with tiny eyes peeking while Mochi creeps closer and sniffs the sheet suspiciously",
             dur=4.2, cam=[("push", 0.0, (0.45, 0.55)), ("dutch", 0.7, (0.5, 0.5))], tr="cut", grade="warm", sfx=[("click", 0.5), ("heart", 1.5), ("gulp", 3.3)]),
        dict(img=f"{MOCHI} curled up sleeping peacefully on top of {YUKI} like she is a pillow, Yuki squashed flat under the fat cat with a deadpan resigned face and one single big tear, a sleepy bubble from Mochi's nose, calm blue moonlight and warm lamp glow in {ROOM}",
             act="Mochi sleeps peacefully on top of squashed Yuki, his belly rising and falling, while Yuki blinks slowly with a single tear rolling down her cheek",
             dur=5.0, cam=[("pull", 0.0, (0.5, 0.55))], tr="dip", grade="calm", sfx=[("purr", 0.0), ("sadtrombone", 1.0), ("pop", 4.2)]),
    ])
