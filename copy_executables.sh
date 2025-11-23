#!/bin/bash
set -e

echo "Gathering executables for Docker build..."

# Create directories
mkdir -p executables/ngtcp2
mkdir -p executables/proxygen
mkdir -p executables/libs

# Copy ngtcp2 client
if [ -f "$HOME/ngtcp2/examples/wsslclient" ]; then
    cp "$HOME/ngtcp2/examples/wsslclient" executables/ngtcp2/
    echo "✓ Copied ngtcp2 wsslclient"
else
    echo "✗ ngtcp2 wsslclient not found at $HOME/ngtcp2/examples/wsslclient"
    exit 1
fi

# Copy proxygen client
if [ -f "$HOME/proxygen/_build/proxygen/httpserver/hq" ]; then
    cp "$HOME/proxygen/_build/proxygen/httpserver/hq" executables/proxygen/
    echo "✓ Copied proxygen hq"
else
    echo "✗ proxygen hq not found at $HOME/proxygen/_build/proxygen/httpserver/hq"
    exit 1
fi

# Optional: Copy shared libraries
echo ""
echo "Checking for required shared libraries..."
echo "For ngtcp2:"
ldd executables/ngtcp2/wsslclient | grep "=> /" | awk '{print $3}' | grep -E "nghttp3|ngtcp2" || echo "  No custom libraries needed"

echo ""
echo "For proxygen:"
ldd executables/proxygen/hq | grep "=> /" | awk '{print $3}' | grep -E "folly|fizz|wangle|mvfst|proxygen" || echo "  No custom libraries needed"

echo ""
echo "Done! Executables ready in ./executables/"