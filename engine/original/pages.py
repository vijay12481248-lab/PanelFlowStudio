"""Comic pages: lettered panels stacked three to a page (1600x2400), a cover page, PNG per page and one PDF.

Panels are 16:9-ish landscape images, so a page is a vertical stack of full-width strips (webtoon style) rather than
tall manga cells: cropping landscape art into tall cells cuts off the left/right characters that the two-reference art
workflow places on purpose.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from engine.original.genres import GENRES
from engine.original.lettering import BOLD_FONTS, font, letter_panel, wrap
from engine.original.models import OriginalStory

PAGE_W, PAGE_H = 1600, 2400
MARGIN, GUTTER, PER_PAGE = 40, 30, 3
SLOT_W = PAGE_W - 2 * MARGIN
SLOT_H = (PAGE_H - 2 * MARGIN - (PER_PAGE - 1) * GUTTER) // PER_PAGE
PAPER = (252, 250, 244)


def fit_slot(img: Image.Image) -> Image.Image:
    """Scale to the slot width and centre-crop the height (the strip is 2.05:1, the art about 1.78:1: ~13% trimmed)."""
    w, h = img.size
    scale = SLOT_W / w
    img = img.resize((SLOT_W, round(h * scale)), Image.LANCZOS)
    if img.height >= SLOT_H:
        top = (img.height - SLOT_H) // 2
        return img.crop((0, top, SLOT_W, top + SLOT_H))
    out = Image.new("RGB", (SLOT_W, SLOT_H), "black")  # art shorter than the slot: letterbox rather than stretch
    out.paste(img, (0, (SLOT_H - img.height) // 2))
    return out


def cover_page(story: OriginalStory, hero: Image.Image | None) -> Image.Image:
    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    d = ImageDraw.Draw(page)
    if hero is not None:
        art = hero.convert("RGB")
        scale = PAGE_H * 0.55 / art.height
        art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
        left = (art.width - (PAGE_W - 2 * MARGIN)) // 2
        art = art.crop((max(left, 0), 0, max(left, 0) + PAGE_W - 2 * MARGIN, art.height))
        page.paste(art, (MARGIN, MARGIN))
        d.rectangle((MARGIN, MARGIN, MARGIN + art.width, MARGIN + art.height), outline="black", width=6)
    title_font, sub_font = font(tuple(BOLD_FONTS), 120), font(tuple(BOLD_FONTS), 44)
    y = int(PAGE_H * 0.62)
    for ln in wrap(d, story.bible.premise.title, title_font, PAGE_W - 2 * MARGIN - 60):
        d.text((MARGIN + 30, y), ln, font=title_font, fill=(30, 25, 20))
        y += 140
    y += 30
    for ln in wrap(d, story.bible.premise.logline, sub_font, PAGE_W - 2 * MARGIN - 60):
        d.text((MARGIN + 30, y), ln, font=sub_font, fill=(70, 60, 50))
        y += 58
    d.text((MARGIN + 30, PAGE_H - MARGIN - 70), f"An original {story.bible.premise.genre} story  -  created with AI tools (PanelFlow Studio)",
           font=font(tuple(BOLD_FONTS), 32), fill=(110, 100, 90))
    return page


def build_pages(story: OriginalStory, ws: Path, progress: Callable[[float, str], None] = lambda p, m: None) -> dict:
    """Letters every panel that has an image and writes pages/page_XXX.png and comic.pdf. Missing images are reported."""
    out_dir = ws / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    have = [p for p in story.panels if (ws / "panels" / f"{p.id}.png").exists()]
    missing = [p.id for p in story.panels if p not in have]
    if not have:
        raise ValueError("no panel images found; run the art step first")
    lettered_dir = ws / "lettered"
    lettered_dir.mkdir(exist_ok=True)
    pages: list[Image.Image] = [cover_page(story, Image.open(ws / "panels" / f"{have[0].id}.png"))]
    for start in range(0, len(have), PER_PAGE):
        progress(start / len(have), f"Page {start // PER_PAGE + 2}")
        page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
        d = ImageDraw.Draw(page)
        for slot, p in enumerate(have[start:start + PER_PAGE]):
            lettered, _ = letter_panel(fit_slot(Image.open(ws / "panels" / f"{p.id}.png")), p, story)
            lettered.save(lettered_dir / f"{p.id}.png")
            y = MARGIN + slot * (SLOT_H + GUTTER)
            page.paste(lettered, (MARGIN, y))
            d.rectangle((MARGIN, y, MARGIN + SLOT_W, y + SLOT_H), outline="black", width=5)
        pages.append(page)
    for i, pg in enumerate(pages):
        pg.save(out_dir / f"page_{i:03d}.png")
    pdf = ws / "comic.pdf"
    pages[0].save(pdf, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    return {"pages": len(pages), "pdf": str(pdf), "page_dir": str(out_dir), "missing_panels": missing,
            "style": GENRES[story.bible.premise.genre].art_style}
