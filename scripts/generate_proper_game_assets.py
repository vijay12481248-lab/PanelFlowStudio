import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path("E:/VIJAY SEKAR/PanelFlow Studio")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.imaging.browser_ai_bridge import browser_ai_bridge

# High-precision sprite sheet prompt engineered for Meta AI
SPRITE_SHEET_PROMPT = (
    "2D video game character sprite sheet of a mechanic father hero for a side-scrolling action platformer. "
    "Clean grid layout of multiple sprite animation frames isolated on a plain solid pure white background. "
    "Includes frames of the same character in side-view: idle standing pose, 4 running animation frames, "
    "aiming a pneumatic tool with his arm pointing forward, and firing. "
    "Character design: athletic middle-aged mechanic in brown jacket, blue jeans, boots, and leather tool belt. "
    "Crisp clean 2D game sprite asset, sharp dark outlines, evenly spaced sprite sheet ready for game engine slicing."
)

async def main():
    print("=" * 70)
    print(" Generating Proper 2D Game Sprite Sheet via Meta AI")
    print("=" * 70)
    print("Prompt:\n", SPRITE_SHEET_PROMPT)

    out_dir = PROJECT_ROOT / "output" / "game_sprites"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = await browser_ai_bridge.execute_prompt_async(
        url="https://www.meta.ai/ai-image-generator/",
        prompt=SPRITE_SHEET_PROMPT,
        extract_type="images",
        output_dir=out_dir,
        headless=True,
    )

    print("\nResult:")
    print("Success:", result.success)
    print("Execution time:", result.execution_time_sec, "s")
    print(f"Extracted {len(result.images)} images:")
    for idx, img in enumerate(result.images):
        print(f"  [{idx+1}] {img.file_path} ({img.width}x{img.height})")

if __name__ == "__main__":
    asyncio.run(main())
