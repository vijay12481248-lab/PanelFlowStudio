import os
import json
import uuid
import asyncio
import subprocess
import aiohttp
from pathlib import Path

from urllib.parse import urlsplit

from engine.comfyui.art import ArtEngine

def _resolve_comfy_base_dir() -> Path:
    env_dir = os.environ.get("PANELFLOW_COMFYUI_DIR") or os.environ.get("COMFYUI_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    default_comfy = Path("E:/VIJAY SEKAR/ComfyUI")
    if default_comfy.exists():
        return default_comfy
    return Path(__file__).resolve().parent.parent.parent / "ComfyUI"

_raw_url = os.environ.get("PANELFLOW_COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
_parsed = urlsplit(_raw_url)
COMFY_HOST = _parsed.netloc or "127.0.0.1:8188"
COMFY_URL = f"{_parsed.scheme or 'http'}://{COMFY_HOST}"
COMFY_WS_URL = f"ws://{COMFY_HOST}/ws"

BASE_DIR = _resolve_comfy_base_dir()
COMFY_INPUT_DIR = BASE_DIR / "input"
COMFY_OUTPUT_DIR = BASE_DIR / "output" / "video"
STUDIO_OUTPUT_DIR = Path("E:/VIJAY SEKAR/PanelFlow Studio/output/chronoflow")
STUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

class ChronoFlowPipeline:
    def __init__(self, comfy_url=COMFY_URL, ws_url=COMFY_WS_URL):
        self.comfy_url = comfy_url
        self.ws_url = ws_url
        self.client_id = str(uuid.uuid4())

    async def check_comfy_status(self):
        try:
            async with aiohttp.ClientSession() as session:
                queue_info = {"busy": False, "reachable": False, "running_prompt_id": "", "running_prompt": "", "pending_count": 0}  # reachable: the queue answer was really received
                try:
                    async with session.get(f"{self.comfy_url}/queue", timeout=aiohttp.ClientTimeout(total=10)) as q_resp:  # a busy ComfyUI answers slowly
                        if q_resp.status == 200:
                            q_data = await q_resp.json()
                            queue_info["reachable"] = True
                            running = q_data.get("queue_running", [])
                            pending = q_data.get("queue_pending", [])
                            if running:
                                item = running[0]
                                p_id = item[1]
                                nodes = item[2]
                                p_text = ""
                                for n in nodes.values():
                                    if "inputs" in n and "prompt" in n["inputs"]:
                                        p_text = str(n["inputs"]["prompt"])[:100]
                                        break
                                queue_info = {
                                    "busy": True,
                                    "reachable": True,
                                    "running_prompt_id": p_id,
                                    "running_prompt": p_text,
                                    "pending_count": len(pending)
                                }
                            elif pending:
                                queue_info["pending_count"] = len(pending)
                except Exception:
                    pass

                async with session.get(f"{self.comfy_url}/system_stats", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        vram_free = 0
                        vram_total = 0
                        gpu_name = "GPU"
                        devices = data.get("devices", [])
                        if devices:
                            dev = devices[0]
                            gpu_name = dev.get("name", "GPU")
                            vram_free = round(dev.get("vram_free", 0) / (1024**3), 2)
                            vram_total = round(dev.get("vram_total", 0) / (1024**3), 2)
                        return {
                            "connected": True,
                            "gpu": gpu_name,
                            "vram_free_gb": vram_free,
                            "vram_total_gb": vram_total,
                            "queue": queue_info
                        }
        except Exception:
            pass
        return {"connected": False, "gpu": "Unknown", "vram_free_gb": 0, "vram_total_gb": 0, "queue": {"busy": False}}

    def compile_h3_prompt(self, detailed_description, subject_definitions=None, summary=None, 
                          retention_analysis=None, soundscape=None, music=None,
                          bokeh_background=False):
        """Compiles a prompt conforming to MiniMax H3's native 6-heading schema."""
        lines = []
        if subject_definitions:
            lines.append("subject_definitions:\n" + subject_definitions.strip())
        if summary:
            lines.append("summary:\n" + summary.strip())
        if retention_analysis:
            lines.append("retention_analysis:\n" + retention_analysis.strip())
        if detailed_description:
            desc = detailed_description.strip()
            if bokeh_background and "bokeh" not in desc.lower() and "depth of field" not in desc.lower():
                desc += " Cinematic shallow depth of field, sharp foreground subject, background softly blurred in lens bokeh."
            lines.append("detailed_description:\n" + desc)
        if soundscape:
            lines.append("overall_soundscape:\n" + soundscape.strip())
        if music:
            lines.append("non_diegetic_music:\n" + music.strip())
        
        return "\n\n".join(lines) if lines else detailed_description

    def build_h3_prompt(self, prompt, width, height, length, steps, lora_name, 
                        workflow_mode="sliding_window", first_frame_filename=None, 
                        last_frame_filename=None, ref_images=None, seed=None,
                        face_refine=False, upscale_mode="none"):
        if seed is None:
            import random
            seed = random.randint(1, 1000000000)

        graph = {
            "1": {
                "class_type": "UNETLoader",
                "inputs": {
                    "unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
                    "weight_dtype": "default"
                }
            },
            "2": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": ["1", 0],
                    "lora_name": lora_name,
                    "strength_model": 1.0
                }
            },
            "3": {
                "class_type": "CLIPLoader",
                "inputs": {
                    "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                    "type": "minimax",
                    "device": "default"
                }
            },
            "4": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "minimax_h3_video_vae_int8_convrot.safetensors"
                }
            },
            "5": {
                "class_type": "VAELoader",
                "inputs": {
                    "vae_name": "minimax_h3_audio_vae_fp32.safetensors"
                }
            }
        }

        # Check conditioning node type: Reference-to-Video vs Image-to-Video
        if workflow_mode == "reference" and ref_images:
            graph["7"] = {
                "class_type": "MiniMaxH3ReferenceToVideo",
                "inputs": {
                    "clip": ["3", 0],
                    "vae": ["4", 0],
                    "audio_vae": ["5", 0],
                    "prompt": prompt,
                    "width": int(width),
                    "height": int(height),
                    "length": int(length),
                    "ref_image_size": "match"
                }
            }
            # Attach up to 9 character sheets / reference images
            ref_dict = {}
            for idx, r_file in enumerate(ref_images[:9]):
                load_node_id = f"ref_img_{idx + 1}"
                graph[load_node_id] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": r_file}
                }
                ref_dict[f"ref_image_{idx}"] = [load_node_id, 0]
            graph["7"]["inputs"]["ref_images"] = ref_dict

        else:
            # Default / FLF2V / Sliding Window conditioning node
            graph["7"] = {
                "class_type": "MiniMaxH3ImageToVideo",
                "inputs": {
                    "clip": ["3", 0],
                    "vae": ["4", 0],
                    "prompt": prompt,
                    "width": int(width),
                    "height": int(height),
                    "length": int(length)
                }
            }
            if first_frame_filename:
                graph["load_first"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": first_frame_filename}
                }
                graph["7"]["inputs"]["first_frame"] = ["load_first", 0]

            if last_frame_filename:
                graph["load_last"] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": last_frame_filename}
                }
                graph["7"]["inputs"]["last_frame"] = ["load_last", 0]

        # Remaining pipeline nodes
        graph.update({
            "8": {
                "class_type": "BasicGuider",
                "inputs": {
                    "model": ["2", 0],
                    "conditioning": ["7", 0]
                }
            },
            "9": {
                "class_type": "KSamplerSelect",
                "inputs": {
                    "sampler_name": "res_multistep"
                }
            },
            "10": {
                "class_type": "BasicScheduler",
                "inputs": {
                    "model": ["2", 0],
                    "scheduler": "simple",
                    "steps": int(steps),
                    "denoise": 1.0
                }
            },
            "11": {
                "class_type": "RandomNoise",
                "inputs": {
                    "noise_seed": seed
                }
            },
            "12": {
                "class_type": "SamplerCustomAdvanced",
                "inputs": {
                    "noise": ["11", 0],
                    "guider": ["8", 0],
                    "sampler": ["9", 0],
                    "sigmas": ["10", 0],
                    "latent_image": ["7", 1]
                }
            },
            "13": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["12", 0],
                    "vae": ["4", 0]
                }
            },
            "14": {
                "class_type": "VAEDecodeAudio",
                "inputs": {
                    "samples": ["12", 0],
                    "vae": ["5", 0]
                }
            },
        })

        last_image_source = ["13", 0]

        if face_refine:
            graph["face_track_crop"] = {
                "class_type": "H3FaceTrackCrop",
                "inputs": {
                    "images": ["13", 0],
                    "detector": "face_yolov8m.pt",
                    "confidence": 0.45,
                    "crop_factor": 1.5,
                    "canvas_width": 512,
                    "canvas_height": 512,
                    "canvas_mode": "pad_to_target",
                    "smooth_window": 5,
                    "size_smooth_window": 5,
                    "smooth_method": "gaussian",
                    "size_mode": "target_longest",
                },
            }
            graph["face_stitch"] = {
                "class_type": "H3FaceStitch",
                "inputs": {
                    "base_images": ["13", 0],
                    "refined_crops": ["face_track_crop", 0],
                    "transform": ["face_track_crop", 1],
                    "paste_region": "face_box",
                    "mask_dilation": 8,
                    "feather": 16,
                    "colour_match": "none",
                    "blend": 1.0,
                    "undetected_frames": "pass_through",
                },
            }
            last_image_source = ["face_stitch", 0]

        if upscale_mode in ("2k", "2k_latent", "upscale_2k"):
            graph["upscale_2k"] = {
                "class_type": "ImageScaleBy",
                "inputs": {
                    "images": last_image_source,
                    "upscale_method": "bicubic",
                    "scale_by": 1.5,
                },
            }
            last_image_source = ["upscale_2k", 0]

        graph["15"] = {
            "class_type": "CreateVideo",
            "inputs": {
                "images": last_image_source,
                "audio": ["14", 0],
                "fps": 24.0,
            },
        }
        graph["16"] = {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["15", 0],
                "filename_prefix": "video/chronoflow_chunk",
                "format": "auto",
                "codec": "auto",
            },
        }

        return graph

    async def generate_art_image(self, prompt, negative_prompt, width=1024, height=1024, seed=None) -> str:
        """One keyframe / reference image from the central ArtEngine, saved into ComfyUI's input/ folder (Character Vault, MiniMax H3).

        There is exactly one text-to-image workflow in PanelFlow (see engine/comfyui/art.py); ChronoFlow does not carry its own graphs.
        """
        art = await asyncio.to_thread(ArtEngine().generate, prompt, negative_prompt, int(width), int(height), seed, "chronoflow_art")
        filename = f"art_{uuid.uuid4().hex[:8]}.png"
        (COMFY_INPUT_DIR / filename).write_bytes(art.png)
        return filename

    def build_inpaint_prompt(self, image_filename, mask_filename, prompt, denoise=0.85, steps=4, seed=None, model="flux"):
        if seed is None:
            import random
            seed = random.randint(1, 1000000000)

        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": "flux1-schnell-fp8.safetensors"
                }
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": prompt
                }
            },
            "3": {
                "class_type": "LoadImage",
                "inputs": {
                    "image": image_filename
                }
            },
            "4": {
                "class_type": "LoadImageMask",
                "inputs": {
                    "image": mask_filename,
                    "channel": "red"
                }
            },
            "5": {
                "class_type": "VAEEncode",
                "inputs": {
                    "pixels": ["3", 0],
                    "vae": ["1", 2]
                }
            },
            "6": {
                "class_type": "SetLatentNoiseMask",
                "inputs": {
                    "samples": ["5", 0],
                    "mask": ["4", 0]
                }
            },
            "7": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["2", 0],
                    "latent_image": ["6", 0],
                    "seed": int(seed),
                    "steps": int(steps),
                    "cfg": 1.0,
                    "sampler_name": "euler",
                    "scheduler": "simple",
                    "denoise": float(denoise)
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["7", 0],
                    "vae": ["1", 2]
                }
            },
            "9": {
                "class_type": "ImageCompositeMasked",
                "inputs": {
                    "destination": ["3", 0],
                    "source": ["8", 0],
                    "mask": ["4", 0],
                    "x": 0,
                    "y": 0,
                    "resize_source": False
                }
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["9", 0],
                    "filename_prefix": "chronoflow_inpaint"
                }
            }
        }

    async def execute_prompt(self, prompt_graph, on_step=None):
        payload = {
            "prompt": prompt_graph,
            "client_id": self.client_id
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.comfy_url}/prompt", json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"ComfyUI prompt submission failed: {text}")
                res = await resp.json()
                prompt_id = res.get("prompt_id")

            ws_url = f"{self.ws_url}?clientId={self.client_id}"
            finished_event = asyncio.Event()

            async def ws_listener():
                try:
                    async with session.ws_connect(ws_url, heartbeat=25, timeout=aiohttp.ClientTimeout(total=None)) as ws:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    msg_type = data.get("type")
                                    payload_data = data.get("data", {})

                                    if msg_type == "progress":
                                        val = payload_data.get("value", 0)
                                        max_val = payload_data.get("max", 1)
                                        if on_step:
                                            on_step(val, max_val)

                                    elif msg_type == "executing":
                                        node = payload_data.get("node")
                                        p_id = payload_data.get("prompt_id")
                                        if p_id == prompt_id and node is None:
                                            finished_event.set()
                                            break
                                    elif msg_type == "execution_error":
                                        p_id = payload_data.get("prompt_id")
                                        if p_id == prompt_id:
                                            finished_event.set()
                                            break
                                except Exception:
                                    pass
                except Exception:
                    pass
                finally:
                    finished_event.set()

            ws_task = asyncio.create_task(ws_listener())

            # Resilient polling loop checking ComfyUI history directly
            import time
            start_poll = time.time()
            while time.time() - start_poll < 900:  # 15 minutes timeout
                await asyncio.sleep(2.0)
                try:
                    async with session.get(f"{self.comfy_url}/history/{prompt_id}") as hist_resp:
                        if hist_resp.status == 200:
                            hist = await hist_resp.json()
                            if prompt_id in hist:
                                p_info = hist[prompt_id]
                                stat = p_info.get("status", {})
                                if stat.get("status_str") == "error":
                                    msgs = stat.get("messages", [])
                                    if ws_task and not ws_task.done(): ws_task.cancel()
                                    raise RuntimeError(f"ComfyUI execution error: {msgs}")
                                outputs = p_info.get("outputs", {})
                                for _, out in outputs.items():
                                    if "images" in out:
                                        for item in out["images"]:
                                            fname = item.get("filename")
                                            if fname and fname.endswith((".mp4", ".mkv", ".webm", ".png", ".jpg", ".jpeg", ".webp")):
                                                sub = item.get("subfolder", "")
                                                if ws_task and not ws_task.done(): ws_task.cancel()
                                                return BASE_DIR / "output" / sub / fname
                except RuntimeError:
                    raise
                except Exception:
                    pass

                if finished_event.is_set():
                    await asyncio.sleep(1.0)
                    try:
                        async with session.get(f"{self.comfy_url}/history/{prompt_id}") as hist_resp:
                            if hist_resp.status == 200:
                                hist = await hist_resp.json()
                                if prompt_id in hist:
                                    p_info = hist[prompt_id]
                                    outputs = p_info.get("outputs", {})
                                    for _, out in outputs.items():
                                        if "images" in out:
                                            for item in out["images"]:
                                                fname = item.get("filename")
                                                if fname and fname.endswith((".mp4", ".mkv", ".webm", ".png", ".jpg", ".jpeg", ".webp")):
                                                    sub = item.get("subfolder", "")
                                                    return BASE_DIR / "output" / sub / fname
                    except Exception:
                        pass
                    break

            if ws_task and not ws_task.done():
                ws_task.cancel()

        raise RuntimeError("Prompt completed but no output media found")

    def extract_tail_frame(self, video_path, output_image_path):
        cmd = [
            "ffmpeg", "-y",
            "-sseof", "-0.05",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(output_image_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not output_image_path.exists():
            cmd_alt = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-vf", "select=eq(n\\,0)",
                "-q:v", "2",
                str(output_image_path)
            ]
            subprocess.run(cmd_alt, capture_output=True, text=True)
        return output_image_path.exists()

    def mux_source_audio(self, video_path, source_path, offset_sec=0.0):
        """Replace `video_path`'s audio with `source_path`'s audio from `offset_sec` on (padded/cut to the video length).

        Used when a shot is re-animated from an edited frame: the new clip keeps the original narration for that stretch."""
        _, _, vdur = self._probe_size_and_duration(video_path)
        tmp = video_path.with_name(video_path.stem + ".mux.mp4")
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-ss", f"{max(0.0, float(offset_sec)):.3f}", "-i", str(source_path),
               "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-t", f"{vdur:.3f}", str(tmp)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not tmp.exists():
            return False
        tmp.replace(video_path)
        return True

    def stitch_chunks(self, chunk_paths, output_stitched_path, crossfade_sec=0.3):
        if not chunk_paths:
            return None
        if len(chunk_paths) == 1:
            import shutil
            shutil.copy2(chunk_paths[0], output_stitched_path)
            return output_stitched_path

        list_file = output_stitched_path.parent / f"concat_{uuid.uuid4().hex[:8]}.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for p in chunk_paths:
                clean_path = str(p).replace("\\", "/")
                f.write(f"file '{clean_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_stitched_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if list_file.exists():
            list_file.unlink()

        if res.returncode == 0 and output_stitched_path.exists():
            return output_stitched_path
        return None

    @staticmethod
    def _probe_size_and_duration(path):
        """(width, height, duration) of a media file via ffprobe; zeros when unreadable."""
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
             "-of", "json", str(path)], capture_output=True, text=True)
        try:
            data = json.loads(out.stdout)
            stream = (data.get("streams") or [{}])[0]
            return int(stream.get("width") or 0), int(stream.get("height") or 0), float(data.get("format", {}).get("duration") or 0)
        except (ValueError, TypeError):
            return 0, 0, 0.0

    def _apply_overlays(self, master_path, overlays, width, height):
        """Burn still overlays (the editor's V2 'edited frame' clips) onto the stitched master, in place."""
        _, _, dur = self._probe_size_and_duration(master_path)
        inputs, graph, last, n = ["-i", str(master_path)], [], "[0:v]", 0
        for o in overlays:
            name = str(o.get("filename") or "")
            img = next((d / name for d in (COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR) if name and Path(name).name == name and (d / name).is_file()), None)
            start = max(0.0, float(o.get("start") or 0))
            end = min(dur, start + float(o.get("duration") or 0))
            if img is None or end <= start:
                continue
            n += 1
            inputs += ["-loop", "1", "-framerate", "24", "-t", f"{dur:.3f}", "-i", str(img)]
            graph.append(f"[{n}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=rgba[ov{n}]")
            graph.append(f"{last}[ov{n}]overlay=enable='between(t,{start:.3f},{end:.3f})'[v{n}]")
            last = f"[v{n}]"
        if not n:
            return
        tmp = master_path.with_name(master_path.stem + ".ovl.mp4")
        cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(graph), "-map", last, "-map", "0:a?",
               "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", str(tmp)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not tmp.exists():
            raise RuntimeError(f"overlay render failed: {res.stderr[-300:]}")
        tmp.replace(master_path)

    def render_timeline_edl(self, clips, output_master_path, overlays=None):
        """Renders an NLE timeline Edit Decision List (V1 clips + V2 still overlays) into a final mastered video."""
        if not clips:
            return None

        import tempfile
        temp_dir = output_master_path.parent / f"timeline_tmp_{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        processed_chunks = []
        out_w, out_h = 1344, 768
        for clip in clips:   # output size follows the first readable clip (the old fixed 1344x768 letterboxed square clips)
            first = clip.get("filename") or Path(clip.get("url", "")).name
            found = next((d / first for d in (STUDIO_OUTPUT_DIR, COMFY_OUTPUT_DIR, COMFY_INPUT_DIR) if first and (d / first).is_file()), None)
            if found:
                w, h, _ = self._probe_size_and_duration(found)
                if w and h:
                    out_w, out_h = w - w % 2, h - h % 2
                break
        try:
            for idx, clip in enumerate(clips):
                src_filename = clip.get("filename") or Path(clip.get("url", "")).name
                src_path = STUDIO_OUTPUT_DIR / src_filename
                if not src_path.exists():
                    src_path = COMFY_OUTPUT_DIR / src_filename
                if not src_path.exists():
                    src_path = COMFY_INPUT_DIR / src_filename

                if not src_path.exists():
                    continue

                in_point = float(clip.get("in_point", 0.0))
                out_point = clip.get("out_point")
                speed = float(clip.get("speed", 1.0))
                volume = float(clip.get("volume", 1.0))

                out_chunk = temp_dir / f"chunk_{idx:03d}.mp4"

                cmd = ["ffmpeg", "-y"]
                if in_point > 0:
                    cmd.extend(["-ss", str(in_point)])
                if out_point is not None and float(out_point) > in_point:
                    cmd.extend(["-to", str(out_point)])

                cmd.extend(["-i", str(src_path)])

                # Filter complex for speed and volume
                pts_factor = 1.0 / max(0.25, min(4.0, speed))
                v_filter = f"setpts={pts_factor:.4f}*PTS,scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2"
                
                # Audio tempo
                atempo = max(0.5, min(2.0, speed))
                a_filter = f"volume={volume:.2f},atempo={atempo:.2f}"

                cmd.extend([
                    "-filter_complex", f"[0:v]{v_filter}[v];[0:a]{a_filter}[a]",
                    "-map", "[v]",
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-crf", "18",
                    "-preset", "fast",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(out_chunk)
                ])

                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and out_chunk.exists():
                    processed_chunks.append(out_chunk)
                else:
                    # Fallback copy if audio filter fails (e.g. no audio stream)
                    cmd_no_a = [
                        "ffmpeg", "-y",
                        "-i", str(src_path),
                        "-vf", v_filter,
                        "-c:v", "libx264",
                        "-crf", "18",
                        "-an",
                        str(out_chunk)
                    ]
                    res_alt = subprocess.run(cmd_no_a, capture_output=True, text=True)
                    if res_alt.returncode == 0 and out_chunk.exists():
                        processed_chunks.append(out_chunk)

            if not processed_chunks:
                return None

            stitched = self.stitch_chunks(processed_chunks, output_master_path)
            if stitched and overlays:
                self._apply_overlays(output_master_path, overlays, out_w, out_h)
            return stitched
        finally:
            import shutil
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
