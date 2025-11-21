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
    print("\nSmoothing comparison saved as 'smoothing_comparison.png'")
    plt.show()


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
    print("\nSegmentation plot saved as 'tcp_segmentation.png'")
    plt.show()

def scenario_ideal_slowstart(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    rtts = np.linspace(0, 5, n_points)
    
    # Single phase: Perfect exponential growth (cwnd doubling every RTT)
    phase1_end = n_points
    cumulative_bytes = np.exp(rtts[:phase1_end] * 1.2) * 500
    
    # Add minimal measurement noise only
    noise = np.random.normal(0, 50, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_bandwidth_transition(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 4: Bandwidth Transition (e.g., WiFi to LTE handoff)
    Smooth transition from high bandwidth to lower bandwidth
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: High bandwidth phase (WiFi)
    phase1_end = 70
    bytes1 = (rtts[:phase1_end] ** 1.5) * 2000
    
    # Phase 2: Transition zone (handoff) - smooth sigmoid transition
    phase2_start = phase1_end
    phase2_end = 90
    transition_length = phase2_end - phase2_start
    transition = 1 / (1 + np.exp(-0.5 * (np.arange(transition_length) - transition_length/2)))
    high_rate = 6000
    low_rate = 2000
    transition_rate = high_rate + (low_rate - high_rate) * transition
    
    bytes2 = np.zeros(transition_length)
    for i in range(transition_length):
        idx = phase2_start + i
        if i == 0:
            bytes2[i] = bytes1[-1] + transition_rate[i] * (rtts[idx] - rtts[idx-1])
        else:
            bytes2[i] = bytes2[i-1] + transition_rate[i] * (rtts[idx] - rtts[idx-1])
    
    # Phase 3: Low bandwidth phase (LTE)
    phase3_start = phase2_end
    bytes3 = bytes2[-1] + (rtts[phase3_start:] - rtts[phase3_start]) * low_rate
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3])
    
    # Add moderate noise
    noise = np.random.normal(0, 600, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_buffer_bloat(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 3: Buffer Bloat
    Large buffer causes sustained high throughput but with variable ACK patterns
    """
    rtts = np.linspace(0, 8, n_points)
    
    # Phase 1: Initial ramp up (exponential)
    phase1_end = 40
    bytes1 = np.exp(rtts[:phase1_end] * 1.0) * 600
    
    # Phase 2: Sustained high throughput (buffer absorbing bursts)
    phase2_start = phase1_end
    bytes2 = bytes1[-1] + (rtts[phase2_start:] - rtts[phase2_start]) * 8000
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2])
    
    # Add bursty noise (ACK compression due to buffering)
    noise = np.random.normal(0, 1500, n_points)
    # Simulate ACK bursts
    burst_indices = np.random.choice(n_points, size=n_points//10, replace=False)
    noise[burst_indices] += np.random.uniform(2000, 5000, len(burst_indices))
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

# Staircase 
def scenario_staircase(n_points : int = 200):
    # Generate synthetic TCP trace data
    np.random.seed(42)
    
    # Simulate different phases
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: Slow start (exponential growth)
    phase1_end = 50
    bytes1 = np.exp(rtts[:phase1_end] * 0.5) * 1000
    
    # Phase 2: Congestion avoidance (linear growth)
    phase2_start = phase1_end
    phase2_end = 120
    bytes2 = bytes1[-1] + (rtts[phase2_start:phase2_end] - rtts[phase2_start]) * 5000
    
    # Phase 3: Rate reduction
    phase3_start = phase2_end
    phase3_end = 160
    bytes3 = bytes2[-1] + (rtts[phase3_start:phase3_end] - rtts[phase3_start]) * 2000
    
    # Phase 4: Recovery
    phase4_start = phase3_end
    bytes4 = bytes3[-1] + (rtts[phase4_start:] - rtts[phase4_start]) * 4500
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3, bytes4])
    
    # Add noise to simulate real TCP behavior
    noise = np.random.normal(0, 500, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)  # Ensure monotonic

    return rtts, cumulative_bytes

def scenario_congestion_avoidance(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 5: Classic Congestion Avoidance
    Linear growth with saw-tooth pattern from AIMD
    """
    rtts = np.linspace(0, 12, n_points)
    
    # Generate AIMD sawtooth pattern with multiple phases
    base_rate = 3000
    growth_rate = 100  # Additive increase per RTT
    segment_length = 40
    
    # Phase 1: First AIMD cycle
    phase1_end = segment_length
    bytes1 = np.zeros(phase1_end)
    for i in range(phase1_end):
        rate = base_rate + growth_rate * i
        if i == 0:
            bytes1[i] = rate * rtts[i]
        else:
            bytes1[i] = bytes1[i-1] + rate * (rtts[i] - rtts[i-1])
    
    # Phase 2: Second AIMD cycle (after multiplicative decrease)
    phase2_start = phase1_end
    phase2_end = phase2_start + segment_length
    bytes2 = np.zeros(segment_length)
    for i in range(segment_length):
        rate = base_rate + growth_rate * i
        idx = phase2_start + i
        if i == 0:
            bytes2[i] = bytes1[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes2[i] = bytes2[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Phase 3: Third AIMD cycle
    phase3_start = phase2_end
    phase3_end = phase3_start + segment_length
    bytes3 = np.zeros(segment_length)
    for i in range(segment_length):
        rate = base_rate + growth_rate * i
        idx = phase3_start + i
        if i == 0:
            bytes3[i] = bytes2[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes3[i] = bytes3[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Phase 4: Fourth AIMD cycle
    phase4_start = phase3_end
    phase4_end = phase4_start + segment_length
    bytes4 = np.zeros(segment_length)
    for i in range(segment_length):
        rate = base_rate + growth_rate * i
        idx = phase4_start + i
        if i == 0:
            bytes4[i] = bytes3[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes4[i] = bytes4[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Phase 5: Final partial cycle
    phase5_start = phase4_end
    remaining = n_points - phase5_start
    bytes5 = np.zeros(remaining)
    for i in range(remaining):
        rate = base_rate + growth_rate * i
        idx = phase5_start + i
        if i == 0:
            bytes5[i] = bytes4[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes5[i] = bytes5[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3, bytes4, bytes5])
    
    # Add realistic noise
    noise = np.random.normal(0, 500, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_rate_limited(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 6: Rate-Limited Connection
    Constant throughput (bottleneck link is fully utilized)
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: Initial ramp-up (exponential)
    phase1_end = 30
    bytes1 = np.exp(rtts[:phase1_end] * 0.7) * 700
    
    # Phase 2: Hit rate limit - perfectly constant throughput
    phase2_start = phase1_end
    rate_limit = 5000
    bytes2 = bytes1[-1] + (rtts[phase2_start:] - rtts[phase2_start]) * rate_limit
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2])
    
    # Add small amount of noise (jitter only)
    noise = np.random.normal(0, 200, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes


def scenario_competing_flows(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 7: Competing Flows
    Variable throughput due to competition with other TCP flows
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: Start alone - high throughput (exponential)
    phase1_end = 50
    bytes1 = np.exp(rtts[:phase1_end] * 0.9) * 700
    
    # Phase 2: Other flows join - throughput drops
    phase2_start = phase1_end
    phase2_end = 100
    bytes2 = bytes1[-1] + (rtts[phase2_start:phase2_end] - rtts[phase2_start]) * 3000
    
    # Phase 3: Some flows leave - throughput increases
    phase3_start = phase2_end
    phase3_end = 150
    bytes3 = bytes2[-1] + (rtts[phase3_start:phase3_end] - rtts[phase3_start]) * 5500
    
    # Phase 4: More competition - throughput drops again
    phase4_start = phase3_end
    bytes4 = bytes3[-1] + (rtts[phase4_start:] - rtts[phase4_start]) * 2500
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3, bytes4])
    
    # Add noise from competing traffic
    noise = np.random.normal(0, 800, n_points)
    # Random spikes from other flows
    spike_indices = np.random.choice(n_points, size=n_points//8, replace=False)
    noise[spike_indices] += np.random.uniform(-1500, 1500, len(spike_indices))
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes


def scenario_application_limited(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 8: Application Limited
    Application sends data in bursts (e.g., video streaming with GOP boundaries)
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Create bursty pattern (application sends frames in bursts)
    burst_size = 20
    idle_size = 10
    burst_rate = 8000
    idle_rate = 500
    
    cumulative_bytes = np.zeros(n_points)
    idx = 0
    
    while idx < n_points:
        # Burst phase
        burst_end = min(idx + burst_size, n_points)
        for i in range(idx, burst_end):
            if i == 0:
                cumulative_bytes[i] = burst_rate * rtts[i]
            else:
                cumulative_bytes[i] = cumulative_bytes[i-1] + burst_rate * (rtts[i] - rtts[i-1])
        idx = burst_end
        
        if idx >= n_points:
            break
        
        # Idle/low rate phase
        idle_end = min(idx + idle_size, n_points)
        for i in range(idx, idle_end):
            cumulative_bytes[i] = cumulative_bytes[i-1] + idle_rate * (rtts[i] - rtts[i-1])
        idx = idle_end
    
    # Add moderate noise
    noise = np.random.normal(0, 400, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes


def scenario_initial_burst_then_steady(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 9: Initial Burst then Steady State
    Large initial window (IW10) followed by steady state
    """
    rtts = np.linspace(0, 8, n_points)
    
    # Phase 1: Large initial burst (IW10 = 10 * MSS = 14600 bytes)
    phase1_end = 20
    bytes1 = np.exp(rtts[:phase1_end] * 1.5) * 500
    
    # Phase 2: Settle into steady state
    phase2_start = phase1_end
    bytes2 = bytes1[-1] + (rtts[phase2_start:] - rtts[phase2_start]) * 4500
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2])
    
    # Add noise
    noise = np.random.normal(0, 400, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)

    return rtts, cumulative_bytes


def scenario_mobile_varying_signal(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 10: Mobile with Varying Signal Strength
    Throughput varies as mobile device moves (fading channel)
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Create sinusoidal variation (signal strength varying)
    # Split into phases for consistency with format
    base_rate = 3500
    variation = 2000
    frequency = 2.0  # cycles over the trace
    
    # Generate as single phase with varying rate
    cumulative_bytes = np.zeros(n_points)
    for i in range(n_points):
        rate = base_rate + variation * np.sin(2 * np.pi * frequency * rtts[i] / rtts[-1])
        if i == 0:
            cumulative_bytes[i] = rate * rtts[i]
        else:
            cumulative_bytes[i] = cumulative_bytes[i-1] + rate * (rtts[i] - rtts[i-1])
    
    # Add significant noise (wireless channel)
    noise = np.random.normal(0, 1000, n_points)
    # Random deep fades
    fade_indices = np.random.choice(n_points, size=n_points//15, replace=False)
    noise[fade_indices] -= np.random.uniform(3000, 6000, len(fade_indices))
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

# Example usage
if __name__ == "__main__":
    rtts, cumulative_bytes = scenario_competing_flows(200)
    
    # Run segmentation with smoothing
    changepoints, time_points, smoothed = segment_trace(
        rtts, 
        cumulative_bytes,
        smooth_cumulative=True,
        cumulative_smooth_window=11,
        smooth_method='savgol',
        throughput_smooth_window=11,
        min_size=10,
        plot=True,
        plot_smoothing_comparison_flag=True
    )
    
    print(f"\nDetected {len(changepoints)} changepoints at indices: {changepoints}")
    if changepoints:
        print(f"Changepoint times: {[f'{time_points[cp]:.2f}' for cp in changepoints]}")