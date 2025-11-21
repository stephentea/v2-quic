"""
Network configuration command generator for Linux tc (traffic control).

This module generates shell commands to configure network parameters using
Linux tc with HTB (Hierarchical Token Bucket) and netem (Network Emulator).
"""

import json
import os
import pathlib
from typing import Optional, TextIO

# Import the parser
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from pipeline.parse_params import NetworkProfile

# Constants
ROOT_TRAFFIC_RATE_LIMIT = 10000000.0  # 10 Gbps in Kbit
DEFAULT_INTERFACE = 'enp0s3'
IFB_INTERFACE = 'ifb0'
HTB_HANDLE = '1a64:'
NETEM_HANDLE = '2054:'

"""
Validate network profile parameters.

Args:
    profile: NetworkProfile to validate
    
Returns:
    True if valid, False otherwise
"""
def validate_profile(profile: NetworkProfile) -> bool:
    if profile.loss < 0 or profile.loss > 100:
        print(f"Error: loss must be between 0 and 100, got {profile.loss}")
        return False
    if profile.delay < 0:
        print(f"Error: delay must be non-negative, got {profile.delay}")
        return False
    if profile.bw <= 0:
        print(f"Error: bandwidth must be positive, got {profile.bw}")
        return False
    if profile.jitter < 0:
        print(f"Error: jitter must be non-negative, got {profile.jitter}")
        return False
    return True

"""
Generate commands to clean up existing tc configurations.

Args:
    interface: Network interface to clean up

Returns:
    List of cleanup command strings
"""
def generate_cleanup_cmds(interface: str = DEFAULT_INTERFACE) -> list[str]:
    
    cmds = []
    
    # Delete existing qdiscs (suppress errors if they don't exist)
    cmds.append(f'sudo /sbin/tc qdisc del dev {interface} root 2>/dev/null || true')
    cmds.append(f'sudo /sbin/tc qdisc del dev {interface} ingress 2>/dev/null || true')
    cmds.append(f'sudo /sbin/tc qdisc del dev {IFB_INTERFACE} root 2>/dev/null || true')
    
    # Remove IFB interface
    cmds.append(f'sudo /usr/bin/ip link set dev {IFB_INTERFACE} down 2>/dev/null || true')
    cmds.append(f'sudo /usr/bin/ip link delete {IFB_INTERFACE} type ifb 2>/dev/null || true')
    
    return cmds

"""
Generate commands for egress (outgoing) traffic shaping.

Args:
    profile: Network profile parameters
    interface: Network interface

Returns:
    List of command strings
"""
def generate_egress_cmds(profile: NetworkProfile, 
                         interface: str = DEFAULT_INTERFACE) -> list[str]:
    cmds = []
    
    # Build netem parameter string
    netem_params = []
    if profile.loss != 0:
        netem_params.append(f'loss {profile.loss:.6f}%')
    if profile.burst_egress != 0:
        netem_params.append(f'{profile.burst_egress}%')
    if profile.delay != 0:
        netem_params.append(f'delay {profile.delay//2}.0ms')
    if profile.jitter != 0:
        netem_params.append(f'{profile.jitter}.0ms')
    
    netem_str = ' ' + ' '.join(netem_params) if netem_params else ''
    
    # Calculate bandwidth parameters
    bw_str = f'{profile.bw}000.0Kbit'
    bw_burst = profile.bw * 10**3 * 1.25
    bw_burst_str = f'{bw_burst:.1f}KB'
    
    # Setup HTB qdisc on root
    cmds.append(
        f'sudo /sbin/tc qdisc add dev {interface} root handle {HTB_HANDLE} htb default 1'
    )
    
    # Create root HTB class
    cmds.append(
        f'sudo /sbin/tc class add dev {interface} parent {HTB_HANDLE} '
        f'classid {HTB_HANDLE}1 htb rate {ROOT_TRAFFIC_RATE_LIMIT}kbit'
    )
    
    # Create HTB class with configured bandwidth
    cmds.append(
        f'sudo /sbin/tc class add dev {interface} parent {HTB_HANDLE} '
        f'classid {HTB_HANDLE}104 htb rate {bw_str} ceil {bw_str} '
        f'burst {bw_burst_str} cburst {bw_burst_str}'
    )
    
    # Attach netem qdisc
    cmds.append(
        f'sudo /sbin/tc qdisc add dev {interface} parent {HTB_HANDLE}104 '
        f'handle {NETEM_HANDLE} netem{netem_str}'
    )
    
    # Add filter to direct traffic
    cmds.append(
        f'sudo /sbin/tc filter add dev {interface} protocol ip parent {HTB_HANDLE} '
        f'prio 5 u32 match ip dst 0.0.0.0/0 match ip src 0.0.0.0/0 '
        f'flowid {HTB_HANDLE}104'
    )
    
    return cmds

"""
Generate commands for ingress (incoming) traffic shaping using IFB.

Args:
    profile: Network profile parameters
    interface: Network interface

Returns:
    List of command strings
"""
def generate_ingress_cmds(profile: NetworkProfile, 
                          interface: str = DEFAULT_INTERFACE) -> list[str]:
    cmds = []
    
    # Build netem parameter string
    netem_params = []
    if profile.loss != 0:
        netem_params.append(f'loss {profile.loss:.6f}%')
    if profile.burst_ingress != 0:
        netem_params.append(f'{profile.burst_ingress}%')
    
    netem_str = ' ' + ' '.join(netem_params) if netem_params else ''
    
    # Calculate bandwidth parameters
    bw_str = f'{profile.bw}000.0Kbit'
    bw_burst = profile.bw * 10**3 * 1.25
    bw_burst_str = f'{bw_burst:.1f}KB'
    
    # Setup IFB device
    cmds.append('modprobe ifb')
    cmds.append(f'sudo /usr/bin/ip link add {IFB_INTERFACE} type ifb')
    cmds.append(f'sudo /usr/bin/ip link set dev {IFB_INTERFACE} up')
    
    # Add ingress qdisc and redirect to IFB
    cmds.append(f'sudo /sbin/tc qdisc add dev {interface} ingress')
    cmds.append(
        f'sudo /sbin/tc filter add dev {interface} parent ffff: '
        f'protocol ip u32 match u32 0 0 flowid {HTB_HANDLE} '
        f'action mirred egress redirect dev {IFB_INTERFACE}'
    )
    
    # Setup HTB on IFB
    cmds.append(
        f'sudo /sbin/tc qdisc add dev {IFB_INTERFACE} root handle {HTB_HANDLE} htb default 1'
    )
    
    cmds.append(
        f'sudo /sbin/tc class add dev {IFB_INTERFACE} parent {HTB_HANDLE} '
        f'classid {HTB_HANDLE}1 htb rate {ROOT_TRAFFIC_RATE_LIMIT}kbit'
    )
    
    cmds.append(
        f'sudo /sbin/tc class add dev {IFB_INTERFACE} parent {HTB_HANDLE} '
        f'classid {HTB_HANDLE}104 htb rate {bw_str} ceil {bw_str} '
        f'burst {bw_burst_str} cburst {bw_burst_str}'
    )
    
    cmds.append(
        f'sudo /sbin/tc qdisc add dev {IFB_INTERFACE} parent {HTB_HANDLE}104 '
        f'handle {NETEM_HANDLE} netem{netem_str}'
    )
    
    cmds.append(
        f'sudo /sbin/tc filter add dev {IFB_INTERFACE} protocol ip parent {HTB_HANDLE} '
        f'prio 5 u32 match ip dst 0.0.0.0/0 match ip src 0.0.0.0/0 '
        f'flowid {HTB_HANDLE}104'
    )
    
    return cmds

"""
Generate shell commands for network parameters from config file.

Args:
    config_file: JSON file containing network parameters
    interface: Network interface to configure

Returns:
    List of command strings, or None if error occurred
"""
def generate_cmds(profile: NetworkProfile, 
                  interface: str = DEFAULT_INTERFACE) -> Optional[list[str]]:
    if not validate_profile(profile):
        return None
    
    # Generate all commands
    cmds = []
    cmds.extend(generate_cleanup_cmds(interface))
    cmds.extend(generate_egress_cmds(profile, interface))
    cmds.extend(generate_ingress_cmds(profile, interface))
    return cmds
