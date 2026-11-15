"""Complete Novel Generation Script.

Uses NovelistAgent and EditorialCriticAgent to write all remaining chapters
outlined in the Story Bible, compiling the complete multi-chapter novel into
a reader-friendly markdown volume.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from engine.creative.agents import NovelistAgent, EditorialCriticAgent
from engine.creative.schema import StoryBible, NovelChapter, ChapterOutline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("write_full_novel")

OUTPUT_DIR = Path(__file__).resolve().parent / "output" / "autonomous_story"


async def main():
    print("=" * 80)
    print("✦ GENERATING THE COMPLETE NOVEL: NINE HEAVENS ECLIPSE ✦")
    print("=" * 80)

    # 1. Load Story Bible
    bible_path = OUTPUT_DIR / "story_bible.json"
    with open(bible_path, "r", encoding="utf-8") as f:
        bible_dict = json.load(f)
    bible = StoryBible(**bible_dict)
    print(f"Loaded Story Bible: '{bible.title}' ({len(bible.chapter_outlines)} chapters outlined)")

    # 2. Load Chapter 1
    ch1_path = OUTPUT_DIR / "chapter_1.json"
    with open(ch1_path, "r", encoding="utf-8") as f:
        ch1_dict = json.load(f)
    chapter_1 = NovelChapter(**ch1_dict)
    print(f"✓ Chapter 1 already on disk: '{chapter_1.title}' ({chapter_1.word_count} words)")

    novelist = NovelistAgent()
    critic = EditorialCriticAgent()

    chapters = [chapter_1]

    # 3. Write Chapter 2 & Chapter 3
    for outline in bible.chapter_outlines[1:]:
        print(f"\n[Writing Chapter {outline.chapter_number}] '{outline.title}'...")
        ch: NovelChapter = await novelist.write_chapter(
            bible=bible,
            outline=outline,
            target_word_count=1000,
        )
        
        # Editorial Critic review
        critique = await critic.critique_and_refine(bible=bible, chapter=ch)
        print(f"  ✓ Critic Score: {critique.score}/10")
        if critique.polished_prose:
            ch.prose = critique.polished_prose

        # Save individual chapter json
        ch_file = OUTPUT_DIR / f"chapter_{outline.chapter_number}.json"
        with open(ch_file, "w", encoding="utf-8") as f:
            f.write(ch.model_dump_json(indent=2))
            
        print(f"  ✓ Saved Chapter {outline.chapter_number} -> {ch_file.name} ({ch.word_count} words)")
        chapters.append(ch)

    # 4. Compile Entire Novel into a Single Markdown Book
    book_file = OUTPUT_DIR / "NINE_HEAVENS_ECLIPSE_COMPLETE_NOVEL.md"
    total_words = sum(c.word_count for c in chapters)
    
    with open(book_file, "w", encoding="utf-8") as f:
        f.write(f"# {bible.title}\n\n")
        f.write(f"> **Logline**: *{bible.logline}*\n\n")
        f.write(f"**Total Chapters**: {len(chapters)} | **Total Word Count**: {total_words} words | **Genre**: Xianxia Action / Dark Fantasy\n\n")
        f.write("---\n\n")
        
        # World Lore Summary
        f.write("## 📜 World Lore & Setting\n\n")
        f.write(f"**World**: {bible.lore.world_name} ({bible.lore.era_or_timeline})\n\n")
        f.write(f"{bible.lore.setting_overview}\n\n")
        f.write("### Immutable Rules of the Realm:\n")
        for r in bible.lore.rules:
            f.write(f"- {r}\n")
        f.write("\n---\n\n")
        
        # Dramatis Personae
        f.write("## 👥 Dramatis Personae\n\n")
        for c in bible.characters:
            f.write(f"### {c.name} ({c.role})\n")
            f.write(f"- **Visual DNA**: `{c.visual_tags}`\n")
            f.write(f"- **Personality**: {c.personality}\n")
            f.write(f"- **Signature Relic**: {c.signature_item}\n\n")
        f.write("---\n\n")
        
        # Full Chapters
        for ch in chapters:
            f.write(f"## Chapter {ch.chapter_number}: {ch.title}\n\n")
            if ch.epigraph:
                f.write(f"> *{ch.epigraph}*\n\n")
            f.write(f"*{ch.summary}*\n\n")
            f.write("---\n\n")
            f.write(f"{ch.prose}\n\n")
            f.write("---\n\n")

    print("\n" + "=" * 80)
    print("🎉 ENTIRE NOVEL COMPLETED & COMPILED!")
    print(f"  • Master Book File: {book_file}")
    print(f"  • Total Chapters: {len(chapters)}")
    print(f"  • Total Word Count: {total_words} words")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
