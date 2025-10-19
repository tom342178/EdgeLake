#!/bin/bash
# EdgeLake Docker Build Environment Setup
# Run this on your Linux VM to prepare for building EdgeLake images

set -e

echo "=== EdgeLake Docker Build Environment Setup ==="

# Update system
echo "Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "Docker already installed"
fi

# Add current user to docker group
echo "Adding user to docker group..."
sudo usermod -aG docker $USER

# Install git if not present
if ! command -v git &> /dev/null; then
    echo "Installing git..."
    sudo apt-get install -y git
fi

# Install make
if ! command -v make &> /dev/null; then
    echo "Installing make..."
    sudo apt-get install -y build-essential
fi

# Enable Docker BuildKit (for faster builds)
echo "Configuring Docker BuildKit..."
sudo mkdir -p /etc/docker
cat <<EOF | sudo tee /etc/docker/daemon.json
{
  "features": {
    "buildkit": true
  },
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

# Restart Docker
echo "Restarting Docker..."
sudo systemctl restart docker
sudo systemctl enable docker

# Setup buildx for multi-platform builds
echo "Setting up Docker buildx..."
docker buildx create --name edgelake-builder --use --bootstrap 2>/dev/null || true
docker buildx inspect --bootstrap

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "IMPORTANT: You must log out and log back in for docker group changes to take effect"
echo ""
echo "To verify setup, run:"
echo "  docker --version"
echo "  docker buildx version"
echo "  docker run hello-world"
echo ""
echo "To build EdgeLake image:"
echo "  cd /path/to/EdgeLake"
echo "  docker build -t edgelake-mcp:latest ."
echo ""
echo "For multi-platform build (ARM64 + AMD64):"
echo "  docker buildx build --platform linux/amd64,linux/arm64 -t edgelake-mcp:latest --load ."
echo ""