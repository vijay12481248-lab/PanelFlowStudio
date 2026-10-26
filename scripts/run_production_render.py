import asyncio, sys, time, logging
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

from engine.pipeline.autopilot import AutoPilotRunner
from engine.database.session import SessionLocal
from engine.database.models import RenderJobRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'

async def progress_reporter(runner):
    while True:
        await asyncio.sleep(10.0)
        st = runner.get_stage('render')
        if st and st.status == 'RUNNING':
            print(f"[Render Progress] {int(st.progress * 100)}% - {st.message}", flush=True)
        elif st and st.status in ('COMPLETED', 'FAILED'):
            break

async def main():
    print("Initializing AutoPilotRunner for Stage 8 Render & Stage 9 Packaging...", flush=True)
    runner = AutoPilotRunner(PROJECT_ID, options={
        'skip_existing_stages': False,
        'target_profile': 'standard_1080p',
        'subtitles': True,
    })
    
    rep_task = asyncio.create_task(progress_reporter(runner))
    
    start_t = time.monotonic()
    print("Starting _run_stage_render...", flush=True)
    try:
        await runner._run_stage_render('standard_1080p', skip_existing=False)
        print(f"Stage render finished in {round(time.monotonic() - start_t, 1)}s! Status: {runner.get_stage('render').status}", flush=True)
        
        print("Starting _run_stage_packaging...", flush=True)
        await runner._run_stage_packaging('standard_1080p')
        print(f"Stage packaging finished! Status: {runner.get_stage('packaging').status}", flush=True)
        print("All production stages completed successfully!", flush=True)
        
        # Print output path
        with SessionLocal() as db:
            last_job = db.query(RenderJobRecord).filter(
                RenderJobRecord.project_id == PROJECT_ID,
                RenderJobRecord.status == "COMPLETE"
            ).order_by(RenderJobRecord.created_at.desc()).first()
            if last_job:
                print(f"FINAL_CERTIFIED_MP4: {last_job.output_path}", flush=True)
    finally:
        rep_task.cancel()

if __name__ == '__main__':
    asyncio.run(main())
