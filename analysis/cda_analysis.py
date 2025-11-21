#!/usr/bin/env python3
"""
Network Trace Segmentation using PELT Changepoint Detection

This script segments traces of cumulative bytes ACKed vs time into different 
protocol phases (slow start, congestion avoidance, rate changes) by applying 
PELT to the smoothed throughput (approximated by first derivative).
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
import ruptures as rpt
from typing import Tuple, List, Optional


def smooth_signal(signal: np.ndarray, method: str = 'savgol', 
                  window_length: int = 11, polyorder: int = 3,
                  moving_avg_window: int = 5) -> np.ndarray:
    """
    Smooth the signal to reduce noise.
    
    Args:
        signal: Input signal to smooth
        method: 'savgol' for Savitzky-Golay or 'moving_avg' for moving average
        window_length: Window length for Savitzky-Golay (must be odd)
        polyorder: Polynomial order for Savitzky-Golay
        moving_avg_window: Window size for moving average
    
    Returns:
        Smoothed signal
    """
    if len(signal) < 3:
        return signal
    
    if method == 'savgol':
        # Ensure window_length is odd and not larger than signal
        window_length = min(window_length, len(signal))
        if window_length % 2 == 0:
            window_length -= 1
        window_length = max(window_length, 3)
        
        # Ensure polyorder is less than window_length
        polyorder = min(polyorder, window_length - 1)
        
        return savgol_filter(signal, window_length=window_length, polyorder=polyorder)
    
    elif method == 'moving_avg':
        window = np.ones(moving_avg_window) / moving_avg_window
        return np.convolve(signal, window, mode='same')
    
    else:
        raise ValueError(f"Unknown smoothing method: {method}")


def compute_throughput(ts: np.ndarray, cumulative_bytes: np.ndarray, 
                      smooth_cumulative: bool = True,
                      smooth_method: str = 'savgol',
                      smooth_window: int = 11) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute instantaneous throughput from cumulative bytes.
    
    Args:
        ts: Time values (in RTTs or seconds)
        cumulative_bytes: Cumulative bytes ACKed at each time point
        smooth_cumulative: Whether to smooth cumulative bytes before differentiation
        smooth_method: Smoothing method ('savgol' or 'moving_avg')
        smooth_window: Window size for smoothing
    
    Returns:
        Tuple of (time_points, throughput, smoothed_cumulative) where time_points are centered
        between consecutive RTT measurements
    """
    if len(ts) != len(cumulative_bytes):
        raise ValueError("ts and cumulative_bytes must have the same length")
    
    if len(ts) < 2:
        raise ValueError("Need at least 2 data points")
    
    # Smooth cumulative bytes if requested
    if smooth_cumulative:
        smoothed_cumulative = smooth_signal(cumulative_bytes, 
                                           method=smooth_method, 
                                           window_length=smooth_window,
                                           moving_avg_window=smooth_window)
    else:
        smoothed_cumulative = cumulative_bytes
    
    # Compute differences
    dt = np.diff(ts)
    dbytes = np.diff(smoothed_cumulative)
    
    # Avoid division by zero
    dt = np.maximum(dt, 1e-10)
    
    # Throughput (bytes per time unit)
    throughput = dbytes / dt
    
    # Time points are centered between measurements
    time_points = (ts[:-1] + ts[1:]) / 2
    
    return time_points, throughput, smoothed_cumulative


def detect_changepoints(signal: np.ndarray, 
                       model: str = 'l2',
                       penalty: Optional[float] = None,
                       min_size: int = 10,
                       auto_penalty: bool = True) -> List[int]:
    """
    Detect changepoints using PELT algorithm.
    
    Args:
        signal: Input signal (should be smoothed throughput)
        model: Cost function ('l2', 'l1', or 'rbf')
        penalty: Penalty value (higher = fewer changepoints)
        min_size: Minimum segment size between changepoints
        auto_penalty: If True and penalty is None, automatically compute penalty
    
    Returns:
        List of changepoint indices
    """
    if len(signal) < min_size * 2:
        print(f"Warning: Signal too short for min_size={min_size}")
        min_size = max(2, len(signal) // 4)
    
    # Auto-compute penalty if not provided
    # Use BIC penalty: log(n) * 2 * variance
    if penalty is None and auto_penalty:
        variance = np.var(signal)
        n = len(signal)
        penalty = np.log(n) * 2 * variance
    elif penalty is None:  # Use default penalty
        penalty = 1.0
    
    # Fit PELT model
    algo = rpt.Pelt(model=model, min_size=min_size).fit(signal)
    
    # Detect changepoints
    changepoints = algo.predict(pen=penalty)
    
    # Remove the last point (i.e. the length of the signal)
    if changepoints and changepoints[-1] == len(signal):
        changepoints = changepoints[:-1]
    
    return changepoints


def plot_smoothing_comparison(rtts: np.ndarray,
                              cumulative_bytes: np.ndarray,
                              smoothed_cumulative: np.ndarray,
                              time_points: np.ndarray,
                              throughput_raw: np.ndarray,
                              throughput_smoothed: np.ndarray):
    """
    Visualize the effect of smoothing cumulative bytes before differentiation.
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Plot 1: Original cumulative bytes
    axes[0, 0].plot(rtts, cumulative_bytes, 'b-', linewidth=1.5, label='Original')
    axes[0, 0].set_xlabel('Time (RTTs)')
    axes[0, 0].set_ylabel('Cumulative Bytes')
    axes[0, 0].set_title('Cumulative Bytes ACKed - Original')
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].legend()
    
    # Plot 2: Smoothed cumulative bytes
    axes[0, 1].plot(rtts, cumulative_bytes, 'b-', alpha=0.3, linewidth=1, label='Original')
    axes[0, 1].plot(rtts, smoothed_cumulative, 'r-', linewidth=2, label='Smoothed')
    axes[0, 1].set_xlabel('Time (RTTs)')
    axes[0, 1].set_ylabel('Cumulative Bytes')
    axes[0, 1].set_title('Cumulative Bytes ACKed - Smoothed')
    axes[0, 1].grid(True, alpha=0.3)
    axes[0, 1].legend()
    
    # Plot 3: Throughput from original cumulative bytes
    axes[1, 0].plot(time_points, throughput_raw, 'g-', linewidth=1.5, label='From Original')
    axes[1, 0].set_xlabel('Time (RTTs)')
    axes[1, 0].set_ylabel('Throughput (bytes/time)')
    axes[1, 0].set_title('Throughput - Differentiated from Original')
    axes[1, 0].grid(True, alpha=0.3)
    axes[1, 0].legend()
    
    # Plot 4: Throughput from smoothed cumulative bytes
    axes[1, 1].plot(time_points, throughput_raw, 'g-', alpha=0.3, linewidth=1, label='From Original')
    axes[1, 1].plot(time_points, throughput_smoothed, 'b-', linewidth=2, label='From Smoothed')
    axes[1, 1].set_xlabel('Time (RTTs)')
    axes[1, 1].set_ylabel('Throughput (bytes/time)')
    axes[1, 1].set_title('Throughput - Comparison')
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].legend()
    
    plt.tight_layout()
    plt.savefig('smoothing_comparison.png', dpi=150, bbox_inches='tight')


def segment_trace(rtts: np.ndarray, 
                  cumulative_bytes: np.ndarray,
                  smooth_cumulative: bool = True,
                  cumulative_smooth_window: int = 11,
                  smooth_method: str = 'savgol',
                  throughput_smooth_window: int = 11,
                  model: str = 'l2',
                  penalty: Optional[float] = None,
                  min_size: int = 10,
                  plot: bool = True,
                  plot_smoothing_comparison_flag: bool = True) -> Tuple[List[int], np.ndarray, np.ndarray]:
    """
    Complete pipeline to segment TCP trace into phases.
    
    Args:
        rtts: Time values (RTTs or timestamps)
        cumulative_bytes: Cumulative bytes ACKed
        smooth_cumulative: Whether to smooth cumulative bytes before differentiation
        cumulative_smooth_window: Window size for smoothing cumulative bytes
        smooth_method: Smoothing method ('savgol' or 'moving_avg')
        throughput_smooth_window: Window size for smoothing throughput
        model: PELT cost function ('l2', 'l1', or 'rbf')
        penalty: Penalty for changepoint detection (None for auto)
        min_size: Minimum segment size
        plot: set to true to generate segmentation visualization
        plot_smoothing_comparison_flag: set to true to generate smoothing comparison
    Returns:
        Tuple of (changepoints, time_points, smoothed_throughput)
    """    
    # Compute throughput with and without cumulative smoothing for comparison
    time_points_raw, throughput_raw, _ = compute_throughput(rtts, cumulative_bytes, 
                                                            smooth_cumulative=False)
    
    time_points, throughput, smoothed_cumulative = compute_throughput(
        rtts, cumulative_bytes,
        smooth_cumulative=smooth_cumulative,
        smooth_method=smooth_method,
        smooth_window=cumulative_smooth_window
    )
    
    # Plot smoothing comparison if requested
    if plot_smoothing_comparison_flag:
        plot_smoothing_comparison(rtts, cumulative_bytes, smoothed_cumulative,
                                 time_points, throughput_raw, throughput)

    # Further smooth the throughput for changepoint detection
    smoothed_throughput = smooth_signal(throughput, method=smooth_method, 
                                       window_length=throughput_smooth_window,
                                       moving_avg_window=throughput_smooth_window)
    
    # Detect changepoints
    changepoints = detect_changepoints(smoothed_throughput, model=model, 
                                      penalty=penalty, min_size=min_size)
        
    # Plot segmentation if requested
    if plot:
        plot_segmentation(rtts, cumulative_bytes, time_points, throughput, 
                         smoothed_throughput, changepoints)

    return changepoints, time_points, smoothed_throughput


def plot_segmentation(rtts: np.ndarray, 
                     cumulative_bytes: np.ndarray,
                     time_points: np.ndarray,
                     throughput: np.ndarray,
                     smoothed: np.ndarray,
                     changepoints: List[int]):
    """
    Visualize the segmentation results.
    """
    fig, axes = plt.subplots(3, 1, figsize=(12, 10))
    
    # Plot 1: Cumulative bytes
    axes[0].plot(rtts, cumulative_bytes, 'b-', linewidth=1.5, label='Cumulative Bytes')
    axes[0].set_xlabel('Time (RTTs)')
    axes[0].set_ylabel('Cumulative Bytes')
    axes[0].set_title('Cumulative Bytes ACKed Over Time')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    
    # Add changepoint lines
    if changepoints:
        for cp in changepoints:
            # Map changepoint index back to original time
            cp_time = time_points[cp]
            axes[0].axvline(cp_time, color='r', linestyle='--', alpha=0.7, linewidth=1.5)
    
    # Plot 2: Raw throughput
    axes[1].plot(time_points, throughput, 'g-', alpha=0.5, linewidth=0.8, label='Raw Throughput')
    axes[1].plot(time_points, smoothed, 'b-', linewidth=2, label='Smoothed Throughput')
    axes[1].set_xlabel('Time (RTTs)')
    axes[1].set_ylabel('Throughput (bytes/time)')
    axes[1].set_title('Throughput Over Time')
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    
    # Add changepoint lines
    if changepoints:
        for cp in changepoints:
            axes[1].axvline(time_points[cp], color='r', linestyle='--', alpha=0.7, linewidth=1.5)
    
    # Plot 3: Segmented throughput with phase labels
    axes[2].plot(time_points, smoothed, 'b-', linewidth=1.5, label='Smoothed Throughput')
    
    if changepoints:
        # Color different segments
        colors = plt.cm.Set3(np.linspace(0, 1, len(changepoints) + 1))
        
        segment_starts = [0] + changepoints
        segment_ends = changepoints + [len(smoothed)]
        
        for i, (start, end) in enumerate(zip(segment_starts, segment_ends)):
            axes[2].axvspan(time_points[start], time_points[end-1], 
                          alpha=0.3, color=colors[i], label=f'Phase {i+1}')
            
            # Add changepoint lines
            if i < len(changepoints):
                axes[2].axvline(time_points[changepoints[i]], color='r', 
                              linestyle='--', linewidth=2, alpha=0.7)
    
    axes[2].set_xlabel('Time (RTTs)')
    axes[2].set_ylabel('Throughput (bytes/time)')
    axes[2].set_title('Segmented TCP Phases')
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(loc='best', ncol=2, fontsize=8)
    
    plt.tight_layout()
    plt.savefig('tcp_segmentation.png', dpi=150, bbox_inches='tight')