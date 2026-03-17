"""
MCP Server for Web Search.
Wraps tools/search.py as an MCP-compliant tool server.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wandai-search")


@mcp.tool()
async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web for information using Tavily API.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).

    Returns:
        List of search results with url, title, content, and score.
    """
    from tools.search import search_web as _search_web

    return await _search_web(query, max_results=max_results)


@mcp.tool()
async def search_news(query: str, max_results: int = 5) -> list[dict]:
    """Search for recent news articles.

    Args:
        query: The news search query string.
        max_results: Maximum number of results to return (default 5).

    Returns:
        List of news article results.
    """
    from tools.search import search_news as _search_news

    return await _search_news(query, max_results=max_results)


if __name__ == "__main__":
    mcp.run()
