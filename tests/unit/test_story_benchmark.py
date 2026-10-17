from engine.story.benchmark import run_story_benchmark


def test_story_benchmark_mock_provider():
    report = run_story_benchmark(provider_id="mock")
    assert report.total_cases == 10
    assert report.passed_cases == 10
    assert report.mean_character_f1 >= 0.90
    assert report.mean_speaker_accuracy >= 0.90
    assert report.mean_scene_f1 >= 0.90
    assert report.mean_event_f1 >= 0.90
    assert report.mean_unsupported_rate <= 0.05
    assert report.mean_latency_ms < 100.0  # Fast execution
