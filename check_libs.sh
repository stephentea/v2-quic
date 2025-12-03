#!/bin/bash
set -e

echo "Gathering executables for Docker build..."

# Create directories
mkdir -p executables/ngtcp2
mkdir -p executables/proxygen
mkdir -p executables/libs

# Copy ngtcp2 client
cp "$HOME/ngtcp2/examples/wsslclient" executables/ngtcp2/
echo "✓ Copied ngtcp2 wsslclient"

# Copy proxygen client
cp "$HOME/proxygen/_build/proxygen/httpserver/hq" executables/proxygen/
echo "✓ Copied proxygen hq"

# Copy custom shared libraries
echo ""
echo "Copying custom shared libraries..."

# Get custom library paths
NGTCP2_LIBS=$(ldd executables/ngtcp2/wsslclient | grep "=> /" | awk '{print $3}' | grep "/usr/local/lib" || true)
PROXYGEN_LIBS=$(ldd executables/proxygen/hq | grep "=> /" | awk '{print $3}' | grep "/usr/local/lib" || true)

for lib in $NGTCP2_LIBS $PROXYGEN_LIBS; do
    if [ -f "$lib" ]; then
        cp "$lib" executables/libs/
        echo "  Copied $(basename $lib)"
    fi
done

echo ""
echo "Done! Executables ready in ./executables/"