import pathlib
from typing import List, Tuple, Dict

import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from analysis.cda_analysis import Segment

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