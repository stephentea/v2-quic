#!/bin/bash
set -e

echo "Gathering executables for Docker build..."

# Create directories
mkdir -p executables/ngtcp2
mkdir -p executables/proxygen
mkdir -p executables/libs

# Copy ngtcp2 client
if [ -f "/home/stephenchien/ngtcp2/examples/wsslclient" ]; then
    cp "/home/stephenchien/ngtcp2/examples/wsslclient" executables/ngtcp2/
    echo "✓ Copied ngtcp2 wsslclient"
else
    echo "✗ ngtcp2 wsslclient not found"
    exit 1
fi

# Copy proxygen client
if [ -f "/home/stephenchien/proxygen/proxygen/_build/proxygen/httpserver/hq" ]; then
    cp "/home/stephenchien/proxygen/proxygen/_build/proxygen/httpserver/hq" executables/proxygen/
    echo "✓ Copied proxygen hq"
else
    echo "✗ proxygen hq not found"
    exit 1
fi

# Copy custom shared libraries
echo ""
echo "Copying custom shared libraries..."

# Function to copy library if it exists
copy_lib() {
    if [ -f "$1" ]; then
        cp "$1" executables/libs/
        echo "  ✓ $(basename $1)"
        return 0
    else
        echo "  ✗ $(basename $1) not found at $1"
        return 1
    fi
}

# ngtcp2 custom libraries
copy_lib "/home/stephenchien/ngtcp2/lib/.libs/libngtcp2.so.16"
copy_lib "/home/stephenchien/nghttp3/build/lib/libnghttp3.so.9"
copy_lib "/home/stephenchien/ngtcp2/crypto/wolfssl/.libs/libngtcp2_crypto_wolfssl.so.5"

# Find and copy libwolfssl
echo ""
echo "Looking for libwolfssl..."
WOLFSSL_LIB=$(find /usr/local/lib /usr/lib -name "libwolfssl.so.42" 2>/dev/null | head -1)
if [ -n "$WOLFSSL_LIB" ]; then
    copy_lib "$WOLFSSL_LIB"
else
    echo "  Trying to find wolfssl in common locations..."
    # Check if wolfssl is in a custom location
    if [ -d "/home/stephenchien/wolfssl" ]; then
        WOLFSSL_LIB=$(find /home/stephenchien/wolfssl -name "libwolfssl.so.42" 2>/dev/null | head -1)
        if [ -n "$WOLFSSL_LIB" ]; then
            copy_lib "$WOLFSSL_LIB"
        fi
    fi
fi

# proxygen custom libraries
copy_lib "/home/stephenchien/proxygen/proxygen/_build/deps/lib/libzstd.so.1"

# Create symlinks for libraries without version numbers
echo ""
echo "Creating symlinks..."
cd executables/libs
for lib in *.so.*; do
    if [ -f "$lib" ]; then
        base=$(echo "$lib" | sed 's/\.[0-9]*$//')
        if [ ! -e "$base" ]; then
            ln -s "$lib" "$base"
            echo "  ✓ $base -> $lib"
        fi
    fi
done
cd ../..

echo ""
echo "Libraries copied:"
ls -lh executables/libs/
echo ""
echo "Done! Executables and libraries ready in ./executables/"