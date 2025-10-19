# Building EdgeLake Docker Images

This guide explains how to build EdgeLake Docker images with MCP server support.

## Quick Start (On Your VM)

```bash
# 1. Setup the build environment (first time only)
bash docker-build-setup.sh
# Log out and log back in after setup

# 2. Build the image
docker build -t edgelake-mcp:latest .

# 3. Test the image
docker run --rm edgelake-mcp:latest python3 -c "import edge_lake.mcp_server; print('MCP OK')"
```

## Build Environment Options

### Option 1: Linux VM (Recommended)

**Pros:**
- Native Docker performance
- Multi-architecture builds (ARM64 + AMD64)
- Best for production/CI/CD
- Consistent build environment

**VM Requirements:**
- OS: Ubuntu 22.04 LTS or Debian 12
- CPU: 4+ cores
- RAM: 8GB minimum (16GB recommended)
- Disk: 50GB+ SSD
- Docker: 24.x or later

**Setup:**
```bash
# Run the setup script
bash docker-build-setup.sh
# Log out and log back in
```

### Option 2: macOS (Local Development)

**Pros:**
- Convenient for development
- Good for testing

**Cons:**
- Slower builds (virtualization overhead)
- Larger images due to QEMU emulation
- Limited to AMD64 or ARM64 (not both)

**Setup:**
```bash
# Install Docker Desktop for Mac
# Enable BuildKit in Docker Desktop settings
```

### Option 3: Windows with WSL2

**Pros:**
- Good for Windows developers
- Native Linux container support

**Cons:**
- Slower than native Linux
- WSL2 resource limits

**Setup:**
```bash
# Install Docker Desktop for Windows with WSL2 backend
# Run builds from WSL2 terminal
```

## Build Commands

### Standard Build (Single Architecture)

```bash
# Build for current architecture
docker build -t edgelake-mcp:latest .

# Build with specific tag
docker build -t edgelake-mcp:v1.0.0 .

# Build with BuildKit (faster, better caching)
DOCKER_BUILDKIT=1 docker build -t edgelake-mcp:latest .
```

### Multi-Platform Build (Linux VM Only)

Build for both AMD64 (servers) and ARM64 (IoT/Raspberry Pi):

```bash
# Setup buildx builder (one time)
docker buildx create --name edgelake-builder --use --bootstrap

# Build and load for local use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t edgelake-mcp:latest \
  --load \
  .

# Build and push to registry
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t yourusername/edgelake-mcp:latest \
  --push \
  .
```

### Build with Custom Arguments

```bash
# Override base image
docker build \
  --build-arg BASE_IMAGE=python:3.11-slim \
  -t edgelake-mcp:slim \
  .

# Build without cache (force rebuild)
docker build --no-cache -t edgelake-mcp:latest .
```

## Optimizing Build Performance

### 1. Use BuildKit

Enable BuildKit for parallel builds and better caching:

```bash
# Method 1: Environment variable
export DOCKER_BUILDKIT=1
docker build -t edgelake-mcp:latest .

# Method 2: Docker daemon config (persistent)
# Already configured by docker-build-setup.sh
```

### 2. Layer Caching

The Dockerfile is already optimized for caching:
- Dependencies installed before code copy
- Multi-stage build to minimize final image size

### 3. Build Cache Management

```bash
# View cache usage
docker buildx du

# Prune build cache
docker buildx prune

# Prune all unused data
docker system prune -a
```

## Testing the Build

```bash
# Test MCP dependencies are installed
docker run --rm edgelake-mcp:latest \
  python3 -c "import mcp; import sse_starlette; print('MCP dependencies OK')"

# Test EdgeLake starts
docker run --rm edgelake-mcp:latest \
  python3 -c "import edge_lake.mcp_server; print('EdgeLake MCP server OK')"

# Interactive shell
docker run -it --rm edgelake-mcp:latest /bin/bash

# Check installed packages
docker run --rm edgelake-mcp:latest pip list | grep -E "mcp|sse-starlette|starlette|uvicorn"
```

## Pushing to Registry

### Docker Hub

```bash
# Login
docker login

# Tag image
docker tag edgelake-mcp:latest yourusername/edgelake-mcp:latest
docker tag edgelake-mcp:latest yourusername/edgelake-mcp:v1.0.0

# Push
docker push yourusername/edgelake-mcp:latest
docker push yourusername/edgelake-mcp:v1.0.0
```

### GitHub Container Registry

```bash
# Login
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Tag
docker tag edgelake-mcp:latest ghcr.io/edgelake/edgelake-mcp:latest

# Push
docker push ghcr.io/edgelake/edgelake-mcp:latest
```

### Private Registry

```bash
# Login
docker login registry.example.com

# Tag
docker tag edgelake-mcp:latest registry.example.com/edgelake-mcp:latest

# Push
docker push registry.example.com/edgelake-mcp:latest
```

## Build Troubleshooting

### "Cannot connect to Docker daemon"

```bash
# Start Docker service
sudo systemctl start docker

# Check Docker is running
docker ps

# Verify user in docker group
groups | grep docker
# If not in group, log out and log back in
```

### "No space left on device"

```bash
# Clean up Docker resources
docker system prune -a --volumes

# Check disk space
df -h

# Check Docker disk usage
docker system df
```

### "Build takes too long"

```bash
# Use BuildKit
export DOCKER_BUILDKIT=1

# Increase Docker resources in Docker Desktop
# Settings → Resources → Increase CPU/Memory

# Use build cache from previous builds
docker build --cache-from edgelake-mcp:latest -t edgelake-mcp:latest .
```

### "pip install fails"

```bash
# Build with no cache to force clean install
docker build --no-cache -t edgelake-mcp:latest .

# Check if requirements.txt files exist
ls -la requirements.txt edge_lake/mcp_server/requirements.txt
```

## Image Size Optimization

Current image uses Alpine Linux (python:3.11-alpine) which is already minimal.

To check image size:
```bash
docker images edgelake-mcp
```

To further optimize:
```bash
# Use multi-stage build (already implemented)
# Remove build dependencies after install
# Use .dockerignore to exclude unnecessary files
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Docker Image

on:
  push:
    branches: [ main ]
    tags: [ 'v*' ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Build image
        uses: docker/build-push-action@v4
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          tags: edgelake-mcp:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

## Best Practices

1. **Use the VM for production builds** - Faster, more reliable
2. **Enable BuildKit** - Better performance and caching
3. **Tag your builds** - Use semantic versioning (v1.0.0, v1.0.1, etc.)
4. **Test before pushing** - Run basic tests on built image
5. **Clean up regularly** - `docker system prune` to free space
6. **Use multi-stage builds** - Already implemented in Dockerfile
7. **Document build process** - Keep this file updated

## Security Considerations

1. **Scan images for vulnerabilities:**
   ```bash
   docker scan edgelake-mcp:latest
   ```

2. **Use official base images** - python:3.11-alpine is official

3. **Don't include secrets** - Use .dockerignore and environment variables

4. **Keep base image updated:**
   ```bash
   docker pull python:3.11-alpine
   docker build --pull -t edgelake-mcp:latest .
   ```

## Support

For build issues:
1. Check this document
2. Review Docker logs: `docker logs <container-id>`
3. Open an issue on GitHub
4. Join the EdgeLake Slack community