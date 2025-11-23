FROM ubuntu:24.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and runtime libraries
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
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
    libboost-system1.74.0 \
    libboost-filesystem1.74.0 \
    libboost-thread1.74.0 \
    libboost-program-options1.74.0 \
    libboost-context1.74.0 \
    libdouble-conversion3 \
    libgoogle-glog0v5 \
    libevent-2.1-7 \
    libgflags2.2 \
    liblz4-1 \
    libzstd1 \
    libsnappy1v5 \
    libsodium23 \
    libfmt8 \
    && rm -rf /var/lib/apt/lists/*

# Set up non-root user with sudo privileges (needed for tc commands)
RUN useradd -m -s /bin/bash netuser && \
    echo "netuser ALL=(ALL) NOPASSWD: /sbin/tc, /usr/bin/ip, /usr/sbin/modprobe" >> /etc/sudoers

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Create directories for executables
RUN mkdir -p /opt/clients

# Copy pre-built executables
COPY --chmod=755 executables/ngtcp2/wsslclient /opt/clients/wsslclient
COPY --chmod=755 executables/proxygen/hq /opt/clients/hq

# Copy any required shared libraries (if needed)
# COPY executables/libs/*.so* /usr/local/lib/
# RUN ldconfig

# Set up application directory
WORKDIR /app
COPY . /app/

# Create necessary directories
RUN mkdir -p /app/data/tmp/qlog /app/data/tmp/pcap /app/data/qlogs /app/data/pcaps && \
    chown -R netuser:netuser /app

# Switch to non-root user
USER netuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV SSLKEYLOGFILE=/app/data/tmp/sslkeylog

# Default command
CMD ["python3", "main.py"]