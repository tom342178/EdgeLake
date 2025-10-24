#!/bin/bash
#
# EdgeLake Docker Entrypoint with MCP Auto-Start
#
# This script starts EdgeLake normally. If MCP_ENABLED=true, the MCP server
# will be started automatically via the autostart.al script included in main.al
#
# Usage (in Dockerfile):
#   COPY docker-entrypoint-with-mcp.sh /app/
#   ENTRYPOINT ["/app/docker-entrypoint-with-mcp.sh"]
#

set -e

EDGELAKE_HOME=${EDGELAKE_HOME:-/app/EdgeLake}
DEPLOYMENT_SCRIPTS=${DEPLOYMENT_SCRIPTS:-/app/deployment-scripts/node-deployment}
MCP_ENABLED=${MCP_ENABLED:-false}

echo "====================================================="
echo "EdgeLake Container Starting"
echo "====================================================="
echo "EdgeLake Home: $EDGELAKE_HOME"
echo "Deployment Scripts: $DEPLOYMENT_SCRIPTS"
echo "MCP Enabled: $MCP_ENABLED"
echo ""

# Export MCP environment variables for autostart.al to use
export MCP_ENABLED
export MCP_PORT=${MCP_PORT:-50051}
export MCP_TRANSPORT=${MCP_TRANSPORT:-sse}
export MCP_HOST=${MCP_HOST:-0.0.0.0}
export MCP_TOOLS=${MCP_TOOLS:-auto}
export MCP_LOG_LEVEL=${MCP_LOG_LEVEL:-INFO}

# Start EdgeLake main process (foreground mode for CLI access)
echo "Starting EdgeLake with interactive CLI..."
if [ -f "$DEPLOYMENT_SCRIPTS/main.al" ]; then
    echo "Processing: $DEPLOYMENT_SCRIPTS/main.al"
    echo "MCP server will auto-start if MCP_ENABLED=true"
    echo ""
    exec python3 "$EDGELAKE_HOME/edge_lake/edgelake.py" process "$DEPLOYMENT_SCRIPTS/main.al"
else
    echo "WARNING: $DEPLOYMENT_SCRIPTS/main.al not found"
    echo "Starting EdgeLake in interactive mode (MCP auto-start disabled)"
    echo ""
    exec python3 "$EDGELAKE_HOME/edge_lake/edgelake.py"
fi