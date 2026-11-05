"""MCP Tool Registry for PanelFlow Studio.

Provides decorator-based tool registration, schema definitions,
and execution dispatch for Model Context Protocol (MCP) clients.
"""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger("panelflow.mcp.registry")


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]
    domain: str = "general"


class MCPToolRegistry:
    _instance = None

    def __new__(cls) -> MCPToolRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[..., Any],
        domain: str = "general",
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description.strip(),
            input_schema=input_schema,
            handler=handler,
            domain=domain,
        )
        logger.debug("Registered MCP tool: %s (%s)", name, domain)

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any] | None = None,
        domain: str = "general",
    ):
        """Decorator for registering an MCP tool function."""
        def decorator(fn: Callable[..., Any]):
            schema = input_schema or {
                "type": "object",
                "properties": {},
            }
            self.register(name, description, schema, fn, domain=domain)
            return fn
        return decorator

    def list_tools(self) -> list[dict[str, Any]]:
        """Returns the list of tools formatted for the MCP tools/list protocol response."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            for t in sorted(self._tools.values(), key=lambda x: x.name)
        ]

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        tool_def = self._tools.get(name)
        if not tool_def:
            raise KeyError(f"Tool '{name}' not found in registry")

        args = arguments or {}
        handler = tool_def.handler

        # Call sync or async handler
        if inspect.iscoroutinefunction(handler):
            result = await handler(**args)
        else:
            result = handler(**args)

        return result


registry = MCPToolRegistry()
