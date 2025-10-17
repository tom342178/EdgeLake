#!/bin/bash
#
# EdgeLake MCP Server - Standalone Mode Startup Script
#
# This script starts the EdgeLake MCP server in standalone mode using stdio transport.
# The server communicates via stdin/stdout following the MCP protocol.
#
# Usage:
#   ./start_standalone.sh [--config-dir /path/to/config]
#
# Environment Variables:
#   EDGELAKE_HOST       - Override default EdgeLake node host
#   EDGELAKE_PORT       - Override default EdgeLake node port
#   EDGELAKE_NODE_NAME  - Override default node name
#

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Change to script directory
cd "$SCRIPT_DIR"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.8 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python $REQUIRED_VERSION or higher required. Found: $PYTHON_VERSION"
    exit 1
fi

# Check if required dependencies are installed
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "Error: pyyaml not installed. Install with: pip install pyyaml"
    exit 1
fi

if ! python3 -c "import mcp" 2>/dev/null; then
    echo "Error: mcp not installed. Install with: pip install mcp"
    exit 1
fi

# Run server in standalone mode
python3 server.py --mode=standalone "$@"
