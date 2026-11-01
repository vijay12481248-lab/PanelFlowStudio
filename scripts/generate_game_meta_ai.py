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

# High-fidelity prompt engineered specifically for Meta AI / Imagine
OPTIMIZED_PROMPT = (
    "A 2D video game screenshot of a side-scrolling action-adventure platformer. "
    "Side-view orthographic camera angle. On the left side on a concrete sidewalk, a determined mechanic father "
    "wearing a brown canvas jacket, blue denim jeans, heavy boots, and a tool belt is aiming a pneumatic rivet tool. "
    "A clear glowing red laser trajectory beam shoots from his weapon across the screen. "
    "On the right side of the street, clumsy green-tinted suburban zombie infected stagger forward past an overturned yellow taxi cab and wooden crates. "
    "A prominent red explosive fuel drum sits between them. "
    "Atmospheric golden hour dusk lighting, warm sunlight reflections on cracked asphalt, detailed suburban town houses and telephone poles in the parallax background. "
    "Clean stylized 2D digital game art, high visual clarity, vibrant colors, video game concept art."
)

async def main():
    print("=" * 70)
    print(" Running Meta AI with Engineered 2D Game Prompt")
    print("=" * 70)
    print("Prompt:\n", OPTIMIZED_PROMPT)
    print("\nExecuting live via Browser AI Bridge...")

    result = await browser_ai_bridge.execute_prompt_async(
        url="https://www.meta.ai/ai-image-generator/",
        prompt=OPTIMIZED_PROMPT,
        extract_type="images",
        output_dir=PROJECT_ROOT / "output" / "game_assets",
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
