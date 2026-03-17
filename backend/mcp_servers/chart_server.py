"""
MCP Server for Chart Generation.
Wraps tools/chart_generator.py as an MCP-compliant tool server.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("wandai-chart")


@mcp.tool()
async def generate_chart(
    chart_type: str,
    data: dict,
    title: str = "Chart",
    x_label: str = "",
    y_label: str = "",
) -> dict:
    """Generate a chart visualization.

    Args:
        chart_type: Type of chart — one of line, bar, pie, scatter, area.
        data: Chart data with 'labels' and 'values' or 'datasets' keys.
              datasets format: [{"label": "Series", "data": [1,2,3]}]
        title: Chart title.
        x_label: X-axis label.
        y_label: Y-axis label.

    Returns:
        Dictionary with success, image_base64, chart_type, and title.
    """
    from tools.chart_generator import generate_chart as _generate_chart

    return await _generate_chart(
        chart_type=chart_type,
        data=data,
        title=title,
        x_label=x_label,
        y_label=y_label,
    )


@mcp.tool()
async def generate_dashboard(charts: list[dict], title: str = "Dashboard") -> dict:
    """Generate a multi-chart dashboard.

    Args:
        charts: List of chart configs, each with type, data, and title keys.
        title: Overall dashboard title.

    Returns:
        Dictionary with success, image_base64, and chart_count.
    """
    from tools.chart_generator import generate_multi_chart

    return await generate_multi_chart(charts=charts, title=title)


if __name__ == "__main__":
    mcp.run()
