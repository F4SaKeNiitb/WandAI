"""
MCP Server for Code Execution.
Wraps tools/code_executor.py as an MCP-compliant tool server.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wandai-code")


@mcp.tool()
async def execute_python(code: str, timeout_seconds: int = 30) -> dict:
    """Execute Python code in a sandboxed environment.

    The sandbox allows: json, math, datetime, collections, re, statistics,
    random, pandas, numpy. File I/O, subprocess, and os are blocked.

    Args:
        code: Python source code to execute.
        timeout_seconds: Maximum execution time in seconds (default 30).

    Returns:
        Dictionary with success, output, and error fields.
    """
    from tools.code_executor import execute_python_code

    success, output, error = await execute_python_code(code, timeout_seconds)
    return {"success": success, "output": output, "error": error}


@mcp.tool()
async def execute_python_with_data(
    code: str, data: dict, timeout_seconds: int = 30
) -> dict:
    """Execute Python code with pre-loaded data variables.

    Variables from the data dict are injected into the execution namespace.

    Args:
        code: Python source code to execute.
        data: Dictionary of variable names to values, available in the code.
        timeout_seconds: Maximum execution time in seconds (default 30).

    Returns:
        Dictionary with success, output, and error fields.
    """
    from tools.code_executor import execute_with_data

    success, output, error = await execute_with_data(code, data, timeout_seconds)
    return {"success": success, "output": output, "error": error}


if __name__ == "__main__":
    mcp.run()
