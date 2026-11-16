"""PanelFlow Studio - Word-Level Animated Karaoke Subtitles for Shorts & Reels.

Generates ASS (Advanced SubStation Alpha) subtitle streams with active word highlights,
pop animations, and strict YouTube Shorts / Instagram Reels safe-zone positioning.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("panelflow.reels.subtitles")


@dataclass
class SubtitleWord:
    word: str
    start: float  # seconds
    end: float  # seconds


def format_ass_time(seconds: float) -> str:
    """Format floating point seconds into ASS timestamp H:MM:SS.cs."""
    seconds = max(0.0, float(seconds))
    cs = int(round(seconds * 100.0))
    h = cs // 360000
    m = (cs // 6000) % 60
    s = (cs // 100) % 60
    c = cs % 100
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def chunk_words(words: list[SubtitleWord], max_words: int = 3) -> list[list[SubtitleWord]]:
    """Split word sequence into short, punchy 2-4 word chunks breaking on punctuation."""
    if not words:
        return []

    chunks: list[list[SubtitleWord]] = []
    current: list[SubtitleWord] = []

    for w in words:
        current.append(w)
        text = w.word.strip()
        has_break_punct = text and text[-1] in ".?!,"
        if len(current) >= max_words or (has_break_punct and len(current) >= 2):
            chunks.append(current)
            current = []

    if current:
        if len(current) == 1 and chunks:
            # Avoid single orphan word at the end
            chunks[-1].append(current[0])
        else:
            chunks.append(current)

    return chunks


def build_karaoke_ass(
    words: list[SubtitleWord | dict],
    hook: str = "",
    font_name: str = "Impact",
    font_size: int = 92,
    active_color: str = "&H0000E5FF&",  # Cyan highlight (ASS &HAABBGGRR&)
    primary_color: str = "&H00FFFFFF&",  # Crisp White
    outline_color: str = "&H00000000&",  # Deep Black
    margin_v: int = 430,  # Vertical margin from bottom (Shorts safe zone)
    hook_margin_v: int = 240,  # Vertical margin from top
    output_path: Path | str | None = None,
) -> str:
    """Compile animated word-by-word karaoke ASS subtitle script.
    
    Args:
        words: List of SubtitleWord objects or dicts with keys 'word', 'start', 'end'.
        hook: Optional punchy hook text displayed during first 2.5 seconds.
        font_name: Font name (default: Impact).
        font_size: Font size for dialogue captions.
        active_color: ASS color code for currently spoken word.
        primary_color: ASS color code for inactive words.
        outline_color: ASS color code for outline.
        margin_v: Distance in px from bottom (PlayResY=1920).
        hook_margin_v: Distance in px from top.
        output_path: Optional path to save the .ass file.
    """
    # Normalize words
    parsed_words: list[SubtitleWord] = []
    for item in words:
        if isinstance(item, SubtitleWord):
            parsed_words.append(item)
        elif isinstance(item, dict):
            parsed_words.append(
                SubtitleWord(
                    word=str(item.get("word") or item.get("text") or ""),
                    start=float(item.get("start", 0.0)),
                    end=float(item.get("end", 0.0)),
                )
            )

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        # Style: Cap (Center-bottom dialogue, alignment 2)
        f"Style: Cap,{font_name},{font_size},{primary_color},{primary_color},{outline_color},&H80000000,"
        f"1,0,0,0,100,100,1,0,1,8,2,2,60,60,{margin_v},1\n"
        # Style: Hook (Top hook banner, alignment 8)
        f"Style: Hook,{font_name},{int(font_size * 1.25)},{active_color},{active_color},{outline_color},&H80000000,"
        f"1,0,0,0,100,100,1,0,1,10,3,8,60,60,{hook_margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )

    events: list[str] = []

    # 1. Top Hook banner event (first 2.5 seconds)
    if hook and hook.strip():
        clean_hook = hook.strip().upper()
        events.append(
            f"Dialogue: 2,{format_ass_time(0.20)},{format_ass_time(2.60)},Hook,,0,0,0,,"
            f"{{\\fad(120,200)\\fscx108\\fscy108\\t(0,120,\\fscx100\\fscy100)}}{clean_hook}"
        )

    # 2. Dialogue word chunks with active karaoke pop
    chunks = chunk_words(parsed_words, max_words=3)
    for ch in chunks:
        for idx, active_item in enumerate(ch):
            t_start = active_item.start
            # End when next word starts or active_item ends
            if idx + 1 < len(ch):
                t_end = ch[idx + 1].start
            else:
                t_end = max(active_item.end, t_start + 0.15)

            if t_end <= t_start:
                t_end = t_start + 0.15

            # Build line text where active word has color pop + scale bounce
            line_parts = []
            for other in ch:
                clean_word = re.sub(r"[,\.\?!]", "", other.word).upper()
                if other is active_item:
                    # Pop animation: scale 120% -> settle 100% over 80ms with active color
                    anim = f"{{\\c{active_color}\\fscx120\\fscy120\\t(0,80,\\fscx100\\fscy100)}}{clean_word}{{\\r}}"
                    line_parts.append(anim)
                else:
                    line_parts.append(clean_word)

            dialogue_text = " ".join(line_parts)
            events.append(
                f"Dialogue: 1,{format_ass_time(t_start)},{format_ass_time(t_end)},Cap,,0,0,0,,{dialogue_text}"
            )

    ass_content = header + "\n".join(events) + "\n"

    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ass_content, encoding="utf-8")

    return ass_content


def align_transcript_words(
    audio_path: Path | str | None = None,
    transcript: str = "",
    duration_sec: float | None = None,
) -> list[SubtitleWord]:
    """Extract or align word-level timestamps.
    
    First tries local WhisperStt if audio file exists; otherwise computes
    proportional word duration timings based on character lengths.
    """
    # 1. Attempt local Whisper if audio exists
    if audio_path is not None:
        ap = Path(audio_path)
        if ap.exists() and ap.stat().st_size > 0:
            try:
                from engine.narration.runtime.audio import WhisperStt
                stt = WhisperStt()
                _, words = stt.words(ap)
                if words:
                    return [SubtitleWord(word=w.text, start=w.start, end=w.end) for w in words]
            except Exception as exc:
                logger.info("Local Whisper transcription not active/available, using alignment fallback: %s", exc)

    # 2. Fallback proportional alignment
    if not transcript or not transcript.strip():
        return []

    words_raw = transcript.strip().split()
    if not words_raw:
        return []

    total_dur = duration_sec if duration_sec and duration_sec > 0.5 else max(2.5, len(words_raw) * 0.38)
    lead_pad = 0.15
    tail_pad = 0.20
    available_dur = max(0.5, total_dur - lead_pad - tail_pad)

    # Proportional weight by word character length
    weights = [max(1, len(w)) for w in words_raw]
    total_weight = sum(weights)

    out_words: list[SubtitleWord] = []
    curr_t = lead_pad

    for w, wt in zip(words_raw, weights):
        word_dur = available_dur * (wt / total_weight)
        end_t = curr_t + word_dur
        out_words.append(SubtitleWord(word=w, start=round(curr_t, 3), end=round(end_t, 3)))
        curr_t = end_t

    return out_words
