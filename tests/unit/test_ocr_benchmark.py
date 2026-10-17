from pathlib import Path
from engine.ocr.benchmark import compute_cer, compute_wer, run_ocr_benchmark
from engine.ocr.cache import compute_ocr_cache_key, store_cached_ocr, get_cached_ocr
from engine.database.session import SessionLocal, init_db

def test_cer_and_wer_metrics():
    # Identical strings
    assert compute_cer("Hello World", "Hello World") == 0.0
    assert compute_wer("Hello World", "Hello World") == 0.0

    # 1 character error
    # Ref length 5, 1 edit -> 1/5 = 0.20
    assert compute_cer("Heilo", "Hello") == 0.20

    # 1 word error in 4 words -> 1/4 = 0.25
    assert compute_wer("The big blue car", "The fast blue car") == 0.25

    # Case where hypothesis is empty
    assert compute_cer("", "Hello") == 1.0
    assert compute_wer("", "Hello world") == 1.0

def test_ocr_benchmark_suite(tmp_path: Path):
    bench_dir = tmp_path / "ocr_bench"
    report = run_ocr_benchmark(engine_id="mock_ocr", output_dir=bench_dir)

    assert report.total_fixtures >= 3
    assert report.engine_id == "mock_ocr"
    assert report.mean_confidence >= 0.85
    assert len(report.results) == report.total_fixtures

    # Verify Japanese fixture was evaluated
    ja_results = [r for r in report.results if r.language == "ja"]
    assert len(ja_results) == 1
    assert ja_results[0].recognized_text == "待て！ここから先へは行かせない。"
    assert ja_results[0].cer == 0.0

def test_deterministic_ocr_cache(tmp_path: Path):
    init_db()
    db = SessionLocal()
    try:
        crop_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        key1, hash1 = compute_ocr_cache_key(crop_hash, "mock_ocr", "1.0", "en", {"contrast": 1.0})
        key2, hash2 = compute_ocr_cache_key(crop_hash, "mock_ocr", "1.0", "en", {"contrast": 1.0})
        key3, hash3 = compute_ocr_cache_key(crop_hash, "mock_ocr", "1.0", "en", {"contrast": 1.5})

        # Deterministic
        assert key1 == key2
        assert hash1 == hash2
        assert key1 != key3  # Settings change produces different cache key

        # Store in cache
        cached = store_cached_ocr(
            db=db,
            crop_sha256=crop_hash,
            engine_id="mock_ocr",
            engine_version="1.0",
            language="en",
            settings={"contrast": 1.0},
            raw_text="Cached recognized text",
            raw_confidence=0.98,
            raw_blocks=[{"text": "Cached recognized text"}],
        )

        assert cached.cache_key == key1

        # Retrieve
        fetched = get_cached_ocr(db, key1)
        assert fetched is not None
        assert fetched.raw_text == "Cached recognized text"
        assert fetched.raw_confidence == 0.98
    finally:
        db.close()
