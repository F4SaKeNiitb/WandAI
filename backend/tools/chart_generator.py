"""
Chart Generator Tool
Creates charts and visualizations using matplotlib.
"""

import base64
import io
import os
from typing import Any
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np


# Chart style configuration
CHART_STYLE = {
    'figure.figsize': (10, 6),
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.dpi': 100,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'axes.facecolor': '#f8f9fa',
    'figure.facecolor': 'white'
}


async def generate_chart(
    chart_type: str,
    data: dict[str, Any],
    title: str = "Chart",
    x_label: str = "",
    y_label: str = "",
    save_path: str = None
) -> dict[str, Any]:
    """
    Generate a chart based on the provided data.
    
    Args:
        chart_type: Type of chart (line, bar, pie, scatter, area)
        data: Chart data with labels and values/datasets
        title: Chart title
        x_label: X-axis label
        y_label: Y-axis label
        save_path: Optional path to save the chart
        
    Returns:
        Dictionary with success status and base64-encoded image
    """
    try:
        # Apply style
        plt.rcParams.update(CHART_STYLE)
        
        fig, ax = plt.subplots()
        
        # Extract data
        labels = data.get('labels', [])
        values = data.get('values', [])
        datasets = data.get('datasets', [])
        
        # Handle single dataset case
        if values and not datasets:
            datasets = [{'label': 'Data', 'data': values}]
        
        if chart_type == 'line':
            for dataset in datasets:
                ax.plot(
                    labels if labels else range(len(dataset['data'])),
                    dataset['data'],
                    label=dataset.get('label', 'Data'),
                    marker='o',
                    markersize=4
                )
            if len(datasets) > 1:
                ax.legend()
                
        elif chart_type == 'bar':
            x = np.arange(len(labels))
            width = 0.8 / len(datasets) if datasets else 0.8
            
            for i, dataset in enumerate(datasets):
                offset = (i - len(datasets)/2 + 0.5) * width
                ax.bar(
                    x + offset,
                    dataset['data'],
                    width,
                    label=dataset.get('label', f'Series {i+1}')
                )
            
            ax.set_xticks(x)
            ax.set_xticklabels(labels, rotation=45, ha='right')
            if len(datasets) > 1:
                ax.legend()
                
        elif chart_type == 'pie':
            values = datasets[0]['data'] if datasets else values
            colors = plt.cm.Pastel1(np.linspace(0, 1, len(values)))
            wedges, texts, autotexts = ax.pie(
                values,
                labels=labels,
                autopct='%1.1f%%',
                colors=colors,
                startangle=90
            )
            ax.axis('equal')
            
        elif chart_type == 'scatter':
            for dataset in datasets:
                d = dataset.get('data', [])
                if isinstance(d[0], (list, tuple)) if d else False:
                    # Data is list of [x, y] pairs
                    x_vals = [p[0] for p in d]
                    y_vals = [p[1] for p in d]
                else:
                    # Data is just y values
                    x_vals = labels if labels else range(len(d))
                    y_vals = d
                
                ax.scatter(
                    x_vals,
                    y_vals,
                    label=dataset.get('label', 'Data'),
                    alpha=0.7
                )
            if len(datasets) > 1:
                ax.legend()
                
        elif chart_type == 'area':
            for dataset in datasets:
                x_vals = labels if labels else range(len(dataset['data']))
                ax.fill_between(
                    x_vals,
                    dataset['data'],
                    alpha=0.3,
                    label=dataset.get('label', 'Data')
                )
                ax.plot(x_vals, dataset['data'], linewidth=1)
            if len(datasets) > 1:
                ax.legend()
        
        # Set labels and title
        ax.set_title(title, fontweight='bold', pad=15)
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
        
        plt.tight_layout()
        
        # Save to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150)
        buffer.seek(0)
        
        # Encode to base64
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        
        # Optionally save to file
        saved_path = None
        if save_path:
            plt.savefig(save_path, format='png', bbox_inches='tight', dpi=150)
            saved_path = save_path
        
        plt.close(fig)
        
        return {
            'success': True,
            'image_base64': image_base64,
            'image_path': saved_path,
            'chart_type': chart_type,
            'title': title
        }
        
    except Exception as e:
        plt.close('all')
        return {
            'success': False,
            'error': str(e)
        }


async def generate_multi_chart(
    charts: list[dict[str, Any]],
    title: str = "Dashboard",
    layout: tuple[int, int] = None
) -> dict[str, Any]:
    """
    Generate multiple charts in a single figure.
    
    Args:
        charts: List of chart configurations
        title: Overall title
        layout: Grid layout as (rows, cols)
        
    Returns:
        Dictionary with success status and base64-encoded image
    """
    try:
        n = len(charts)
        if layout is None:
            # Auto-calculate layout
            cols = min(2, n)
            rows = (n + cols - 1) // cols
            layout = (rows, cols)
        
        fig, axes = plt.subplots(layout[0], layout[1], figsize=(10*layout[1], 6*layout[0]))
        if n == 1:
            axes = [axes]
        else:
            axes = axes.flatten()
        
        for i, chart_config in enumerate(charts):
            if i >= len(axes):
                break
            
            ax = axes[i]
            chart_type = chart_config.get('type', 'line')
            data = chart_config.get('data', {})
            labels = data.get('labels', [])
            datasets = data.get('datasets', [{'data': data.get('values', [])}])
            
            # Simplified chart rendering for multi-chart
            if chart_type == 'line':
                for ds in datasets:
                    ax.plot(labels or range(len(ds['data'])), ds['data'])
            elif chart_type == 'bar':
                ax.bar(labels or range(len(datasets[0]['data'])), datasets[0]['data'])
            elif chart_type == 'pie':
                ax.pie(datasets[0]['data'], labels=labels, autopct='%1.1f%%')
            
            ax.set_title(chart_config.get('title', f'Chart {i+1}'))
        
        # Hide unused subplots
        for i in range(n, len(axes)):
            axes[i].set_visible(False)
        
        fig.suptitle(title, fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150)
        buffer.seek(0)
        
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close(fig)
        
        return {
            'success': True,
            'image_base64': image_base64,
            'chart_count': n
        }
        
    except Exception as e:
        plt.close('all')
        return {
            'success': False,
            'error': str(e)
        }
