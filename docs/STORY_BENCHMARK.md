# PanelFlow Studio — Mock / Deterministic Heuristic Benchmark

> **Benchmark Category**: **MOCK / DETERMINISTIC TESTS**  
> **Execution Engine**: Pure Python Spatial Balloon Geometry & Rule-Based In-Memory Engine (Zero Neural Network Inference)  
> **Latency Note**: The 0.09 ms mean latency represents in-memory coordinate math and deterministic template formatting. It is NOT real LLM inference.

**Provider**: `mock_llm` | **Model**: `mock-deterministic-v1`  
**Test Cases**: 10/10 Passed  

## Aggregate Metrics

- **Mean Character Resolution F1**: 100.0%
- **Mean Speaker Attribution Accuracy**: 100.0%
- **Mean Scene Boundary F1**: 100.0%
- **Mean Event Extraction F1**: 100.0%
- **Mean Unsupported Claim Rate**: 0.00% (Target: <= 5.0%)
- **Mean Algorithmic Execution Latency**: 0.09 ms (In-Memory Heuristics)

## Detailed Results by Illustrated Sequence

| Case ID | Title | Char F1 | Speaker Acc | Scene F1 | Event F1 | Unsupported % | Latency (ms) | Status |
|---------|-------|---------|-------------|----------|----------|---------------|--------------|--------|
| `case_01_dialogue` | Two-Character Dialogue Alternation | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.3ms | PASS |
| `case_02_tail_vector` | Spatial Balloon Tail Vector Disambiguation | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_03_enter_room` | Character Enters Room | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_04_location_change` | Location Change Between Panels | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_05_combat` | Combat Sequence with Sound Effects | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_06_silent_panels` | Silent Dramatic Discovery Panels | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.0ms | PASS |
| `case_07_narration_vs_speech` | Narration Caption vs Character Speech | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_08_alias_resolution` | Character Alias and Title Resolution | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_09_flashback` | Flashback Temporal Boundary | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
| `case_10_solitary_speaker` | Solitary Character Speech Attribution | 100.0% | 100.0% | 100.0% | 100.0% | 0.00% | 0.1ms | PASS |
