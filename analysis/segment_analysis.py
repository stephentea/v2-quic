import pathlib
from typing import List, Tuple, Dict
import numpy as np
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from analysis.cda_analysis import Segment

"""
Compare segments between two traces across multiple runs.

Args:
    segments1: List of segment lists for trace 1 (one list per run)
    segments2: List of segment lists for trace 2 (one list per run)
    trace1_name: Name of trace 1
    trace2_name: Name of trace 2

Returns:
    Dictionary containing comparison results
"""
def segment_analysis(segments1: List[List[Segment]], segments2: List[List[Segment]], 
                     trace1_name: str = "Trace 1", trace2_name: str = "Trace 2"):
    # Get segment counts for each iteration
    seg1_lens = [len(segment) for segment in segments1]
    seg2_lens = [len(segment) for segment in segments2]
    
    # Find number of segments common across all iterations
    num_common_seg1 = min(seg1_lens)
    num_common_seg2 = min(seg2_lens)
    
    # Find maximum segments to consider
    max_seg1 = max(seg1_lens)
    max_seg2 = max(seg2_lens)
    
    # Initialize storage for per-segment statistics for trace 1
    trace1_durations    = {i: [] for i in range(max_seg1)}
    trace1_avg_rates    = {i: [] for i in range(max_seg1)}
    trace1_median_rates = {i: [] for i in range(max_seg1)}
    trace1_bytes        = {i: [] for i in range(max_seg1)}
    
    # Initialize storage for per-segment statistics for trace 2
    trace2_durations    = {i: [] for i in range(max_seg2)}
    trace2_avg_rates    = {i: [] for i in range(max_seg2)}
    trace2_median_rates = {i: [] for i in range(max_seg2)}
    trace2_bytes        = {i: [] for i in range(max_seg2)}
    
    # Collect segment statistics for trace 1
    for segments in segments1:
        for i, segment in enumerate(segments):
            trace1_durations[i].append(segment.duration_ms)
            trace1_avg_rates[i].append(segment.avg_rate)
            trace1_median_rates[i].append(segment.median_rate)
            trace1_bytes[i].append(segment.bytes_transferred)
    
    # Collect segment statistics for trace 2
    for segments in segments2:
        for i, segment in enumerate(segments):
            trace2_durations[i].append(segment.duration_ms)
            trace2_avg_rates[i].append(segment.avg_rate)
            trace2_median_rates[i].append(segment.median_rate)
            trace2_bytes[i].append(segment.bytes_transferred)
    
    # Compute statistics for each segment position
    trace1_stats = []
    for i in range(max_seg1):
        if len(trace1_durations[i]) > 0:
            stats = {
                'segment_id': i,
                'avg_duration': np.mean(trace1_durations[i]),
                'avg_bytes': np.mean(trace1_bytes[i]),
                'avg_rate': np.mean(trace1_avg_rates[i]),
                'avg_median_rate': np.mean(trace1_median_rates[i]),
                'is_common': (i < num_common_seg1)  # Present in all iterations
            }
            trace1_stats.append(stats)
    
    trace2_stats = []
    for i in range(max_seg2):
        if len(trace2_durations[i]) > 0:
            stats = {
                'segment_id': i,
                'avg_duration': np.mean(trace2_durations[i]),
                'avg_bytes': np.mean(trace2_bytes[i]),
                'avg_rate': np.mean(trace2_avg_rates[i]),
                'avg_median_rate': np.mean(trace2_median_rates[i]),
                'is_common': (i < num_common_seg2)  # Present in all iterations
            }
            trace2_stats.append(stats)
    
    # Summary statistics
    summary = {
        'trace1_name': trace1_name,
        'trace2_name': trace2_name,
        'num_common_segments_trace1': num_common_seg1,
        'num_common_segments_trace2': num_common_seg2,
        'avg_segments_trace1': np.mean(seg1_lens),
        'avg_segments_trace2': np.mean(seg2_lens)
    }
    
    return {
        'summary': summary,
        'trace1_stats': trace1_stats,
        'trace2_stats': trace2_stats,
    }

"""
Find the first segment where duration or average rate differs by more than the threshold.

Args:
    comparison_results: Dictionary returned by segment_analysis()
    duration_threshold: Percentage threshold for duration difference (default 5%)
    rate_threshold: Percentage threshold for rate difference (default 5%)

Returns:
    Dictionary with information about the first significant difference, or None if no difference found
"""
def find_first_significant_difference(comparison_results: Dict, 
                                      duration_threshold: float = 5.0,
                                      rate_threshold: float = 5.0) -> Dict:
    
    trace1_stats = comparison_results['trace1_stats']
    trace2_stats = comparison_results['trace2_stats']
    
    # Create lookup by segment_id for trace2
    trace2_lookup = {s['segment_id']: s for s in trace2_stats}
    
    for c1_stats in trace1_stats:
        seg_id = c1_stats['segment_id']
        if seg_id not in trace2_lookup:
            continue
        
        c2_stats = trace2_lookup[seg_id]
        
        # Calculate percentage differences
        if c1_stats['avg_duration'] > 0:
            duration_diff = abs((c2_stats['avg_duration'] - c1_stats['avg_duration']) / c1_stats['avg_duration'] * 100)
        else:
            duration_diff = 0
            
        if c1_stats['avg_rate'] > 0:
            rate_diff = abs((c2_stats['avg_rate'] - c1_stats['avg_rate']) / c1_stats['avg_rate'] * 100)
        else:
            rate_diff = 0
        
        if duration_diff > duration_threshold or rate_diff > rate_threshold:
            return {
                'segment_id': seg_id,
                'duration_pct_diff': (c2_stats['avg_duration'] - c1_stats['avg_duration']) / c1_stats['avg_duration'] * 100 if c1_stats['avg_duration'] > 0 else 0,
                'rate_pct_diff': (c2_stats['avg_rate'] - c1_stats['avg_rate']) / c1_stats['avg_rate'] * 100 if c1_stats['avg_rate'] > 0 else 0,
                'bytes_pct_diff': (c2_stats['avg_bytes'] - c1_stats['avg_bytes']) / c1_stats['avg_bytes'] * 100 if c1_stats['avg_bytes'] > 0 else 0,
                'exceeds_duration_threshold': duration_diff > duration_threshold,
                'exceeds_rate_threshold': rate_diff > rate_threshold,
                'trace1_stats': c1_stats,
                'trace2_stats': c2_stats
            }
    
    return None

"""
Visualize segment comparison between two traces.

Args:
    comparison_results: Dictionary returned by segment_analysis()
    filename: Output filename for the plot
"""
def visualize_segment_comparison(comparison_results: Dict,
                                 filename: str = "segment_comparison.png"):
    
    summary = comparison_results['summary']
    trace1_stats = comparison_results['trace1_stats']
    trace2_stats = comparison_results['trace2_stats']
    
    trace1_name = summary['trace1_name']
    trace2_name = summary['trace2_name']
    avg_seg1 = summary['avg_segments_trace1']
    avg_seg2 = summary['avg_segments_trace2']
    
    # Extract data for plotting
    c1_segment_ids = [s['segment_id'] for s in trace1_stats]
    c1_durations = [s['avg_duration'] for s in trace1_stats]
    c1_bytes = [s['avg_bytes'] for s in trace1_stats]
    c1_rates = [s['avg_rate'] for s in trace1_stats]
    c1_median_rates = [s['avg_median_rate'] for s in trace1_stats]
    c1_is_common = [s['is_common'] for s in trace1_stats]
    
    c2_segment_ids = [s['segment_id'] for s in trace2_stats]
    c2_durations = [s['avg_duration'] for s in trace2_stats]
    c2_bytes = [s['avg_bytes'] for s in trace2_stats]
    c2_rates = [s['avg_rate'] for s in trace2_stats]
    c2_median_rates = [s['avg_median_rate'] for s in trace2_stats]
    c2_is_common = [s['is_common'] for s in trace2_stats]
    
    # Create figure with 4 subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle(f'Segment Comparison: {trace1_name} (avg: {avg_seg1:.1f} segs) vs {trace2_name} (avg: {avg_seg2:.1f} segs)', 
                 fontsize=16, fontweight='bold')
    
    # Helper function to plot with conditional styling
    def plot_with_style(ax, x_data, y_data, is_common, label, color, marker):
        # First, plot a dotted line connecting all segments to ensure continuity
        ax.plot(x_data, y_data, color=color, linewidth=1, linestyle=':', alpha=0.4)
        
        # Then plot common segments with solid line and bold markers
        common_x = [x for x, c in zip(x_data, is_common) if c]
        common_y = [y for y, c in zip(y_data, is_common) if c]
        if common_x:
            ax.plot(common_x, common_y, marker=marker, color=color, 
                   linewidth=3, linestyle='-', label=f'{label} (common)', 
                   markersize=8, markeredgewidth=2)
        
        # Plot non-common segments with markers only (line already drawn)
        uncommon_x = [x for x, c in zip(x_data, is_common) if not c]
        uncommon_y = [y for y, c in zip(y_data, is_common) if not c]
        if uncommon_x:
            ax.plot(uncommon_x, uncommon_y, marker=marker, color=color, 
                   linewidth=0, linestyle='', label=f'{label} (not common)', 
                   markersize=6, alpha=0.7, markeredgewidth=1.5)
        
        # Add data labels above each point
        for x, y in zip(x_data, y_data):
            ax.annotate(f'{y:.1f}', 
                       xy=(x, y), 
                       xytext=(0, 5), 
                       textcoords='offset points',
                       ha='center', 
                       fontsize=8, 
                       color=color,
                       weight='bold')
    
    # Plot 1: Duration comparison
    ax1 = axes[0, 0]
    plot_with_style(ax1, c1_segment_ids, c1_durations, c1_is_common, 
                   trace1_name, 'tab:blue', 'o')
    plot_with_style(ax1, c2_segment_ids, c2_durations, c2_is_common, 
                   trace2_name, 'tab:orange', 's')
    ax1.set_xlabel('Segment ID')
    ax1.set_ylabel('Average Duration (ms)')
    ax1.set_title('Average Segment Duration')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Bytes transferred comparison
    ax2 = axes[0, 1]
    plot_with_style(ax2, c1_segment_ids, c1_bytes, c1_is_common, 
                   trace1_name, 'tab:blue', 'o')
    plot_with_style(ax2, c2_segment_ids, c2_bytes, c2_is_common, 
                   trace2_name, 'tab:orange', 's')
    ax2.set_xlabel('Segment ID')
    ax2.set_ylabel('Average Bytes Transferred')
    ax2.set_title('Average Bytes Transferred')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Rate comparison
    ax3 = axes[1, 0]
    plot_with_style(ax3, c1_segment_ids, c1_rates, c1_is_common, 
                   trace1_name, 'tab:blue', 'o')
    plot_with_style(ax3, c2_segment_ids, c2_rates, c2_is_common, 
                   trace2_name, 'tab:orange', 's')
    ax3.set_xlabel('Segment ID')
    ax3.set_ylabel('Average Rate (bytes/ms)')
    ax3.set_title('Average Rate')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Median rate comparison
    ax4 = axes[1, 1]
    plot_with_style(ax4, c1_segment_ids, c1_median_rates, c1_is_common, 
                   trace1_name, 'tab:blue', 'o')
    plot_with_style(ax4, c2_segment_ids, c2_median_rates, c2_is_common, 
                   trace2_name, 'tab:orange', 's')
    ax4.set_xlabel('Segment ID')
    ax4.set_ylabel('Average Median Rate (bytes/ms)')
    ax4.set_title('Average Median Rate')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Visualization saved to {filename}")