import numpy as np

def analyze_ttlb(analysis):
    ttlb_results = {}

    # For each client, compute average, variance, and stddev of TTLB
    for client, analyses in analysis.items():
        ttlb_values = []
        for analysis_res in analyses:
            if 'ttlb' in analysis_res and analysis_res['ttlb'] is not None:
                ttlb_values.append(analysis_res['ttlb'])
        if len(ttlb_values) > 0:
            avg_ttlb    = np.mean(ttlb_values)
            var_ttlb    = np.var(ttlb_values)
            stddev_ttlb = np.std(ttlb_values)
            ttlb_results[client.name] = (avg_ttlb, var_ttlb, stddev_ttlb)
        else:
            ttlb_results[client.name] = None
    return ttlb_results