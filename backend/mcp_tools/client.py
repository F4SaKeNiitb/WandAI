"""
MCP Tool Manager.
Connects to MCP servers, discovers tools, and provides them as LangChain tools.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from core.logging import get_logger
logger = get_logger("MCP")


@dataclass
class ToolInfo:
    """Metadata about a discovered MCP tool."""
    name: str
    description: str
    input_schema: dict
    server_name: str


class MCPToolManager:
    """Manages connections to MCP servers and exposes their tools."""

    def __init__(self):
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, ToolInfo] = {}
        self._contexts: list[Any] = []  # keep context managers alive

    async def connect_stdio(self, server_name: str, command: str, args: list[str] | None = None, env: dict | None = None) -> None:
        """Connect to an MCP server via stdio transport."""
        try:
            server_params = StdioServerParameters(
                command=command,
                args=args or [],
                env=env,
            )

            ctx = stdio_client(server_params)
            streams = await ctx.__aenter__()
            self._contexts.append(ctx)

            session = ClientSession(*streams)
            await session.__aenter__()
            self._contexts.append(session)

            await session.initialize()
            self._sessions[server_name] = session

            # Discover tools
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                tool_info = ToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    server_name=server_name,
                )
                self._tools[tool.name] = tool_info
        except Exception as e:
            logger.error(f"Failed to connect to MCP server '{server_name}': {e}")
            raise

    async def list_tools(self) -> list[ToolInfo]:
        """List all discovered tools across all connected servers."""
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Call a tool by name with the given arguments.

        Args:
            name: The tool name as discovered via list_tools().
            arguments: Tool arguments matching the input schema.

        Returns:
            The tool result.
        """
        tool_info = self._tools.get(name)
        if not tool_info:
            raise ValueError(f"Unknown tool: {name}. Available: {list(self._tools.keys())}")

        session = self._sessions.get(tool_info.server_name)
        if not session:
            raise RuntimeError(f"No active session for server: {tool_info.server_name}")

        try:
            result = await session.call_tool(name, arguments)
        except Exception as e:
            logger.warning(f"MCP tool call failed, attempting reconnection: {e}")
            # Attempt one reconnection
            try:
                await self.connect_stdio(tool_info.server_name, "python", ["-m", f"mcp_servers.{tool_info.server_name}_server"])
                session = self._sessions.get(tool_info.server_name)
                result = await session.call_tool(name, arguments)
            except Exception as reconnect_err:
                logger.error(f"MCP reconnection failed: {reconnect_err}")
                raise RuntimeError(f"MCP tool call failed after reconnection attempt: {e}") from e

        # MCP returns a CallToolResult; extract content
        if hasattr(result, 'content') and result.content:
            contents = []
            for item in result.content:
                if hasattr(item, 'text'):
                    contents.append(item.text)
                else:
                    contents.append(str(item))
            return contents[0] if len(contents) == 1 else contents
        return result

    def as_langchain_tools(self) -> list:
        """Convert all discovered MCP tools to LangChain BaseTool instances."""
        from mcp_tools.langchain_adapter import MCPTool

        langchain_tools = []
        for tool_info in self._tools.values():
            langchain_tools.append(MCPTool(mcp_manager=self, tool_info=tool_info))
        return langchain_tools

    async def close(self) -> None:
        """Close all sessions and connections."""
        for ctx in reversed(self._contexts):
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"MCP cleanup error: {e}")
        self._contexts.clear()
        self._sessions.clear()
        self._tools.clear()
