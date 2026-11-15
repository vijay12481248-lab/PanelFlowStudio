"""Titles, descriptions, tags and captions for the ten reels -> output/reels/<slug>/PUBLISH.md and _READY_TO_UPLOAD/PUBLISH_ALL.md.

  python tools/reels/publish.py        (also asserts the YouTube limits: title <= 100 chars, tags <= 500 chars total)

Copy is written for the search/browse phrase a real viewer would use, one clear promise per video that the video keeps,
no invented statistics. Hashtags: YouTube shows the first three above the title, so those three are the strongest; Instagram gets 5-8.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from specs import REELS  # noqa: E402

OUT = ROOT / "output" / "reels"
DISCLOSURE = "Tick 'Altered or synthetic content' (YouTube) / 'AI info' label (Instagram): the voice and pictures are AI-generated."
COMMON_TAGS = ["shorts", "youtube shorts", "funny shorts", "relatable", "animation", "stick figure", "comedy", "cartoon"]

COPY = {
    "r01_one_percent": dict(
        yt_title="POV: Your Phone Hits 1% 😭 (We've All Been Here)",
        yt_desc=("Phone at 1% and the charger is nowhere. Tag the friend who lives in a relationship with a wall socket. 🔌\n\n"
                 "Which is you: panic, detective mode, or sitting next to the wall like a loyal dog? Tell me in the comments.\n\n"
                 "New funny relatable animations every week - subscribe so you don't miss the next one."),
        yt_hash="#shorts #relatable #phoneaddiction",
        tags=["phone at 1%", "low battery", "phone battery funny", "charger", "phone addiction", "pov", "relatable humor", "funny animation"],
        ig="POV: your phone just hit 1%. 🔋😭 Tag the person who sits next to the wall socket like a loyal dog.",
        ig_hash="#relatable #phoneaddiction #lowbattery #funnyreels #stickman #animation #comedy #pov",
        pin="Be honest: how long can your phone survive at 1% - 10 minutes or 10 seconds?"),
    "r02_ac_war": dict(
        yt_title="Every Marriage Is Just a War Over the AC Remote 🥶🔥",
        yt_desc=("He wants the room like a fridge. She wants it like a toaster. Midnight remote battles, one burrito, one sweaty potato - and still neither would sleep anywhere else. ❤️\n\n"
                 "Tag your partner (or your AC-war opponent) and tell me: what temperature do you fight for?\n\n"
                 "Subscribe for more funny relationship animations."),
        yt_hash="#shorts #marriage #couplegoals",
        tags=["marriage jokes", "husband wife comedy", "ac remote war", "couple goals", "married life funny", "relationship humor", "husband and wife"],
        ig="Every marriage is just two people fighting over one AC remote. 🥶🔥 Tag your partner.",
        ig_hash="#marriagejokes #husbandwife #couplegoals #relatable #funnyreels #marriedlife #stickman #animation",
        pin="What's your AC war number? I'll start: 18 degrees, no negotiation. 😅"),
    "r03_study_plan": dict(
        yt_title="Study Plan vs Reality 😅 (Every Student Ever)",
        yt_desc=("Plan: study 8 hours straight. Reality: organise the desk, one tiny video, drool on chapter four, meet chapter one at sunrise on exam day. 📚\n\n"
                 "Send this to the friend who 'starts studying tomorrow'. Which hour did YOU give up?\n\n"
                 "Subscribe for more student life animations."),
        yt_hash="#shorts #student #exams",
        tags=["study plan vs reality", "student life", "exam stress", "study motivation funny", "procrastination", "exam preparation", "student memes"],
        ig="Plan: 8 hours of studying. Reality: organise the desk, 'one tiny video', sleep. 📚😅 Send to your study buddy.",
        ig_hash="#studentlife #studymotivation #exams #procrastination #relatable #funnyreels #stickman #animation",
        pin="Which hour of the study plan do you always break? Hour 1 counts too. 😂"),
    "r04_five_minutes": dict(
        yt_title="\"Just 5 More Minutes\" of Scrolling 💀 (3 AM Be Like)",
        yt_desc=("One more video. Okay, one more. Okay, the last one. Now it's 3 AM and you're watching a man restore a rusty knife. 🔪📱\n\n"
                 "Your thumb is a bodybuilder now. Tag someone who needs to put the phone down (it might be you).\n\n"
                 "Subscribe for more relatable phone-addiction humor."),
        yt_hash="#shorts #phoneaddiction #scrolling",
        tags=["phone addiction", "doomscrolling", "scrolling at night", "3am scrolling", "five more minutes", "reels addiction", "night owl funny"],
        ig="Just five more minutes of scrolling... 💀 It's 3 AM and you're watching a man restore a rusty knife.",
        ig_hash="#phoneaddiction #doomscrolling #relatable #3am #funnyreels #nightowl #stickman #animation",
        pin="What's the weirdest video that kept you up past 3 AM? Mine is the rusty knife one."),
    "r05_mom_radar": dict(
        yt_title="Moms Have a Superpower... and Then This Happens ❤️",
        yt_desc=("Open a chips packet quietly - she hears it from three rooms away. Hide your phone under the blanket - the shadow appears. 👀\n\n"
                 "But watch to the end: when you're sick, she stays awake all night. Send this to your mom (or tag her) and say thank you. ❤️\n\n"
                 "Subscribe for funny and heartwarming family animations."),
        yt_hash="#shorts #mom #family",
        tags=["mom superpower", "mom radar", "funny mom", "mothers love", "family comedy", "emotional shorts", "love you mom", "indian mom humor"],
        ig="Moms have one superpower: radar. 👀 (Watch to the end ❤️) Tag your mom.",
        ig_hash="#mom #momlove #familyreels #relatable #wholesome #emotional #stickman #animation",
        pin="What's the one thing your mom always knows before you tell her? 😂❤️"),
    "r06_exam_brain": dict(
        yt_title="My Brain in the Exam Hall 🧠💀 (It Just Left)",
        yt_desc=("Last night I knew everything. In the exam hall my brain packed a suitcase and walked out - leaving only a song from 2012. 🎵\n\n"
                 "Then I walk out and every answer arrives. Thanks, brain. Real helpful.\n\n"
                 "Tag the friend whose brain always leaves during exams. Subscribe for more student humor."),
        yt_hash="#shorts #exam #student",
        tags=["exam hall funny", "brain blank in exam", "exam stress", "student humor", "exam memes", "forgot everything in exam", "school life"],
        ig="Last night: knew everything. Exam hall: brain left the building. 🧠💀 Tag your exam buddy.",
        ig_hash="#examseason #studentlife #relatable #examstress #funnyreels #school #stickman #animation",
        pin="What did your brain choose to remember instead of the answer? 😂"),
    "r07_snooze_mafia": dict(
        yt_title="Alarm 1: Wake Up! Me: LOL 😴 (Wait for the Ending)",
        yt_desc=("Six alarms, one negotiation with myself, one very fast morning - and then the twist at the office door. 😂⏰\n\n"
                 "How many alarms do YOU set? Tell me the number and tag your snooze-button friend.\n\n"
                 "Subscribe for more funny morning-routine animations."),
        yt_hash="#shorts #morning #alarm",
        tags=["alarm clock funny", "snooze button", "waking up in the morning", "monday morning", "office humor", "late for work", "relatable morning"],
        ig="Alarm one: wake up! Me: ha, good joke. ⏰😴 Wait for the ending.",
        ig_hash="#morningroutine #snooze #relatable #officehumor #funnyreels #alarm #stickman #animation",
        pin="How many alarms do you set every morning? Be honest. ⏰"),
    "r08_wifi_down": dict(
        yt_title="When the Wi-Fi Goes Down, the Family Meets Again 😳",
        yt_desc=("The router died. Dad became a bomb squad expert. The family looked at each other: who are you people? Then they talked, laughed and played cards... until the Wi-Fi came back. 📶\n\n"
                 "Call someone you love tonight - or at least put the phone down at dinner. Tag your family group.\n\n"
                 "Subscribe for more relatable and wholesome animations."),
        yt_hash="#shorts #family #wifi",
        tags=["wifi down", "no internet funny", "family time", "phone addiction family", "wholesome", "relatable family", "router fix funny"],
        ig="Wi-Fi went down. The family is in danger. 😳📶 (Then something beautiful happened...)",
        ig_hash="#wifi #family #phoneaddiction #wholesome #relatable #funnyreels #stickman #animation",
        pin="When did your family last talk for an hour with no phones?"),
    "r09_group_project": dict(
        yt_title="Group Project: 4 People, 1 Worker 😤 (Guess Who)",
        yt_desc=("Classmate two: 'I'll do the design. Vibes.' Me: finishing everything at 3 AM. Presentation day: the lazy ones talk about my slides. Teacher: great teamwork! 🙃\n\n"
                 "Comment who the worker in your team was (you know it was you). Tag your group-project crew.\n\n"
                 "Subscribe for more college life humor."),
        yt_hash="#shorts #groupproject #college",
        tags=["group project", "group assignment funny", "college life", "student teamwork", "one person does all the work", "university humor", "student memes"],
        ig="Group project: 4 people, 1 worker. Guess who. 🙃 Tag your group-project crew.",
        ig_hash="#groupproject #collegelife #studentlife #relatable #funnyreels #teamwork #stickman #animation",
        pin="Be honest: were you the worker, or one of the sunglasses? 😎"),
    "r10_dad_love": dict(
        yt_title="My Dad Never Said \"I Love You\"... But Watch This ❤️",
        yt_desc=("He wakes up at five to warm the car so you won't be cold. He says he's not hungry so you can have the last piece. He pretends he doesn't cry at the bus stop. ❤️\n\n"
                 "Some fathers never say I love you - they say: did you eat? Send this to your dad today, or tell him you love him first.\n\n"
                 "Subscribe for more wholesome family animations."),
        yt_hash="#shorts #dad #family",
        tags=["dad love", "fathers love", "dad never says i love you", "emotional shorts", "father and son", "wholesome", "family love", "dad sacrifice"],
        ig="He never said I love you. He says: did you eat? ❤️ Send this to your dad.",
        ig_hash="#dad #fatherlove #family #emotional #wholesome #relatable #stickman #animation",
        pin="What does your dad say instead of 'I love you'? ❤️"),
}


def build(r, c):
    tags = c["tags"] + COMMON_TAGS
    tag_str = ", ".join(tags)
    assert len(c["yt_title"]) <= 100, (r["slug"], len(c["yt_title"]))
    assert len(tag_str) <= 500, (r["slug"], len(tag_str))
    return tag_str, f"""# {r['title']}

**Files:** `{r['slug']}.mp4` · cover: `_READY_TO_UPLOAD/thumbnails/` · on-screen hook: {r['hook']}

## YouTube Shorts
**Title** ({len(c['yt_title'])} chars):
{c['yt_title']}

**Description:**
{c['yt_desc']}

{c['yt_hash']}

**Tags** ({len(tag_str)}/500 chars):
{tag_str}

**Pinned comment:** {c['pin']}

## Instagram Reels
**Caption:**
{c['ig']}

{c['ig_hash']}

**Pinned comment:** {c['pin']}

## Before you post
- {DISCLOSURE}
- Upload as PRIVATE first, watch it once with sound, then publish (project rule: public/scheduled needs your explicit go-ahead).
- Audience: set "not made for kids" or "made for kids" yourself - that declaration is yours.
"""


if __name__ == "__main__":
    allmd = ["# Titles, descriptions, tags - all 10 reels\n"]
    for n, r in enumerate(REELS, 1):
        tag_str, md = build(r, COPY[r["slug"]])
        (OUT / r["slug"] / "PUBLISH.md").write_text(md, encoding="utf-8")
        allmd.append(md.replace("# ", f"# {n}. ", 1))
    (OUT / "_READY_TO_UPLOAD" / "PUBLISH_ALL.md").write_text("\n---\n\n".join(allmd), encoding="utf-8")
    print("wrote", len(REELS), "PUBLISH.md files + PUBLISH_ALL.md")
