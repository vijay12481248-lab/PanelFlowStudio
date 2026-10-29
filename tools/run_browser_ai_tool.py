#!/usr/bin/env python3
"""CLI utility to execute prompts against AI web tools (ChatGPT, Gemini, Meta AI, Claude, etc.)
and extract generated images and responses into PanelFlow Studio.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure root in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.imaging.browser_ai_bridge import browser_ai_bridge


def main():
    parser = argparse.ArgumentParser(description="PanelFlow Studio Browser AI Bridge Tool")
    parser.add_argument("--url", default="https://chatgpt.com", help="Target website URL")
    parser.add_argument("--prompt", default="", help="Prompt text to input and execute")
    parser.add_argument("--extract-type", choices=["images", "text", "all"], default="all", help="What to extract")
    parser.add_argument("--project-id", default=None, help="Optional PanelFlow project ID to register assets to")
    parser.add_argument("--output-dir", default="output/web_ai", help="Directory where extracted images are saved")
    parser.add_argument("--headful", action="store_true", help="Launch visible browser instead of headless")
    parser.add_argument("--login", action="store_true", help="Launch interactive browser session to sign in")
    parser.add_argument("--timeout", type=float, default=120.0, help="Maximum execution timeout in seconds")

    args = parser.parse_args()

    if args.login:
        print(f"Opening interactive browser window for {args.url}...")
        res = browser_ai_bridge.launch_interactive_session(args.url)
        print(f"Browser launched: {res.get('message')}")
        print(f"Profile saved at: {res.get('profile_dir')}")
        return

    out_p = Path(args.output_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {args.url} (Headless: {not args.headful})...")
    print(f"Prompt: {args.prompt[:80]}...")

    result = browser_ai_bridge.execute_prompt(
        url=args.url,
        prompt=args.prompt,
        extract_type=args.extract_type,
        output_dir=out_p,
        headless=not args.headful,
        timeout_sec=args.timeout,
        project_id=args.project_id,
    )

    if result.success:
        print("\n=== SUCCESS ===")
        print(f"Platform: {result.platform}")
        print(f"Execution time: {result.execution_time_sec}s")
        if result.images:
            print(f"\nExtracted Images ({len(result.images)}):")
            for idx, img in enumerate(result.images, 1):
                print(f"  [{idx}] {img.filename} ({img.width}x{img.height}, {img.byte_size} bytes)")
                print(f"      Path: {img.file_path}")
        if result.text_response:
            print(f"\nResponse Text:\n{result.text_response[:400]}")
    else:
        print("\n=== FAILED ===")
        print(f"Error: {result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
