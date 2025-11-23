import numpy as np
import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
from typing import Tuple, Dict, List

def analyze_ttlb(analysis) -> Tuple[Dict[str, Tuple], Dict[str, List[Tuple]]]:
    # For each trace, compute average, variance, and stddev of TTLB
    single_results = {}
    for trace, analyses in analysis.items():
        ttlb_values = []
        for analysis_res in analyses:
            if 'ttlb' in analysis_res and analysis_res['ttlb'] is not None:
                ttlb_values.append(analysis_res['ttlb'])
        if len(ttlb_values) > 0:
            avg_ttlb    = np.mean(ttlb_values)
            var_ttlb    = np.var(ttlb_values)
            stddev_ttlb = np.std(ttlb_values)
            single_results[trace.name] = (avg_ttlb, var_ttlb, stddev_ttlb)
        else:
            single_results[trace.name] = None

    # Compute pairwise TTLB comparisons
    pairwise_results = {}
    n = len(traces)
    traces = list(analysis.keys())
    for i in range(n):
        trace1 = traces[i]
        ttlb1 = single_results[trace1.name][0]
        pairwise_results[trace1.name] = []
        for j in range(n):
            trace2 = traces[j]
            ttlb2 = single_results[trace2.name][0]
            if ttlb1 is not None and ttlb2 is not None:
                diff = ttlb2 - ttlb1
                percentage_diff = (diff / ttlb1)
                pairwise_results[trace1.name].append((trace2.name, percentage_diff))
            else:
                pairwise_results[trace1.name].append((trace2.name, None))

    return single_results, pairwise_results

""" 
Create a heatmap using seaborn to visualize pairwise TTLB percentage differences.
"""
def plot_ttlb_heatmap(pairwise_results: Dict[str, List[Tuple]], 
                      filename: str = 'ttlb_heatmap.png',
                      title: str = 'TTLB Percentage Difference Heatmap',
                      annot: bool = True,
                      fmt: str = '.2%') -> plt.Figure:    
    # Extract trace names
    trace_names = list(pairwise_results.keys())
    num_traces = len(trace_names)
    
    # Create matrix
    matrix = np.zeros((num_traces, num_traces))
    for i, trace1 in enumerate(num_traces):
        for j, (_, pct_diff) in enumerate(pairwise_results[trace1]):
            if pct_diff is not None:
                matrix[i, j] = pct_diff
            else:
                matrix[i, j] = np.nan
    
    # Create DataFrame for better labeling
    df = pd.DataFrame(matrix, index=trace_names, columns=trace_names)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Create heatmap
    sns.heatmap(df, annot=annot, fmt=fmt, cmap='RdYlGn_r', 
                cbar_kws={'label': 'Percentage Difference'},
                linewidths=0.5, linecolor='white', ax=ax)
    
    # Labels and title
    ax.set_xlabel('Baseline', fontsize=12)
    ax.set_ylabel('Reference', fontsize=12)
    ax.set_title(title, fontsize=14, pad=20)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

"""
Create a bar chart showing TTLB averages with error bars for each trace.

Args:
    single_results: Dictionary with trace names as keys and 
                    (avg_ttlb, var_ttlb, stddev_ttlb) tuples as values
    filename: Output filename for bar chart
    title: Title for the chart
    error_type: Type of error bars to show ('stddev', 'variance', or 'both')
    sort_by: How to sort bars ('asc', 'desc', or None for original order)

Returns:
    matplotlib Figure object
"""
def plot_ttlb_barchart(single_results: Dict[str, Tuple],
                       filename: str = 'ttlb_barchart.png',
                       title: str = 'TTLB by Trace',
                       error_type: str = 'stddev',
                       sort_by: str = None):
    
    # Filter out None values
    valid_traces = {k: v for k, v in single_results.items() if v is not None}
    
    if not valid_traces:
        raise ValueError("No valid TTLB data to plot")
    
    # Extract data
    trace_names = list(valid_traces.keys())
    avg_values = [valid_traces[name][0] for name in trace_names]
    var_values = [valid_traces[name][1] for name in trace_names]
    std_values = [valid_traces[name][2] for name in trace_names]
    
    # Sort by TTLB if necessary
    if sort_by == 'asc':
        sorted_indices = np.argsort(avg_values)
        trace_names = [trace_names[i] for i in sorted_indices]
        avg_values = [avg_values[i] for i in sorted_indices]
        var_values = [var_values[i] for i in sorted_indices]
        std_values = [std_values[i] for i in sorted_indices]
    elif sort_by == 'desc':
        sorted_indices = np.argsort(avg_values)[::-1]
        trace_names = [trace_names[i] for i in sorted_indices]
        avg_values = [avg_values[i] for i in sorted_indices]
        var_values = [var_values[i] for i in sorted_indices]
        std_values = [std_values[i] for i in sorted_indices]
    
    # Determine error bars based on error_type
    if error_type == 'stddev':
        yerr = std_values
        error_label = 'Standard Deviation'
    elif error_type == 'variance':
        yerr = var_values
        error_label = 'Variance'
    else:  # fall back to stddev
        yerr = std_values
        error_label = 'Standard Deviation'
    
    # Create figure and axis
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Create bar positions
    x_pos = np.arange(len(trace_names))
    
    # Create bars
    bars = ax.bar(x_pos, avg_values, color='steelblue', edgecolor='black', linewidth=1.5, alpha=0.8)
    
    # Add error bars
    ax.errorbar(x_pos, avg_values, yerr=yerr, fmt='none', ecolor='red', capsize=5, 
                capthick=2, elinewidth=2, alpha=0.7, label=error_label)
    
    # Customize the plot
    ax.set_xlabel('Trace Name', fontsize=12, fontweight='bold')
    ax.set_ylabel('Time to Last Byte (TTLB)', fontsize=12, fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(trace_names, rotation=45, ha='right')
    
    # Add grid for better readability
    ax.yaxis.grid(True, linestyle='--', alpha=0.3)
    ax.set_axisbelow(True)
    
    # Add value labels on top of bars
    for i, (bar, avg, err) in enumerate(zip(bars, avg_values, yerr)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + err + 3,
                f'{avg:.2f} ± {err:.2f}',
                ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    # Add statistics text box
    stats_text = f'Min TTLB: {min(avg_values):.2f}\n'
    stats_text += f'Max TTLB: {max(avg_values):.2f}\n'
    
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
            fontsize=10, verticalalignment='top', bbox=props)
    
    plt.tight_layout()
    
    # Save if filename provided
    if filename:
        fig.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Figure saved to: {filename}")

    plt.close()
