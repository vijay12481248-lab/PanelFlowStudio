import asyncio
import edge_tts
from pathlib import Path

ssml = """<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-GB">
<voice name="en-GB-RyanNeural">
Thousands of years ago... <break time="250ms"/> one idiot had an idea!
</voice></speak>"""

async def test_ssml():
    try:
        c = edge_tts.Communicate(ssml, voice="en-GB-RyanNeural")
        out = Path("output/shorts/wheel_short/voice_variations/test_ssml.mp3")
        await c.save(str(out))
        print("SSML success! Size:", out.stat().st_size)
    except Exception as e:
        print("SSML error:", e)

if __name__ == "__main__":
    asyncio.run(test_ssml())
