import sys
import argparse
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure panelflow root directory is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.story.benchmark import run_story_benchmark


def main():
    parser = argparse.ArgumentParser(description="PanelFlow Studio - Story Understanding & Script Adaptation Benchmark")
    parser.add_argument("--provider", default="mock", help="LLM Provider to benchmark (default: mock)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", default=None, help="Optional output filepath for benchmark report")
    args = parser.parse_args()

    report = run_story_benchmark(provider_id=args.provider)

    if args.json:
        out = json.dumps(report.model_dump(), indent=2)
        print(out)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
        return

    # Markdown Table format
    lines = []
    lines.append("# PanelFlow Studio - Story Understanding & Script Adaptation Benchmark")
    lines.append("")
    lines.append(f"**Provider**: `{report.provider_id}` | **Model**: `{report.model_name}`")
    lines.append(f"**Test Cases**: {report.passed_cases}/{report.total_cases} Passed")
    lines.append("")
    lines.append("## Aggregate Metrics")
    lines.append("")
    lines.append(f"- **Mean Character Resolution F1**: {report.mean_character_f1 * 100:.1f}%")
    lines.append(f"- **Mean Speaker Attribution Accuracy**: {report.mean_speaker_accuracy * 100:.1f}%")
    lines.append(f"- **Mean Scene Boundary F1**: {report.mean_scene_f1 * 100:.1f}%")
    lines.append(f"- **Mean Event Extraction F1**: {report.mean_event_f1 * 100:.1f}%")
    lines.append(f"- **Mean Unsupported Claim Rate**: {report.mean_unsupported_rate * 100:.2f}% (Target: <= 5.0%)")
    lines.append(f"- **Mean Latency**: {report.mean_latency_ms:.2f} ms")
    lines.append("")
    lines.append("## Detailed Results by Illustrated Sequence")
    lines.append("")
    lines.append("| Case ID | Title | Char F1 | Speaker Acc | Scene F1 | Event F1 | Unsupported % | Latency (ms) | Status |")
    lines.append("|---------|-------|---------|-------------|----------|----------|---------------|--------------|--------|")

    for r in report.results:
        status_badge = "PASS" if r.passed else "FAIL"
        lines.append(
            f"| `{r.case_id}` | {r.title} | {r.character_f1 * 100:.1f}% | {r.speaker_accuracy * 100:.1f}% | {r.scene_f1 * 100:.1f}% | {r.event_f1 * 100:.1f}% | {r.unsupported_claim_rate * 100:.2f}% | {r.latency_ms:.1f}ms | {status_badge} |"
        )

    lines.append("")
    report_text = "\n".join(lines)
    print(report_text)

    if args.output:
        Path(args.output).write_text(report_text, encoding="utf-8")
        print(f"\nReport written to: {args.output}")


if __name__ == "__main__":
    main()
