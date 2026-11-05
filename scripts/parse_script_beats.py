import re
import json
from pathlib import Path

def parse_master_script(script_path: Path):
    text = script_path.read_text(encoding="utf-8")
    
    # Pattern to match: [MM:SS - MM:SS] **Title** \n Text
    pattern = r"\[(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\]\s*\*\*(.*?)\*\*\s*\n(.*?)(?=\n\[|\n---|\Z)"
    matches = re.findall(pattern, text, re.DOTALL)
    
    beats = []
    for idx, (start_ts, end_ts, title, content) in enumerate(matches, 1):
        clean_text = content.strip().replace("*", "")
        # Remove any stage directions like [00:00 - ...]
        clean_text = re.sub(r"\[.*?\]", "", clean_text).strip()
        beats.append({
            "beat_id": f"beat_{idx:02d}",
            "act": (idx - 1) // 5 + 1,
            "title": title.strip(),
            "target_start": start_ts,
            "target_end": end_ts,
            "text": clean_text,
            "word_count": len(clean_text.split())
        })
    return beats

if __name__ == "__main__":
    script_p = Path("output/Regressed_Assassin_Duke/MASTER_SCRIPT.md")
    beats = parse_master_script(script_p)
    print(f"Parsed {len(beats)} beats:")
    total_words = 0
    for b in beats:
        print(f"[{b['beat_id']}] Act {b['act']} ({b['target_start']}-{b['target_end']}) - {b['title']}: {b['word_count']} words")
        total_words += b['word_count']
    print(f"Total words: {total_words}")
    
    out_json = Path("output/Regressed_Assassin_Duke/parsed_beats.json")
    out_json.write_text(json.dumps(beats, indent=2), encoding="utf-8")
    print(f"Saved to {out_json}")
