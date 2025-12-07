#!/usr/bin/env python3
"""
parse-params.py - Parse network experiment configuration file
"""

import json
import sys
from typing import Dict, List, NamedTuple, Optional
from enum import Enum

class LogType(Enum):
    PCAP = 0
    QLOG = 1
    SQLOG = 2
    NETLOG = 3

"""Client configuration"""
class Client(NamedTuple): 
    name: str        # client name
    exec_path: str   # exec path
    is_h3: bool      # true iff client is H3
    logtype: LogType # file type of log file
    uses_pcap: bool  # true iff client uses PCAP for logs

"""Network profile for tc"""
class NetworkProfile(NamedTuple):
    loss: float          # percentage loss 
    delay: int           # delay (in ms)
    bw: int              # bandwidth
    jitter: float        # jitter (in ms), i.e. delay +/- jitter
    burst_ingress: int   # burst size for ingress queue
    burst_egress: int    # burst size for egress queue

"""Experiment configuration"""
class Experiment(NamedTuple):
    name: str                # experiment name 
    endpoints: List[str]     # endpoints (must be 1 or more)
    clients: List[str]       # client names (must be 1 or more)
    iterations: int          # number of iterations for each client/endpoint
    interface: str           # network interface (ex: eth0, enp0s3)
    profile: NetworkProfile  # network profile (loss/bandwidth/delay/jitter)
    mode: str                # 'multi_client' or 'multi_endpoint'

"""
Parse the JSON parameter file and create client and experiment dictionaries.

Args:
    json_file: Path to the JSON configuration file
    
Returns:
    Tuple of (client_dict, experiment_dict)
    - client_dict:     Maps client name     -> Client object
    - experiment_dict: Maps experiment name -> Experiment object
"""
def parse_params(json_file: str) -> tuple[Dict[str, Client], Dict[str, Experiment]]:
    
    with open(json_file, 'r') as f:
        config = json.load(f)
    
    # Parse clients
    client_dict = {}
    client_names = config.get('clients', [])
    client_exec_paths = config.get('client-exec-paths', {})
    
    for client_name in client_names:
        exec_path = client_exec_paths.get(client_name, '')
        is_h3 = 'h3' in client_name.lower()
        match client_name:
            case "curl_h2":     logtype = LogType.PCAP
            case "chrome_h2":   logtype = LogType.NETLOG
            case "chrome_h3":   logtype = LogType.NETLOG
            case "ngtcp2_h3":   logtype = LogType.SQLOG
            case "proxygen_h3": logtype = LogType.QLOG
            case _: assert(0) 
        
        uses_pcap: bool = (logtype == LogType.PCAP)
        
        client_dict[client_name] = Client(
            name=client_name,
            exec_path=exec_path,
            is_h3=is_h3,
            logtype=logtype,
            uses_pcap=uses_pcap
        )
    
    # Parse experiments
    experiment_dict = {}
    experiments = config.get('experiments', [])
    
    for exp in experiments:
        profile_data = exp.get('profile', {})
        profile = NetworkProfile(
            loss=profile_data.get('loss', 0),
            delay=profile_data.get('delay', 0),
            bw=profile_data.get('bw', 0),
            jitter=profile_data.get('jitter', 0),
            burst_ingress=profile_data.get('burst_ingress', 0),
            burst_egress=profile_data.get('burst_egress', 0)
        )

        endpoints = exp.get('endpoints', [])
        clients_list = exp.get('clients', [])

        # Validate: exactly one must be multi-valued
        num_endpoints = len(endpoints)
        num_clients = len(clients_list)
        if num_endpoints > 1 and num_clients > 1:
            raise ValueError(
                f"Experiment '{exp.get('name')}': Cannot specify multiple endpoints AND multiple clients. Choose one or the other."
            )

        # Determine mode
        if num_endpoints > 1:
            mode = 'multi_endpoint'
        else:
            mode = 'multi_client'
        
        experiment = Experiment(
            name=exp.get('name', ''),
            endpoints = endpoints,
            clients=clients_list,
            iterations=exp.get('iterations', 1),
            interface=exp.get('interface', ''),
            profile=profile,
            mode=mode
        )
        
        experiment_dict[experiment.name] = experiment
    
    return client_dict, experiment_dict
