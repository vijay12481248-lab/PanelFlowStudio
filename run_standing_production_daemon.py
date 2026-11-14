"""Standing Autonomous Production Daemon for 1000-Episode Manhua Video Series.

Continuously produces episodes according to the master roadmap:
- 20-minute episode structure (6 Acts, 200-240 panels)
- Autonomous self-review, mistake detection & correction
- ComfyUI ArtEngine (Qwen Image 2.1) generation
- 2.5D camera choreography video composition (Zero MiniMax H3)
- Durable ledger tracking and automatic error recovery
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.creative.infinite_series_engine import InfiniteSeriesProductionEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/series_1000/production_daemon.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("standing_production_daemon")


async def main():
    logger.info("================================================================================")
    logger.info("✦ LAUNCHING STANDING 1000-EPISODE AUTONOMOUS PRODUCTION ENGINE ✦")
    logger.info("================================================================================")
    
    engine = InfiniteSeriesProductionEngine()
    total_target = engine.ledger.get("total_planned_episodes", 1000)
    
    while True:
        curr_idx = engine.ledger.get("current_episode_index", 1)
        if curr_idx > total_target:
            logger.info("🎉 All 1,000 episodes completed! Grand Sovereign Coronation achieved.")
            break
            
        logger.info(f"\n🎬 Starting Production of Episode {curr_idx}/{total_target}...")
        try:
            res = await engine.produce_episode(curr_idx, render_video=True)
            logger.info(f"✓ Episode {curr_idx} Done: Status={res['status']} | Audit Score={res.get('audit_score')}/10 | Video={res.get('output_video_path')}")
            
            # Brief pause for GPU cooling & log flush
            await asyncio.sleep(1.0)
            
        except Exception as e:
            logger.error(f"❌ Error in Episode {curr_idx}: {e}", exc_info=True)
            try:
                engine.mistake_ledger.record_mistake(
                    domain="production_engine",
                    category="runtime_recovery",
                    flawed_pattern=f"Episode {curr_idx} failed: {str(e)}",
                    prevention_rule="Log exception, flush GPU VRAM cache, and resume production loop.",
                )
            except Exception as log_err:
                logger.warning(f"Could not record mistake: {log_err}")
                
            await asyncio.sleep(5.0)
            continue


if __name__ == "__main__":
    asyncio.run(main())
