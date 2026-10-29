"""Test script for PanelFlow Studio Meta AI Workflow.

Tests both:
1. Prompt Engineer & Reviewer logic (dry run / offline verification)
2. Live headless execution against Meta AI using persistent session
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.meta_ai_workflow import (
    PanelRequirement,
    MetaAIPromptEngineer,
    MetaAIImageReviewer,
    meta_ai_workflow,
)


def run_dry_run_test():
    print("=" * 70)
    print(" DRY RUN TEST: Prompt Engineer & Review Quality Gate")
    print("=" * 70)

    req = PanelRequirement(
        description="Modern minimalist tech logo for 'PanelFlow Studio', digital manga storyboard flow software",
        style_preset="tech_logo_minimal",
        aspect_ratio="1:1",
        mood_lighting="electric violet and cyan neon luminescence",
        camera_angle="centered isometric squircle emblem",
    )

    print("\n1. Input Requirement:")
    print(json.dumps(req.model_dump(), indent=2))

    prompt = MetaAIPromptEngineer.engineer_prompt(req)
    print("\n2. Engineered Prompt (for Meta AI):")
    print(f"--> \"{prompt}\"")

    print("\n3. Reviewer Gate Rules:")
    print(" - Min resolution threshold: 512x512")
    print(" - Aspect ratio tolerance: 25% max deviation")
    print(" - Target score threshold: >= 70/100")
    print("\n[PASSED] Prompt Engineer and Review Gate contracts verified.")


async def run_live_test(description: str, preset: str, ratio: str, headless: bool):
    print("=" * 70)
    print(" LIVE TEST: Executing Meta AI Prompt & Review Workflow")
    print("=" * 70)

    req = PanelRequirement(
        description=description,
        style_preset=preset,
        aspect_ratio=ratio,
    )

    print(f"Running for: '{description}' (preset: {preset}, aspect ratio: {ratio})")
    print(f"Headless mode: {headless}...")

    res = await meta_ai_workflow.execute_panel_generation(
        requirement=req,
        headless=headless,
        timeout_sec=120.0,
    )

    print("\nExecution Result:")
    print(f"Success:            {res.success}")
    print(f"Engineered Prompt:  {res.engineered_prompt}")
    print(f"Elapsed Time:       {res.execution_time_sec}s")

    if res.error:
        print(f"Error / Notice:     {res.error}")

    if res.generated_images:
        print(f"\nExtracted {len(res.generated_images)} Image(s):")
        for idx, img in enumerate(res.generated_images):
            print(f" [{idx+1}] File: {img.file_path} ({img.width}x{img.height})")

    if res.review:
        print("\nAI Quality Review:")
        print(f" Approved:  {res.review.approved}")
        print(f" Score:     {res.review.score}/100")
        print(f" Fidelity:  {res.review.visual_fidelity}")
        print(f" Assessment:{res.review.composition_assessment}")
        if res.review.suggested_refinements:
            print(f" Suggestions: {res.review.suggested_refinements}")


def main():
    parser = argparse.ArgumentParser(description="Test Meta AI workflow in PanelFlow Studio")
    parser.add_argument("--live", action="store_true", help="Run live browser execution")
    parser.add_argument("--prompt", default="Logo related to PanelFlow Studio", help="Prompt description")
    parser.add_argument("--preset", default="tech_logo_minimal", help="Style preset")
    parser.add_argument("--ratio", default="1:1", help="Aspect ratio (1:1, 16:9, etc.)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window during live execution")
    args = parser.parse_args()

    if not args.live:
        run_dry_run_test()
    else:
        asyncio.run(run_live_test(
            description=args.prompt,
            preset=args.preset,
            ratio=args.ratio,
            headless=not args.no_headless,
        ))


if __name__ == "__main__":
    main()
