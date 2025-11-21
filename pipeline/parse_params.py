#!/usr/bin/env python3
"""
parse-params.py - Parse network experiment configuration file
"""

import json
import sys
from typing import Dict, List, NamedTuple, Optional

"""Client configuration"""
class Client(NamedTuple): 
    name: str        # client name
    exec_path: str   # exec path
    is_h3: bool      # true iff client is H3

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
    name: str
    endpoint: str
    clients: List[str]
    iterations: int
    profile: NetworkProfile

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
        
        client_dict[client_name] = Client(
            name=client_name,
            exec_path=exec_path,
            is_h3=is_h3
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
        
        experiment = Experiment(
            name=exp.get('name', ''),
            endpoint=exp.get('endpoint', ''),
            clients=exp.get('clients', []),
            iterations=exp.get('iterations', 1),
            profile=profile
        )
        
        experiment_dict[experiment.name] = experiment
    
    return client_dict, experiment_dict
