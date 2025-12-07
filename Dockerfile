FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    tshark \
    wireshark-common \
    iproute2 \
    iputils-ping \
    kmod \
    sudo \
    curl \
    libssl3 \
    libev4 \
    libc-ares2 \
    zlib1g \
    libsodium23 \
    libboost-all-dev \
    libgoogle-glog-dev \
    libdouble-conversion-dev \
    libevent-dev \
    libgflags-dev \
    liblz4-1 \
    libsnappy1v5 \
    libunwind8 \
    libfmt-dev \
    && rm -rf /var/lib/apt/lists/*

RUN setcap cap_net_raw,cap_net_admin=eip /usr/bin/dumpcap

RUN useradd -m -s /bin/bash netuser && \
    echo "netuser ALL=(ALL) NOPASSWD: /sbin/tc, /usr/bin/ip, /usr/sbin/modprobe" >> /etc/sudoers

RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip setuptools wheel

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /opt/clients

COPY --chmod=755 executables/ngtcp2/wsslclient /opt/clients/wsslclient
COPY --chmod=755 executables/proxygen/hq /opt/clients/hq

COPY executables/libs/*.so* /usr/local/lib/
RUN ldconfig

WORKDIR /app
COPY pipeline/ /app/pipeline/
COPY clients/ /app/clients/
COPY network/ /app/network/
COPY analysis/ /app/analysis/
COPY main.py /app/
COPY run_periodic.py /app/

RUN mkdir -p /app/data/tmp/qlog /app/data/tmp/pcap /app/data/qlogs /app/data/pcaps && \
    mkdir -p /tmp/logs && \
    chown -R netuser:netuser /app && \
    chown -R netuser:netuser /tmp/logs && \
    chmod -R 755 /app/data

USER netuser

ENV PYTHONUNBUFFERED=1
ENV SSLKEYLOGFILE=/app/data/tmp/sslkeylog

# Default command
CMD ["python3", "run_periodic.py"]
