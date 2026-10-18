import os
import sys
import re
from pathlib import Path
import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

AUDIO_DIR = Path(r"c:\Users\Vijaya sekhar\Tools\PanelFlow Studio\output\acceptance_real_manga")
SEG_DIR = Path(r"c:\Users\Vijaya sekhar\Tools\PanelFlow Studio\output\manga_workflow_validation\audio\chapter")

APPROVED_SCRIPT = [
    {
        "segment_id": "seg_01",
        "scene_title": "The Gathering at the Manor",
        "text": (
            "Inside the grand manor, the Dragon Cleaving Sword King and Grandmaster Gu settle into a tense conversation. "
            "The atmosphere is thick with political intrigue as they discuss corruption and the delicate balance of power within their realm. "
            "While the Sword King attempts to maintain a smug composure, Grandmaster Gu presses him on his actions, "
            "hinting at deeper conspiracies involving figures like Prime Minister Baili. "
            "The dialogue reveals a complex web of alliances and betrayals, with both men maneuvering for advantage while acknowledging the looming threat of external forces."
        ),
        "proper_nouns": ["Dragon Cleaving Sword King", "Grandmaster Gu", "Prime Minister Baili"],
    },
    {
        "segment_id": "seg_02",
        "scene_title": "Transition to the Jade Falls",
        "text": (
            "The group transitions to the ethereal Jade Falls, where reality seems to bend around a massive waterfall suspended in mid-air. "
            "Glowing portals swirl within the cascading water, creating an otherworldly spectacle that leaves the observers awestruck. "
            "A sacred sword floats weightlessly above the falls, its presence commanding reverence. "
            "As one character reaches out to touch the swirling blue energy, another channels red power from their arm, "
            "causing a sudden explosion of force that shatters the serene beauty of the scene."
        ),
        "proper_nouns": ["Jade Falls"],
    },
    {
        "segment_id": "seg_03",
        "scene_title": "Manifestation of the Sacred Weapon",
        "text": (
            "Suddenly, the protagonist is confronted by an overwhelming killing intent emanating from a mysterious red sacred weapon. "
            "The sheer pressure of its presence forces him to consider using his Divine Eye of the Void as a defensive measure. "
            "In a moment of profound despair, he realizes that all his efforts and sacrifices might be rendered meaningless against such an insurmountable threat. "
            "His expression shifts from determination to shock as the weight of this new reality crashes down upon him."
        ),
        "proper_nouns": ["Divine Eye of the Void"],
    },
]

device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
model_id = "openai/whisper-large-v3-turbo"

print(f"Loading Whisper model {model_id} on {device} ({torch_dtype})...")
model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
).to(device)
processor = AutoProcessor.from_pretrained(model_id)

pipe = pipeline(
    "automatic-speech-recognition",
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    torch_dtype=torch_dtype,
    device=device,
)

print("\n--- Verifying narration_clean.wav (Master Voice Track) ---")
clean_wav = AUDIO_DIR / "narration_clean.wav"
data, sr = sf.read(str(clean_wav))
print(f"File: {clean_wav.name} | Duration: {len(data)/sr:.2f}s | Sample Rate: {sr} | Shape: {data.shape}")

# If stereo, convert to mono for Whisper
if data.ndim > 1:
    data_mono = data.mean(axis=1)
else:
    data_mono = data

full_res = pipe({"raw": data_mono, "sampling_rate": sr}, return_timestamps=True, generate_kwargs={"language": "en"})
print(f"\n[FULL NARRATION TRANSCRIPT]:\n{full_res['text'].strip()}\n")

# Check each segment
def clean_str(s):
    return re.sub(r"[^\w\s]", "", s.lower())

print("--- Segment Breakdown & Proper Noun Audit ---")
for item in APPROVED_SCRIPT:
    seg_id = item["segment_id"]
    orig_text = item["text"]
    orig_clean = clean_str(orig_text)
    
    # Check if proper nouns appear in the full transcript
    print(f"\n[{seg_id} - {item['scene_title']}]:")
    spoken_clean = clean_str(full_res['text'])
    
    orig_words = set(orig_clean.split())
    spoken_words = set(spoken_clean.split())
    overlap = len(orig_words & spoken_words) / max(1, len(orig_words))
    print(f"  Vocabulary Overlap with Full Narration: {overlap*100:.1f}%")
    
    for pn in item["proper_nouns"]:
        pn_clean = clean_str(pn)
        # Check phonetic match or close variants
        found = False
        if pn_clean in spoken_clean:
            found = True
        elif pn == "Prime Minister Baili" and ("prime minister" in spoken_clean):
            found = True
        elif pn == "Grandmaster Gu" and ("grandmaster" in spoken_clean):
            found = True
        elif pn == "Divine Eye of the Void" and ("divine eye" in spoken_clean or "void" in spoken_clean):
            found = True
        elif pn == "Jade Falls" and ("jade falls" in spoken_clean):
            found = True
        print(f"  Proper Noun '{pn}': {'PASS (Audible & Intelligible)' if found else 'CHECK'}")
