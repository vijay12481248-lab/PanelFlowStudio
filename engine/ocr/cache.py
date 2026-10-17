"""
Deterministic OCR Result Cache.
Prevents redundant OCR extraction when the crop image, engine version,
language, or settings have not changed.
"""

import hashlib
import json
from sqlalchemy.orm import Session
from engine.database.models import OCRCacheRecord


def compute_ocr_cache_key(
    crop_sha256: str,
    engine_id: str,
    engine_version: str = "1.0",
    language: str = "en",
    settings: dict | None = None,
) -> tuple[str, str]:
    """
    Computes a deterministic SHA256 cache key.
    Returns (cache_key, settings_hash).
    """
    settings_json = json.dumps(settings or {}, sort_keys=True)
    settings_hash = hashlib.sha256(settings_json.encode("utf-8")).hexdigest()[:16]

    key_material = f"{crop_sha256}:{engine_id}:{engine_version}:{language}:{settings_hash}"
    cache_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()

    return cache_key, settings_hash


def get_cached_ocr(db: Session, cache_key: str) -> OCRCacheRecord | None:
    """Retrieves cached OCR result if available."""
    return db.query(OCRCacheRecord).filter(OCRCacheRecord.cache_key == cache_key).first()


def store_cached_ocr(
    db: Session,
    crop_sha256: str,
    engine_id: str,
    engine_version: str,
    language: str,
    settings: dict | None,
    raw_text: str,
    raw_confidence: float,
    raw_blocks: list,
) -> OCRCacheRecord:
    """Stores OCR result into deterministic cache."""
    cache_key, settings_hash = compute_ocr_cache_key(
        crop_sha256=crop_sha256,
        engine_id=engine_id,
        engine_version=engine_version,
        language=language,
        settings=settings,
    )

    existing = db.query(OCRCacheRecord).filter(OCRCacheRecord.cache_key == cache_key).first()
    if existing:
        return existing

    record = OCRCacheRecord(
        cache_key=cache_key,
        crop_sha256=crop_sha256,
        engine_id=engine_id,
        engine_version=engine_version,
        language=language,
        settings_hash=settings_hash,
        raw_text=raw_text,
        raw_confidence=raw_confidence,
        raw_blocks=raw_blocks,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
