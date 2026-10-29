import pytest
from bs4 import BeautifulSoup
from engine.acquisition.web.series.models import (
    SeriesChapter,
    CompilationMode,
)
from engine.acquisition.web.series.discovery import (
    parse_chapter_number,
    infer_series_url_and_pattern,
    SeriesTocStrategy,
    ChapterDropdownStrategy,
    UrlPatternProbeStrategy,
)
from engine.acquisition.web.series.grouper import SmartChapterGrouper


def test_parse_chapter_number():
    assert parse_chapter_number("Chapter 927 - Twisted Reality", "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-927/") == 927.0
    assert parse_chapter_number("Ch. 921.5 - Special Extra", "https://site.com/manga/title/ch-921-5/") == 921.5
    assert parse_chapter_number("Episode #042", "https://site.com/ep/042") == 42.0
    assert parse_chapter_number("", "https://site.com/manga/series-title/chapter-1000/") == 1000.0


def test_infer_series_url_and_pattern():
    url = "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-927/"
    series_url, pattern = infer_series_url_and_pattern(url)
    assert series_url == "https://manhuaplus.com/manga/demon-magic-emperor01/"
    assert pattern == "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-{chapter_number}/"


def test_chapter_grouper_individual():
    grouper = SmartChapterGrouper()
    chapters = [
        SeriesChapter(sequence=float(i), title=f"Chapter {i}", url=f"https://site.com/ch-{i}")
        for i in range(1, 6)
    ]
    bundles = grouper.partition_chapters(chapters, "Test Series", CompilationMode.INDIVIDUAL)
    assert len(bundles) == 5
    assert bundles[0].chapters[0].sequence == 1.0
    assert bundles[0].output_filename == "Test_Series_Chapter_1_1080p.mp4"
    assert bundles[4].chapters[0].sequence == 5.0
    assert bundles[4].output_filename == "Test_Series_Chapter_5_1080p.mp4"


def test_chapter_grouper_compiled_25min():
    grouper = SmartChapterGrouper(default_chapter_duration_sec=210.0)  # 3.5 min per chapter
    # 15 chapters * 3.5 min = 52.5 min -> should produce two ~25-minute bundles
    chapters = [
        SeriesChapter(sequence=float(i), title=f"Chapter {i}", url=f"https://site.com/ch-{i}")
        for i in range(921, 936)
    ]
    bundles = grouper.partition_chapters(
        chapters, "Demon Magic Emperor", CompilationMode.COMPILED, target_duration_minutes=25.0
    )
    assert len(bundles) >= 2
    # Check that timestamps start at 00:00
    assert bundles[0].chapter_markers[0]["timestamp_str"] == "00:00"
    assert bundles[0].chapter_markers[0]["chapter_sequence"] == 921.0
    assert "Chapters_921-" in bundles[0].output_filename


def test_chapter_grouper_compiled_60min():
    grouper = SmartChapterGrouper(default_chapter_duration_sec=200.0)
    # 20 chapters * 200s = 4000s (~66.6 min) -> fits in 1-hour cut (with 15% tolerance) or 2 bundles
    chapters = [
        SeriesChapter(sequence=float(i), title=f"Chapter {i}", url=f"https://site.com/ch-{i}")
        for i in range(1, 21)
    ]
    bundles = grouper.partition_chapters(
        chapters, "Epic Manhua", CompilationMode.COMPILED, target_duration_minutes=60.0
    )
    assert len(bundles) >= 1
    assert bundles[0].target_duration_minutes == 60.0


def test_chapter_markers_timestamps():
    grouper = SmartChapterGrouper()
    # 2 chapters with custom known durations
    ch1 = SeriesChapter(sequence=1.0, title="Ch 1", url="https://site.com/1")
    ch2 = SeriesChapter(sequence=2.0, title="Ch 2", url="https://site.com/2")
    known = {1.0: 125.0, 2.0: 150.0}
    bundles = grouper.partition_chapters([ch1, ch2], "Series", CompilationMode.COMPILED, target_duration_minutes=10.0, known_durations=known)
    assert len(bundles) == 1
    markers = bundles[0].chapter_markers
    assert markers[0]["timestamp_str"] == "00:00"
    assert markers[0]["duration_sec"] == 125.0
    assert markers[1]["timestamp_str"] == "02:05"  # 125s = 2 min 5 sec
    assert markers[1]["duration_sec"] == 150.0


@pytest.mark.asyncio
async def test_chapter_dropdown_strategy_mock():
    html = """
    <html>
      <head><title>Demon Magic Emperor - Chapter 10</title></head>
      <body>
        <select class="single-chapter-select">
          <option value="/manga/demon/chapter-1/">Chapter 1 - Awakening</option>
          <option value="/manga/demon/chapter-2/">Chapter 2 - Power</option>
          <option value="/manga/demon/chapter-3/">Chapter 3 - Battle</option>
        </select>
      </body>
    </html>
    """
    strat = ChapterDropdownStrategy()
    assert await strat.can_handle("https://site.com/manga/demon/chapter-10/", html)
    meta = await strat.discover("https://site.com/manga/demon/chapter-10/", html)
    assert meta is not None
    assert meta.total_chapters_detected == 3
    assert meta.chapters[0].sequence == 1.0
    assert meta.chapters[2].sequence == 3.0


@pytest.mark.asyncio
async def test_series_toc_strategy_mock():
    html = """
    <html>
      <head><title>Demon Magic Emperor Manga Online</title></head>
      <body>
        <div class="post-title"><h1>Demon Magic Emperor</h1></div>
        <div class="listing-chapters_wrap">
          <ul class="version-chap">
            <li><a href="https://site.com/manga/demon/chapter-1/">Chapter 1</a></li>
            <li><a href="https://site.com/manga/demon/chapter-2/">Chapter 2</a></li>
            <li><a href="https://site.com/manga/demon/chapter-3/">Chapter 3</a></li>
            <li><a href="https://site.com/manga/other-series/chapter-99/">Other Manga 99</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    strat = SeriesTocStrategy()
    meta = await strat.discover("https://site.com/manga/demon/", html)
    assert meta is not None
    assert meta.title == "Demon Magic Emperor"
    # Notice: 'other-series' link must be filtered out by slug matching!
    assert meta.total_chapters_detected == 3
    assert meta.chapters[0].sequence == 1.0
    assert meta.chapters[2].sequence == 3.0


def test_url_pattern_range_generation():
    pattern = "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-{chapter_number}/"
    chapters = UrlPatternProbeStrategy.generate_range_chapters(pattern, 921.0, 925.0)
    assert len(chapters) == 5
    assert chapters[0].sequence == 921.0
    assert chapters[0].url == "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-921/"
    assert chapters[-1].sequence == 925.0
    assert chapters[-1].url == "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-925/"
