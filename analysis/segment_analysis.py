import pathlib
from typing import List, Tuple, Dict
import numpy as np
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from analysis.cda_analysis import Segment

"""
Compare segments between two clients across multiple runs.

Args:
    segments1: List of segment lists for client 1 (one list per run)
    segments2: List of segment lists for client 2 (one list per run)
    client1_name: Name of client 1
    client2_name: Name of client 2

Returns:
    Dictionary containing comparison results
"""
def segment_analysis(segments1: List[List[Segment]], segments2: List[List[Segment]], 
                     client1_name: str = "Client 1", client2_name: str = "Client 2"):
    # Compare average number of segments
    seg1_lens = [len(segment) for segment in segments1]
    seg2_lens = [len(segment) for segment in segments2]
    avg_seg1_len = sum(seg1_lens) / len(seg1_lens)
    avg_seg2_len = sum(seg2_lens) / len(seg2_lens)
    
    # Find minimum segment length across all runs for both clients
    min_seg_len = min(min(seg1_lens), min(seg2_lens))
    
    # Initialize storage for per-segment statistics
    client1_durations    = {i: [] for i in range(min_seg_len)}
    client1_avg_rates    = {i: [] for i in range(min_seg_len)}
    client1_median_rates = {i: [] for i in range(min_seg_len)}
    client1_bytes        = {i: [] for i in range(min_seg_len)}
    
    client2_durations    = {i: [] for i in range(min_seg_len)}
    client2_avg_rates    = {i: [] for i in range(min_seg_len)}
    client2_median_rates = {i: [] for i in range(min_seg_len)}
    client2_bytes        = {i: [] for i in range(min_seg_len)}
    
    # Collect segment statistics for client 1
    for segments in segments1:
        for i in range(min_seg_len):
            segment = segments[i]
            client1_durations[i].append(segment.duration_ms)
            client1_avg_rates[i].append(segment.avg_rate)
            client1_median_rates[i].append(segment.median_rate)
            client1_bytes[i].append(segment.bytes_transferred)
    
    # Collect segment statistics for client 2
    for segments in segments2:
        for i in range(min_seg_len):
            segment = segments[i]
            client2_durations[i].append(segment.duration_ms)
            client2_avg_rates[i].append(segment.avg_rate)
            client2_median_rates[i].append(segment.median_rate)
            client2_bytes[i].append(segment.bytes_transferred)
    
    # Compute statistics for each segment position
    segment_stats = []
    for i in range(min_seg_len):
        stats = {
            'segment_id': i,
            'client1': {
                'avg_duration': np.mean(client1_durations[i]),
                'std_duration': np.std(client1_durations[i]),
                'avg_rate_mean': np.mean(client1_avg_rates[i]),
                'std_rate_mean': np.std(client1_avg_rates[i]),
                'avg_rate_median': np.mean(client1_median_rates[i]),
                'std_rate_median': np.std(client1_median_rates[i]),
                'avg_bytes': np.mean(client1_bytes[i]),
                'std_bytes': np.std(client1_bytes[i]),
            },
            'client2': {
                'avg_duration': np.mean(client2_durations[i]),
                'std_duration': np.std(client2_durations[i]),
                'avg_rate_mean': np.mean(client2_avg_rates[i]),
                'std_rate_mean': np.std(client2_avg_rates[i]),
                'avg_rate_median': np.mean(client2_median_rates[i]),
                'std_rate_median': np.std(client2_median_rates[i]),
                'avg_bytes': np.mean(client2_bytes[i]),
                'std_bytes': np.std(client2_bytes[i]),
            }
        }
        
        # Compute differences and percentage differences
        stats['diff_duration'] = stats['client2']['avg_duration'] - stats['client1']['avg_duration']
        stats['pct_diff_duration'] = (stats['diff_duration'] / stats['client1']['avg_duration']) * 100 if stats['client1']['avg_duration'] > 0 else 0
        
        stats['diff_rate'] = stats['client2']['avg_rate_mean'] - stats['client1']['avg_rate_mean']
        stats['pct_diff_rate'] = (stats['diff_rate'] / stats['client1']['avg_rate_mean']) * 100 if stats['client1']['avg_rate_mean'] > 0 else 0
        
        stats['diff_bytes'] = stats['client2']['avg_bytes'] - stats['client1']['avg_bytes']
        stats['pct_diff_bytes'] = (stats['diff_bytes'] / stats['client1']['avg_bytes']) * 100 if stats['client1']['avg_bytes'] > 0 else 0
        
        segment_stats.append(stats)
    
    # Summary statistics
    summary = {
        'client1_name': client1_name,
        'client2_name': client2_name,
        'avg_num_segments_client1': avg_seg1_len,
        'std_num_segments_client1': np.std(seg1_lens),
        'avg_num_segments_client2': avg_seg2_len,
        'std_num_segments_client2': np.std(seg2_lens),
        'min_common_segments': min_seg_len,
        'diff_num_segments': avg_seg1_len - avg_seg2_len,
        'pct_diff_num_segments': ((avg_seg2_len - avg_seg1_len) / avg_seg1_len) * 100 if avg_seg1_len > 0 else 0,
    }
    
    return {
        'summary': summary,
        'segment_stats': segment_stats,
        'raw_data': {
            'client1_durations': client1_durations,
            'client1_avg_rates': client1_avg_rates,
            'client1_median_rates': client1_median_rates,
            'client1_bytes': client1_bytes,
            'client2_durations': client2_durations,
            'client2_avg_rates': client2_avg_rates,
            'client2_median_rates': client2_median_rates,
            'client2_bytes': client2_bytes,
        }
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
    
    segment_stats = comparison_results['segment_stats']
    
    for stats in segment_stats:
        duration_diff = abs(stats['pct_diff_duration'])
        rate_diff = abs(stats['pct_diff_rate'])
        
        if duration_diff > duration_threshold or rate_diff > rate_threshold:
            return {
                'segment_id': stats['segment_id'],
                'duration_pct_diff': stats['pct_diff_duration'],
                'rate_pct_diff': stats['pct_diff_rate'],
                'bytes_pct_diff': stats['pct_diff_bytes'],
                'exceeds_duration_threshold': duration_diff > duration_threshold,
                'exceeds_rate_threshold': rate_diff > rate_threshold,
                'client1_stats': stats['client1'],
                'client2_stats': stats['client2']
            }
    
    return None

"""
Visualize segment comparison between two clients.

Args:
    comparison_results: Dictionary returned by segment_analysis()
    filename: Output filename for the plot
"""
def visualize_segment_comparison(comparison_results: Dict,
                                 filename: str = "segment_comparison.png"):
    
    summary = comparison_results['summary']
    segment_stats = comparison_results['segment_stats']
    
    client1_name = summary['client1_name']
    client2_name = summary['client2_name']
    
    # Extract data for plotting
    segment_ids = [s['segment_id'] for s in segment_stats]
    
    # Client 1 data
    c1_durations = [s['client1']['avg_duration'] for s in segment_stats]
    c1_duration_stds = [s['client1']['std_duration'] for s in segment_stats]
    c1_rates = [s['client1']['avg_rate_mean'] for s in segment_stats]
    c1_rate_stds = [s['client1']['std_rate_mean'] for s in segment_stats]
    c1_bytes = [s['client1']['avg_bytes'] for s in segment_stats]
    c1_byte_stds = [s['client1']['std_bytes'] for s in segment_stats]
    
    # Client 2 data
    c2_durations = [s['client2']['avg_duration'] for s in segment_stats]
    c2_duration_stds = [s['client2']['std_duration'] for s in segment_stats]
    c2_rates = [s['client2']['avg_rate_mean'] for s in segment_stats]
    c2_rate_stds = [s['client2']['std_rate_mean'] for s in segment_stats]
    c2_bytes = [s['client2']['avg_bytes'] for s in segment_stats]
    c2_byte_stds = [s['client2']['std_bytes'] for s in segment_stats]
    
    # Percentage differences
    pct_diff_duration = [s['pct_diff_duration'] for s in segment_stats]
    pct_diff_rate = [s['pct_diff_rate'] for s in segment_stats]
    pct_diff_bytes = [s['pct_diff_bytes'] for s in segment_stats]
    
    # Create figure with subplots
    fig, axes = plt.subplots(3, 2, figsize=(16, 10))
    fig.suptitle(f'Segment Comparison: {client1_name} vs {client2_name}', 
                 fontsize=16, fontweight='bold')
    
    # Plot 1: Duration comparison
    ax1 = axes[0, 0]
    ax1.errorbar(segment_ids, c1_durations, yerr=c1_duration_stds, 
                 marker='o', label=client1_name, capsize=5, linewidth=2)
    ax1.errorbar(segment_ids, c2_durations, yerr=c2_duration_stds, 
                 marker='s', label=client2_name, capsize=5, linewidth=2)
    ax1.set_xlabel('Segment ID')
    ax1.set_ylabel('Duration (ms)')
    ax1.set_title('Segment Duration Comparison')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Duration percentage difference
    ax2 = axes[0, 1]
    colors = ['green' if abs(d) <= 5 else 'red' for d in pct_diff_duration]
    ax2.bar(segment_ids, pct_diff_duration, color=colors, alpha=0.7)
    ax2.axhline(y=5, color='red', linestyle='--', linewidth=1, label='±5% threshold')
    ax2.axhline(y=-5, color='red', linestyle='--', linewidth=1)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax2.set_xlabel('Segment ID')
    ax2.set_ylabel('% Difference')
    ax2.set_title(f'Duration % Diff ({client2_name} vs {client1_name})')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Rate comparison
    ax3 = axes[1, 0]
    ax3.errorbar(segment_ids, c1_rates, yerr=c1_rate_stds, 
                 marker='o', label=client1_name, capsize=5, linewidth=2)
    ax3.errorbar(segment_ids, c2_rates, yerr=c2_rate_stds, 
                 marker='s', label=client2_name, capsize=5, linewidth=2)
    ax3.set_xlabel('Segment ID')
    ax3.set_ylabel('Average Rate (bytes/ms)')
    ax3.set_title('Segment Rate Comparison')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Rate percentage difference
    ax4 = axes[1, 1]
    colors = ['green' if abs(r) <= 5 else 'red' for r in pct_diff_rate]
    ax4.bar(segment_ids, pct_diff_rate, color=colors, alpha=0.7)
    ax4.axhline(y=5, color='red', linestyle='--', linewidth=1, label='±5% threshold')
    ax4.axhline(y=-5, color='red', linestyle='--', linewidth=1)
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax4.set_xlabel('Segment ID')
    ax4.set_ylabel('% Difference')
    ax4.set_title(f'Rate % Diff ({client2_name} vs {client1_name})')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    # Plot 5: Bytes transferred comparison
    ax5 = axes[2, 0]
    ax5.errorbar(segment_ids, c1_bytes, yerr=c1_byte_stds, 
                 marker='o', label=client1_name, capsize=5, linewidth=2)
    ax5.errorbar(segment_ids, c2_bytes, yerr=c2_byte_stds, 
                 marker='s', label=client2_name, capsize=5, linewidth=2)
    ax5.set_xlabel('Segment ID')
    ax5.set_ylabel('Bytes Transferred')
    ax5.set_title('Bytes Transferred Comparison')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    
    # Plot 6: Bytes percentage difference
    ax6 = axes[2, 1]
    colors = ['green' if abs(b) <= 5 else 'red' for b in pct_diff_bytes]
    ax6.bar(segment_ids, pct_diff_bytes, color=colors, alpha=0.7)
    ax6.axhline(y=5, color='red', linestyle='--', linewidth=1, label='±5% threshold')
    ax6.axhline(y=-5, color='red', linestyle='--', linewidth=1)
    ax6.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax6.set_xlabel('Segment ID')
    ax6.set_ylabel('% Difference')
    ax6.set_title(f'Bytes % Diff ({client2_name} vs {client1_name})')
    ax6.legend()
    ax6.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Visualization saved to {filename}")