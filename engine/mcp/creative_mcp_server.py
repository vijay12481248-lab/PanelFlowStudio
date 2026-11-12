#!/usr/bin/env python3
"""PanelFlow Studio — Dedicated Creative Multi-Agent MCP Server.

Provides a dedicated Model Context Protocol (JSON-RPC 2.0 stdio) interface for
external orchestrators (Coordinator, Claude Code, Cursor, Windsurf, Antigravity Swarm)
to interact exclusively with PanelFlow Studio's creative agents, knowledge RAG,
manhua structural analyzer, dynamic agent forge, and skill builder.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import tools aggregator to register all creative tools
import engine.mcp.tools  # noqa: F401
from engine.mcp.registry import registry

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("panelflow.mcp.creative_server")

SERVER_NAME = "panelflow-creative-agents"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"


class CreativeMCPServer:
    """Dedicated MCP Server exposing PanelFlow Studio's creative agents."""

    def __init__(self, filter_creative_only: bool = True):
        self.registry = registry
        self.filter_creative_only = filter_creative_only

    def _get_exposed_tools(self) -> list[dict[str, Any]]:
        all_tools = self.registry.list_tools()
        if not self.filter_creative_only:
            return all_tools
        allowed_exact = {"panelflow_configure_freellmapi", "panelflow_get_llm_status", "panelflow_reset_to_local_llm"}
        return [t for t in all_tools if t["name"].startswith("panelflow_creative_") or t["name"] in allowed_exact]

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: missing method"},
            }

        # 1. Initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {
                            "listChanged": False,
                        },
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
                    },
                },
            }

        # 2. Notifications
        if method in ("notifications/initialized", "initialized"):
            return None

        # 3. Ping
        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        # 4. Tools List
        if method == "tools/list":
            tools = self._get_exposed_tools()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": tools,
                },
            }

        # 5. Tools Call
        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Missing tool name"},
                }

            # If filtered, reject non-creative tools
            allowed_exact = {"panelflow_configure_freellmapi", "panelflow_get_llm_status", "panelflow_reset_to_local_llm"}
            if self.filter_creative_only and not (tool_name.startswith("panelflow_creative_") or tool_name in allowed_exact):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool '{tool_name}' is not exposed by this creative agent MCP server.",
                    },
                }

            try:
                result = await self.registry.call_tool(tool_name, tool_args)
                formatted_text = json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": formatted_text,
                            }
                        ],
                        "isError": False,
                    },
                }
            except Exception as e:
                logger.exception("Error executing tool %s: %s", tool_name, e)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Tool execution failed: {str(e)}",
                            }
                        ],
                        "isError": True,
                    },
                }

        # Method Not Found
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async def run_stdio(self) -> None:
        tools = self._get_exposed_tools()
        logger.info(
            "PanelFlow Creative Agents MCP Server running on stdio (%d creative tools available)...",
            len(tools),
        )

        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                break
            line_str = line.strip()
            if not line_str:
                continue

            try:
                request = json.loads(line_str)
            except json.JSONDecodeError as exc:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
                continue

            response = await self.handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()


def main():
    server = CreativeMCPServer()
    try:
        asyncio.run(server.run_stdio())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
