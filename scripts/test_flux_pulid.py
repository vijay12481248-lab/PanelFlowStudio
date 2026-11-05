"""Test FLUX + PuLID workflow on ComfyUI."""
import json
import os
import sys
import time
from pathlib import Path

# Add project root
sys.path.insert(0, ".")

os.environ["PANELFLOW_COMFYUI_WORKFLOW_DIR"] = r"E:\VIJAY SEKAR\ComfyUI\workflow"
from engine.comfyui import ComfyUIClient
from engine.original.art import ComfyRunner

# 1. Define workflow dict
wf = {
  "1": {
    "class_type": "CheckpointLoaderSimple",
    "inputs": {
      "ckpt_name": "flux1-schnell-fp8.safetensors"
    }
  },
  "2": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "",
      "clip": ["1", 1]
    }
  },
  "3": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "",
      "clip": ["1", 1]
    }
  },
  "4": {
    "class_type": "EmptySD3LatentImage",
    "inputs": {
      "width": 1344,
      "height": 768,
      "batch_size": 1
    }
  },
  "8": {
    "class_type": "LoadImage",
    "inputs": {
      "image": ""
    }
  },
  "9": {
    "class_type": "PulidFluxModelLoader",
    "inputs": {
      "pulid_file": "pulid_flux_v0.9.0.safetensors"
    }
  },
  "10": {
    "class_type": "PulidFluxInsightFaceLoader",
    "inputs": {
      "provider": "CPU"
    }
  },
  "11": {
    "class_type": "PulidFluxEvaClipLoader",
    "inputs": {}
  },
  "12": {
    "class_type": "ApplyPulidFlux",
    "inputs": {
      "model": ["1", 0],
      "pulid_flux": ["9", 0],
      "eva_clip": ["11", 0],
      "face_analysis": ["10", 0],
      "image": ["8", 0],
      "weight": 0.85,
      "start_at": 0.0,
      "end_at": 0.85
    }
  },
  "5": {
    "class_type": "KSampler",
    "inputs": {
      "seed": 42,
      "steps": 4,
      "cfg": 1.0,
      "sampler_name": "euler",
      "scheduler": "simple",
      "denoise": 1.0,
      "model": ["12", 0],
      "positive": ["2", 0],
      "negative": ["3", 0],
      "latent_image": ["4", 0]
    }
  },
  "6": {
    "class_type": "VAEDecode",
    "inputs": {
      "samples": ["5", 0],
      "vae": ["1", 2]
    }
  },
  "7": {
    "class_type": "SaveImage",
    "inputs": {
      "filename_prefix": "panelflow_pulid",
      "images": ["6", 0]
    }
  }
}

client = ComfyUIClient()
runner = ComfyRunner(client=client)

# Upload reference portrait (Arjuna)
ref_img = Path("output/Original_Stories/mahabharata_kurukshetra/sheets/arjuna_sdxl.png").resolve()
uploaded_name = runner._upload(ref_img)
print("Uploaded reference image to ComfyUI:", uploaded_name)

# Patch workflow
wf["2"]["inputs"]["text"] = "Anime illustration. Close-up of the face and shoulders. An adult man with athletic warrior, golden plate armor, ornate silver diadem, holding divine longbow Gandiva. Confident smile, resolute piercing eyes, golden sunrise rim lighting. Safe, masterpiece, absurdres. No text, no watermark."
wf["3"]["inputs"]["text"] = "lowres, bad anatomy, bad hands, blurry, text, watermark, beard, mustache"
wf["8"]["inputs"]["image"] = uploaded_name
wf["5"]["inputs"]["seed"] = 777

print("Submitting prompt to ComfyUI with ApplyPulidFlux...")
t0 = time.time()
pid = client.submit_prompt(wf)
print(f"Prompt queued, ID: {pid}")

while time.time() - t0 < 120:
    hist = client.history(pid)
    if hist and pid in hist:
        imgs = hist[pid]["outputs"].get("7", {}).get("images", [])
        if imgs:
            i = imgs[0]
            data = client.download_output(i["filename"], i["subfolder"], i["type"])
            out_file = Path("output/Original_Stories/mahabharata_kurukshetra/panels/arjuna_pulid_test.png")
            out_file.write_bytes(data)
            print(f"[SUCCESS] PuLID-FLUX generated in {time.time()-t0:.1f}s: {out_file} ({len(data)/(1024*1024):.2f} MB)")
            break
    time.sleep(2)
