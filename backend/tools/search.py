"""
Search Tool
Web search integration using Tavily API.
"""

import os
from typing import Any
import httpx
from config import config


async def search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Search the web using Tavily API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        
    Returns:
        List of search results with url, title, and content
    """
    api_key = config.search.tavily_api_key
    
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY is not configured. Cannot perform web search. "
            "Please set the TAVILY_API_KEY environment variable to enable real search."
        )
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": max_results,
                    "include_answer": False,
                    "include_raw_content": False
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                return [
                    {
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "score": r.get("score", 0)
                    }
                    for r in results
                ]
            else:
                print(f"Search API error: {response.status_code} - {response.text}")
                return []
                
    except Exception as e:
        print(f"Search failed: {str(e)}")
        return []


async def search_news(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Search for news articles using Tavily API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results
        
    Returns:
        List of news results
    """
    api_key = config.search.tavily_api_key
    
    if not api_key:
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "topic": "news"
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            return []
            
    except Exception as e:
        print(f"News search failed: {str(e)}")
        return []
