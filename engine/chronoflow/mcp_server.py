#!/usr/bin/env python3
"""
ChronoFlow Pro Studio — Model Context Protocol (MCP) Server
Allows AI Agents (Antigravity, Claude, Cursor, etc.) to control the
video generation pipeline, character vault, and storyboard director headlessly.
"""

import sys
import json
import asyncio
import aiohttp
from pathlib import Path

import os
STUDIO_API = os.environ.get("CHRONOFLOW_API_URL", "http://127.0.0.1:8765/api/chronoflow")

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

TOOLS = [
    {
        "name": "chronoflow_status",
        "description": "Check GPU status, VRAM availability, installed MiniMax H3 models, and ComfyUI connection.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chronoflow_list_characters",
        "description": "List all character profiles and turnaround reference sheets stored in the Character Vault for actor consistency across shots.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chronoflow_save_character",
        "description": "Save or update a character in the Character Vault with reference image filename, name, role, and description.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Character name (e.g. 'Eli the Scavenger')"},
                "role": {"type": "string", "description": "Role (e.g. 'Protagonist', 'Villain', 'Sidekick')"},
                "image": {"type": "string", "description": "Filename of character reference in ComfyUI input/ folder"},
                "description": {"type": "string", "description": "Visual attributes, clothing, facial details"}
            },
            "required": ["name", "image"]
        }
    },
    {
        "name": "chronoflow_ai_director_plan",
        "description": "Generate a professional multi-scene storyboard breakdown from a high-level story idea, automatically compiling native 6-heading MiniMax H3 prompts for each shot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "idea": {"type": "string", "description": "High-level story idea or cinematic scene synopsis"},
                "duration": {"type": "integer", "description": "Target video duration in seconds (e.g. 15, 30, 60)"}
            },
            "required": ["idea"]
        }
    },
    {
        "name": "chronoflow_generate_video",
        "description": "Dispatch video generation in ChronoFlow Studio using MiniMax H3. Supports workflows: 'sliding_window' (continuation chaining), 'flf2v' (first & last keyframe bridging), 'reference' (character sheet consistency), or 'storyboard' (multi-scene production).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workflow_mode": {
                    "type": "string",
                    "enum": ["sliding_window", "flf2v", "reference", "storyboard"],
                    "description": "Conditioning mode. 'sliding_window' for long continuous shots, 'flf2v' for start-to-end transitions, 'reference' for character sheet locking, 'storyboard' for multi-scene movies."
                },
                "prompt": {"type": "string", "description": "Video prompt or compiled 6-heading description"},
                "total_duration": {"type": "number", "description": "Target duration in seconds (e.g. 15, 30, 60)"},
                "first_frame": {"type": "string", "description": "Starting image filename in input/ folder (optional)"},
                "last_frame": {"type": "string", "description": "Ending image filename in input/ folder for FLF2V mode (optional)"},
                "ref_images": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of character sheet filenames in input/ folder for reference locking"
                },
                "scenes": {
                    "type": "array",
                    "description": "List of scene beat objects for storyboard mode"
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "chronoflow_get_job_status",
        "description": "Check current step progress, chunk timeline, and output video URL for a running or completed ChronoFlow job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job ID returned by chronoflow_generate_video"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "chronoflow_generate_image",
        "description": "Generate high-quality reference image or keyframe using Qwen-Image-2.1 or FLUX.1.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "enum": ["qwen", "flux"], "description": "Model to use (default: qwen for Qwen-Image-2.1)"},
                "prompt": {"type": "string", "description": "Detailed image generation prompt"},
                "negative_prompt": {"type": "string", "description": "Negative prompt"},
                "width": {"type": "integer", "description": "Image width (e.g. 1024 or 1344)"},
                "height": {"type": "integer", "description": "Image height (e.g. 1024 or 768)"},
                "steps": {"type": "integer", "description": "Sampling steps (default: 8)"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "chronoflow_cancel_job",
        "description": "Cancel an active video generation job in ChronoFlow Studio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job ID to cancel"}
            },
            "required": ["job_id"]
        }
    }
]

async def call_api(method, endpoint, json_data=None):
    url = f"{STUDIO_API}{endpoint}"
    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                return await resp.json()
        elif method == "POST":
            async with session.post(url, json=json_data or {}, timeout=aiohttp.ClientTimeout(total=180)) as resp:
                return await resp.json()
        elif method == "DELETE":
            async with session.delete(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                return await resp.json()

async def handle_tool_call(name, args):
    try:
        if name == "chronoflow_status":
            res = await call_api("GET", "/status")
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_list_characters":
            res = await call_api("GET", "/characters")
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_save_character":
            res = await call_api("POST", "/characters", args)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_ai_director_plan":
            res = await call_api("POST", "/ai_director/plan", args)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_generate_video":
            res = await call_api("POST", "/generate", args)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_generate_image":
            res = await call_api("POST", "/generate_image", args)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_get_job_status":
            job_id = args.get("job_id")
            res = await call_api("GET", f"/job/{job_id}")
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        elif name == "chronoflow_cancel_job":
            res = await call_api("POST", "/cancel", args)
            return {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]}

        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"API Error: {str(e)}"}]}

async def process_jsonrpc():
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "chronoflow-pro-studio",
                        "version": "1.0.0"
                    }
                }
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS}
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            call_res = await handle_tool_call(tool_name, tool_args)
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": call_res
            }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method {method} not found"}
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(process_jsonrpc())
