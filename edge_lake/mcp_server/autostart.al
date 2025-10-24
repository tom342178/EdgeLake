#-----------------------------------------------------------------------------------------------------------------------
# EdgeLake MCP Server - Auto-Start Script
#
# This script automatically starts the MCP server when included in node deployment.
# It reads configuration from environment variables and starts the server appropriately.
#
# Environment Variables:
#   MCP_ENABLED        - Set to "true" to enable MCP server (default: false)
#   MCP_PORT           - Port for MCP server SSE endpoint (default: 50051)
#   MCP_TRANSPORT      - Transport mode: "sse" or "stdio" (default: sse)
#   MCP_TOOLS          - Tool selection: "auto", "all", or comma-separated list (default: auto)
#   MCP_LOG_LEVEL      - Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
#   MCP_HOST           - Host to bind to for SSE server (default: 0.0.0.0)
#
# Usage:
#   Add to your node's main.al script:
#   process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al
#
# Or include conditionally:
#   if !mcp_enabled then
#       process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al
#   end
#-----------------------------------------------------------------------------------------------------------------------

# Check if MCP is enabled via environment variable
on error ignore
mcp_enabled_str = python !MCP_ENABLED
on error goto

# Default to false if not set
if !mcp_enabled_str == "" then
    mcp_enabled_str = false
end

# Only proceed if MCP is enabled (check string values since environment variables are strings)
if !mcp_enabled_str == "true" or !mcp_enabled_str == "True" or !mcp_enabled_str == "TRUE" then
    # Get configuration from environment variables with defaults
    on error ignore
    mcp_port = python !MCP_PORT
    mcp_transport = python !MCP_TRANSPORT
    mcp_tools = python !MCP_TOOLS
    mcp_host = python !MCP_HOST
    on error goto

    # Set defaults if not provided
    if !mcp_port == "" then
        mcp_port = 50051
    end

    if !mcp_transport == "" then
        mcp_transport = sse
    end

    if !mcp_tools == "" then
        mcp_tools = auto
    end

    if !mcp_host == "" then
        mcp_host = 0.0.0.0
    end

    # Build and execute the run command
    echo "Starting EdgeLake MCP Server..."
    echo "  Transport: !mcp_transport"
    echo "  Port: !mcp_port"
    echo "  Tools: !mcp_tools"

    # Run the MCP server (note: host binding is handled internally, not a command parameter)
    run mcp server where transport = !mcp_transport and port = !mcp_port and tools = !mcp_tools

    # Wait a moment for startup
    sleep 2

    # Check status
    get mcp server

    echo "EdgeLake MCP Server auto-start complete"
else
    echo "EdgeLake MCP Server is disabled (MCP_ENABLED != true)"
end