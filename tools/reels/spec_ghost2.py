"""r14: 'The Ghost Who Went Viral' v2 - rewritten for jokes after the owner's note on r13 ("not funny enough, same sound effects, same motion again and again").

What changed against r13: (1) it is a joke script with callbacks and a twist (ghosts have no reflection; the scare is mistaken for decoration, then for a playlist;
a bedsheet sponsor; the only thing that finally scares Gerald is the rent), (2) two speakers: a narrator and Mia's own lines (`voice` per scene),
(3) every shot has its own camera move, transition, colour look and sound effects from the wider comedy set in cine.py, and sounds are pitch-varied per use,
(4) comic timing: a silent beat with crickets, a reaction insert, a punchline held on a freeze. Pictures: HiDream; clips: MiniMax H3; assembly: cine.py.
`autosfx: False` switches off the automatic transition whoosh and punch thud in that shot."""
from spec_ghost import CLIP_STYLE, GERALD, MIA, PLACE, STYLE

NOTE = " No microphone, no tripod, no camera, no new objects appear."

GHOST2 = dict(
    slug="r14_ghost_rent", cine=True, title="The Ghost Who Only Feared the Rent", hook="HE HAUNTED 200 YEARS. ZERO REVIEWS.", voice="marcus_male",
    music=("playful spooky comedic instrumental, mischievous pizzicato strings, harpsichord, soft theremin, light bouncy percussion, "
           "haunted house cartoon score that turns triumphant, instrumental"),
    bpm=112, key="A Minor", music_sec=60,
    palette="blue moonlight and warm candle glow", chars=f"{GERALD}; {MIA}",
    style=STYLE, clip_style=CLIP_STYLE + NOTE,
    tags="#shorts #ghost #haunted #funny #animation #comedy #rent #viral #storytime",
    scenes=[
        dict(img=f"{GERALD}, floating alone in a dark grand hall {PLACE}, rubbing his stubby hands together with a mischievous grin, headlights of a car shining through the window across the floor",
             act="Gerald rubs his stubby hands with a mischievous grin and glances at the window as car headlights sweep across the hall",
             line="Gerald has haunted this mansion for two hundred years. Reviews? Zero.",
             cam=[("pull", 0.0, (0.5, 0.55)), ("drift", 0.55, (0.4, 0.5))], tr="dip", grade="night", sfx=[("creak", 0.0), ("wail", 3.4)]),
        dict(img=f"{GERALD} seen from the side, floating beside a large ornate antique mirror hanging on the wall of a dark hall, he is making a goofy scary face with hands raised like claws toward the mirror, the mirror shows a perfectly empty dim hallway with a candle and nobody in it, a small notebook floating next to him",
             act="Gerald raises his hands like claws and makes a goofy scary face at the mirror, then slowly looks confused at the empty reflection",
             line="He practices his scary face in the mirror. Ghosts don't have reflections.",
             cam=[("push", 0.0, (0.5, 0.5)), ("dutch", 0.7, (0.5, 0.5))], tr="cut", grade="cold", sfx=[("pop", 1.6), ("boing", 3.9)]),
        dict(img=f"{MIA} walking into the dark grand hall {PLACE} dragging a suitcase, looking down at her phone, in the background {GERALD} peeks from behind a curtain with sparkling excited eyes",
             act="Mia walks across the hall looking at her phone with headphones on while Gerald peeks from behind the curtain and giggles",
             line="Oh nice! The listing said spooky vibes.", voice="aria_female",
             cam=[("drift", 0.0, (0.35, 0.5)), ("punch", 0.7, (0.6, 0.5))], tr="whip", grade="night", sfx=[("notify", 0.3)]),
        dict(img=f"{GERALD} bursting out with arms spread wide and chains flying and candles flaring {PLACE}, while {MIA} stands calmly in the foreground still looking at her phone with bored half-closed eyes, completely unbothered",
             act="Gerald bursts out with arms wide, chains flying and candles flaring while Mia keeps scrolling her phone completely unbothered",
             line="Aww, cute decoration!", voice="aria_female", autosfx=False,
             cam=[("shake", 0.0, (0.5, 0.5)), ("punchout", 0.6, (0.5, 0.55))], tr="cut", grade="night", sfx=[("stinger", 0.0), ("whoosh", 0.1), ("rimshot", 1.5)]),
        dict(img=f"{MIA} dancing happily with big headphones on and her arms in the air in the dark grand hall {PLACE}, while {GERALD} behind her wails with chains rattling and plates flying, his face exhausted and frustrated",
             act="Mia dances happily with her arms in the air while Gerald behind her wails, shakes his chains and plates fly past",
             line="Ooh, who made this playlist? The bass is insane!", voice="aria_female",
             cam=[("dutch", 0.0, (0.5, 0.5)), ("shake", 0.6, (0.5, 0.5))], tr="zoom", grade="warm", sfx=[("wail", 0.0), ("crash", 1.7), ("boing", 3.3)]),
        dict(still=True, dur=1.6, autosfx=False, music="drop",
             img=f"{GERALD} slumped on the grand staircase of the haunted mansion, deflated and exhausted with sweat drops, a chain wrapped around him and one plate balanced on his head, sad tired eyes, blue moonlight",
             cam=[("pull", 0.0, (0.5, 0.55))], tr="cut", grade="cold", sfx=[("cricket", 0.0), ("sadtrombone", 0.25)]),
        dict(img=f"{MIA} holding up her phone filming {GERALD} with a huge delighted smile and sparkling eyes, a small glowing ring light on her phone, {GERALD} frozen with shocked wide eyes and floating plates around him, warm light",
             act="Mia films Gerald with a delighted smile while Gerald stares at her in shock and plates float around him",
             line="Wait... you're real?! Don't move. Going live!", voice="aria_female",
             cam=[("push", 0.0, (0.5, 0.5)), ("punch", 0.55, (0.45, 0.5))], tr="glitch", grade="warm", sfx=[("pop", 0.2), ("slidewhistle", 1.9)]),
        dict(still=True, dur=1.1, autosfx=False,
             img="a giant glowing smartphone floating in a dark mansion hall surrounded by a swirling cloud of pink hearts, thumbs up icons and sparkling stars, no text, magical light",
             cam=[("shake", 0.0, (0.5, 0.5))], tr="flash", grade="day", sfx=[("notify", 0.0), ("notify", 0.16), ("notify", 0.31), ("ding", 0.46), ("tada", 0.62)]),
        dict(img=f"{GERALD} wearing tiny sunglasses and posing smugly with a thumbs-up next to a tall stack of folded colorful bedsheets, a glowing ring light behind him, colorful party lights, the haunted mansion hall",
             act="Gerald poses smugly with his thumbs up and slowly lowers his sunglasses while sparkles twinkle around the stack of bedsheets",
             line="Ten million followers later, his first sponsor was a bedsheet company.",
             cam=[("drift", 0.0, (0.3, 0.5)), ("pull", 0.6, (0.5, 0.5))], tr="whip", grade="day", sfx=[("tada", 0.2), ("pop", 3.4)]),
        dict(img=f"{MIA} cheerfully holding an extremely long white paper receipt that unrolls across the whole floor and a pen, smiling sweetly, {GERALD} in front of her terrified with huge round eyes and tiny pupils, sweat drops, spooky green light in the mansion hall",
             act="Mia cheerfully holds out the long receipt while Gerald's eyes go huge and he trembles with sweat drops flying",
             line="Great news, Gerald. You're on the lease. Rent is due.", voice="aria_female",
             cam=[("push", 0.0, (0.55, 0.5)), ("dutch", 0.65, (0.5, 0.5))], tr="cut", grade="alarm", sfx=[("heart", 1.3), ("gulp", 3.3)]),
        dict(still=True, autosfx=False, music="drop",
             img=f"extreme close-up of {GERALD} with a terrified scream face, huge white eyes with tiny pupils, wide open mouth, dark background with dramatic green light, horror movie lighting",
             line="Two hundred years of haunting, and the only thing that ever scared Gerald... was the rent.",
             cam=[("push", 0.0, (0.5, 0.5)), ("shake", 0.8, (0.5, 0.45))], tr="dip", grade="alarm", sfx=[("riser", 3.2), ("scratch", 5.0), ("boom", 5.06)]),
        dict(img=f"{GERALD} sitting sheepishly on the front steps of the haunted mansion at dusk hugging a tiny coin purse and sweating, a long line of tourists with suitcases waiting at the gate behind him, blue moonlight and warm glow from the door",
             act="Gerald hugs the tiny coin purse and sweats nervously while the tourists at the gate wave their suitcases",
             line="Would you pay rent to a ghost? Tell me below.",
             cam=[("pull", 0.0, (0.5, 0.55)), ("punch", 0.9, (0.5, 0.5))], tr="cut", grade="warm", sfx=[("tada", 0.1), ("rimshot", 2.8)]),
    ])
