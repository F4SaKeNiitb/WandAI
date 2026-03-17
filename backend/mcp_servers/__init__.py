"""
MCP (Model Context Protocol) Tool Servers.
Exposes WandAI's tools as MCP-compliant servers for interoperability.
"""

MCP_SERVERS = {
    "wandai-search": {
        "module": "mcp_servers.search_server",
        "description": "Web search tool via Tavily API",
        "transport": "stdio",
    },
    "wandai-code": {
        "module": "mcp_servers.code_server",
        "description": "Sandboxed Python code execution",
        "transport": "stdio",
    },
    "wandai-chart": {
        "module": "mcp_servers.chart_server",
        "description": "Chart and visualization generation",
        "transport": "stdio",
    },
}
