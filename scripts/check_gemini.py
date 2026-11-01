"""List the Gemini models your API key can use and run one small test call.

Usage: set GEMINI_API_KEY (Google AI Studio key), then: python scripts/check_gemini.py [model_id]
"""
import asyncio
import os
import sys
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.narration.__main__ import GEMINI_ENDPOINT  # noqa: E402
from engine.llm.providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402


class Pong(BaseModel):
    word: str


async def main(model):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        sys.exit("Set GEMINI_API_KEY first (create a key at https://aistudio.google.com/apikey).")
    p = OpenAICompatibleProvider(GEMINI_ENDPOINT, model or "unset", key, timeout=60)
    models = await p.list_available_models()
    print("models:", *sorted(m.removeprefix("models/") for m in models), sep="\n  ")
    if model:
        out = await p.generate_structured('Reply with the JSON {"word": "pong"}.', Pong, model=model)
        print("test call ok:", out)


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
