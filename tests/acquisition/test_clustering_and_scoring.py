"""
Tests for image clustering, candidate scoring, and natural numeric sequence resolution.
"""
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.discovery.candidate_clusterer import CandidateClusterer
from engine.acquisition.web.discovery.candidate_scorer import CandidateScorer
from engine.acquisition.web.discovery.sequence_resolver import SequenceResolver, natural_sort_key


def test_candidate_clustering():
    clusterer = CandidateClusterer()

    # 10 large chapter images in /manga/ch1/
    chapter_cands = [
        ImageCandidate(
            url=f"https://cdn.manga.com/ch1/page_{i:02d}.jpg",
            resolved_url=f"https://cdn.manga.com/ch1/page_{i:02d}.jpg",
            dom_order=i,
            natural_width=800,
            natural_height=1200,
        )
        for i in range(1, 11)
    ]

    # 3 small sidebar thumbnails in /covers/
    sidebar_cands = [
        ImageCandidate(
            url=f"https://cdn.manga.com/covers/thumb_{i}.jpg",
            resolved_url=f"https://cdn.manga.com/covers/thumb_{i}.jpg",
            dom_order=20 + i,
            natural_width=80,
            natural_height=100,
        )
        for i in range(1, 4)
    ]

    # 2 avatars
    avatar_cands = [
        ImageCandidate(
            url=f"https://cdn.manga.com/avatars/user_{i}.png",
            resolved_url=f"https://cdn.manga.com/avatars/user_{i}.png",
            dom_order=30 + i,
            natural_width=32,
            natural_height=32,
        )
        for i in range(1, 3)
    ]

    all_cands = chapter_cands + sidebar_cands + avatar_cands
    clusters = clusterer.cluster_candidates(all_cands)

    assert len(clusters) == 3
    # Dominant cluster must be the chapter cluster
    dominant = clusters[0]
    assert len(dominant.candidates) == 10
    assert dominant.cluster_score > clusters[1].cluster_score
    assert dominant.common_path_prefix.endswith("ch1")


def test_candidate_scorer():
    scorer = CandidateScorer()

    good_cand = ImageCandidate(
        url="https://cdn.example.com/chapter-1/page_01.jpg",
        resolved_url="https://cdn.example.com/chapter-1/page_01.jpg",
        natural_width=800,
        natural_height=1200,
    )
    score_good = scorer.score_candidate(good_cand, in_reader_container=True)
    assert score_good >= 0.80

    bad_cand = ImageCandidate(
        url="https://cdn.example.com/static/ad_banner_icon.png",
        resolved_url="https://cdn.example.com/static/ad_banner_icon.png",
        natural_width=32,
        natural_height=32,
    )
    score_bad = scorer.score_candidate(bad_cand, in_reader_container=False)
    assert score_bad <= 0.30


def test_natural_sorting_order():
    resolver = SequenceResolver()

    # Out of order with filenames 1, 2, 10
    c10 = ImageCandidate(url="http://example.com/page_10.jpg", resolved_url="http://example.com/page_10.jpg", dom_order=1)
    c1 = ImageCandidate(url="http://example.com/page_1.jpg", resolved_url="http://example.com/page_1.jpg", dom_order=2)
    c2 = ImageCandidate(url="http://example.com/page_2.jpg", resolved_url="http://example.com/page_2.jpg", dom_order=3)

    pages = resolver.resolve_sequence([c10, c1, c2])

    assert len(pages) == 3
    # Check natural sequence: page_1, page_2, page_10 (NOT page_1, page_10, page_2)
    assert "page_1.jpg" in pages[0].source_url
    assert "page_2.jpg" in pages[1].source_url
    assert "page_10.jpg" in pages[2].source_url
    assert pages[0].sequence == 1
    assert pages[1].sequence == 2
    assert pages[2].sequence == 3
