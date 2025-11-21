import pathlib
from typing import Optional, TextIO
import matplotlib.pyplot as plt

# Import the parser
import sys
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.absolute()))
from pipeline.parse_params import parse_params
from clients.run_clients import run_experiment
from analysis.ack_analysis import analyze_pcap, analyze_qlog
from analysis.ttlb_analysis import analyze_ttlb


def main():
    # Run each experiment 
    (clients, experiments) = parse_params('params.json', )
    for experiment in experiments.values():
        output_files = run_experiment(experiment, clients)
        analysis = {}  # maps from ClientObject to analysis results
        for (client, client_outputs) in output_files.items():
            analysis[client] = []
            ttlb_sum = 0
            ttlb_count = 0
            for client_output in client_outputs:
                if client.is_h3:
                    analysis_res = analyze_qlog(client_output)
                else:
                    analysis_res = analyze_pcap(client_output)
                analysis[client].append(analysis_res)
        
        # Analyze TTLB
        single_ttlb_res, pairwise_ttlb_res = analyze_ttlb(analysis)
        for (client, res) in single_ttlb_res.items():
            if res is not None:
                print(f'Client: {res.name}, Avg TTLB: {res[0]} ms, Variance: {res[1]}, StdDev: {res[2]} ms')
        for (client, res) in pairwise_ttlb_res.items():
            for (other_client, perc_diff) in res:
                print(f'Client: {client} vs {other_client}, Percentage Diff in Avg TTLB: {perc_diff}')

                # if ttlb is not None:
                #     ttlb_sum += ttlb
                #     ttlb_count += 1

                # x = []
                # y = []
                # print(analysis_res['ttlb'])
                # for (ts, cumack) in analysis_res['ack_packets_ts']:
                #     x.append(ts)
                #     y.append(cumack)
                # print(x)
                # print(y)
                # plt.scatter(x, y)
                # plt.xlabel('Time (ms)')
                # plt.ylabel('Cumulative ACK')
                # plt.title(f'{client.name} - {client_output}')
                # plt.savefig(f'{client.name}.png')  # Save instead of show
                # plt.close() 

            ttlb_avg = ttlb_sum / ttlb_count
            print(client.name, ttlb_avg)
main()