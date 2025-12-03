#!/bin/bash
set -e

IMAGE_NAME="network-measurement-tool:latest"
IMAGE_FILE="network-measurement-tool.tar.gz"

echo "=== Network Measurement Tool Deployment ==="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed!"
    echo "Install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi

# Check if image file exists
if [ ! -f "$IMAGE_FILE" ]; then
    echo "Error: Image file $IMAGE_FILE not found!"
    echo "Please copy the image file to this directory first."
    exit 1
fi

# Load the image
echo "Loading Docker image..."
gunzip -c "$IMAGE_FILE" | docker load

# Verify image loaded
if docker images | grep -q "network-measurement-tool"; then
    echo "✓ Image loaded successfully"
else
    echo "✗ Failed to load image"
    exit 1
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p results data

# Check for params_docker.json
if [ ! -f "params_docker.json" ]; then
    echo "Warning: params_docker.json not found. Using default configuration."
fi

# Detect network interface
DETECTED_INTERFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
echo ""
echo "Detected network interface: $DETECTED_INTERFACE"
echo "Make sure to update params_docker.json if this is incorrect."

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "To run the measurement tool:"
echo "  docker run --privileged --network host \\"
echo "    -v \$(pwd)/params_docker.json:/app/params_docker.json:ro \\"
echo "    -v \$(pwd)/results:/app/results \\"
echo "    -v \$(pwd)/data:/app/data \\"
echo "    $IMAGE_NAME"