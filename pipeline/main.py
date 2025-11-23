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
from analysis.segment_analysis import segment_analysis, find_first_significant_difference, visualize_segment_comparison


def main():
    # Run each experiment 
    (clients, experiments) = parse_params('params.json', )
    for experiment in experiments.values():
        output_files = run_experiment(experiment, clients)
        analysis = {}  # maps from ClientObject to analysis results
        all_segments = []
        for (client, client_outputs) in output_files.items():
            analysis[client] = []
            curr_segments = []
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
                curr_segments.append(segments)
                plot_segmented_trace(x, y, segments, filename=f'{experiment.name}-{client.name}')
            all_segments.append(curr_segments)
        
        # Analyze TTLB
        single_ttlb_res, pairwise_ttlb_res = analyze_ttlb(analysis)
        plot_ttlb_barchart(single_ttlb_res, filename=f'ttlb-barchart-{experiment.name}')
        plot_ttlb_heatmap(pairwise_ttlb_res, filename=f'ttlb-heatmap-{experiment.name}')

        # Analyze segments
        segment_cmp = segment_analysis(all_segments[0], all_segments[1], "proxygen_h3", "ngtcp2_h3")
        visualize_segment_comparison(segment_cmp, filename=f'segments-{experiment.name}-1')

        segment_cmp = segment_analysis(all_segments[0], all_segments[2], "proxygen_h3", "curl_h2")
        visualize_segment_comparison(segment_cmp, filename=f'segments-{experiment.name}-2')

        segment_cmp = segment_analysis(all_segments[1], all_segments[2], "ngtcp2_h3", "curl_h2")
        visualize_segment_comparison(segment_cmp, filename=f'segments-{experiment.name}-3')
main()