"""
analyze_pcap() parses pcap and returns cumulative ACKs and RTTs.
analyze_qlog() parses qlog/sqlog and returns cumulative ACKs and RTTs.
"""

import json
from collections import OrderedDict

def make_unique(key, dct):
    counter = 0
    unique_key = key

    while unique_key in dct:
        counter += 1
        unique_key = '{}_{}'.format(key, counter)
    return unique_key


def parse_object_pairs(pairs):
    dct = OrderedDict()
    for key, value in pairs:
        if key in dct:
            key = make_unique(key, dct)
        dct[key] = value

    return dct


def merge(intervals):
    intervals.sort()

    result = []
    for start, end in intervals:
        if not result or start > result[-1][1]:
            result.append([start, end])
        elif end > result[-1][1]:
            result[-1][1] = end

    return result


def analyze_pcap(filename: str) -> tuple[dict, str]:
    ack_ts = {}
    rx_ts = {}
    window_updates = {}
    max_stream_data = {}
    lost_packets = []
    ack_packets_ts = []
    rx_packets_ts = []
    initial_rtt = None
    second_rtt = None
    init_cwnd = 0
    time_to_detection = {}
    detections = []
    first_client_packet_time = None
    last_server_packet_time = None

    if str(filename).count('delay-50') > 0:
        delay = 50
    elif str(filename).count('delay-100') > 0:
        delay = 100
    else:
        delay = 0

    with open(filename) as f:
        decoder = json.JSONDecoder(object_pairs_hook=parse_object_pairs)

        data = decoder.decode(f.read())

        num_lost = 0
        start_data_time = None
        sack_segs = []

        fin = False
        prev_seq = 0

        # Associate each ACK offset with a timestamp
        for packet in data:
            tcp = packet['_source']['layers']['tcp']
            srcport = tcp['tcp.srcport']
            time = float(tcp['Timestamps']['tcp.time_relative']) * 1000

            if tcp['tcp.flags_tree']['tcp.flags.fin'] == '1':
                fin = True

            init_rtt = tcp.get('tcp.analysis', {}).get(
                'tcp.analysis.initial_rtt')
            if init_rtt is not None:
                initial_rtt = float(init_rtt)

            if tcp.get("tcp.analysis", {}).get("tcp.analysis.acks_frame") == "4":
                second_rtt = float(tcp.get("tcp.analysis").get(
                    "tcp.analysis.ack_rtt"))

            # receive packet
            if srcport == '443':
                if tcp['tcp.len'] == '1376' and int(tcp['tcp.seq']) >= 3000:
                    if start_data_time is None:
                        start_data_time = time

                    min_rtt = min(initial_rtt, second_rtt) * 1000

                    if time - start_data_time < min_rtt:
                        init_cwnd += 1

                bytes_seq = int(tcp['tcp.seq'])
                bytes_len = int(tcp['tcp.len'])

                if bytes_seq in time_to_detection \
                        and bytes_seq > 1 \
                        and prev_seq != bytes_seq:
                    lost_packets.append(
                        (time_to_detection[bytes_seq], bytes_seq))
                    num_lost += 1
                    detections.append(
                        time - time_to_detection[bytes_seq])

                time_to_detection[bytes_seq] = time
                prev_seq = bytes_seq

                if tcp['tcp.len'] == '0' or int(tcp['tcp.seq']) < 3000:
                    continue

                if fin:
                    continue

                bytes_seq = int(tcp['tcp.seq']) / 1024
                bytes_len = int(tcp['tcp.len']) / 1024

                rx_ts[time + delay] = bytes_seq
                rx_packets_ts.append((time + delay, {'length': bytes_len}))

                # Track last server packet time (for data packets)
                if (int(tcp['tcp.len'])) > 0:
                    last_server_packet_time = time

                if bytes_seq > prev_seq:
                    prev_seq = bytes_seq
                else:
                    num_lost += 1
                    
            # send packet
            else:
                # Track first client packet time
                if first_client_packet_time is None:
                    first_client_packet_time = time

                if fin:
                    continue

                if tcp['tcp.flags_tree']['tcp.flags.syn'] == '1' and time > 500:
                    fin = True
                    continue

                bytes_ack = int(tcp['tcp.ack']) / 1024

                sack = tcp.get('tcp.options_tree', {}).get(
                    'tcp.options.sack_tree', {})

                if 'tcp.options.sack_le' in sack and 'tcp.options.sack_re' in sack:
                    le = 0
                    re = 0
                    for k, v in sack.items():
                        if k in {'tcp.option_kind', 'tcp.option_len', 'tcp.options.sack.count'}:
                            continue

                        if k.count('tcp.options.sack_le') > 0:
                            le = int(v)
                        elif k.count('tcp.options.sack_re') > 0:
                            re = int(v)
                            sack_segs.append([le, re])

                    sack_segs = merge(sack_segs)

                    added_segs = []
                    bytes_ack_prev = bytes_ack * 1024
                    for left, right in sack_segs:
                        if right <= bytes_ack_prev:
                            continue
                        if bytes_ack_prev < left:
                            added_segs.append([left / 1024, right / 1024])
                            bytes_ack += (right - left) / 1024
                        elif bytes_ack_prev < right:
                            added_segs.append([bytes_ack / 1024, right / 1024])
                            bytes_ack += (right - bytes_ack) / 1024

                ack_ts[time] = bytes_ack

                ack_packets_ts.append((time, bytes_ack))
                window = int(tcp['tcp.window_size']) / 1024
                window_updates[time] = window
                max_stream_data[time] = bytes_ack + window

    # Calculate TTLB
    ttlb = None
    if first_client_packet_time is not None and last_server_packet_time is not None:
        ttlb = last_server_packet_time - first_client_packet_time
    ttlb = ack_packets_ts[-1][0] - ack_packets_ts[0][0]

    return {
        'ack_ts': ack_ts,
        'ack_packets_ts': ack_packets_ts,
        'rx_ts': rx_ts,
        'rx_packets_ts': rx_packets_ts,
        'lost_packets': lost_packets,
        'ttlb': ttlb
    }


def analyze_qlog(filename: str) -> tuple[dict, str]:
    ack_ts = {}
    pkts_received = {}
    rx_ts = {}
    max_stream_data = {}
    lost_packets = []
    rx_packets_ts = []
    ack_packets_ts = []
    time_to_detection = {}
    detections = []
    first_client_packet_time = None
    last_server_packet_time = None
    first_time = None
    global_max_ack = None
    prev_pkt = {'pn': 0, 'dl': 0}
    loss_count = 0

    with open(filename, 'rb') as f:
        if 'sqlog' in filename.name:
            # Parse first line (metadata)
            RS = b'\x1e'
            lines = f.read().split(RS)
            first_obj = json.loads(lines[1].strip())

            # Get time format from metadata
            trace_info = first_obj.get('trace', {})
            common_fields = trace_info.get('common_fields', {})
            time_units = 'ms'  # JSON-SEQ uses milliseconds
            
            # Parse events from remaining lines
            events = []
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                
                event_obj = json.loads(line)
                
                # Convert to qlog array format: [time, category, event_type, data]
                time_val = event_obj.get('time', 0)
                name = event_obj.get('name', '')
                data = event_obj.get('data', {})
                
                # Split name into category and event_type
                if ':' in name:
                    category, event_type = name.split(':', 1)
                else:
                    category = ''
                    event_type = name
                
                events.append([time_val, category, event_type, data])
        else:
            # Standard qlog format - single JSON object
            data = json.load(open(filename))
            traces = data['traces'][0]
            events = traces['events']
            if 'configuration' in traces:
                time_units = traces['configuration']['time_units']
            else:
                time_units = 'ms'

        # Store all stream packets received by client
        for event in events:
            if not event:
                continue

            if time_units == 'ms':
                ts = int(event[0])
            else:
                ts = int(event[0]) / 1000

            event_type = event[2]
            event_data = event[3]

            if event_type.lower() == 'packet_sent' and first_time is None:
                first_time = ts

            if first_time is None:
                continue

            ts -= first_time

            if event_type.lower() == 'packet_received':
                # Associate packet num with data offset
                if 'frames' not in event_data:
                    continue

                frames = event_data['frames']

                for frame in frames:
                    if frame['frame_type'].lower() == 'stream':
                        if int(frame['stream_id']) != 0:
                            continue

                        pkt_num = int(event_data['header']['packet_number'])
                        offset = int(frame['offset'])
                        length = int(frame['length'])

                        if offset in time_to_detection:
                            detections.append(ts - time_to_detection[offset])

                        data_length = (offset + length) / 1024

                        pkts_received[pkt_num] = data_length
                        rx_ts[ts] = data_length
                        rx_packets_ts.append((ts, {'length': length / 1024}))

                        # Track last server packet time
                        last_server_packet_time = ts

                        if prev_pkt['pn'] + 1 != pkt_num:
                            lost_packets.append((ts, data_length))
                            loss_count += 1
                            time_to_detection[int(
                                prev_pkt['dl'] * 1024)] = ts

                        prev_pkt['pn'] = pkt_num
                        prev_pkt['dl'] = data_length

            if event_type.lower() == 'packet_sent':
                # Track first client packet time
                if first_client_packet_time is None:
                    first_client_packet_time = ts

                # Get max ack sent
                if 'frames' not in event_data:
                    continue

                packet_type = event_data.get('packet_type')
                if packet_type is None:
                    packet_type = event_data['header']['packet_type']
                frames = event_data['frames']

                for frame in frames:
                    if frame['frame_type'] == 'max_stream_data':
                        if 'maximum' in frame:
                            max_stream_data[ts] = int(frame['maximum']) / 1024

                    if 'acked_ranges' not in frame:
                        continue

                    for ack in frame['acked_ranges']:
                        if len(ack) != 2:
                            continue

                        ack_begin = int(ack[0])
                        ack_end = int(ack[1])
                        for i in range(ack_begin, ack_end + 1):
                            if i not in pkts_received:
                                continue

                            if global_max_ack is None:
                                global_max_ack = pkts_received[i]

                            global_max_ack = max(
                                global_max_ack, pkts_received[i])

                if packet_type != '1RTT':
                    ack_packets_ts.append((ts, 0))
                if global_max_ack is not None:
                    ack_ts[ts] = global_max_ack
                    ack_packets_ts.append((ts, global_max_ack))

    # Calculate TTLB
    ttlb = None
    if first_client_packet_time is not None and last_server_packet_time is not None:
        ttlb = last_server_packet_time - first_client_packet_time
    print(ack_packets_ts[-1][0], ack_packets_ts[0][0])
    ttlb = ack_packets_ts[-1][0] - ack_packets_ts[0][0]

    return {
        'ack_ts': ack_ts,
        'ack_packets_ts': ack_packets_ts,
        'rx_ts': rx_ts,
        'rx_packets_ts': rx_packets_ts,
        'max_stream_data': max_stream_data,
        'lost_packets': lost_packets,
        'ttlb': ttlb
    }