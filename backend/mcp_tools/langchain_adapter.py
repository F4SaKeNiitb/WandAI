"""
LangChain adapter for MCP tools.
Wraps MCP tools as LangChain BaseTool instances so agents can bind them.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from mcp_tools.client import MCPToolManager, ToolInfo


def _build_args_schema(tool_info: ToolInfo) -> Type[BaseModel]:
    """Dynamically build a Pydantic model from an MCP tool's JSON Schema."""
    input_schema = tool_info.input_schema
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    field_definitions: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")

        # Map JSON Schema types to Python types
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        python_type = type_map.get(prop_type, Any)

        if prop_name in required:
            field_definitions[prop_name] = (python_type, Field(description=description))
        else:
            default = prop_schema.get("default")
            field_definitions[prop_name] = (
                python_type | None,
                Field(default=default, description=description),
            )

    model_name = f"{tool_info.name.replace('-', '_').title().replace('_', '')}Args"
    return create_model(model_name, **field_definitions)


class MCPTool(BaseTool):
    """LangChain tool that delegates to an MCP server via MCPToolManager."""

    name: str = ""
    description: str = ""
    mcp_manager: Any = None  # MCPToolManager (Any to avoid Pydantic issues)
    tool_info: Any = None  # ToolInfo
    args_schema: Type[BaseModel] | None = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, mcp_manager: MCPToolManager, tool_info: ToolInfo, **kwargs):
        # Build args schema from MCP tool's input schema
        schema = _build_args_schema(tool_info)
        super().__init__(
            name=tool_info.name,
            description=tool_info.description,
            mcp_manager=mcp_manager,
            tool_info=tool_info,
            args_schema=schema,
            **kwargs,
        )

    def _run(self, **kwargs) -> Any:
        """Synchronous fallback — runs the async version in an event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self._arun(**kwargs)).result()
        return asyncio.run(self._arun(**kwargs))

    async def _arun(self, **kwargs) -> Any:
        """Call the MCP tool asynchronously."""
        result = await self.mcp_manager.call_tool(self.tool_info.name, kwargs)
        # Try to parse JSON results for richer output
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                pass
        return result
