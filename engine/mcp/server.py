#!/usr/bin/env python3
"""PanelFlow Studio — the one Model Context Protocol (MCP) server (JSON-RPC 2.0 over stdio).

Exposes every capability of PanelFlow Studio, ChronoFlow video studio included, as tools. All tools are thin wrappers over
the engine's HTTP API (default http://127.0.0.1:8765), so there is exactly one server to attach.

A client that only wants a slice can ask for a profile:

    python scripts/run_mcp_server.py                      # every tool (default)
    python scripts/run_mcp_server.py --profile creative   # the creative agents and the LLM settings only
    python scripts/run_mcp_server.py --profile chronoflow # the ChronoFlow video studio only

or set PANELFLOW_MCP_PROFILE. A tool outside the profile is neither listed nor callable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
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

# Import tools aggregator to register all tools
import engine.mcp.tools  # noqa: F401
from engine.mcp.registry import registry

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("panelflow.mcp.server")

SERVER_NAME = "panelflow-studio-mcp"
SERVER_VERSION = "1.1.0"
PROTOCOL_VERSION = "2024-11-05"

# LLM settings the creative agents need alongside their own tools.
_CREATIVE_EXTRA = {"panelflow_configure_freellmapi", "panelflow_get_llm_status", "panelflow_reset_to_local_llm"}
PROFILES = ("all", "creative", "chronoflow")


def tool_in_profile(name: str, domain: str, profile: str) -> bool:
    """Is the tool part of `profile`? ("all" is everything.)"""
    if profile == "creative":
        return name.startswith("panelflow_creative_") or name in _CREATIVE_EXTRA
    if profile == "chronoflow":
        return domain == "chronoflow"
    return True


class MCPServer:
    def __init__(self, profile: str = "all"):
        if profile not in PROFILES:
            raise ValueError(f"Unknown MCP profile {profile!r}; choose one of {', '.join(PROFILES)}")
        self.registry = registry
        self.profile = profile

    def exposed_tools(self) -> list[dict[str, Any]]:
        """The tools this server lists and accepts, after the profile."""
        tools = self.registry.list_tools()
        if self.profile == "all":
            return tools
        return [t for t in tools if tool_in_profile(t["name"], self.registry.get_tool(t["name"]).domain, self.profile)]

    def _allows(self, name: str) -> bool:
        tool = self.registry.get_tool(name)
        return tool is not None and tool_in_profile(name, tool.domain, self.profile)

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
            tools = self.exposed_tools()
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

            if self.profile != "all" and not self._allows(tool_name):
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' is not exposed by the '{self.profile}' profile of this server."},
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
        logger.info("PanelFlow Studio MCP Server running on stdio (profile %s, %d tools available)...", self.profile, len(self.exposed_tools()))

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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="PanelFlow Studio MCP server (stdio)")
    parser.add_argument("--profile", choices=PROFILES, default=os.environ.get("PANELFLOW_MCP_PROFILE", "all"),
                        help="which tools to expose (default: all, or PANELFLOW_MCP_PROFILE)")
    args = parser.parse_args(argv)
    server = MCPServer(profile=args.profile)
    try:
        asyncio.run(server.run_stdio())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
