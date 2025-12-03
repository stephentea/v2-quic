#!/bin/bash
set -e

PACKAGE_NAME="network-measurement-tool-package"
VERSION=$(date +%Y%m%d_%H%M%S)
PACKAGE_DIR="${PACKAGE_NAME}_${VERSION}"

echo "=== Creating deployment package ==="

# Create package directory
mkdir -p "$PACKAGE_DIR"

# Save Docker image
echo "Saving Docker image (this may take a few minutes)..."
docker save network-measurement-tool:latest | gzip > "$PACKAGE_DIR/network-measurement-tool.tar.gz"

# Copy deployment files
echo "Copying deployment files..."
cp deploy.sh "$PACKAGE_DIR/"
cp docker-compose.yml "$PACKAGE_DIR/" 2>/dev/null || echo "No docker-compose.yml found (optional)"

# Create sample params_docker.json
cat > "$PACKAGE_DIR/params_docker.json" << 'EOF'
{
  "network_interface": "eth0",
  "clients": ["ngtcp2_h3", "proxygen_h3", "curl_h2"],
  "client-exec-paths": {
    "ngtcp2_h3": "/opt/clients/wsslclient",
    "proxygen_h3": "/opt/clients/hq",
    "curl_h2": "/usr/bin/curl"
  },
  "experiments": [
    {
      "name": "example-experiment",
      "endpoints": ["https://www.google.com"],
      "clients": ["curl_h2"],
      "iterations": 3,
      "interface": "eth0",
      "profile": {
        "loss": 0.1,
        "delay": 10,
        "bw": 50,
        "jitter": 5,
        "burst_ingress": 0,
        "burst_egress": 0
      }
    }
  ],
  "analysis": {},
  "output-dir": "./results"
}
EOF

# Create README for deployment
cat > "$PACKAGE_DIR/README.txt" << 'EOF'
Network Measurement Tool - Deployment Package
=============================================

PREREQUISITES:
- Docker must be installed on the target system
- Root/sudo access for privileged container execution
- Network interface for testing (usually eth0)

DEPLOYMENT STEPS:

1. Copy this entire directory to your target VM/server

2. Run the deployment script:
   ./deploy.sh

3. Edit params_docker.json to configure your experiments:
   - Update "interface" to match your network interface (eth0, ens3, etc.)
   - Add/modify endpoints
   - Configure network profiles

4. Run measurements:
   docker run --privileged --network host \
     -v $(pwd)/params_docker.json:/app/params_docker.json:ro \
     -v $(pwd)/results:/app/results \
     -v $(pwd)/data:/app/data \
     network-measurement-tool:latest

5. Results will be saved in ./results/ directory

NOTES:
- The container requires --privileged and --network host for traffic control
- Check your network interface with: ip addr show
- Results include pickle files, plots, and analysis
EOF

# Create tarball
echo "Creating final tarball..."
tar -czf "${PACKAGE_NAME}_${VERSION}.tar.gz" "$PACKAGE_DIR"

# Clean up
rm -rf "$PACKAGE_DIR"

echo ""
echo "=== Package created successfully ==="
echo "File: ${PACKAGE_NAME}_${VERSION}.tar.gz"
echo "Size: $(du -h ${PACKAGE_NAME}_${VERSION}.tar.gz | cut -f1)"
echo ""
echo "To deploy on another VM:"
echo "1. Copy ${PACKAGE_NAME}_${VERSION}.tar.gz to target VM"
echo "2. tar -xzf ${PACKAGE_NAME}_${VERSION}.tar.gz"
echo "3. cd ${PACKAGE_DIR}"
echo "4. ./deploy.sh"