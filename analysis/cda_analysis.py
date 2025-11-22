#!/usr/bin/env python3
"""
PELT-Based Rate Segmentation for TCP Traces

This script uses PELT changepoint detection on the rate signal to automatically
detect transitions between flat (rate≈0) and active (rate>0) periods.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from typing import Tuple, List, Optional, NamedTuple
import ruptures as rpt

"""Segment characteristics"""
class Segment(NamedTuple): 
    segment_id: int                 # index in array 
    start_idx: int                  # start index in rtts (inclusive)
    end_idx: int                    # end index in rtts (exclusive)
    rtts: np.ndarray                # rtts in segment
    cumulative_bytes: np.ndarray    # cumulative bytes ACKed in segment
    rates: np.ndarray               # rates (throughput) in segment
    duration_ms: float              # duration of segment in ms
    bytes_transferred: float        # total bytes transferred in segment
    avg_rate: float                 # average rate in segment
    median_rate: float              # median rate in segment
    num_points: int                 # number of points in segment

""" 
Smooth the signal to reduce noise, returning signal of same shape,
using Savitzky-Golay filter. 
"""
def smooth_signal(signal: np.ndarray, window_length: int = 11, polyorder: int = 3) -> np.ndarray:
    if len(signal) < 3:
        return signal

    window_length = min(window_length, len(signal))
    if window_length % 2 == 0:
        window_length -= 1
    window_length = max(window_length, 3)
    polyorder = min(polyorder, window_length - 1)
    return savgol_filter(signal, window_length=window_length, polyorder=polyorder)

"""
Compute local rate (slope) using a sliding window.
This gives us the instantaneous transfer rate at each point.
Returns rates, with same size as original signals.
"""
def compute_local_rate(rtts: np.ndarray, cumulative_bytes: np.ndarray, 
                       window_size: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    if len(rtts) < window_size:
        window_size = max(2, len(rtts) // 2)
    
    rates = np.zeros(len(rtts))
    for i in range(len(rtts)):
        # Define window around point i
        start = max(0, i - window_size // 2)
        end = min(len(rtts), i + window_size // 2 + 1)
        
        if end - start < 2:
            continue
        
        # Fit line through window points
        window_rtts = rtts[start:end]
        window_bytes = cumulative_bytes[start:end]
        
        # Compute slope (rate)
        if len(window_rtts) >= 2:
            dt = window_rtts[-1] - window_rtts[0]
            if dt > 0:
                dbytes = window_bytes[-1] - window_bytes[0]
                rates[i] = dbytes / dt
    
    return rates

"""
Use PELT on the rate signal to detect changepoints.

Args:
    rtts: Time values
    cumulative_bytes: Cumulative bytes
    smooth_window: Window for smoothing cumulative bytes
    rate_window: Window for computing local rate
    min_segment_length: Minimum segment size for PELT
    penalty: PELT penalty (None for auto)

Returns:
    List of changepoint indices
"""
def detect_rate_changepoints_pelt(rtts: np.ndarray, 
                                  cumulative_bytes: np.ndarray,
                                  smooth_window: int = 21,
                                  rate_window: int = 20,
                                  min_segment_length: int = 10,
                                  penalty: Optional[float] = None,
                                  penalty_factor: Optional[float] = None) -> List[int]:
    if len(rtts) < min_segment_length * 2:
        print("   WARNING: Trace too short for PELT segmentation.")
        return []
    
    # Smooth cumulative bytes
    smoothed_bytes = smooth_signal(cumulative_bytes, window_length=smooth_window)

    # Compute local rate
    rates = compute_local_rate(rtts, smoothed_bytes, window_size=rate_window)
    
    # Smooth the rate signal
    smoothed_rates = smooth_signal(rates, window_length=smooth_window)
    
    # Apply PELT to the rate signal
    if penalty is None:
        variance = np.var(smoothed_rates)
        if variance == 0:
            variance = 1.0
        n = len(smoothed_rates)
        if penalty_factor is None:
            penalty_factor = 2.0
        penalty = penalty_factor * np.log(n) * variance
    
    # Run PELT
    algo = rpt.Pelt(model='l2', min_size=min_segment_length).fit(smoothed_rates)
    changepoints = algo.predict(pen=penalty)
    
    # Remove the last point (is always length of signal)
    if changepoints and changepoints[-1] == len(smoothed_rates):
        changepoints = changepoints[:-1]
    
    print(f"   PELT detected {len(changepoints)} changepoints with penalty={penalty:.2f}")
    
    return changepoints, smoothed_rates

"""
Segment trace using PELT on the rate signal.

Returns:
    Tuple of (segments list, smoothed_rates array)
"""
def segment_trace_pelt(rtts: np.ndarray, 
                       cumulative_bytes: np.ndarray) -> List[Segment]:
    # Choose parameters based on trace length
    n = len(rtts)
    smooth_window = 21 if n > 200 else 11 if n > 20 else 3
    rate_window   = 20 if n > 200 else 11 if n > 20 else 3
    min_segment_length = 10 if n > 200 else 5 if n > 20 else 1
    penalty_factor = 2.0 if n > 200 else 1.0 if n > 20 else 0.001

    # Detect changepoints using PELT
    changepoints, smoothed_rates = detect_rate_changepoints_pelt(
        rtts, 
        cumulative_bytes,
        smooth_window=smooth_window,
        rate_window=rate_window,
        min_segment_length=min_segment_length,
        penalty=None,
        penalty_factor=penalty_factor
    )
    
    # Create segments
    segments = []
    segment_starts = [0] + changepoints
    segment_ends = changepoints + [len(rtts)]
    
    for seg_id, (start, end) in enumerate(zip(segment_starts, segment_ends)):
        if end - start < 1:
            continue
        
        seg_rtts = rtts[start:end + 1]
        seg_bytes = cumulative_bytes[start:end + 1]
        seg_rates = smoothed_rates[start:end + 1]
        
        # Compute segment characteristics
        duration = seg_rtts[-1] - seg_rtts[0]
        bytes_transferred = seg_bytes[-1] - seg_bytes[0]
        if duration > 0:
            avg_rate = bytes_transferred / duration
        else:
            avg_rate = 0        
        median_rate = np.median(seg_rates)

        segments.append(Segment(
            segment_id=seg_id,
            start_idx=start,    # inclusive
            end_idx=end + 1,    # exclusive
            rtts=seg_rtts,
            cumulative_bytes=seg_bytes,
            rates=seg_rates,
            duration_ms=duration,
            bytes_transferred=bytes_transferred,
            avg_rate=avg_rate,
            median_rate=median_rate,
            num_points=len(seg_rtts)
        ))
    
    return segments

"""
Plot the original trace with segment boundaries and save to file.

Args:
    rtts: Time values (in ms)
    cumulative_bytes: Cumulative bytes ACKed
    segments: List of Segment objects from segment_trace_pelt
    filename: Output filename for the plot
    title: Plot title
    figsize: Figure size
"""
def plot_segmented_trace(rtts: np.ndarray, 
                        cumulative_bytes: np.ndarray,
                        segments: List[Segment],
                        filename: str = "trace_segmentation.png",
                        title: str = "Network Trace Segmentation",
                        figsize: Tuple[int, int] = (14, 8)):
    
    _, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)
    
    # Top plot: Cumulative bytes with segment boundaries
    ax1.plot(rtts, cumulative_bytes, 'b-', linewidth=1.5, label='Cumulative Bytes')
    
    # Add vertical lines at segment boundaries
    colors = plt.cm.tab10(np.linspace(0, 1, len(segments)))
    for i, seg in enumerate(segments):
        # Draw vertical line at segment start
        ax1.axvline(x=seg.rtts[0], color=colors[i], linestyle='--', 
                   linewidth=2, alpha=0.7, label=f'Seg {seg.segment_id}')
        
        # Shade the segment region
        ax1.axvspan(seg.rtts[0], seg.rtts[-1], alpha=0.1, color=colors[i])
    
    # Mark the end of the last segment
    if segments:
        ax1.axvline(x=segments[-1].rtts[-1], color='red', linestyle='--', 
                   linewidth=2, alpha=0.7)
    
    ax1.set_ylabel('Cumulative Bytes', fontsize=12)
    ax1.set_title(title, fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left', fontsize=9, ncol=min(4, len(segments)))
    
    # Bottom plot: Instantaneous rate with segments
    ax2.set_xlabel('RTT (ms)', fontsize=12)
    ax2.set_ylabel('Rate (bytes/ms)', fontsize=12)
    
    for i, seg in enumerate(segments):
        # Plot rate for each segment
        ax2.plot(seg.rtts, seg.rates, color=colors[i], linewidth=2, 
                label=f'Seg {seg.segment_id}: {seg.avg_rate:.2f} B/ms avg')
        
        # Add vertical line at segment boundary
        ax2.axvline(x=seg.rtts[0], color=colors[i], linestyle='--', 
                   linewidth=2, alpha=0.7)
        
        # Shade the segment region
        ax2.axvspan(seg.rtts[0], seg.rtts[-1], alpha=0.1, color=colors[i])
    
    # Mark the end of the last segment
    if segments:
        ax2.axvline(x=segments[-1].rtts[-1], color='red', linestyle='--', 
                   linewidth=2, alpha=0.7)
    
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', fontsize=9, ncol=2)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Plot saved to {filename}")