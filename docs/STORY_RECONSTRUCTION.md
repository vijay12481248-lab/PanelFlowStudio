# Bounded story reconstruction

The visual pipeline still observes panels in reading order and reuses its existing vision checkpoints. Chapter reconstruction then processes up to twelve story panels per request, with a 3,072-token output ceiling. Model output uses short integer panel numbers; application code restores real panel IDs and derives contiguous scene ranges.

Sections share a character/location registry and the preceding section summary. Visible cast extraction is required when source observations identify people, so speed cannot be obtained by silently returning an empty character registry. Unsupported identity references remain unassigned and produce continuity review warnings.

Every validated section is checkpointed before the next request. Cache keys include the algorithm version, provider/settings, current registry, compact input, and full original observations including their real IDs. Changing late evidence can reuse earlier sections. Interrupted requests resume at the first uncached section.

Oversized or invalid sections split into smaller requests down to three panels. Split decisions are checkpointed too. Persistent failures in a smallest section stop with the affected panel range; they do not trigger automatic whole-chapter retries. Transient network failures can use the existing job retry mechanism and saved sections. Ollama output-limit responses are detected explicitly, and JSON repairs no longer append the entire failed output to the next prompt.

Progress advances from 80% through 96% as sections are saved, then to 98% for final validation/persistence. Live model telemetry remains available within each section. Cancellation closes a tracked streaming model request as soon as cancellation is observed rather than deliberately waiting for its entire output budget.

## Local verification

```powershell
python -m pytest tests/unit/test_section_reconstruction.py tests/unit/test_model_activity.py tests/unit/test_visual_storytelling.py tests/integration/test_jobs.py -q
python tools/benchmark_story_sections.py "C:\path\to\project-workspace"
```

The benchmark reads saved panel evidence and writes to a new temporary workspace. It does not replace the project's narrative or update the project database. It validates scene coverage and references, records token usage and elapsed time, and verifies a cached second run.

On the saved 48-panel chapter tested with local `qwen3.5:9b`, reconstruction completed in 62.53 seconds with four requests, no retries/splits, five character entries, six scenes, thirteen beats, and fifteen events. The cached second run took 0.046 seconds and made no model requests. Input requests used 1,276–1,912 tokens and responses used 874–1,078 tokens. These timings exclude initial image analysis and are a single local observation, not a runtime guarantee. Structural validation does not replace human review of narrative accuracy.
