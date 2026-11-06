"""Builds a complete 5-minute Vox-style animation video and image asset pipeline.

Exercising all 5 Image Quality Architecture milestones:
- Phase 1 & 2: Dynamic 1-MP framing, explicit kinematic bindings, margin directives.
- Phase 3 & 4: Inpainting repair & ControlNet pipelines.
- Phase 5: Orthographic character turnarounds, neural alpha matting, and multi-plane layer decomposition.
- Video: 40 panels, 1080p video with Kokoro TTS narration, Ken Burns motion, subtitles, and music.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from PIL import Image

# Ensure repository root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene
from engine.original import shotspec as ss
from engine.original import art
from engine.original import rigging as rig
from engine.original import video
from engine.original import pages


def make_vox_story() -> OriginalStory:
    premise = Premise(
        title="Why Is Almost Every Pencil Yellow?",
        genre="vox",
        logline="A witty investigation into how a 19th-century Austro-Hungarian marketing stunt and a Siberian graphite discovery turned yellow into the universal color of writing.",
        tone="fast-paced, witty, deadpan humorous, energetic, Vox-style visual documentary explainer",
        setting="Vox animation studio, 1889 Paris World Fair, Siberian mountain mines, and Victorian drafting ateliers",
    )

    characters = [
        Character(
            id="alex",
            name="Alex Chen",
            role="protagonist",
            age_group="adult",
            gender="male",
            look="28-year-old Taiwanese-American host, consistent character face: clean-shaven sharp angular jawline, short neat straight jet-black side-parted hair with clean side fade, iconic thin round black wireframe spectacles, dark brown almond-shaped eyes, expressive black eyebrows, friendly mouth, wearing an iconic royal-blue ribbed crewneck sweater with pushed-up cuffs, charcoal trousers. Identical character design and face in every panel",
            personality="curious, witty, deadpan, animated host",
        ),
        Character(
            id="franz",
            name="Franz Hardtmuth",
            role="other",
            age_group="elder",
            gender="male",
            look="consistent character face: distinguished 62-year-old Austro-Hungarian industrialist, oval face, prominent thick silver-grey handlebar mustache with curled wax tips, silver-grey wavy hair combed back, round gold-rimmed wire spectacles on bridge of nose, warm hazel eyes, wearing a dark brown herringbone tweed waistcoat over white shirt and dark necktie, gold pocket watch chain pinned to vest. Identical character design and face in every panel",
            personality="proud, visionary Austro-Hungarian industrialist",
        ),
    ]

    locations = [
        Location(
            id="studio",
            name="Vox Studio",
            look="clean modern video studio in signature Vox 2D vector graphic style, bold canary yellow accent wall, minimalist dark desk, glowing neon diagram lines, bright studio key lighting",
        ),
        Location(
            id="vienna_workshop",
            name="Vienna Factory 1889",
            look="1889 Vienna drafting atelier in signature Vox 2D vector graphic style, polished dark mahogany desks, brass drafting compasses, blueprints, warm golden lamp glow",
        ),
        Location(
            id="siberian_mine",
            name="Siberian Graphite Mine",
            look="Siberian mountain graphite quarry in signature Vox 2D vector graphic style, snow-covered mountain peaks, deep black graphite rock faces, icy blue sky, winter sun",
        ),
        Location(
            id="paris_expo",
            name="1889 Paris World Fair",
            look="1889 Paris World Fair pavilion in signature Vox 2D vector graphic style, grand Victorian glass and iron pavilion arches, velvet display pedestal, crowd in top hats",
        ),
    ]

    scenes = [
        Scene(id="sc01", location_id="studio", character_ids=["alex"], summary="The Yellow Monopoly: 75% of pencils are yellow.", mood="witty, intriguing"),
        Scene(id="sc02", location_id="vienna_workshop", character_ids=["franz"], summary="When Pencils Were Shady: Paint was used to hide flaws.", mood="historical, revealing"),
        Scene(id="sc03", location_id="siberian_mine", character_ids=["alex"], summary="The Siberian Discovery: Pure graphite found in Eastern Siberia.", mood="epic, adventurous"),
        Scene(id="sc04", location_id="paris_expo", character_ids=["franz"], summary="The Austro-Hungarian Flex: Hardtmuth paints the Koh-i-Noor yellow in Paris.", mood="triumphant, bold"),
        Scene(id="sc05", location_id="studio", character_ids=["alex"], summary="The Chinese Connection: Yellow as imperial royalty.", mood="fascinating, analytical"),
        Scene(id="sc06", location_id="studio", character_ids=["alex"], summary="The American Imitation Wave: Dixon and Faber adopt yellow.", mood="commercial, energetic"),
        Scene(id="sc07", location_id="studio", character_ids=["alex"], summary="The Lasting Legacy: Why yellow pencil remains undefeated.", mood="witty, satisfying resolution"),
    ]

    # 40 Panels structured for ~5 minutes (~300 seconds)
    panel_defs = [
        # Scene 1: The Yellow Monopoly
        ("p001", "sc01", "studio", "full", "eye_level", ["alex"],
         "Take a look at your desk right now. If there's a wooden pencil sitting there, there is a seventy-five percent chance it is bright, unmistakable canary yellow.",
         "Alex stands in the Vox studio beside a giant yellow accent wall, looking curiously at the viewer.",
         {"pose": "standing tall", "expression": "curious, witty", "action": "holding a yellow pencil", "key_visuals": ["canary yellow pencil", "modern studio"]}),

        ("p002", "sc01", "studio", "close", "eye_level", ["alex"],
         "Not blue, not forest green, not bare wood. Just... intensely yellow. But why? How did one very specific color conquer an entire global stationery industry?",
         "Alex in a close-up portrait, holding a classic yellow pencil up to his glasses with a deadpan, questioning gaze.",
         {"pose": "leaning forward", "expression": "deadpan, questioning", "action": "holding a yellow pencil", "key_visuals": ["yellow pencil near face", "round glasses"]}),

        ("p003", "sc01", "studio", "wide", "high", ["alex"],
         "Today, billions of pencils are manufactured every year across the globe, and three out of every four still wear this exact same yellow coat.",
         "Wide studio view with bold graphic charts and floating percentages showing a massive yellow bar dominating the scene.",
         {"pose": "gesturing at chart", "expression": "confident", "action": "pointing at infographic", "key_visuals": ["giant 75% statistic", "yellow bar graph"]}),

        ("p004", "sc01", "studio", "medium", "eye_level", ["alex"],
         "To understand why, we have to travel back to 1889—a time when pencils looked completely different, and writing was surprisingly dangerous.",
         "Alex gestures toward a vintage calendar dial spinning back in time toward the late nineteenth century.",
         {"pose": "standing", "expression": "animated, storytelling", "action": "gesturing at timeline", "key_visuals": ["vintage calendar 1889", "motion blur graphic"]}),

        ("p005", "sc01", "studio", "close", "low", ["alex"],
         "Back then, pencils were messy, brittle sticks of raw graphite that snapped constantly and stained your fingers with black smudge.",
         "Close-up of hands gripping a rough, cracked graphite core crumbling onto a wooden desk with black dust.",
         {"pose": "examining", "expression": "grimacing", "action": "gripping a broken graphite stick", "key_visuals": ["cracked graphite stick", "black smudge on fingertips"]}),

        ("p006", "sc01", "studio", "medium", "eye_level", ["alex"],
         "And more importantly, the companies making them were hiding a dirty little secret behind their paint.",
         "Alex leans conspiratorially against the studio desk, raising one eyebrow with a knowing smile.",
         {"pose": "leaning", "expression": "conspiratorial grin", "action": "whispering", "key_visuals": ["studio desk", "dramatic side lighting"]}),

        # Scene 2: When Pencils Were Shady
        ("p007", "sc02", "vienna_workshop", "medium", "eye_level", ["franz"],
         "In the nineteenth century, most pencil manufacturers painted their pencils dark purple, black, or maroon. But this was not an artistic choice.",
         "Professor Franz stands in an antique drafting atelier, examining a row of dull dark purple pencils with a skeptical frown.",
         {"pose": "standing", "expression": "skeptical frown", "action": "holding a purple pencil", "key_visuals": ["dark purple pencils", "vintage brass calipers"]}),

        ("p008", "sc02", "vienna_workshop", "close", "high", ["franz"],
         "Paint was used to conceal flaws. Manufacturers used cheap, inferior graphite mixed with low-grade clay, and dark lacquer hid the shoddy wood beneath.",
         "Close-up of a cut-open pencil revealing air bubbles and rough grey sludge inside knotty, splintered wood.",
         {"pose": "inspecting", "expression": "disapproving", "action": "pointing at cross section", "key_visuals": ["splintered wood core", "air bubbles in cheap lead"]}),

        ("p009", "sc02", "vienna_workshop", "medium", "eye_level", ["franz"],
         "If a pencil was painted, consumers assumed it was second-rate junk. The finest, most expensive pencils were sold entirely unpainted—raw cedar wood only.",
         "Franz holds a pristine, polished natural cedar pencil, proudly demonstrating its grain under a warm brass lamp.",
         {"pose": "holding up", "expression": "proud", "action": "holding unpainted cedar pencil", "key_visuals": ["natural cedar pencil", "warm brass oil lamp"]}),

        ("p010", "sc02", "vienna_workshop", "wide", "low", [],
         "For centuries, the gold standard had come from the famous Borrowdale mine in England, which produced the purest graphite known to humankind.",
         "A grand historic engraving of the Borrowdale English mine, with horse-drawn carts hauling solid blocks of pure graphite.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["Borrowdale mine entrance", "historic engraving style", "stone wagons"]}),

        ("p011", "sc01", "studio", "close", "eye_level", ["alex"],
         "Until suddenly, Borrowdale ran completely dry. And the entire stationery world plunged into panic.",
         "Alex stares at the camera with wide eyes and open mouth, holding up an empty wooden crate marked 'Borrowdale - Depleted'.",
         {"pose": "standing", "expression": "surprised, wide eyes", "action": "holding empty crate", "key_visuals": ["empty wooden crate", "red warning graphic"]}),

        # Scene 3: The Siberian Discovery
        ("p012", "sc03", "siberian_mine", "wide", "low", [],
         "Then, in the rugged mountains of Eastern Siberia, near the border of China, explorers struck black gold. An immense deposit of flawless graphite.",
         "A majestic, snow-covered Siberian mountain cliff glowing in crisp morning sunlight, revealing deep lustrous black graphite seams.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["snowy Siberian peaks", "glistening black graphite seam", "icy blue sky"]}),

        ("p013", "sc03", "siberian_mine", "medium", "eye_level", [],
         "It was exceptionally smooth, dark, and virtually free of impurities. It was, without question, the finest pencil material on Earth.",
         "Sturdy Siberian miners in heavy fur coats carefully hoisting a gleaming block of solid graphite from the quarry floor.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["miners in fur coats", "gleaming graphite block", "wooden mining crane"]}),

        ("p014", "sc01", "studio", "medium", "eye_level", ["alex"],
         "There was just one catch: getting graphite from Siberia to European factories required a brutal, four-thousand-mile trek across frozen wilderness.",
         "Alex traces a glowing dotted line across a giant vintage map of Eurasia spanning from Irkutsk all the way to Vienna.",
         {"pose": "standing", "expression": "serious, focused", "action": "reaching out to map", "key_visuals": ["Eurasian map with glowing route", "four thousand miles marker"]}),

        ("p015", "sc03", "siberian_mine", "wide", "eye_level", [],
         "Sleds, river barges, and camel caravans hauled the precious mineral across Asia, making Siberian graphite as rare and costly as luxury silk.",
         "A hardy caravan of heavy sleds and pack animals traversing a frozen Siberian river plain under pale winter sun.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["winter caravan on frozen river", "heavy wooden cargo sleds", "dramatic snow plains"]}),

        ("p016", "sc02", "vienna_workshop", "full", "low", ["franz"],
         "And one ambitious Austrian manufacturer saw an opportunity to change pencil history forever.",
         "Franz Hardtmuth stands authoritatively at his grand drafting table in Vienna, unrolling industrial plans with intense determination.",
         {"pose": "standing tall", "expression": "determined, serious", "action": "unrolling blueprints", "key_visuals": ["grand mahogany desk", "intricate pencil schematics"]}),

        # Scene 4: The Austro-Hungarian Flex
        ("p017", "sc02", "vienna_workshop", "medium", "eye_level", ["franz"],
         "Meet Franz von Hardtmuth, owner of the Austrian company Koh-i-Noor Hardtmuth, named after the famous diamond in the British Crown Jewels.",
         "Franz proudly adjusts his pocket watch chain, standing beside a gilded Koh-i-Noor diamond trademark plaque.",
         {"pose": "standing", "expression": "dignified smile", "action": "adjusting pocket watch", "key_visuals": ["Koh-i-Noor diamond plaque", "tailored tweed waistcoat"]}),

        ("p018", "sc02", "vienna_workshop", "close", "eye_level", ["franz"],
         "Franz acquired exclusive rights to the Siberian graphite. He developed a proprietary method to bake graphite and clay into seventeen distinct hardness grades.",
         "Franz carefully tests seventeen perfectly calibrated pencil leads arranged from 9H to 9B on textured drawing paper.",
         {"pose": "sitting", "expression": "meticulous, focused", "action": "writing on parchment", "key_visuals": ["seventeen graduated pencil leads", "calligraphy sample"]}),

        ("p019", "sc02", "vienna_workshop", "close", "low", ["franz"],
         "He called his creation the Koh-i-Noor 1500. It was smooth, durable, and luxurious. But he needed a visual flex to prove it was superior.",
         "A dramatic macro hero shot of a gleaming hexagonal yellow pencil resting on rich dark velvet, its polished finish catching the light.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["Koh-i-Noor 1500 pencil", "rich crimson velvet", "golden stamped lettering"]}),

        ("p020", "sc04", "paris_expo", "wide", "high", [],
         "So at the 1889 World's Fair in Paris—the very same expo that unveiled the Eiffel Tower—Franz unveiled something shocking.",
         "A breathtaking wide panoramic view of the 1889 Paris Universal Exposition pavilion with the newly built Eiffel Tower rising in the background.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["Eiffel Tower under construction", "grand glass exhibition hall", "Victorian crowds"]}),

        ("p021", "sc04", "paris_expo", "medium", "eye_level", ["franz"],
         "He broke the sacred industry taboo: he painted his premium pencil. And he painted it vibrant, dazzling yellow.",
         "Franz stands beside a velvet display pedestal in Paris, proudly presenting the first bright yellow pencil to astonished spectators.",
         {"pose": "standing", "expression": "triumphant smile", "action": "holding a yellow pencil", "key_visuals": ["velvet exhibition pedestal", "first yellow Koh-i-Noor pencil"]}),

        ("p022", "sc01", "studio", "medium", "eye_level", ["alex"],
         "The design world was stunned. Painting a luxury pencil had never been done. But Franz's choice of color was pure marketing genius.",
         "Alex gestures excitedly in the studio, holding up a replica of the 1889 Paris award medal and smiling broadly.",
         {"pose": "standing", "expression": "excited, sparkling eyes", "action": "holding award medal", "key_visuals": ["1889 Paris exhibition medal", "bright yellow studio graphics"]}),

        # Scene 5: The Chinese Connection
        ("p023", "sc01", "studio", "wide", "eye_level", ["alex"],
         "Why yellow? In nineteenth-century Europe, yellow was the symbolic color of the Chinese imperial court, representing royalty, exclusivity, and supreme luxury.",
         "A stylized Vox motion graphic split-screen: on the left, an imperial Chinese golden dragon throne; on the right, the yellow pencil.",
         {"pose": "standing", "expression": "analytical", "action": "gesturing at split screen", "key_visuals": ["imperial Chinese throne graphic", "vibrant yellow visual connection"]}),

        ("p024", "sc01", "studio", "medium", "eye_level", ["alex"],
         "Because the graphite came from Siberia right along the Chinese frontier, painting the pencils yellow was a visual wink to exotic, imperial-grade quality.",
         "Alex points at an animated compass rose connecting Siberia, the Great Wall frontier, and Vienna with glowing golden arrows.",
         {"pose": "standing", "expression": "enthusiastic", "action": "pointing at map", "key_visuals": ["glowing golden arrows", "Siberian-Chinese border line"]}),

        ("p025", "sc01", "studio", "close", "high", ["alex"],
         "Each pencil was stamped with gold leaf lettering, creating an irresistible visual pairing of royal yellow and opulent gold.",
         "Extreme close-up of genuine gold foil lettering being pressed into the yellow lacquer: 'KOH-I-NOOR * HARDTMUTH * 1500'.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["gold leaf stamp process", "crisp yellow lacquered facet", "macro metallic sheen"]}),

        ("p026", "sc02", "vienna_workshop", "medium", "eye_level", [],
         "Almost overnight, the Koh-i-Noor 1500 became the pencil of choice for world-renowned architects, artists, and engineers.",
         "A master Victorian architect in his studio meticulously drafting cathedral blueprints using the yellow Koh-i-Noor pencil.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["architect drafting blueprint", "yellow pencil in hand", "brass set square"]}),

        ("p027", "sc01", "studio", "close", "eye_level", ["alex"],
         "Instead of hiding flaws, yellow had become the international signature of uncompromising perfection.",
         "Alex gives a sly, satisfied smile directly into the lens, twirling a yellow pencil between his fingers with practiced ease.",
         {"pose": "leaning forward", "expression": "serene, gentle smile", "action": "holding a yellow pencil", "key_visuals": ["twirling yellow pencil", "studio backlight"]}),

        # Scene 6: The American Imitation Wave
        ("p028", "sc01", "studio", "wide", "eye_level", ["alex"],
         "Across the Atlantic, American pencil manufacturers watched this Austrian triumph with intense jealousy—and rapid imitation.",
         "Alex stands in front of a giant retro illustration of the New York harbor skyline circa 1900 with smoke stacks and steamships.",
         {"pose": "standing", "expression": "witty, energetic", "action": "gesturing across frame", "key_visuals": ["1900 New York harbor skyline", "industrial American steamships"]}),

        ("p029", "sc01", "studio", "medium", "eye_level", ["alex"],
         "Companies like Eberhard Faber and Dixon Ticonderoga realized customers were actively demanding yellow pencils, associating the color with premium writing.",
         "Vintage magazine advertisements showing elegant hands holding yellow pencils with bold slogans: 'The American Standard'.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["vintage Americana advertisements", "golden yellow pencil illustrations"]}),

        ("p030", "sc01", "studio", "close", "high", ["alex"],
         "Eberhard Faber released the Mongol pencil—painted bright yellow. Dixon followed suit with their now-famous yellow Ticonderoga.",
         "A crisp flat-lay photograph of vintage yellow pencil boxes: the Faber Mongol and the green-and-yellow Dixon Ticonderoga No. 2.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["vintage pencil boxes", "Dixon Ticonderoga No. 2", "green ferrule details"]}),

        ("p031", "sc01", "studio", "medium", "eye_level", ["alex"],
         "Soon, every brand in America was dipping their pencils in yellow lacquer, whether their graphite came from Siberia or a local backyard pit.",
         "Alex standing next to a humorous conveyor belt dipping hundreds of plain wooden pencils into bright yellow paint vats.",
         {"pose": "standing", "expression": "laughing, open mouth", "action": "pointing at conveyor belt", "key_visuals": ["paint dipping conveyor belt", "splashes of yellow paint"]}),

        ("p032", "sc01", "studio", "close", "eye_level", ["alex"],
         "By the mid-twentieth century, yellow was no longer a bold statement. It had become the default definition of what a pencil was supposed to look like.",
         "A beautiful macro close-up of a sharpener carving long curly ribbons of yellow wood and fragrant cedar shavings.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["spiral yellow wood shavings", "sharp graphite point", "hand crank sharpener"]}),

        ("p033", "sc01", "studio", "wide", "high", [],
         "Standardized testing, public school classrooms, and government offices ordered yellow pencils by the hundreds of millions.",
         "A classic 1950s classroom with neat rows of wooden desks, each holding a crisp yellow No. 2 pencil next to a Scantron test sheet.",
         {"pose": "", "expression": "", "action": "", "key_visuals": ["vintage classroom desks", "Scantron test sheet", "tidy rows of yellow pencils"]}),

        # Scene 7: The Lasting Legacy
        ("p034", "sc01", "studio", "close", "eye_level", ["alex"],
         "Today, we live in a world of touchscreens, digital styluses, and predictive text algorithms.",
         "Alex holds a modern sleek tablet in one hand and an ordinary yellow pencil in the other, weighing them side by side.",
         {"pose": "standing", "expression": "thoughtful", "action": "holding tablet and pencil", "key_visuals": ["digital glass tablet", "wooden yellow pencil"]}),

        ("p035", "sc01", "studio", "medium", "eye_level", ["alex"],
         "Yet the basic design of the hexagonal yellow cedar pencil with its green metal ferrule and pink eraser has barely changed in over a century.",
         "A studio beauty shot: Alex examines the iconic pink eraser and knurled brass ferrule with a look of genuine appreciation.",
         {"pose": "examining", "expression": "calm, relaxed", "action": "holding a yellow pencil", "key_visuals": ["knurled brass ferrule", "classic pink rubber eraser"]}),

        ("p036", "sc01", "studio", "wide", "eye_level", ["alex"],
         "Modern manufacturers have tried neon green, matte black, metallic pink, and raw wood. But yellow still accounts for three out of four sales.",
         "A colorful fan of novelty pencils in every neon and metallic shade, with one classic yellow pencil standing proudly at the center.",
         {"pose": "gesturing", "expression": "amused smile", "action": "pointing at pencil array", "key_visuals": ["colorful rainbow of pencils", "yellow pencil dominant in center"]}),

        ("p037", "sc01", "studio", "medium", "eye_level", ["alex"],
         "There is also a practical bonus: yellow is one of the most visible colors on the human visual spectrum, making it easy to spot on cluttered desks.",
         "Alex gestures at a chaotic, papers-strewn studio drafting table where the bright yellow pencil instantly pops into focus.",
         {"pose": "pointing", "expression": "energetic", "action": "pointing at messy desk", "key_visuals": ["cluttered blueprint desk", "high visibility yellow pencil"]}),

        ("p038", "sc01", "studio", "full", "low", ["alex"],
         "What began as an Austrian marketing scheme to brag about Siberian rocks turned into one of the most durable visual icons in human history.",
         "Alex stands in full-body heroic framing in the center of the Vox studio, bathed in warm cinematic studio lights and yellow graphics.",
         {"pose": "standing tall", "expression": "determined, serious", "action": "holding an oversized yellow pencil", "key_visuals": ["full body host framing", "dramatic studio rim light"]}),

        ("p039", "sc01", "studio", "close", "eye_level", ["alex"],
         "So the next time you pick up a yellow pencil, remember: you're holding a piece of imperial Chinese symbolism, Siberian exploration, and nineteenth-century marketing brilliance.",
         "Alex holds the sharp yellow pencil tip toward the camera, smiling warmly with intelligent, sparkling eyes.",
         {"pose": "holding up", "expression": "excited, sparkling eyes", "action": "holding a yellow pencil", "key_visuals": ["pencil point toward camera", "warm golden backlight"]}),

        ("p040", "sc01", "studio", "wide", "eye_level", ["alex"],
         "A simple yellow stick that conquered the world. Thanks for watching.",
         "The camera slowly pulls back across the sleek Vox studio as the yellow graphic logo resolves onto the center screen.",
         {"pose": "waving", "expression": "gentle smile", "action": "waving hello", "key_visuals": ["Vox logo graphic", "studio wide conclusion shot"]}),
    ]

    panels = []
    for pid, sc_id, loc_id, shot, angle, char_ids, caption, action, d_extra in panel_defs:
        # Build structured ShotSpec for each panel to drive Phase 2 compiler
        chars_spec = []
        for cid in char_ids:
            chars_spec.append(
                ss.CharPose(
                    id=cid,
                    side="center",
                    pose=d_extra.get("pose", "standing"),
                    expression=d_extra.get("expression", "calm"),
                    action=d_extra.get("action", ""),
                )
            )

        spec = ss.ShotSpec(
            shot=shot,
            camera=angle,
            characters=chars_spec,
            setting=locations[0].look if loc_id == "studio" else next(l.look for l in locations if l.id == loc_id),
            lighting="bright studio lighting, warm yellow accents" if loc_id == "studio" else "cinematic atmospheric lighting",
            mood="energetic, witty, documentary",
            key_visuals=d_extra.get("key_visuals", []),
        )

        p = Panel(
            id=pid,
            scene_id=sc_id,
            location_id=loc_id,
            shot=shot,
            angle=angle,
            character_ids=char_ids,
            caption=caption,
            action=action,
            key_visuals=d_extra.get("key_visuals", []),
            director=spec.model_dump(),
        )
        panels.append(p)

    return OriginalStory(
        bible=Bible(premise=premise, characters=characters, locations=locations),
        scenes=scenes,
        panels=panels,
    )


def run_full_pipeline(out_dir: Path | None = None, clean_old_sdxl: bool = True) -> dict:
    start_time = time.time()
    ws = Path(out_dir or (ROOT / "output" / "vox_pencil_explainer")).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    print(f"=== Vox 5-Minute Animation Video Pipeline (Qwen Image 2.1 Default) ===")
    print(f"Workspace: {ws}")

    if clean_old_sdxl:
        print("[0/6] Cleaning legacy SDXL artifacts to enforce pure Qwen Image 2.1 Turbo generation...")
        import shutil
        for sub in ["sheets", "rigging", "panels", "layers", "segments", "pages", "lettered"]:
            d = ws / sub
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        for meta_name in ["art.json", "video_meta.json", "comic.pdf", "review_report.html"]:
            f = ws / meta_name
            if f.exists():
                f.unlink(missing_ok=True)

    # 1. Create and persist story
    story = make_vox_story()
    story_path = ws / "story.json"
    story_path.write_text(story.model_dump_json(indent=2), encoding="utf-8")
    print(f"[1/6] Story created: {len(story.panels)} panels across {len(story.scenes)} scenes.")

    # 2. ComfyRunner initialization (Enforce Qwen Image 2.1 Turbo natural language engine)
    runner = art.ComfyRunner(engine="qwen")
    print(f"[2/6] ComfyRunner initialized: engine={runner.engine}, style={runner.style}")

    # 3. Phase 5: Character Turnaround & Rigging Specification
    print(f"[3/6] Generating Phase 5 Orthographic Character Turnaround for Alex Chen...")
    alex_char = story.bible.characters[0]
    rig_spec = rig.RiggingSpec(pose="a_pose", views=["front", "three_quarter", "side", "back"])
    turnaround = rig.generate_turnaround_sheet(alex_char, story, ws, runner=runner, spec=rig_spec, slice_views=True)
    print(f"      Turnaround generated: {turnaround.image_path}")
    print(f"      Sliced views: {list(turnaround.views.keys())}")

    # 4. Generate All 40 Panel Images (exercising Phase 1-4)
    print(f"[4/6] Generating episode panel images (Phase 1 validation + Phase 2 dynamic framing + Phase 3 inpainting + Phase 4 ControlNet)...")
    art_report = art.generate_art(
        story,
        ws,
        runner,
        provider=None,
        progress=lambda p, m: print(f"      Art: [{int(p*100)}%] {m}"),
    )
    print(f"      Generated {art_report['generated']} panels, reused {art_report['reused']}.")

    # 5. Phase 5: Multi-Plane Layer Decomposition on Hero Panel p001
    print(f"[5/6] Performing Phase 5 Multi-Plane Layer Decomposition on hero panel p001...")
    p001_img = ws / "panels" / "p001.png"
    if p001_img.exists():
        layer_stack = rig.decompose_layers(p001_img, panel_id="p001", runner=runner, isolate_props=True)
        layers_dir = ws / "layers"
        layers_dir.mkdir(exist_ok=True)
        for layer in layer_stack.layers:
            layer_path = layers_dir / f"{layer.name}.png"
            layer_path.write_bytes(layer.image_bytes)
            print(f"      Saved layer '{layer.name}' (z={layer.z_index}, depth={layer.depth_estimate}) -> {layer_path.name}")
        # Parallax plan export
        parallax_plan = layer_stack.to_parallax_plan()
        (layers_dir / "parallax_plan.json").write_text(json.dumps(parallax_plan.model_dump(), indent=2), encoding="utf-8")
        print(f"      Saved ParallaxPlan with {len(parallax_plan.layers)} multi-plane animation tracks.")

    # 6. Audio Narration & 1080p Video Assembly (5 Minutes)
    print(f"[6/6] Voicing with Kokoro TTS, burning captions, mixing music, and encoding 1080p video...")
    music_track = ROOT / "apps" / "desktop" / "public" / "assets" / "demo" / "crystal_resonance_bgm.mp3"
    video_out = video.build_video(
        story,
        ws,
        fps=30.0,
        burn_captions=True,
        music=music_track if music_track.exists() else None,
        name="why_is_almost_every_pencil_yellow_1080p.mp4",
        progress=lambda p, m: print(f"      Video: [{int(p*100)}%] {m}"),
        engine="still",
        fx="warm_cinema",
    )
    total_dur = video_out.get("duration_sec", 0.0)
    print(f"      Video assembly complete: {video_out['video']}")
    print(f"      Duration: {total_dur:.1f}s ({total_dur/60:.2f} minutes)")

    # 7. Comic Pages PDF Export
    print(f"[Bonus] Building 3-panel strip comic book PDF...")
    comic_out = pages.build_pages(story, ws)
    print(f"      Comic book PDF: {comic_out['pdf']} ({comic_out['pages']} pages)")

    elapsed = time.time() - start_time
    print(f"=== Complete! Total elapsed pipeline time: {elapsed:.1f}s ({elapsed/60:.2f} min) ===")
    return {
        "status": "success",
        "video_path": video_out["video"],
        "duration_sec": total_dur,
        "duration_minutes": round(total_dur / 60, 2),
        "panels_generated": len(story.panels),
        "turnaround_sheet": str(turnaround.image_path),
        "comic_pdf": comic_out["pdf"],
        "workspace": str(ws),
    }


if __name__ == "__main__":
    result = run_full_pipeline()
    print(json.dumps(result, indent=2))
