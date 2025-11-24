import os
import pathlib
import pickle
from typing import List, Dict, Tuple
from datetime import datetime
import numpy as np

# Import the parser
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from pipeline.parse_params import parse_params
from clients.run_clients import NetworkTrace, run_experiment
from analysis.ack_analysis import analyze_pcap, analyze_qlog
from analysis.ttlb_analysis import analyze_ttlb, plot_ttlb_heatmap, plot_ttlb_barchart
from analysis.cda_analysis import segment_trace_pelt, plot_segmented_trace
from analysis.segment_analysis import Segment, segment_analysis, find_first_significant_difference, visualize_segment_comparison


def main():
    os.makedirs('results', exist_ok=True)
    # Run each experiment 
    (clients, experiments) = parse_params('params.json')
    for experiment in experiments.values():
        output_files = run_experiment(experiment, clients)
        analysis: Dict[NetworkTrace, Dict] = {}                   # NetworkTrace -> Analysis Results
        all_segments: List[Tuple[str, List[List[Segment]]]]  = [] # List of List of Segments per NetworkTrace
        for (trace, outputs) in output_files.items():
            analysis[trace]              = []
            curr_segments: List[Segment] = []
            iteration: int               = 0
            for output in outputs:
                if trace.is_h3:
                    analysis_res = analyze_qlog(output)
                else:
                    analysis_res = analyze_pcap(output)
                analysis[trace].append(analysis_res)

                x = []
                y = []
                for (ts, cumack) in analysis_res['ack_packets_ts']:
                    x.append(ts)
                    y.append(cumack)
                x, y = np.array(x), np.array(y)

                segments = segment_trace_pelt(x, y)
                curr_segments.append(segments)
                iteration += 1
            
            all_segments.append((trace.name, curr_segments))
        
        # Generate unique timestamp for file names
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        # Save all_segments to pickle file
        segments_filename = f'results/segments_data_{experiment.name}_{timestamp}.pkl'
        with open(segments_filename, 'wb') as f:
            pickle.dump(all_segments, f)
        print(f"Saved segments data to: {segments_filename}")
        
        # Save analysis dict to pickle file
        analysis_filename = f'results/analysis_data_{experiment.name}_{timestamp}.pkl'
        with open(analysis_filename, 'wb') as f:
            pickle.dump(analysis, f)
        print(f"Saved analysis data to: {analysis_filename}")

        # # Load segment data
        # with open(segments_filename, 'rb') as f:
        #     all_segments_load = pickle.load(f)

        # # Load analysis data
        # with open(analysis_filename, 'rb') as f:
        #     analysis_load = pickle.load(f)
        
        # # Analyze TTLB
        # single_ttlb_res, pairwise_ttlb_res = analyze_ttlb(analysis_load)
        # plot_ttlb_barchart(single_ttlb_res, filename=f'ttlb-barchart-{experiment.name}')
        # plot_ttlb_heatmap(pairwise_ttlb_res, filename=f'ttlb-heatmap-{experiment.name}')

        # # Analyze all pairwise segments
        # for i in range(len(all_segments_load)):
        #     for j in range(i + 1, len(all_segments_load)):
        #         (name_i, segments_i) = all_segments_load[i]
        #         (name_j, segments_j) = all_segments_load[j]
        #         segment_cmp = segment_analysis(segments_i, segments_j, name_i, name_j)
        #         visualize_segment_comparison(segment_cmp, filename=f'segments-{experiment.name}-{name_i}-vs-{name_j}')

main()