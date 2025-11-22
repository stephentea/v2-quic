#!/usr/bin/env python3
"""
PELT-Based Rate Segmentation for TCP Traces

This script uses PELT changepoint detection on the rate signal to automatically
detect transitions between flat (rate≈0) and active (rate>0) periods.
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from typing import Tuple, List, Optional, NamedTuple
import ruptures as rpt

"""Segment characteristics"""
class Segment(NamedTuple): 
    segment_id: int                 # index in array 
    start_idx: int                  # start index in rtts (inclusive)
    end_idx: int                    # end index in rtts (exclusive)
    rtts: np.ndarray                # rtts in segment
    cumulative_bytes: np.ndarray    # cumulative bytes ACKed in segment
    rates: np.ndarray               # rates (throughput) in segment
    duration_ms: float              # duration of segment in ms
    bytes_transferred: float        # total bytes transferred in segment
    avg_rate: float                 # average rate in segment
    median_rate: float              # median rate in segment
    num_points: int                 # number of points in segment

""" 
Smooth the signal to reduce noise, returning signal of same shape,
using Savitzky-Golay filter. 
"""
def smooth_signal(signal: np.ndarray, window_length: int = 11, polyorder: int = 3) -> np.ndarray:
    if len(signal) < 3:
        return signal

    window_length = min(window_length, len(signal))
    if window_length % 2 == 0:
        window_length -= 1
    window_length = max(window_length, 3)
    polyorder = min(polyorder, window_length - 1)
    return savgol_filter(signal, window_length=window_length, polyorder=polyorder)

"""
Compute local rate (slope) using a sliding window.
This gives us the instantaneous transfer rate at each point.
Returns rates, with same size as original signals.
"""
def compute_local_rate(rtts: np.ndarray, cumulative_bytes: np.ndarray, 
                       window_size: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    if len(rtts) < window_size:
        window_size = max(2, len(rtts) // 2)
    
    rates = np.zeros(len(rtts))
    for i in range(len(rtts)):
        # Define window around point i
        start = max(0, i - window_size // 2)
        end = min(len(rtts), i + window_size // 2 + 1)
        
        if end - start < 2:
            continue
        
        # Fit line through window points
        window_rtts = rtts[start:end]
        window_bytes = cumulative_bytes[start:end]
        
        # Compute slope (rate)
        if len(window_rtts) >= 2:
            dt = window_rtts[-1] - window_rtts[0]
            if dt > 0:
                dbytes = window_bytes[-1] - window_bytes[0]
                rates[i] = dbytes / dt
    
    return rates

"""
Use PELT on the rate signal to detect changepoints.

Args:
    rtts: Time values
    cumulative_bytes: Cumulative bytes
    smooth_window: Window for smoothing cumulative bytes
    rate_window: Window for computing local rate
    min_segment_length: Minimum segment size for PELT
    penalty: PELT penalty (None for auto)

Returns:
    List of changepoint indices
"""
def detect_rate_changepoints_pelt(rtts: np.ndarray, 
                                  cumulative_bytes: np.ndarray,
                                  smooth_window: int = 21,
                                  rate_window: int = 20,
                                  min_segment_length: int = 10,
                                  penalty: Optional[float] = None,
                                  penalty_factor: Optional[float] = None) -> List[int]:
    if len(rtts) < min_segment_length * 2:
        print("   WARNING: Trace too short for PELT segmentation.")
        return []
    
    # Smooth cumulative bytes
    smoothed_bytes = smooth_signal(cumulative_bytes, window_length=smooth_window)

    # Compute local rate
    rates = compute_local_rate(rtts, smoothed_bytes, window_size=rate_window)
    
    # Smooth the rate signal
    smoothed_rates = smooth_signal(rates, window_length=smooth_window)
    
    # Apply PELT to the rate signal
    if penalty is None:
        variance = np.var(smoothed_rates)
        if variance == 0:
            variance = 1.0
        n = len(smoothed_rates)
        if penalty_factor is None:
            penalty_factor = 2.0
        penalty = penalty_factor * np.log(n) * variance
    
    # Run PELT
    algo = rpt.Pelt(model='l2', min_size=min_segment_length).fit(smoothed_rates)
    changepoints = algo.predict(pen=penalty)
    
    # Remove the last point (is always length of signal)
    if changepoints and changepoints[-1] == len(smoothed_rates):
        changepoints = changepoints[:-1]
    
    print(f"   PELT detected {len(changepoints)} changepoints with penalty={penalty:.2f}")
    
    return changepoints, smoothed_rates

"""
Segment trace using PELT on the rate signal.

Returns:
    Tuple of (segments list, smoothed_rates array)
"""
def segment_trace_pelt(rtts: np.ndarray, 
                       cumulative_bytes: np.ndarray) -> List[Segment]:
    # Choose parameters based on trace length
    n = len(rtts)
    smooth_window = 21 if n > 200 else 11 if n > 20 else 3
    rate_window   = 20 if n > 200 else 11 if n > 20 else 3
    min_segment_length = 10 if n > 200 else 5 if n > 20 else 1
    penalty_factor = 2.0 if n > 200 else 1.0 if n > 20 else 0.001

    # Detect changepoints using PELT
    changepoints, smoothed_rates = detect_rate_changepoints_pelt(
        rtts, 
        cumulative_bytes,
        smooth_window=smooth_window,
        rate_window=rate_window,
        min_segment_length=min_segment_length,
        penalty=None,
        penalty_factor=penalty_factor
    )
    
    # Create segments
    segments = []
    segment_starts = [0] + changepoints
    segment_ends = changepoints + [len(rtts)]
    
    for seg_id, (start, end) in enumerate(zip(segment_starts, segment_ends)):
        if end - start < 1:
            continue
        
        seg_rtts = rtts[start:end + 1]
        seg_bytes = cumulative_bytes[start:end + 1]
        seg_rates = smoothed_rates[start:end + 1]
        
        # Compute segment characteristics
        duration = seg_rtts[-1] - seg_rtts[0]
        bytes_transferred = seg_bytes[-1] - seg_bytes[0]
        if duration > 0:
            avg_rate = bytes_transferred / duration
        else:
            avg_rate = 0        
        median_rate = np.median(seg_rates)

        segments.append(Segment(
            segment_id=seg_id,
            start_idx=start,    # inclusive
            end_idx=end + 1,    # exclusive
            rtts=seg_rtts,
            cumulative_bytes=seg_bytes,
            rates=seg_rates,
            duration_ms=duration,
            bytes_transferred=bytes_transferred,
            avg_rate=avg_rate,
            median_rate=median_rate,
            num_points=len(seg_rtts)
        ))
    
    return segments

def scenario_real_curl_trace():
    rtts = [0.0, 48.290088000000004, 48.297051, 80.300681, 87.14267600000001, 92.593348, 93.94026699999999, 94.351486, 128.266, 128.69887899999998, 135.363452, 141.777256, 154.076946, 160.94487900000001, 166.97646699999999, 166.98862, 174.10646, 174.11164000000002, 180.069301, 184.100449, 184.96664900000002, 189.822504, 190.223895, 193.647697, 193.652195, 193.653558, 198.268503, 198.282389, 205.44527300000001, 205.45349900000002, 208.88259100000002, 208.88726899999997, 212.73111699999998, 215.16608100000002, 219.043421, 219.049423, 222.637116, 226.577344, 226.582795, 230.103188, 230.108588, 230.110401, 234.801318, 234.805967, 234.808071, 237.82351, 237.82821800000002, 237.82956099999998, 242.558483, 242.563042, 242.564525, 242.565657, 245.896936, 245.901365, 246.60938900000002, 250.89937099999997, 252.378257, 252.383076, 252.38457800000003, 254.817378, 257.367446, 260.20047400000004, 260.204932, 260.206365, 260.20752699999997, 262.962689, 262.967077, 264.923566, 270.10551599999997, 270.96252799999996, 270.967037, 270.96853, 270.969682, 272.271657, 280.672796, 280.67744500000003, 280.678918, 280.68017000000003, 289.979981, 289.985511, 289.987274, 289.988697, 296.572699, 307.32266200000004, 307.33177900000004, 307.333432, 307.334634, 307.33581599999997, 307.336958, 317.640294, 1822.5547980000001, 1828.7028540000001, 1835.119162, 1841.734242, 1848.002504, 1848.0145459999999, 1854.914118, 1854.926522, 1861.746385, 1861.758106, 1868.885399, 1868.890328, 1875.99542, 1876.000309, 1883.787541, 1890.7379580000002, 1890.742757, 1897.692984, 1898.007161, 1905.8441559999999, 1905.8531229999999, 1913.1946520000001, 1913.199391, 1920.356263, 1920.360852, 1927.991602, 1934.956425, 1935.542111, 1941.99115, 1941.995949, 1950.236699, 1950.241348, 1958.2907400000001, 1958.295519, 1966.633982, 1966.642307, 1973.9926320000002, 1973.997441, 1981.362684, 1981.368074, 1989.926198, 1990.534034, 1996.956404, 1999.511522, 2003.133615, 2006.967144, 2009.5893669999998, 2013.6058879999998, 2015.941946, 2020.3516829999999, 2022.810541, 2027.2165700000003, 2029.8375210000002, 2035.9110939999998, 2043.1280040000001, 2043.133284, 2050.522622, 2058.698841, 2058.7037100000002, 2066.434647, 2066.912731, 2074.770355, 2074.7752739999996, 2083.025091, 2083.030531, 2090.1032370000003, 2090.558719, 2097.669416, 2104.14786, 2104.152529, 2113.734357, 2121.6540259999997, 2121.657943, 2129.213091, 2129.21801, 2137.952153, 2138.689162, 2145.2737439999996, 2146.982199, 2153.405701, 2158.778548, 2161.3189589999997, 2167.462627, 2167.467206, 2174.928769, 2174.933868, 2181.112312, 2183.007115, 2187.956982, 2190.935151, 2195.000693, 2198.008667, 2200.9694839999997, 2205.849991, 2207.232556, 2213.814855, 2221.0510870000003, 2221.0558159999996, 2227.913579, 2229.481641, 2233.893121, 2234.300272, 2236.263373, 2240.088336, 2240.092974, 2243.549288, 2243.557333, 2246.6618679999997, 2246.6663869999998, 2250.347711, 2253.279994, 2258.045014, 2259.46534, 2266.2466210000002, 2274.320619, 2274.326691, 2281.6528, 2281.657409, 2289.1128209999997, 2289.1175590000003, 2296.730466, 2297.159177, 2304.5767979999996, 2304.581497, 2312.2508279999997, 2312.2555070000003, 2319.9891589999997, 2319.9936270000003, 2327.5881790000003, 2327.5926870000003, 2335.1258239999997, 2335.130623, 2343.5036400000004, 2343.511024, 2352.769397, 2352.774807, 2359.9866129999996, 2360.389687, 2367.924547, 2368.512827, 2374.727909, 2375.0063, 2375.6841369999997, 2375.688856, 2381.8858139999998, 2383.458846, 2389.0035639999996, 2389.414863, 3896.075566, 3904.440067, 3911.0181079999998, 3911.0299999999997, 3918.0044129999997, 3918.009131, 3918.010674, 3926.055308, 3926.070626, 3933.399992, 3933.402226, 3933.403529, 3940.87529, 3940.8808510000003, 3940.882634, 3947.0611980000003, 3948.036482, 3948.0409, 3954.812002, 3954.823684, 3954.8253170000003, 3960.9413139999997, 3962.103266, 3962.125738, 3969.212691, 3969.21736, 3975.981909, 3984.0369619999997, 3984.575289, 3991.924292, 3998.6707969999998, 3998.675276, 4005.8556330000006, 4005.860442, 4012.7328230000003, 4012.737802, 4019.6745739999997, 4019.679083, 4026.981278, 4026.9857460000003, 4033.9690739999996, 4033.9739239999994, 4041.2749369999997, 4047.873656, 4048.70496, 4056.300814, 4056.77441, 4063.8776529999996, 4064.485459, 4072.004981, 4072.019568, 4080.095951, 4080.1112799999996, 4088.6299700000004, 4088.637944, 4096.009619, 4096.0141380000005, 4103.760603, 4104.356046000001, 4111.080141, 4111.084629, 4118.168075, 4118.173595, 4125.782614000001, 4133.642742, 4133.647612, 4141.8722609999995, 4141.878523, 4148.982518000001, 4148.987507, 4156.535210999999, 4156.5402, 4163.726939, 4171.020377999999, 4171.025507, 5675.0517, 5681.695789, 5688.327806, 5694.7256, 5694.737642, 5701.054805, 5701.059865, 5708.154381, 5708.159441000001, 5708.160934, 5708.162085999999, 5714.001766, 5715.134314, 5720.055401, 5721.117006, 5721.121183, 5727.122045, 5727.133707, 7232.391415, 7238.747004999999, 7238.751744, 7245.0828679999995, 7245.094660000001, 7251.84871, 7251.862967, 7258.327736, 7258.332435, 7265.1489710000005, 7265.153971, 7271.621064, 7271.6259230000005, 7278.563467, 7278.568276, 7285.622462, 7285.631298, 7291.985315, 7291.996435999999, 7299.101092, 7299.11659, 7305.866453000001, 7306.655338, 7313.141651999999, 7313.146320999999, 7319.966054, 7326.809456, 7326.8140539999995, 7333.852166, 7340.124344000001, 7340.129113, 7347.070834, 7347.082777, 7354.677148000001, 7354.68879, 7361.021602, 7361.033514, 7368.038133, 7374.821327000001, 7374.833119, 7381.941783, 7381.957161, 7389.242595, 7389.247254, 7436.516777, 7443.942513, 7451.0636349999995, 7451.075357, 7458.650662, 7459.0834509999995, 7465.524681, 7465.5295209999995, 7472.741356, 7480.240825, 7480.245905000001, 7487.740624999999, 7487.765972, 7494.463457, 7494.468115, 7502.089798, 7502.097152, 7508.920341, 7517.050168, 7524.752006, 7531.796093, 7538.639125000001, 7538.645306, 7545.9126559999995, 7545.917214, 7552.998721, 7553.00349, 7559.836623, 7560.425414, 7566.857753, 7566.863544, 7574.690961, 7574.69567, 7582.524058999999, 7582.529098, 7589.348851, 7590.390619, 7595.79472, 7597.087025999999, 7601.851761, 7603.983157, 7603.987876, 7608.126134, 7608.130883000001, 7610.5188689999995, 7614.459212, 7617.827681, 7617.833422000001, 7621.26567, 7621.271441, 7625.256272, 7628.12918, 7628.13474, 7632.889590999999, 7632.895222, 7635.37003, 7642.687208, 7642.697387, 7651.751708, 7659.738273, 7659.749755, 7667.984934, 7667.996105, 7676.798525, 7676.809225, 7685.863527, 7685.874497000001, 7693.8470609999995, 7693.8549060000005, 7701.162536, 7702.228129, 7702.234941000001, 7709.9048139999995, 7709.919621, 7717.776053, 7717.78527, 9222.343541, 9228.243564999999, 9234.337881, 9240.648492, 9240.653391, 9246.923756, 10751.822211, 10758.323588, 10764.72536, 10764.737201999998, 10771.756934000001, 10778.781840000001, 10785.280593, 10792.131178, 10798.730518999999, 10798.742612, 10805.141778, 10805.153941, 10811.857391, 10811.869122999999, 10818.104087, 10818.11607, 10824.998450000001, 10831.603511000001, 10837.941453, 10845.564964, 10852.493826, 10852.512671, 10859.135165, 10859.781313, 10867.081945, 10867.092976, 10874.011959000001, 10880.851705, 10880.856584, 10888.161243, 10888.169499, 10894.956531, 10894.96145, 10901.810641999999, 10901.815542, 10908.15157, 10908.625015, 10915.004294999999, 10922.087685999999, 10929.08744, 10929.099282, 10936.291136, 10943.655316999999, 10950.72646, 10951.097334, 10958.478146, 10965.478166, 10965.489857999999, 10972.925953, 10972.930802, 10979.604472, 10979.609131, 10986.542164999999, 10993.424926, 10993.430647000001, 11000.118553, 11000.123713, 11007.573103, 11007.577832, 11015.800302000001, 11015.805131000001, 11023.771834, 11024.616193, 11031.303699, 11031.31501, 11038.750875, 11039.532105999999, 11045.735596, 11045.740464999999, 11052.965321, 11059.34215, 11067.0563, 11074.904386, 11074.919935, 11081.873003, 11081.877892, 11089.139104999998, 11089.595459, 11096.6417, 11096.646358999998, 11103.741661999999, 11104.011887, 11110.576138, 11110.580095, 11117.804615000001, 11125.039204, 11125.043921999999, 11132.134622000001, 11132.139451000001, 11140.443720000001, 11140.452737, 11148.288229, 11148.292978000001, 11155.761053, 11162.970765, 11163.591686, 11170.125795, 11177.575145, 11177.579864, 11185.101549, 11185.107049999999, 11192.126967, 11192.132337000001, 11199.532195, 11206.886297000001, 11206.890955, 11214.473565, 11214.478224, 11222.240053, 11222.244702, 11229.344053, 11229.348541, 11236.822591999999, 11236.831478999999, 11243.687655, 11243.692194, 11250.049691999999, 11251.671059, 11257.311506, 11258.947344999999, 11264.781045, 11266.310604999999, 11271.021604, 11273.315614, 11273.320784, 11277.771216, 11280.702948, 11280.708599, 11284.972983, 11290.953307, 11290.960059, 11291.675486999999, 11298.959879, 11298.966030000001, 11306.891385, 11306.896856, 11314.733315, 11314.739176, 11322.139174, 11322.146096999999, 11330.239545999999, 11330.244395, 11338.410866, 11339.05463, 11345.865366, 11345.870055000001, 11353.30062, 11353.305519, 11359.051429000001, 11360.111271, 12864.595721000002, 12870.770453000001, 12877.583689, 12896.320706999999, 12896.329844]
    cumacks = [0.0, 0.0009765625, 0.0009765625, 2.8134765625, 3.212890625, 3.212890625, 3.212890625, 3.212890625, 6.55078125, 6.55078125, 13.58203125, 14.63671875, 22.72265625, 28.11328125, 33.73828125, 40.76953125, 43.58203125, 48.328125, 53.71875, 59.109375, 65.84765625, 72.87890625, 76.62890625, 79.44140625, 83.66015625, 86.47265625, 88.81640625, 95.49609375, 112.37109375, 115.7109375, 124.1484375, 126.9609375, 129.1875, 146.70703125, 160.76953125, 162.87890625, 175.0078125, 180.6328125, 195.22265625, 200.84765625, 206.47265625, 215.4375, 225.28125, 232.3125, 242.15625, 251.82421875, 254.63671875, 267.29296875, 272.0390625, 279.0703125, 294.5390625, 297.3515625, 301.5703125, 321.90234375, 327.52734375, 330.33984375, 340.18359375, 354.24609375, 361.27734375, 390.69140625, 393.50390625, 401.94140625, 411.78515625, 418.93359375, 424.55859375, 434.40234375, 452.68359375, 456.90234375, 459.71484375, 466.74609375, 486.43359375, 489.24609375, 494.87109375, 520.18359375, 549.71484375, 563.77734375, 579.24609375, 583.46484375, 587.68359375, 600.33984375, 632.68359375, 646.74609375, 649.55859375, 649.55859375, 649.55859375, 649.55859375, 649.55859375, 649.55859375, 649.55859375, 650.96484375, 712.83984375, 715.65234375, 719.87109375, 724.08984375, 726.90234375, 729.71484375, 736.74609375, 739.55859375, 745.18359375, 752.21484375, 759.24609375, 767.68359375, 774.71484375, 784.55859375, 801.43359375, 811.27734375, 818.30859375, 828.15234375, 835.18359375, 846.43359375, 852.05859375, 860.49609375, 868.93359375, 875.96484375, 885.80859375, 904.08984375, 913.93359375, 922.37109375, 926.58984375, 940.65234375, 951.90234375, 958.93359375, 968.77734375, 977.21484375, 981.43359375, 995.49609375, 1002.52734375, 1013.77734375, 1027.83984375, 1033.46484375, 1037.68359375, 1053.15234375, 1057.37109375, 1072.83984375, 1077.05859375, 1092.52734375, 1096.74609375, 1112.21484375, 1116.43359375, 1131.90234375, 1136.12109375, 1151.58984375, 1155.80859375, 1176.90234375, 1179.71484375, 1197.99609375, 1219.08984375, 1221.90234375, 1240.18359375, 1247.21484375, 1261.27734375, 1275.33984375, 1282.37109375, 1290.80859375, 1303.46484375, 1313.30859375, 1324.55859375, 1331.58984375, 1348.46484375, 1354.08984375, 1376.58984375, 1379.40234375, 1399.08984375, 1410.33984375, 1421.58984375, 1425.80859375, 1444.08984375, 1448.30859375, 1466.58984375, 1469.40234375, 1489.08984375, 1491.90234375, 1511.58984375, 1514.40234375, 1517.21484375, 1538.30859375, 1541.12109375, 1562.21484375, 1565.02734375, 1586.12109375, 1588.93359375, 1610.02734375, 1612.83984375, 1633.93359375, 1636.74609375, 1660.65234375, 1677.52734375, 1684.55859375, 1690.18359375, 1708.46484375, 1711.27734375, 1714.08984375, 1732.37109375, 1735.18359375, 1739.40234375, 1742.21484375, 1757.68359375, 1761.90234375, 1764.71484375, 1782.99609375, 1790.02734375, 1808.30859375, 1815.33984375, 1840.65234375, 1860.33984375, 1865.96484375, 1881.43359375, 1891.27734375, 1898.30859375, 1916.58984375, 1927.83984375, 1943.30859375, 1946.12109375, 1970.02734375, 1992.52734375, 1996.74609375, 2019.24609375, 2023.46484375, 2036.12109375, 2050.18359375, 2060.02734375, 2076.90234375, 2088.15234375, 2103.62109375, 2114.87109375, 2130.33984375, 2140.18359375, 2157.05859375, 2162.68359375, 2183.77734375, 2189.40234375, 2192.21484375, 2200.65234375, 2211.90234375, 2221.74609375, 2223.15234375, 2223.15234375, 2223.15234375, 2224.55859375, 2227.37109375, 2230.18359375, 2240.02734375, 2240.02734375, 2251.27734375, 2251.27734375, 2254.08984375, 2259.71484375, 2261.12109375, 2268.15234375, 2270.96484375, 2275.18359375, 2276.58984375, 2286.43359375, 2287.83984375, 2296.27734375, 2301.90234375, 2304.71484375, 2314.55859375, 2317.37109375, 2318.77734375, 2330.02734375, 2332.83984375, 2339.87109375, 2349.71484375, 2366.58984375, 2379.24609375, 2383.46484375, 2400.33984375, 2412.99609375, 2417.21484375, 2427.05859375, 2434.08984375, 2441.12109375, 2450.96484375, 2462.21484375, 2467.83984375, 2476.27734375, 2486.12109375, 2493.15234375, 2504.40234375, 2522.68359375, 2525.49609375, 2540.96484375, 2543.77734375, 2559.24609375, 2566.27734375, 2577.52734375, 2584.55859375, 2595.80859375, 2601.43359375, 2615.49609375, 2618.30859375, 2635.18359375, 2646.43359375, 2654.87109375, 2661.90234375, 2674.55859375, 2682.99609375, 2694.24609375, 2698.46484375, 2713.93359375, 2733.62109375, 2740.65234375, 2753.30859375, 2760.33984375, 2774.40234375, 2778.62109375, 2795.49609375, 2806.74609375, 2816.58984375, 2837.68359375, 2837.68359375, 2837.68359375, 2858.77734375, 2861.58984375, 2865.80859375, 2867.21484375, 2871.43359375, 2874.24609375, 2879.87109375, 2881.27734375, 2885.49609375, 2889.71484375, 2891.12109375, 2892.52734375, 2902.37109375, 2903.77734375, 2906.58984375, 2913.62109375, 2913.62109375, 2913.62109375, 2926.27734375, 2927.68359375, 2929.08984375, 2930.49609375, 2934.71484375, 2938.93359375, 2941.74609375, 2944.55859375, 2948.77734375, 2950.18359375, 2955.80859375, 2957.21484375, 2964.24609375, 2967.05859375, 2972.68359375, 2974.08984375, 2981.12109375, 2983.93359375, 2990.96484375, 2995.18359375, 3000.80859375, 3006.43359375, 3010.65234375, 3017.68359375, 3020.49609375, 3031.74609375, 3035.96484375, 3042.99609375, 3052.83984375, 3055.65234375, 3064.08984375, 3069.71484375, 3075.33984375, 3078.15234375, 3087.99609375, 3092.21484375, 3100.65234375, 3113.30859375, 3116.12109375, 3125.96484375, 3130.18359375, 3138.62109375, 3144.24609375, 3152.68359375, 3166.74609375, 3180.80859375, 3183.62109375, 3194.87109375, 3199.08984375, 3208.93359375, 3217.37109375, 3222.99609375, 3237.05859375, 3239.87109375, 3252.52734375, 3255.33984375, 3267.99609375, 3279.24609375, 3283.46484375, 3290.49609375, 3298.93359375, 3314.40234375, 3329.87109375, 3345.33984375, 3362.21484375, 3365.02734375, 3379.08984375, 3383.30859375, 3395.96484375, 3400.18359375, 3412.83984375, 3418.46484375, 3429.71484375, 3438.15234375, 3446.58984375, 3449.40234375, 3463.46484375, 3466.27734375, 3481.74609375, 3487.37109375, 3500.02734375, 3505.65234375, 3518.30859375, 3523.93359375, 3528.15234375, 3536.58984375, 3539.40234375, 3542.21484375, 3554.87109375, 3560.49609375, 3564.71484375, 3573.15234375, 3577.37109375, 3580.18359375, 3592.83984375, 3597.05859375, 3599.87109375, 3602.68359375, 3612.52734375, 3619.55859375, 3626.58984375, 3639.24609375, 3658.93359375, 3664.55859375, 3678.62109375, 3687.05859375, 3699.71484375, 3706.74609375, 3720.80859375, 3730.65234375, 3741.90234375, 3744.71484375, 3762.99609375, 3770.02734375, 3778.46484375, 3784.08984375, 3795.33984375, 3803.77734375, 3803.77734375, 3803.77734375, 3824.87109375, 3827.68359375, 3831.90234375, 3834.71484375, 3837.52734375, 3837.52734375, 3838.93359375, 3845.96484375, 3848.77734375, 3850.18359375, 3855.80859375, 3861.43359375, 3867.05859375, 3872.68359375, 3878.30859375, 3879.71484375, 3882.52734375, 3886.74609375, 3892.37109375, 3893.77734375, 3897.99609375, 3902.21484375, 3910.65234375, 3919.08984375, 3927.52734375, 3934.55859375, 3937.37109375, 3944.40234375, 3947.21484375, 3954.24609375, 3958.46484375, 3964.08984375, 3973.93359375, 3978.15234375, 3985.18359375, 3989.40234375, 3996.43359375, 4004.87109375, 4007.68359375, 4014.71484375, 4018.93359375, 4024.55859375, 4030.18359375, 4042.83984375, 4055.49609375, 4059.71484375, 4068.15234375, 4080.80859375, 4093.46484375, 4097.68359375, 4106.12109375, 4120.18359375, 4124.40234375, 4134.24609375, 4144.08984375, 4148.30859375, 4156.74609375, 4162.37109375, 4176.43359375, 4179.24609375, 4190.49609375, 4196.12109375, 4204.55859375, 4207.37109375, 4220.02734375, 4228.46484375, 4235.49609375, 4241.12109375, 4250.96484375, 4257.99609375, 4266.43359375, 4276.27734375, 4281.90234375, 4294.55859375, 4298.77734375, 4305.80859375, 4322.68359375, 4339.55859375, 4342.37109375, 4356.43359375, 4366.27734375, 4373.30859375, 4383.15234375, 4390.18359375, 4394.40234375, 4407.05859375, 4409.87109375, 4425.33984375, 4436.58984375, 4443.62109375, 4461.90234375, 4475.96484375, 4480.18359375, 4492.83984375, 4498.46484375, 4504.08984375, 4516.74609375, 4520.96484375, 4535.02734375, 4554.71484375, 4568.77734375, 4574.40234375, 4594.08984375, 4598.30859375, 4613.77734375, 4620.80859375, 4633.46484375, 4646.12109375, 4653.15234375, 4672.83984375, 4682.68359375, 4692.52734375, 4703.77734375, 4712.21484375, 4724.87109375, 4733.30859375, 4736.12109375, 4754.40234375, 4768.46484375, 4775.49609375, 4778.30859375, 4796.58984375, 4802.21484375, 4817.68359375, 4823.30859375, 4838.77734375, 4844.40234375, 4859.87109375, 4865.49609375, 4869.71484375, 4880.96484375, 4887.99609375, 4893.62109375, 4903.46484375, 4910.49609375, 4914.71484375, 4925.96484375, 4932.99609375, 4941.43359375, 4955.49609375, 4959.71484375, 4977.99609375, 4985.02734375, 5000.49609375, 5007.52734375, 5022.99609375, 5031.43359375, 5046.90234375, 5059.55859375, 5070.80859375, 5077.83984375, 5094.71484375, 5098.93359375, 5111.58984375, 5111.58984375, 5111.58984375, 5112.99609375, 5115.80859375, 5135.49609375, 5140.4384765625, 5140.4384765625]
    return np.array(rtts), np.array(cumacks)

def scenario_real_100kb():
    rtts = [0.0, 26.46299, 49.99799, 50.13599, 50.18999, 72.968, 74.359, 76.688, 98.682, 175.981, 176.12399]
    cumacks = [0, 0, 11.84375, 11.84375, 27.1875, 55.4755, 68.4521, 80.249, 82.608, 100.03125, 100.03125]
    return np.array(rtts), np.array(cumacks)

def scenario_ideal_slowstart(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    rtts = np.linspace(0, 5, n_points)
    
    # Single phase: Perfect exponential growth (cwnd doubling every RTT)
    phase1_end = n_points
    cumulative_bytes = np.exp(rtts[:phase1_end] * 1.2) * 500
    
    # Add minimal measurement noise only
    noise = np.random.normal(0, 50, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_bandwidth_transition(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 4: Bandwidth Transition (e.g., WiFi to LTE handoff)
    Smooth transition from high bandwidth to lower bandwidth
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: High bandwidth phase (WiFi)
    phase1_end = 70
    bytes1 = (rtts[:phase1_end] ** 1.5) * 2000
    
    # Phase 2: Transition zone (handoff) - smooth sigmoid transition
    phase2_start = phase1_end
    phase2_end = 90
    transition_length = phase2_end - phase2_start
    transition = 1 / (1 + np.exp(-0.5 * (np.arange(transition_length) - transition_length/2)))
    high_rate = 6000
    low_rate = 2000
    transition_rate = high_rate + (low_rate - high_rate) * transition
    
    bytes2 = np.zeros(transition_length)
    for i in range(transition_length):
        idx = phase2_start + i
        if i == 0:
            bytes2[i] = bytes1[-1] + transition_rate[i] * (rtts[idx] - rtts[idx-1])
        else:
            bytes2[i] = bytes2[i-1] + transition_rate[i] * (rtts[idx] - rtts[idx-1])
    
    # Phase 3: Low bandwidth phase (LTE)
    phase3_start = phase2_end
    bytes3 = bytes2[-1] + (rtts[phase3_start:] - rtts[phase3_start]) * low_rate
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3])
    
    # Add moderate noise
    noise = np.random.normal(0, 600, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_buffer_bloat(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 3: Buffer Bloat
    Large buffer causes sustained high throughput but with variable ACK patterns
    """
    rtts = np.linspace(0, 8, n_points)
    
    # Phase 1: Initial ramp up (exponential)
    phase1_end = 40
    bytes1 = np.exp(rtts[:phase1_end] * 1.0) * 600
    
    # Phase 2: Sustained high throughput (buffer absorbing bursts)
    phase2_start = phase1_end
    bytes2 = bytes1[-1] + (rtts[phase2_start:] - rtts[phase2_start]) * 8000
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2])
    
    # Add bursty noise (ACK compression due to buffering)
    noise = np.random.normal(0, 1500, n_points)
    # Simulate ACK bursts
    burst_indices = np.random.choice(n_points, size=n_points//10, replace=False)
    noise[burst_indices] += np.random.uniform(2000, 5000, len(burst_indices))
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

# Staircase 
def scenario_staircase(n_points : int = 200):
    # Generate synthetic TCP trace data
    np.random.seed(42)
    
    # Simulate different phases
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: Slow start (exponential growth)
    phase1_end = 50
    bytes1 = np.exp(rtts[:phase1_end] * 0.5) * 1000
    
    # Phase 2: Congestion avoidance (linear growth)
    phase2_start = phase1_end
    phase2_end = 120
    bytes2 = bytes1[-1] + (rtts[phase2_start:phase2_end] - rtts[phase2_start]) * 5000
    
    # Phase 3: Rate reduction
    phase3_start = phase2_end
    phase3_end = 160
    bytes3 = bytes2[-1] + (rtts[phase3_start:phase3_end] - rtts[phase3_start]) * 2000
    
    # Phase 4: Recovery
    phase4_start = phase3_end
    bytes4 = bytes3[-1] + (rtts[phase4_start:] - rtts[phase4_start]) * 4500
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3, bytes4])
    
    # Add noise to simulate real TCP behavior
    noise = np.random.normal(0, 500, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)  # Ensure monotonic

    return rtts, cumulative_bytes

def scenario_congestion_avoidance(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 5: Classic Congestion Avoidance
    Linear growth with saw-tooth pattern from AIMD
    """
    rtts = np.linspace(0, 12, n_points)
    
    # Generate AIMD sawtooth pattern with multiple phases
    base_rate = 3000
    growth_rate = 100  # Additive increase per RTT
    segment_length = 40
    
    # Phase 1: First AIMD cycle
    phase1_end = segment_length
    bytes1 = np.zeros(phase1_end)
    for i in range(phase1_end):
        rate = base_rate + growth_rate * i
        if i == 0:
            bytes1[i] = rate * rtts[i]
        else:
            bytes1[i] = bytes1[i-1] + rate * (rtts[i] - rtts[i-1])
    
    # Phase 2: Second AIMD cycle (after multiplicative decrease)
    phase2_start = phase1_end
    phase2_end = phase2_start + segment_length
    bytes2 = np.zeros(segment_length)
    for i in range(segment_length):
        rate = base_rate + growth_rate * i
        idx = phase2_start + i
        if i == 0:
            bytes2[i] = bytes1[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes2[i] = bytes2[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Phase 3: Third AIMD cycle
    phase3_start = phase2_end
    phase3_end = phase3_start + segment_length
    bytes3 = np.zeros(segment_length)
    for i in range(segment_length):
        rate = base_rate + growth_rate * i
        idx = phase3_start + i
        if i == 0:
            bytes3[i] = bytes2[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes3[i] = bytes3[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Phase 4: Fourth AIMD cycle
    phase4_start = phase3_end
    phase4_end = phase4_start + segment_length
    bytes4 = np.zeros(segment_length)
    for i in range(segment_length):
        rate = base_rate + growth_rate * i
        idx = phase4_start + i
        if i == 0:
            bytes4[i] = bytes3[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes4[i] = bytes4[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Phase 5: Final partial cycle
    phase5_start = phase4_end
    remaining = n_points - phase5_start
    bytes5 = np.zeros(remaining)
    for i in range(remaining):
        rate = base_rate + growth_rate * i
        idx = phase5_start + i
        if i == 0:
            bytes5[i] = bytes4[-1] + rate * (rtts[idx] - rtts[idx-1])
        else:
            bytes5[i] = bytes5[i-1] + rate * (rtts[idx] - rtts[idx-1])
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3, bytes4, bytes5])
    
    # Add realistic noise
    noise = np.random.normal(0, 500, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_rate_limited(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 6: Rate-Limited Connection
    Constant throughput (bottleneck link is fully utilized)
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: Initial ramp-up (exponential)
    phase1_end = 30
    bytes1 = np.exp(rtts[:phase1_end] * 0.7) * 700
    
    # Phase 2: Hit rate limit - perfectly constant throughput
    phase2_start = phase1_end
    rate_limit = 5000
    bytes2 = bytes1[-1] + (rtts[phase2_start:] - rtts[phase2_start]) * rate_limit
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2])
    
    # Add small amount of noise (jitter only)
    noise = np.random.normal(0, 200, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes


def scenario_competing_flows(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 7: Competing Flows
    Variable throughput due to competition with other TCP flows
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Phase 1: Start alone - high throughput (exponential)
    phase1_end = 50
    bytes1 = np.exp(rtts[:phase1_end] * 0.9) * 700
    
    # Phase 2: Other flows join - throughput drops
    phase2_start = phase1_end
    phase2_end = 100
    bytes2 = bytes1[-1] + (rtts[phase2_start:phase2_end] - rtts[phase2_start]) * 3000
    
    # Phase 3: Some flows leave - throughput increases
    phase3_start = phase2_end
    phase3_end = 150
    bytes3 = bytes2[-1] + (rtts[phase3_start:phase3_end] - rtts[phase3_start]) * 5500
    
    # Phase 4: More competition - throughput drops again
    phase4_start = phase3_end
    bytes4 = bytes3[-1] + (rtts[phase4_start:] - rtts[phase4_start]) * 2500
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2, bytes3, bytes4])
    
    # Add noise from competing traffic
    noise = np.random.normal(0, 800, n_points)
    # Random spikes from other flows
    spike_indices = np.random.choice(n_points, size=n_points//8, replace=False)
    noise[spike_indices] += np.random.uniform(-1500, 1500, len(spike_indices))
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes


def scenario_application_limited(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 8: Application Limited
    Application sends data in bursts (e.g., video streaming with GOP boundaries)
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Create bursty pattern (application sends frames in bursts)
    burst_size = 20
    idle_size = 10
    burst_rate = 8000
    idle_rate = 500
    
    cumulative_bytes = np.zeros(n_points)
    idx = 0
    
    while idx < n_points:
        # Burst phase
        burst_end = min(idx + burst_size, n_points)
        for i in range(idx, burst_end):
            if i == 0:
                cumulative_bytes[i] = burst_rate * rtts[i]
            else:
                cumulative_bytes[i] = cumulative_bytes[i-1] + burst_rate * (rtts[i] - rtts[i-1])
        idx = burst_end
        
        if idx >= n_points:
            break
        
        # Idle/low rate phase
        idle_end = min(idx + idle_size, n_points)
        for i in range(idx, idle_end):
            cumulative_bytes[i] = cumulative_bytes[i-1] + idle_rate * (rtts[i] - rtts[i-1])
        idx = idle_end
    
    # Add moderate noise
    noise = np.random.normal(0, 400, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes


def scenario_initial_burst_then_steady(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 9: Initial Burst then Steady State
    Large initial window (IW10) followed by steady state
    """
    rtts = np.linspace(0, 8, n_points)
    
    # Phase 1: Large initial burst (IW10 = 10 * MSS = 14600 bytes)
    phase1_end = 20
    bytes1 = np.exp(rtts[:phase1_end] * 1.5) * 500
    
    # Phase 2: Settle into steady state
    phase2_start = phase1_end
    bytes2 = bytes1[-1] + (rtts[phase2_start:] - rtts[phase2_start]) * 4500
    
    # Combine phases
    cumulative_bytes = np.concatenate([bytes1, bytes2])
    
    # Add noise
    noise = np.random.normal(0, 400, n_points)
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)

    return rtts, cumulative_bytes


def scenario_mobile_varying_signal(n_points: int = 200) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Scenario 10: Mobile with Varying Signal Strength
    Throughput varies as mobile device moves (fading channel)
    """
    rtts = np.linspace(0, 10, n_points)
    
    # Create sinusoidal variation (signal strength varying)
    # Split into phases for consistency with format
    base_rate = 3500
    variation = 2000
    frequency = 2.0  # cycles over the trace
    
    # Generate as single phase with varying rate
    cumulative_bytes = np.zeros(n_points)
    for i in range(n_points):
        rate = base_rate + variation * np.sin(2 * np.pi * frequency * rtts[i] / rtts[-1])
        if i == 0:
            cumulative_bytes[i] = rate * rtts[i]
        else:
            cumulative_bytes[i] = cumulative_bytes[i-1] + rate * (rtts[i] - rtts[i-1])
    
    # Add significant noise (wireless channel)
    noise = np.random.normal(0, 1000, n_points)
    # Random deep fades
    fade_indices = np.random.choice(n_points, size=n_points//15, replace=False)
    noise[fade_indices] -= np.random.uniform(3000, 6000, len(fade_indices))
    cumulative_bytes = cumulative_bytes + np.cumsum(noise)
    cumulative_bytes = np.maximum.accumulate(cumulative_bytes)
    
    return rtts, cumulative_bytes

def scenario_real_100kb_2():
    rtts = [0, 54, 54, 85, 117, 119, 120, 147]
    cumacks = [0, 0, 0, 27.8984375, 69.5361328125, 82.330078125, 84.65625, 84.65625]
    return np.array(rtts), np.array(cumacks)

def scenario_real_100kb_3():
    rtts = [0.0, 32.334483999999996, 49.258456, 77.64374000000001, 83.678962, 84.980699, 85.229395, 85.46682, 113.565613, 113.891173, 119.889014, 126.674606, 136.045604, 141.648366, 141.651081, 143.697082, 143.69943700000002, 147.748028, 147.77710199999999, 151.126765, 157.66594, 160.075502, 162.612859, 168.09229, 170.383165, 173.362759, 174.837781, 182.402878, 182.435599, 182.436791, 182.446289]
    cumacks = [0.0, 0.0009765625, 0.0009765625, 2.8134765625, 3.2138671875, 3.2138671875, 3.2138671875, 3.2138671875, 6.5498046875, 6.5498046875, 13.5810546875, 14.6357421875, 22.7216796875, 25.5341796875, 28.1123046875, 30.9248046875, 33.5029296875, 36.3154296875, 41.7646484375, 47.1552734375, 53.7177734375, 57.9365234375, 64.4990234375, 71.2373046875, 76.6279296875, 84.7138671875, 88.9326171875, 95.7294921875, 98.1904296875, 104.2158203125, 104.2158203125]    
    return np.array(rtts), np.array(cumacks)

def scenario_real_1mb_1():
    rtts = [0.0, 37.2419999986887, 68.218999998644, 68.28099999949336, 99.56900000013411, 101.12999999895692, 123.80399999953806, 130.2050000000745, 133.6279999986291, 136.3969999998808, 139.41799999959767, 163.25499999895692, 163.5, 163.56499999947846, 166.4799999985844, 172.1820000000298, 172.28999999910593, 192.01299999840558, 197.34299999848008, 197.44799999892712, 201.80399999953806, 201.8980000000447, 224.5, 224.64199999906123, 230.71299999952316, 230.7879999987781, 255.65499999932945, 263.59999999962747, 263.7139999996871, 263.804999999702, 263.83799999952316, 288.30399999953806, 288.4320000000298, 291.31299999915063, 297.15599999949336, 317.93799999915063, 348.093999998644, 350.75799999944866, 350.8119999989867]
    cumacks = [0, 0, 27.1884765625, 27.1884765625, 58.7958984375, 81.2099609375, 82.3896484375, 114.2333984375, 146.076171875, 177.927734375, 190.904296875, 230.998046875, 268.7392578125, 275.8173828125, 313.5595703125, 356.001953125, 393.720703125, 413.865234375, 451.5927734375, 481.05859375, 518.77734375, 531.8173828125, 569.552734375, 607.271484375, 647.33203125, 669.865234375, 701.701171875, 739.451171875, 777.1767578125, 814.9189453125, 825.552734375, 863.2841796875, 892.751953125, 924.5771484375, 957.701171875, 957.701171875, 995.443359375, 1024.0615234375, 1024.0615234375]
    return np.array(rtts), np.array(cumacks)

def scenario_real_1mb_2():
    rtts = [0, 27, 27, 50, 72, 74, 93, 96, 100, 102, 115, 118, 122, 125, 128, 137, 149, 150, 150, 159, 175, 175, 181, 183, 201, 201, 203, 223, 225]
    cumacks = [0, 0, 0, 27.8994140625, 76.51953125, 84.6611328125, 116.056640625, 147.4521484375, 185.833984375, 198.6279296875, 230.0234375, 266.0712890625, 332.333984375, 407.86328125, 426.45703125, 457.826171875, 539.166015625, 660.017578125, 668.15234375, 812.2236328125, 879.611328125, 894.6962890625, 894.6962890625, 894.6962890625, 930.6923828125, 1006.2294921875, 1006.2294921875, 1006.2294921875, 1006.2294921875]
    return np.array(rtts), np.array(cumacks)

def scenario_real_1mb_3():
    rtts = [0.0, 22.783968, 22.983802, 43.962083, 50.097015, 51.312180999999995, 51.526592, 51.529047, 71.897341, 72.177425, 77.665201, 77.882458, 86.055787, 88.386386, 88.389061, 91.66906800000001, 94.236976, 94.240402, 97.60498700000001, 99.937685, 99.94011, 103.26917900000001, 105.610277, 105.612692, 107.430205, 108.895218, 109.807025, 111.180076, 111.84931900000001, 111.851664, 112.975398, 114.679659, 114.681653, 115.471812, 116.6719, 116.674204, 117.293203, 120.03573800000001, 120.038383, 120.713157, 120.727153, 121.657134, 122.47197999999999, 122.474625, 124.375084, 126.101827, 126.104241, 127.16719200000001, 128.855303, 129.06161899999998, 129.063853, 129.940404, 130.410134, 131.96228, 131.964615, 131.965356, 133.013509, 133.01580299999998, 135.456974, 135.472854, 135.686524, 137.849233, 137.851578, 137.85230900000002, 138.603065, 138.80178700000002, 138.82443899999998, 141.693161, 141.695545, 141.696247, 143.987497, 143.989842, 144.00311599999998, 144.714789, 147.23734199999998, 148.031329, 148.033774, 148.03454499999998, 150.01715700000003, 150.019562, 150.020263, 150.91602, 150.930888, 150.93179, 152.70710400000002, 153.370186, 154.099281, 154.101615, 155.355333, 156.18666000000002, 156.88421599999998, 156.88656, 158.244843, 158.98004, 159.939567, 160.150922, 160.15300599999998, 161.050387, 161.821551, 162.61587799999998, 162.618463, 162.619114, 163.681513, 164.435074, 165.50092, 166.31151799999998, 166.313922, 166.490453, 167.51976, 167.522235, 168.495547, 168.510876, 169.34046999999998, 170.014612, 171.05021100000002, 173.755246, 173.757801, 173.758663, 175.152693, 175.154907, 175.972658, 176.521255, 179.225479, 181.554951, 182.02473999999998, 184.693498, 187.385548, 188.307324, 190.279022, 192.96971399999998, 193.772868, 194.84783099999999, 196.208218, 198.497104, 199.267066, 201.697858, 204.165077, 204.691112, 207.490905, 213.856675, 213.863468, 213.86471]
    cumacks = [0.0, 0.0009765625, 0.0009765625, 2.8134765625, 3.2138671875, 3.2138671875, 3.2138671875, 3.2138671875, 8.8388671875, 8.8388671875, 13.0576171875, 14.6376953125, 17.3330078125, 20.1455078125, 24.3642578125, 27.1767578125, 29.5205078125, 37.9580078125, 42.1767578125, 44.9892578125, 53.7197265625, 61.8056640625, 68.8369140625, 71.2392578125, 75.4580078125, 78.2705078125, 84.9501953125, 90.1064453125, 92.9189453125, 97.1376953125, 99.5400390625, 103.7587890625, 106.5712890625, 115.7119140625, 118.5244140625, 121.3369140625, 123.7978515625, 128.0166015625, 133.6416015625, 140.6728515625, 144.0126953125, 155.2626953125, 160.8876953125, 164.2275390625, 168.4462890625, 172.6650390625, 181.1025390625, 197.9189453125, 202.1376953125, 214.7939453125, 219.0126953125, 221.8251953125, 223.5830078125, 226.3955078125, 232.0205078125, 239.0517578125, 253.1142578125, 257.3330078125, 264.3642578125, 282.6455078125, 285.2978515625, 289.5166015625, 296.5478515625, 300.7666015625, 303.5791015625, 313.4228515625, 320.2783203125, 335.7470703125, 344.1845703125, 348.4033203125, 351.2158203125, 358.0126953125, 363.6376953125, 383.3251953125, 386.1376953125, 393.1689453125, 405.8251953125, 411.4501953125, 414.2626953125, 418.6572265625, 427.0947265625, 435.5322265625, 439.7509765625, 446.7822265625, 449.5947265625, 452.4072265625, 460.8447265625, 474.9072265625, 477.7197265625, 490.3759765625, 500.2197265625, 510.0634765625, 512.8759765625, 515.6884765625, 518.5009765625, 528.3447265625, 538.1884765625, 541.0009765625, 553.6572265625, 557.8759765625, 562.0947265625, 573.3447265625, 576.1572265625, 578.9697265625, 583.1884765625, 593.0322265625, 601.4697265625, 604.2822265625, 614.1259765625, 616.9384765625, 619.7509765625, 635.2197265625, 639.4384765625, 642.2509765625, 645.0634765625, 649.2822265625, 667.5634765625, 680.2197265625, 683.0322265625, 702.7197265625, 705.5322265625, 708.3447265625, 711.1572265625, 768.8134765625, 771.6259765625, 774.4384765625, 777.2509765625, 834.9072265625, 837.7197265625, 840.5322265625, 843.3447265625, 898.1884765625, 901.0009765625, 903.8134765625, 906.6259765625, 964.2822265625, 967.0947265625, 969.9072265625, 972.7197265625, 1027.5634765625, 1030.3759765625, 1031.189453125]
    return np.array(rtts), np.array(cumacks)

def scenario_real_1mb_4():
    rtts = [0.0, 34.66799999959767, 65.28299999982119, 95.11299999989569, 95.343999998644, 127.08699999935925, 129.875, 164.59899999946356, 164.7379999998957, 167.5230000000447, 169.1279999986291, 188.1509999986738, 198.11899999901652, 199.14199999906123, 199.23199999891222, 229.74499999918044, 229.90299999900162, 239.125, 260.8179999999702, 263.2639999985695, 264.55199999921024, 269.1069999989122, 269.163999998942, 271.75899999961257, 273.5269999988377, 299.8319999985397, 307.5719999987632, 307.6689999997616, 307.71199999935925, 336.9029999990016, 338.5139999985695, 346.52899999916553, 346.6380000002682, 364.6229999996722, 394.9759999997914, 397.96299999952316, 402.6579999998212, 402.7290000002831, 406.1610000003129, 425.94999999925494, 430.7180000003427, 433.78099999949336]
    cumacks = [0, 0, 26.9609375, 54.9638671875, 54.9638671875, 90.3310546875, 108.0263671875, 135.1591796875, 152.845703125, 178.798828125, 200.033203125, 209.470703125, 250.7431640625, 281.37890625, 299.07421875, 348.60546875, 367.451171875, 391.1591796875, 420.6435546875, 456.0341796875, 465.4716796875, 503.2216796875, 513.82421875, 552.740234375, 569.21484375, 605.77734375, 645.865234375, 685.974609375, 701.4169921875, 727.3408203125, 756.8330078125, 799.3017578125, 839.36328125, 839.36328125, 873.56640625, 906.59765625, 947.88671875, 980.91796875, 1019.8193359375, 1024.056640625, 1024.056640625, 1024.056640625]
    return np.array(rtts), np.array(cumacks)

def scenario_real_1mb_5():
    rtts = [0, 30, 30, 52, 71, 74, 77, 81, 105, 105, 125, 128, 132, 148, 151, 155, 170, 172, 182, 182, 194, 195, 204, 209, 209, 218, 226, 226, 230, 247, 251, 272]
    cumacks = [0, 0, 0, 27.8994140625, 38.1376953125, 57.91015625, 76.51953125, 84.6611328125, 160.24609375, 178.85546875, 178.85546875, 247.447265625, 298.623046875, 311.39453125, 357.91796875, 402.1005859375, 433.49609375, 471.8701171875, 550.92578125, 612.517578125, 700.8056640625, 705.4541015625, 732.1640625, 813.505859375, 836.748046875, 842.54296875, 927.369140625, 988.953125, 988.953125, 988.953125, 1024.0322265625, 1024.0322265625]
    return np.array(rtts), np.array(cumacks)

def scenario_real_1mb_6():
    rtts = [0.0, 30.890307999999997, 30.915115, 61.665032000000004, 68.091541, 70.366018, 70.731111, 70.733846, 99.63701599999999, 99.644339, 105.433105, 111.146048, 121.494488, 124.014876, 127.176143, 127.17874800000001, 127.823895, 129.491096, 132.64198399999998, 133.20981600000002, 139.02975, 139.03985899999998, 1897.923912, 1904.653909, 1910.4497170000002, 1916.342166, 1922.0698869999999, 1927.540096, 1933.204098, 1938.636486, 1938.672744, 1944.180222, 1944.223223, 1949.978265, 1955.808979, 1955.811563, 1961.5774560000002, 1961.5812329999999, 1967.4244899999999, 1974.232272, 1979.96353, 1979.993526, 1985.941309, 1985.973038, 1992.063177, 1997.785719, 1997.8019789999998, 2003.5932189999999, 2003.6020959999998, 2009.316952, 2009.319698, 2015.103453, 2015.141104, 2021.0739389999999, 2021.1175400000002, 2067.7231049999996, 2073.420068, 3900.319059, 3906.092145, 3911.950049, 3911.953837, 3917.651481, 3917.673532, 3923.3724589999997, 3923.375435, 3929.081721, 3929.1054050000002, 3934.671158, 3934.95037, 3941.1767050000003, 3947.197685, 3947.202013, 3947.22179, 3953.080926, 3953.084263, 3958.464673, 3958.928441, 3965.364293, 3965.367148, 3971.081694, 3971.098486, 3977.296382, 3977.3269290000003, 3977.328512, 3983.6481510000003, 3983.652479, 3989.4578300000003, 3989.460445, 3995.22778, 3995.230285, 4001.0886699999996, 4001.111723, 4001.1131659999996, 4007.239683, 4007.2633680000004, 4013.778933, 4019.781619, 4019.7840730000003, 4019.7986309999997, 4025.8825580000002, 4025.92075, 4032.0598910000003, 4032.082533, 4038.016821, 4038.0325900000003, 4038.033552, 4044.1789850000005, 4044.1813289999996, 4050.3196289999996, 4050.322123, 4057.0134830000006, 5565.8268499999995, 5571.795036, 5578.084378, 5584.0371700000005, 5589.524877, 5595.82842, 5601.968723999999, 5602.009008999999, 5607.719563, 5607.737015, 5613.83803, 5613.861755, 5619.2338150000005, 5619.698264000001, 5624.925698, 5625.225289, 5630.922453, 5630.925238, 5637.0090150000005, 5637.026027, 5642.965484, 5643.008805, 5643.010559, 5648.683577, 5649.229419, 5654.465776, 5654.96522, 5660.990423, 5660.997426, 7166.377221000001, 7172.049217, 7177.674927, 7177.678313, 7183.883308, 7190.077081, 7195.645864, 7195.649270999999, 7201.973107, 7208.0176409999995, 7208.041476, 7214.138072, 7219.919833999999, 7219.922269, 7219.936726, 7225.979897, 7225.995346000001, 7232.189380000001, 7232.192956999999, 7238.106911, 7243.557213, 8747.673261, 8753.322325, 8753.331361, 8759.889246, 8759.892943, 8759.91792, 8765.626585, 8771.33521, 8771.337754999999, 8777.435729, 8777.503115, 8783.079072, 8783.081486000001, 8788.8267, 8788.849672999999, 8788.851176, 8794.977613000001, 8800.77816, 8800.795974, 8806.389813999998, 8812.071489, 10316.273431000001, 10322.055649, 10328.086898, 10333.888917999999, 10333.956564999999, 10339.917532, 10339.933481999999, 10345.78775, 10351.916501, 10357.968780000001, 10357.984369, 10363.649803, 10363.652158, 10368.995349, 10369.422879, 10374.851034000001, 10375.151807, 10381.022977, 10386.758141, 10386.760585999999, 10392.594536, 10398.314597, 10404.696061999999, 10404.712753, 10410.448519, 10410.452056, 10416.825535, 10422.908531, 10422.912017, 10428.915423999999, 10435.099379000001, 10435.122482, 10440.961701999999, 10441.014651, 10447.054326, 10452.570901, 11958.597976000001, 11964.574822999999, 11970.207626000001, 11976.207993, 11982.926924, 11982.929307999999, 11988.986540999998, 11994.578237000002, 11994.582014000001, 13499.867139, 13506.040514, 13506.043971000001, 13511.76867, 13517.467657, 13517.483586999999, 13523.016754, 13523.031962, 13528.915084, 13535.035209, 13540.76794, 13540.770504999999, 13546.81317, 13546.8397, 13552.64726, 13552.650615999999, 13558.889083, 13558.891558, 13564.667499000001, 13564.669923, 13570.199533, 13575.986555, 13584.878865, 13584.911115, 13584.912448000001]
    cumacks = [0.0, 0.0009765625, 0.0009765625, 2.8134765625, 3.212890625, 3.212890625, 3.212890625, 3.212890625, 6.55078125, 6.55078125, 13.58203125, 14.63671875, 20.02734375, 22.83984375, 22.83984375, 22.83984375, 22.83984375, 22.83984375, 22.83984375, 32.33203125, 32.33203125, 32.33203125, 39.12890625, 41.94140625, 44.75390625, 47.56640625, 51.78515625, 56.00390625, 60.22265625, 63.03515625, 65.84765625, 68.66015625, 71.47265625, 78.50390625, 81.31640625, 85.53515625, 88.34765625, 92.56640625, 101.00390625, 109.44140625, 112.25390625, 117.87890625, 123.50390625, 126.31640625, 134.75390625, 137.56640625, 144.59765625, 147.41015625, 153.03515625, 157.25390625, 162.87890625, 169.91015625, 172.72265625, 179.75390625, 183.97265625, 185.37890625, 185.37890625, 186.78515625, 189.59765625, 191.00390625, 193.81640625, 196.62890625, 200.84765625, 202.25390625, 207.87890625, 209.28515625, 214.91015625, 216.31640625, 223.34765625, 231.78515625, 233.19140625, 234.59765625, 240.22265625, 243.03515625, 250.06640625, 251.47265625, 259.91015625, 262.72265625, 269.75390625, 273.97265625, 279.59765625, 282.41015625, 288.03515625, 290.84765625, 296.47265625, 302.09765625, 303.50390625, 313.34765625, 314.75390625, 324.59765625, 326.00390625, 330.22265625, 337.25390625, 345.69140625, 349.91015625, 362.56640625, 363.97265625, 365.37890625, 375.22265625, 382.25390625, 389.28515625, 393.50390625, 403.34765625, 406.16015625, 411.78515625, 417.41015625, 427.25390625, 431.47265625, 438.50390625, 445.53515625, 445.53515625, 446.94140625, 449.75390625, 461.00390625, 462.41015625, 468.03515625, 476.47265625, 480.69140625, 484.91015625, 486.31640625, 493.34765625, 500.37890625, 501.78515625, 503.19140625, 511.62890625, 513.03515625, 521.47265625, 528.50390625, 531.31640625, 535.53515625, 541.16015625, 542.56640625, 548.19140625, 552.41015625, 553.81640625, 563.66015625, 565.06640625, 569.28515625, 569.28515625, 569.28515625, 570.69140625, 573.50390625, 580.53515625, 580.53515625, 586.16015625, 593.19140625, 594.59765625, 600.22265625, 607.25390625, 611.47265625, 614.28515625, 622.72265625, 624.12890625, 625.53515625, 631.16015625, 633.97265625, 639.59765625, 641.00390625, 649.44140625, 650.84765625, 650.84765625, 652.25390625, 653.66015625, 655.06640625, 656.47265625, 660.69140625, 660.69140625, 666.31640625, 667.72265625, 671.94140625, 673.34765625, 678.97265625, 683.19140625, 686.00390625, 688.81640625, 691.62890625, 693.03515625, 701.47265625, 704.28515625, 709.91015625, 718.34765625, 723.97265625, 733.81640625, 736.62890625, 740.84765625, 742.25390625, 746.47265625, 749.28515625, 752.09765625, 757.72265625, 764.75390625, 768.97265625, 771.78515625, 774.59765625, 778.81640625, 780.22265625, 787.25390625, 788.66015625, 795.69140625, 802.72265625, 805.53515625, 811.16015625, 821.00390625, 830.84765625, 837.87890625, 840.69140625, 844.91015625, 850.53515625, 860.37890625, 866.00390625, 871.62890625, 882.87890625, 885.69140625, 894.12890625, 898.34765625, 905.37890625, 908.19140625, 908.19140625, 909.59765625, 912.41015625, 919.44140625, 925.06640625, 927.87890625, 932.09765625, 937.72265625, 937.72265625, 937.72265625, 944.75390625, 946.16015625, 947.56640625, 951.78515625, 954.59765625, 956.00390625, 958.81640625, 961.62890625, 967.25390625, 972.87890625, 974.28515625, 979.91015625, 982.72265625, 986.94140625, 988.34765625, 993.97265625, 998.19140625, 1002.41015625, 1005.22265625, 1010.84765625, 1019.28515625, 1027.72265625, 1030.53515625, 1031.1884765625, 1031.1884765625]
    return np.array(rtts), np.array(cumacks)

"""
Plot the original trace with segment boundaries and save to file.

Args:
    rtts: Time values (in ms)
    cumulative_bytes: Cumulative bytes ACKed
    segments: List of Segment objects from segment_trace_pelt
    filename: Output filename for the plot
    title: Plot title
    figsize: Figure size
"""
def plot_segmented_trace(rtts: np.ndarray, 
                        cumulative_bytes: np.ndarray,
                        segments: List[Segment],
                        filename: str = "trace_segmentation.png",
                        title: str = "TCP Trace Segmentation",
                        figsize: Tuple[int, int] = (14, 8)):
    
    _, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, sharex=True)
    
    # Top plot: Cumulative bytes with segment boundaries
    ax1.plot(rtts, cumulative_bytes, 'b-', linewidth=1.5, label='Cumulative Bytes')
    
    # Add vertical lines at segment boundaries
    colors = plt.cm.tab10(np.linspace(0, 1, len(segments)))
    for i, seg in enumerate(segments):
        # Draw vertical line at segment start
        ax1.axvline(x=seg.rtts[0], color=colors[i], linestyle='--', 
                   linewidth=2, alpha=0.7, label=f'Seg {seg.segment_id}')
        
        # Shade the segment region
        ax1.axvspan(seg.rtts[0], seg.rtts[-1], alpha=0.1, color=colors[i])
    
    # Mark the end of the last segment
    if segments:
        ax1.axvline(x=segments[-1].rtts[-1], color='red', linestyle='--', 
                   linewidth=2, alpha=0.7)
    
    ax1.set_ylabel('Cumulative Bytes', fontsize=12)
    ax1.set_title(title, fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left', fontsize=9, ncol=min(4, len(segments)))
    
    # Bottom plot: Instantaneous rate with segments
    ax2.set_xlabel('RTT (ms)', fontsize=12)
    ax2.set_ylabel('Rate (bytes/ms)', fontsize=12)
    
    for i, seg in enumerate(segments):
        # Plot rate for each segment
        ax2.plot(seg.rtts, seg.rates, color=colors[i], linewidth=2, 
                label=f'Seg {seg.segment_id}: {seg.avg_rate:.2f} B/ms avg')
        
        # Add vertical line at segment boundary
        ax2.axvline(x=seg.rtts[0], color=colors[i], linestyle='--', 
                   linewidth=2, alpha=0.7)
        
        # Shade the segment region
        ax2.axvspan(seg.rtts[0], seg.rtts[-1], alpha=0.1, color=colors[i])
    
    # Mark the end of the last segment
    if segments:
        ax2.axvline(x=segments[-1].rtts[-1], color='red', linestyle='--', 
                   linewidth=2, alpha=0.7)
    
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper left', fontsize=9, ncol=2)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Plot saved to {filename}")

# Example usage
if __name__ == "__main__":
    # Run PELT-based segmentation
    # 5MB : smooth_window = 21, rate_window = 20, min_segment_length = 10 (200+ points)
    # 100KB : smooth_window = 3, rate_window = 3, min_segment_length = 1  (~ 10 points)

    # Load trace
    rtts, cumulative_bytes = scenario_real_1mb_5()
    segments = segment_trace_pelt(rtts, cumulative_bytes)
    plot_segmented_trace(rtts, cumulative_bytes, segments, 
                         filename="trace_segmentation.png",
                         title="Network Trace with PELT Segmentation")