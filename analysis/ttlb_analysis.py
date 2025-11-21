import numpy as np
def analyze_ttlb(analysis):
    # For each client, compute average, variance, and stddev of TTLB
    single_results = {}
    for client, analyses in analysis.items():
        ttlb_values = []
        for analysis_res in analyses:
            if 'ttlb' in analysis_res and analysis_res['ttlb'] is not None:
                ttlb_values.append(analysis_res['ttlb'])
        if len(ttlb_values) > 0:
            avg_ttlb    = np.mean(ttlb_values)
            var_ttlb    = np.var(ttlb_values)
            stddev_ttlb = np.std(ttlb_values)
            single_results[client.name] = (avg_ttlb, var_ttlb, stddev_ttlb)
        else:
            single_results[client.name] = None

    # Compute pairwise TTLB comparisons
    pairwise_results = {}
    clients = list(analysis.keys())
    for i in range(len(clients)):
        client1 = clients[i]
        ttlb1 = single_results[client1.name][0]
        pairwise_results[client1.name] = []
        for j in range(len(clients)):
            client2 = clients[j]
            ttlb2 = single_results[client2.name][0]
            if ttlb1 is not None and ttlb2 is not None:
                diff = ttlb2 - ttlb1
                percentage_diff = (diff / ttlb1)
                pairwise_results[client1.name].append((client2.name, percentage_diff))
            else:
                pairwise_results[client1.name].append((client2.name, None))

    return single_results, pairwise_results