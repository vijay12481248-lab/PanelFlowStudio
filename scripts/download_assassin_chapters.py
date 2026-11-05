import asyncio
import httpx
from pathlib import Path
import sys
import time

sys.path.insert(0, ".")
from engine.acquisition.adapters.generic_web import GenericAuthorizedWebAdapter

OUTPUT_DIR = Path("output/Regressed_Assassin_Duke/raw_chapters")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.kakamanga.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

async def download_file(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str, dest_path: Path):
    if dest_path.exists() and dest_path.stat().st_size > 1000:
        return True
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.get(url, timeout=20.0)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    dest_path.write_bytes(resp.content)
                    return True
                elif resp.status_code == 404:
                    return False
            except Exception as e:
                await asyncio.sleep(1.0)
        return False

async def download_chapter(ch_num: int, adapter: GenericAuthorizedWebAdapter):
    ch_url = f"https://www.kakamanga.com/manga/the-regressed-son-of-a-duke-is-an-assassin/chapter-{ch_num}"
    ch_dir = OUTPUT_DIR / f"chapter_{ch_num}"
    ch_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Inspecting Chapter {ch_num}...", flush=True)
    insp = adapter.inspect(ch_url)
    if not insp.is_valid or not insp.chapters:
        print(f"Error inspecting chapter {ch_num}: {insp.error}", flush=True)
        return 0
    
    candidates = adapter.list_pages(insp.chapters[0])
    print(f"Chapter {ch_num}: Found {len(candidates)} image candidates.", flush=True)
    
    sem = asyncio.Semaphore(10)
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        tasks = []
        for cand in candidates:
            filename = f"slice_{cand.sequence:04d}.webp"
            dest = ch_dir / filename
            tasks.append(download_file(client, sem, cand.source_uri, dest))
        
        results = await asyncio.gather(*tasks)
        success_count = sum(1 for r in results if r)
        print(f"Chapter {ch_num} downloaded: {success_count}/{len(candidates)} slices saved to {ch_dir}", flush=True)
        return success_count

async def main():
    t0 = time.time()
    adapter = GenericAuthorizedWebAdapter()
    print("=== Starting Download of Chapters 1 to 5 ===", flush=True)
    total_downloaded = 0
    for ch in range(1, 6):
        count = await download_chapter(ch, adapter)
        total_downloaded += count
    
    elapsed = time.time() - t0
    print(f"\n[DONE] Finished downloading all 5 chapters: {total_downloaded} images in {elapsed:.1f}s", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
