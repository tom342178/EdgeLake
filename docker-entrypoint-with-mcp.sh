#!/bin/bash
#
# EdgeLake Docker Entrypoint with MCP Auto-Start
#
# This script wraps the standard EdgeLake startup to automatically
# start the MCP server if MCP_ENABLED=true
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

# Create a temporary combined init script
INIT_SCRIPT="/tmp/edgelake-init.al"

cat > "$INIT_SCRIPT" <<EOF
#-----------------------------------------------------------------------------------------------------------------------
# EdgeLake Auto-Generated Initialization Script
# Generated at container start with MCP auto-start support
#-----------------------------------------------------------------------------------------------------------------------

# Run main deployment script
process $DEPLOYMENT_SCRIPTS/main.al

# Auto-start MCP server if enabled
process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al

EOF

echo "Initialization script created at: $INIT_SCRIPT"
echo ""
echo "Starting EdgeLake with MCP support..."
echo "====================================================="
echo ""

# Start EdgeLake with the combined init script
exec python3 "$EDGELAKE_HOME/edge_lake/edgelake.py" process "$INIT_SCRIPT"