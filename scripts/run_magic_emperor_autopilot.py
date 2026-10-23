import asyncio
import json
import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from engine.pipeline.autopilot import AutoPilotRunner

async def main():
    project_id = "a4e8115d-1e24-4a23-88b5-ecc72941bc8f"
    print(f"=== Starting AutoPilot Automation for Magic Emperor ({project_id}) ===")
    
    runner = AutoPilotRunner(
        project_id=project_id,
        options={
            "target_profile": "standard_1080p",
            "skip_existing_stages": True,
            "enable_thumbnails": True,
        }
    )
    
    # Run the full pipeline
    await runner.execute()
    
    snapshot = runner.snapshot()
    print("\n=== AutoPilot Run Finished ===")
    print(f"Status: {snapshot.status}")
    print(f"Progress: {int(snapshot.overall_progress * 100)}%")
    print(f"Started: {snapshot.started_at}")
    print(f"Completed: {snapshot.completed_at}")
    
    print("\n--- Stages ---")
    for s in snapshot.stages:
        print(f"[{s.status.ljust(9)}] {s.name.ljust(45)} ({s.duration_sec}s) - {s.message}")
        
    print("\n--- Result Bundle ---")
    print(json.dumps(snapshot.result, indent=2))
    
    print("\n--- Recent Logs ---")
    for log in snapshot.logs[-15:]:
        print(log)

if __name__ == "__main__":
    asyncio.run(main())
