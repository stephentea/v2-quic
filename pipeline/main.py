import pathlib
from typing import List, Dict, Tuple
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
    # Run each experiment 
    (clients, experiments) = parse_params('params.json', )
    for experiment in experiments.values():
        output_files = run_experiment(experiment, clients)
        analysis: Dict[NetworkTrace, Dict] = {}             # NetworkTrace -> Analysis Results
        all_segments: List[Tuple[str, List[Segment]]]  = [] # List of List of Segments per NetworkTrace
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
                plot_segmented_trace(x, y, segments, filename=f'{experiment.name}-{trace.name}-{iteration}')
                iteration += 1
            
            all_segments.append((trace.name, curr_segments))
        
        # Analyze TTLB
        single_ttlb_res, pairwise_ttlb_res = analyze_ttlb(analysis)
        plot_ttlb_barchart(single_ttlb_res, filename=f'ttlb-barchart-{experiment.name}')
        plot_ttlb_heatmap(pairwise_ttlb_res, filename=f'ttlb-heatmap-{experiment.name}')

        # Analyze all pairwise segments
        for i in range(len(all_segments)):
            for j in range(i + 1, len(all_segments)):
                (name_i, segments_i) = all_segments[i]
                (name_j, segments_j) = all_segments[j]
                segment_cmp = segment_analysis(segments_i, segments_j, name_i, name_j)
                visualize_segment_comparison(segment_cmp, filename=f'segments-{experiment.name}-{name_i}-vs-{name_j}')

main()