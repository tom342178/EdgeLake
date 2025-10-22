#!/bin/bash
# Test script for EdgeLake MCP Server
# Usage: ./test-mcp-server.sh

set -e

IMAGE_NAME="edgelake-mcp:latest"
CONTAINER_NAME="edgelake-mcp-test"

echo "Testing EdgeLake MCP Server..."
echo "Image: $IMAGE_NAME"
echo ""

# Check if image exists
if ! docker image inspect $IMAGE_NAME > /dev/null 2>&1; then
    echo "Error: Image $IMAGE_NAME not found"
    echo "Please build the image first using:"
    echo "  docker build -t edgelake-mcp:latest -f Dockerfile ."
    exit 1
fi

# Stop and remove existing container if it exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping and removing existing container..."
    docker stop $CONTAINER_NAME > /dev/null 2>&1 || true
    docker rm $CONTAINER_NAME > /dev/null 2>&1 || true
fi

# Run the container
echo "Starting MCP server container..."
docker run -d \
    --name $CONTAINER_NAME \
    -p 3000:3000 \
    $IMAGE_NAME

# Wait a few seconds for server to start
echo "Waiting for server to start..."
sleep 3

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "✓ Container is running"
    echo ""
    echo "Container logs:"
    echo "==============="
    docker logs $CONTAINER_NAME
    echo ""
    echo "✓ MCP server is up!"
    echo ""
    echo "Useful commands:"
    echo "  View logs:        docker logs -f $CONTAINER_NAME"
    echo "  Stop container:   docker stop $CONTAINER_NAME"
    echo "  Remove container: docker rm $CONTAINER_NAME"
    echo "  Shell access:     docker exec -it $CONTAINER_NAME /bin/bash"
else
    echo "✗ Container failed to start"
    echo ""
    echo "Logs:"
    docker logs $CONTAINER_NAME
    exit 1
fi
