import asyncio
from engine.creative.infinite_series_engine import InfiniteSeriesProductionEngine

async def run():
    engine = InfiniteSeriesProductionEngine()
    res = await engine.produce_episode(1, render_video=True)
    print("✓ Successfully produced Episode 1!")
    print("Status:", res["status"])
    print("Video:", res.get("output_video_path"))
    print("Audit Score:", res.get("audit_score"))

if __name__ == "__main__":
    asyncio.run(run())
