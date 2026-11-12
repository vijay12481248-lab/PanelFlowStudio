#!/usr/bin/env python3
"""Runner script for PanelFlow Creative Agents MCP Server."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.mcp.creative_mcp_server import main

if __name__ == "__main__":
    main()
