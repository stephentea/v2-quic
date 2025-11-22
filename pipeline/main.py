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
from analysis.ttlb_analysis import analyze_ttlb, plot_ttlb_heatmap, plot_ttlb_barchart
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
        plot_ttlb_barchart(single_ttlb_res, filename=f'ttlb-barchart-{client.name}')
        plot_ttlb_heatmap(pairwise_ttlb_res, filename=f'ttlb-heatmap-{client.name}')
main()