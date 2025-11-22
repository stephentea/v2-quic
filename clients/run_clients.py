#!/usr/bin/env python3
"""
Network performance benchmarking client runner.

This module runs HTTP/2 and HTTP/3 clients against specified endpoints,
captures packet traces (tshark for H2, qlogs for H3), and saves results.
"""

import os
import json
import time
import pathlib
import subprocess
import shutil
from urllib.parse import urlparse
from typing import Optional

# Import other modules
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from pipeline.parse_params import Client, Experiment
from network.generate_cmds import generate_cmds

# Directories
ROOT_DIR = pathlib.Path(__file__).parent.parent.absolute()
DATA_PATH = ROOT_DIR / 'data'
TMP_DIR = DATA_PATH / 'tmp'
TMP_QLOG = TMP_DIR / 'qlog'
TMP_PCAP = TMP_DIR / 'pcap'
QLOG_DIR = DATA_PATH / 'qlogs'
PCAP_DIR = DATA_PATH / 'pcaps'
SSL_KEY_LOG_FILE = TMP_DIR / 'sslkeylog'

DIRS = [TMP_DIR, TMP_QLOG, TMP_PCAP, QLOG_DIR, PCAP_DIR]

# Timing constants
PCAP_START_DELAY = 2.0
PCAP_STOP_DELAY = 1.0


def make_dirs(dirs: list[pathlib.Path]) -> None:
    """Create directories if they don't exist."""
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)


def remove_files(dirname: pathlib.Path) -> None:
    """Remove all files in a directory."""
    if not dirname.exists():
        return
    
    for filename in os.listdir(dirname):
        file_path = dirname / filename
        try:
            if file_path.is_file() or file_path.is_symlink():
                file_path.unlink()
            elif file_path.is_dir():
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')


def parse_url(url: str) -> tuple[str, str, str]:
    """Parse URL into host, port, and path components."""
    url_obj = urlparse(url)
    url_host = url_obj.netloc
    url_path = url_obj.path or '/'
    
    if ':' in url_host:
        url_host, url_port = url_host.split(':')
    else:
        url_port = '443'
    
    return url_host, url_port, url_path


def prepare_environment() -> dict:
    """Prepare OS environment for capturing TLS keys."""
    env = os.environ.copy()
    env['SSLKEYLOGFILE'] = str(SSL_KEY_LOG_FILE)
    return env


def record_pcap(url_host: str, interface: str = 'enp0s3') -> subprocess.Popen:
    """Start capturing packets with tshark for H2 clients."""
    pcap_file = TMP_PCAP / 'out.pcapng'
    
    cmd = [
        'tshark',
        '-i', interface,
        '-f', f'host {url_host} and tcp',
        '-w', str(pcap_file)
    ]
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(PCAP_START_DELAY)
        return process
    except FileNotFoundError:
        raise RuntimeError("tshark not found. Please install wireshark/tshark.")


def parse_pcap_to_json(client: str, iteration: int, output_dir: pathlib.Path) -> str:
    """Convert pcap file to JSON format using tshark and save to output directory."""
    pcap_file = TMP_PCAP / 'out.pcapng'
    json_file = output_dir / f'{client}_{iteration}.json'
    
    cmd = [
        'tshark',
        '-r', str(pcap_file),
        '-T', 'json',
        '-o', f'tls.keylog_file: {SSL_KEY_LOG_FILE}',
        '-J', 'tcp http2'
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=True
        )
        
        # Save raw JSON output to preserve duplicate keys
        with open(json_file, 'w') as f:
            f.write(result.stdout.decode())

        return json_file
    
    except subprocess.CalledProcessError as e:
        print(f"Error parsing pcap: {e.stderr.decode()}")
        raise
    except Exception as e:
        print(f"Unexpected error parsing pcap: {e}")
        raise


def build_client_command(client: Client, url: str, qlog_dir: Optional[pathlib.Path] = None) -> list[str]:
    """Build command for running a client."""
    url_host, url_port, url_path = parse_url(url)
    
    exec_path = client.exec_path
    
    if client.name == 'curl_h2':
        return ['curl', '-o', '/dev/null', '-s', '--http2', url]
    
    elif client.is_h3:
        # For H3 clients, add qlog directory parameter
        cmd = [exec_path]
        
        if 'proxygen' in client.name.lower():
            cmd.extend([
                '--mode=client',
                f'--host={url_host}',
                f'--port={url_port}',
                f'--path={url_path}',
                '--httpversion=1.1',
                '--log_response=false'
            ])
            if qlog_dir:
                cmd.append(f'--qlogger_path={qlog_dir}')
        
        elif 'ngtcp2' in client.name.lower():
            cmd.extend([
                '--quiet',
                '--exit-on-all-streams-close',
                url_host,
                url_port,
                url
            ])
            if qlog_dir:
                cmd.append(f'--qlog-dir={qlog_dir}')
        
        return cmd
    
    else:
        # Other H2 clients
        return [exec_path, url]


def run_iteration(client: Client, url: str, iteration: int, 
                  qlog_output_dir: Optional[pathlib.Path] = None,
                  pcap_output_dir: Optional[pathlib.Path] = None) -> str:
    """Run a single iteration of a client request."""
    url_host, url_port, url_path = parse_url(url)
    
    env = prepare_environment()
    pcap_process = None
    
    try:
        # For H2 clients, start packet capture
        if not client.is_h3:
            remove_files(TMP_PCAP)
            pcap_process = record_pcap(url_host)
        else:
            # For H3 clients, clean qlog directory
            remove_files(TMP_QLOG)
        
        # Build and run client command
        cmd = build_client_command(client, url, TMP_QLOG if client.is_h3 else None)
        print(cmd)
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            env=env
        )
        end_time = time.time()
        duration = end_time - start_time
        print(f"    Client ran for {duration:.2f} seconds")

        # Stop packet capture for H2
        if pcap_process:
            time.sleep(PCAP_STOP_DELAY)
            pcap_process.terminate()
            try:
                pcap_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pcap_process.kill()
                pcap_process.wait()
        
        # Save results
        if not client.is_h3:
            # Parse and save pcap as JSON (preserving duplicate keys for analyze_pcap)
            if pcap_output_dir:
                output_file = parse_pcap_to_json(client.name, iteration, pcap_output_dir)
        else:
            # Move qlog to output directory
            if client.name == "ngtcp2_h3":
                qlog_files = list(TMP_QLOG.glob('*.sqlog'))
            elif client.name == "proxygen_h3":
                qlog_files = list(TMP_QLOG.glob('*.qlog'))
            if not qlog_files:
                raise Exception('No qlog file created')
            
            qlog_file = qlog_files[0]
            
            if qlog_output_dir:
                if client.name == "ngtcp2_h3":
                    output_file = qlog_output_dir / f'{client.name}_{iteration}.sqlog'
                elif client.name == "proxygen_h3":
                    output_file = qlog_output_dir / f'{client.name}_{iteration}.qlog'
                shutil.move(str(qlog_file), str(output_file))
            
            remove_files(TMP_QLOG)
        
        # Clean up SSL key log
        if SSL_KEY_LOG_FILE.exists():
            SSL_KEY_LOG_FILE.unlink()
        
        # Return output file name
        return output_file
    
    except Exception as e:
        if pcap_process:
            pcap_process.kill()
        raise e


"""Run a complete experiment with all specified clients."""
def run_experiment(experiment: Experiment, client_dict: dict[str, Client]) -> None:
    print(f'\n{"="*60}'); print(f'Running Experiment: {experiment.name}'); print(f'{"="*60}')
    print(f'Endpoint: {experiment.endpoint}')
    print(f'Iterations: {experiment.iterations}')
    print(f'Clients: {", ".join(experiment.clients)}')
    
    # Create output directories
    make_dirs(DIRS)
    exp_qlog_dir = QLOG_DIR / experiment.name
    exp_pcap_dir = PCAP_DIR / experiment.name
    
    for dir_path in [exp_qlog_dir, exp_pcap_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    # Run network commands
    cmds : str = generate_cmds(experiment.profile)
    for cmd in cmds:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f'Warning: {cmd} failed with error: {result.stderr}')
    
    # Run each client
    output_files = {}
    for client_name in experiment.clients:
        if client_name not in client_dict:
            print(f'Warning: Client {client_name} not found in configuration')
            continue
        
        client = client_dict[client_name]
        output_files[client] = []
        print(f'\n--- Running client: {client_name} ---')
        
        # Create client-specific output directory
        if client.is_h3:
            client_output_dir = exp_qlog_dir / client_name
        else:
            client_output_dir = exp_pcap_dir / client_name
        client_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Run iterations
        for i in range(0, experiment.iterations):
            print(f'  Iteration {i + 1}/{experiment.iterations}...', end=' ')
            
            retries = 0
            max_retries = 10
            
            while retries < max_retries:
                try:
                    output_file = run_iteration(
                        client, 
                        experiment.endpoint, 
                        i,
                        qlog_output_dir=client_output_dir if client.is_h3 else None,
                        pcap_output_dir=client_output_dir if not client.is_h3 else None
                    )
                    output_files[client].append(output_file)
                    print(f'✓ created output file {output_file}')
                    break
                
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        print(f'✗ Failed after {max_retries} retries: {e}')
                        raise
                    else:
                        print(f'Retry {retries}/{max_retries}... with error: {e}', end=' ')
        
        print(f'Completed {client_name}: {experiment.iterations} iterations')
    return output_files
