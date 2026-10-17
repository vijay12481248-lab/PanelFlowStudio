"""
Deduplication engine for candidate URLs and downloaded image payloads.
"""
from typing import List, Set, Tuple
from engine.acquisition.web.models.image_candidate import ImageCandidate
from engine.acquisition.web.models.chapter_manifest import ChapterPage


class DuplicateDetector:
    def __init__(self):
        self._seen_urls: Set[str] = set()
        self._seen_hashes: Set[str] = set()

    def reset(self):
        self._seen_urls.clear()
        self._seen_hashes.clear()

    def is_duplicate_url(self, url: str) -> bool:
        norm = url.strip().rstrip("/")
        if norm in self._seen_urls:
            return True
        self._seen_urls.add(norm)
        return False

    def is_duplicate_content(self, sha256_hash: str) -> bool:
        if not sha256_hash:
            return False
        if sha256_hash in self._seen_hashes:
            return True
        self._seen_hashes.add(sha256_hash)
        return False

    def filter_candidates(self, candidates: List[ImageCandidate]) -> Tuple[List[ImageCandidate], int]:
        unique: List[ImageCandidate] = []
        dupes_count = 0
        local_urls: Set[str] = set()

        for c in candidates:
            norm = c.resolved_url.strip().rstrip("/")
            if norm in local_urls:
                dupes_count += 1
                continue
            local_urls.add(norm)
            unique.append(c)

        return unique, dupes_count

    def filter_pages(self, pages: List[ChapterPage]) -> Tuple[List[ChapterPage], int]:
        unique: List[ChapterPage] = []
        dupes_count = 0
        local_hashes: Set[str] = set()

        for p in pages:
            if p.sha256 and p.sha256 in local_hashes:
                dupes_count += 1
                continue
            if p.sha256:
                local_hashes.add(p.sha256)
            unique.append(p)

        return unique, dupes_count
