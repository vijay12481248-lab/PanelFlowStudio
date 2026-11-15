"""r11: 'One Mosquito vs You at 2 AM' - a 60 s movie-trailer parody for tools/reels (stages tts/music/art/clips) and tools/reels/cine.py (assembly).

Extra keys beyond specs.py, all read by cine.py:
  still=True   insert shot: only a picture (no narration, no H3 clip), `dur` seconds, camera moves and sound effects carry it
  cam          camera shots inside the scene: (move, start fraction of the scene, (cx, cy) focus 0-1)
  tr           how the cut INTO the scene looks: cut | flash | whip | zoom | glitch | dip
  grade        colour look: night | alarm | day | warm | cold | calm
  sfx          (name, seconds from scene start); camera punches and transitions add their own sounds
  music        "drop" = the music bed ducks out for this scene (silence before a scare)
"""

CHARS = ("a stick-figure guy with messy black hair, big round dot eyes and blue striped pajamas, and one tiny cartoon mosquito with a round gray body, "
         "long thin legs, two small see-through wings and glowing red eyes")
SHOCK = "face in extreme shock, eyes huge with tiny pupils, mouth wide open, sweat drops flying"

MOSQUITO = dict(
    slug="r11_mosquito_war", cine=True, title="One Mosquito vs Me at 2 AM (Movie Trailer Edition)", hook="2 AM... YOU HEAR IT", voice="marcus_male",
    music=("cinematic movie trailer comedy score, tense low strings pulse and ticking, deep boom hits, rising tension then a playful pizzicato and "
           "marimba breakdown, tongue in cheek epic orchestral percussion"),
    bpm=100, key="D minor", music_sec=72,
    palette="cinematic dramatic lighting, deep navy blue night colors with strong contrast",
    chars=CHARS,
    tags="#shorts #mosquito #relatable #funny #animation #comedy #nightmare #sleepless #moviecomedy",
    scenes=[
        dict(img="wide shot of a dark bedroom at 2 AM, the guy sleeping peacefully on his back in bed with a tiny smile, a big full moon in the window, a tiny mosquito with glowing red eyes hovering right above his ear",
             act="the guy breathes slowly asleep while the tiny mosquito hovers and flies one small circle above his ear",
             line="Two AM. The whole house is asleep. Then... you hear it.",
             cam=[("push", 0.0, (0.5, 0.6)), ("punch", 0.62, (0.62, 0.52))], tr="dip", grade="night", sfx=[("buzz", 0.5)]),
        dict(img=f"the guy lying in bed stiff as a board, {SHOCK}, eyes snapped wide open staring at the ceiling, dark bedroom, moonlight",
             act="his eyes snap open wide, he freezes stiff as a board and a sweat drop slides down his cheek",
             line="That tiny evil sound. Right next to your ear.",
             cam=[("punch", 0.0, (0.5, 0.38)), ("push", 0.35, (0.5, 0.4))], tr="flash", grade="night", sfx=[("buzz", 0.1)]),
        dict(still=True, dur=0.8, img="extreme close-up of one giant wide-open eye with a tiny shaking pupil and red veins, in the pupil's reflection a tiny mosquito, dark background",
             cam=[("shake", 0.0, (0.5, 0.5))], tr="cut", grade="alarm", sfx=[("stinger", 0.0)]),
        dict(img="the guy sitting up in bed with his hand on a wall light switch, bright yellow room light on, he scans the empty room with narrowed suspicious eyes, nothing visible in the air, messy blanket",
             act="he flips the light on, narrows his eyes and turns his head slowly left and right searching the room",
             line="You turn on the light. Nothing. Of course.",
             cam=[("drift", 0.0, (0.35, 0.45)), ("push", 0.5, (0.5, 0.4))], tr="whip", grade="day", sfx=[("click", 0.05)]),
        dict(img=f"the guy lying in bed in the dark slapping his own cheek hard, red hand mark, {SHOCK}, stars and impact lines around his face, the tiny mosquito flying away unharmed in the corner",
             act="he slaps his own cheek hard, his head snaps sideways and the tiny mosquito flies away",
             line="Lights off. It's back. So you slap your own face.",
             cam=[("push", 0.0, (0.5, 0.45)), ("punch", 0.55, (0.5, 0.42))], tr="cut", grade="night", sfx=[("buzz", 0.1), ("slap", 0.62)]),
        dict(img="the guy standing on the bed in pajamas with a red headband like a warrior, holding an electric mosquito racket like a sword, fierce angry eyes, sweat, dramatic low angle, moonlight behind him, blanket tied like a cape",
             act="he raises the racket high with both hands, the blanket cape flutters and his eyes burn with anger",
             line="Now it's personal. You grab the racket. You are a warrior.",
             cam=[("pull", 0.0, (0.5, 0.55)), ("dutch", 0.5, (0.5, 0.45))], tr="whip", grade="warm", sfx=[("riser", 0.0)]),
        dict(img="chaotic bedroom battle, the guy mid-air jumping and swinging the racket, pillows exploding with feathers, a lamp falling and breaking, the tiny mosquito dodging calmly in the center, motion lines",
             act="he jumps and swings the racket wildly, feathers explode and the tiny mosquito dodges calmly",
             line="Ten minutes of war. Lamp destroyed. Pillow destroyed. Mosquito? Untouched.",
             cam=[("shake", 0.0, (0.5, 0.5)), ("punch", 0.7, (0.5, 0.5))], tr="zoom", grade="warm", sfx=[("swoosh", 0.3), ("swoosh", 0.9), ("crash", 2.6)]),
        dict(img="close view of a wall at night, the tiny mosquito standing on the wall with a smug evil smile and one tiny hand waving hello, the guy's face at the left edge with huge shocked eyes and clenched teeth",
             act="the tiny mosquito waves its tiny hand and wiggles while the guy's eyes twitch with anger",
             line="Then it lands on the wall. Looks at you. And smiles.",
             cam=[("push", 0.0, (0.62, 0.5)), ("push", 0.7, (0.7, 0.5))], tr="cut", grade="cold", music="drop", sfx=[("buzz", 0.0), ("ding", 3.4)]),
        dict(still=True, dur=0.9, img="extreme close-up of the tiny mosquito's face with a smug smirk and one raised eyebrow wearing tiny dark sunglasses, red glowing reflection, dark background",
             cam=[("push", 0.0, (0.5, 0.5))], tr="cut", grade="alarm", sfx=[("ding", 0.0)]),
        dict(img="the guy tiptoeing in a dramatic spotlight toward a wall with one hand raised flat high above his head, one foot lifted, eyes narrowed, super serious face, sweat drop, black background around the spotlight",
             act="he tiptoes slowly one step with his raised hand trembling and a sweat drop falls",
             line="Slowly. Quietly. One clean shot. You raise your hand.",
             cam=[("push", 0.0, (0.5, 0.45)), ("dutch", 0.4, (0.5, 0.4))], tr="cut", grade="cold", music="drop", sfx=[("heart", 0.2), ("heart", 1.4), ("heart", 2.5)]),
        dict(still=True, dur=0.7, img="extreme close-up of a flat open palm slamming onto a wall with big bursting impact star lines and one tiny squashed gray dot under the palm, bright white flash",
             cam=[("punchout", 0.0, (0.5, 0.5))], tr="flash", grade="day", sfx=[("slap", 0.0), ("boom", 0.0)]),
        dict(img="the guy standing on the bed with both fists raised in victory, huge proud grin, a pillow worn as a golden crown, confetti, bright warm light, a tiny dead mosquito on the floor",
             act="he pumps both fists in the air, grins, and the pillow crown wobbles on his head",
             line="Got it! Finally! You feel like a king.",
             cam=[("pull", 0.0, (0.5, 0.5)), ("shake", 0.5, (0.5, 0.5))], tr="cut", grade="warm", sfx=[("tada", 0.1)]),
        dict(img="the guy sleeping happily in bed under moonlight with a peaceful smile, a pillow crown on the nightstand, soft blue light, totally calm quiet bedroom",
             act="he breathes slowly with a peaceful smile, his chest rises and falls",
             line="Finally. Peace. You close your eyes.",
             cam=[("push", 0.0, (0.5, 0.55))], tr="dip", grade="calm", music="drop", sfx=[]),
        dict(img=f"dark bedroom, the guy sitting up in bed in terror, {SHOCK}, behind him in the darkness at least eight pairs of glowing red eyes in the shadows, a swarm of tiny mosquitoes, big moon",
             act="the guy's jaw drops in terror while the glowing red eyes in the dark blink",
             line="Then you hear it again. But this time, it brought friends.",
             cam=[("punch", 0.0, (0.5, 0.4)), ("dutch", 0.3, (0.5, 0.45))], tr="glitch", grade="alarm", sfx=[("swarm", 0.0), ("boom", 0.0)]),
        dict(img="bright golden morning, the guy lying on the bed like a zombie with exhausted half-closed eyes and dark circles, his whole body covered in many small red bite dots, messy hair, five fat round mosquitoes sleeping happily on the ceiling lamp with snoring bubbles",
             act="the guy blinks slowly with exhausted eyes and sways while the fat mosquitoes' bellies rise and fall as they snore",
             line="Morning. Fourteen bites. Zero sleep. And the mosquitoes? Sleeping like kings.",
             cam=[("drift", 0.0, (0.5, 0.7)), ("drift", 0.45, (0.5, 0.25))], tr="whip", grade="day", sfx=[("birds", 0.0)]),
        dict(img="close up of the guy staring straight into the camera with a tired deadpan face and dark circles, one tiny mosquito sitting on his shoulder also staring at the camera with the same blank expression, warm morning light",
             act="the guy blinks slowly and the tiny mosquito beside him tilts its head",
             line="How many bites do you have right now? Be honest.",
             cam=[("push", 0.0, (0.5, 0.45)), ("punch", 0.86, (0.5, 0.4))], tr="cut", grade="day", sfx=[("buzz", 3.4)]),
    ])
