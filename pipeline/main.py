import pathlib
from typing import Optional, TextIO
import matplotlib.pyplot as plt
import numpy as np

# Import the parser
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from pipeline.parse_params import parse_params
from clients.run_clients import run_experiment
from analysis.ack_analysis import analyze_pcap, analyze_qlog
from analysis.ttlb_analysis import analyze_ttlb
from analysis.cda_analysis import segment_trace_pelt, plot_segmented_trace


def main():
    # Run each experiment 
    (clients, experiments) = parse_params('params.json', )
    for experiment in experiments.values():
        output_files = run_experiment(experiment, clients)
        analysis = {}  # maps from ClientObject to analysis results
        for (client, client_outputs) in output_files.items():
            analysis[client] = []
            for client_output in client_outputs:
                if client.is_h3:
                    analysis_res = analyze_qlog(client_output)
                else:
                    analysis_res = analyze_pcap(client_output)
                analysis[client].append(analysis_res)

                x = []
                y = []
                for (ts, cumack) in analysis_res['ack_packets_ts']:
                    x.append(ts)
                    y.append(cumack)
                x, y = np.array(x), np.array(y)
                segments = segment_trace_pelt(x, y)
                plot_segmented_trace(x, y, segments, filename=f'{client.name}')
        
        # Analyze TTLB
        single_ttlb_res, pairwise_ttlb_res = analyze_ttlb(analysis)
        for (client, res) in single_ttlb_res.items():
            if res is not None:
                print(f'Client: {client}, Avg TTLB: {res[0]} ms, Variance: {res[1]}, StdDev: {res[2]} ms')
        for (client, res) in pairwise_ttlb_res.items():
            for (other_client, perc_diff) in res:
                print(f'Client: {client} vs {other_client}, Percentage Diff in Avg TTLB: {perc_diff}')
main()