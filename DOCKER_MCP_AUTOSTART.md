# EdgeLake MCP Server - Docker Auto-Start Guide

This guide explains how to automatically start the MCP server when an EdgeLake Docker container starts.

## Overview

The MCP server can now start automatically when EdgeLake initializes. This is controlled by environment variables in the Docker configuration.

## Quick Setup

### 1. Environment Variables (Already Configured)

The query node config already has MCP auto-start enabled:

**File**: `docker-makefiles/query-configs/advance_configs.env`

```bash
# --- MCP Server Configuration ---
MCP_ENABLED=true              # Enable auto-start
MCP_PORT=50051                # SSE endpoint port
MCP_TRANSPORT=sse             # Use SSE transport (recommended)
MCP_HOST=0.0.0.0              # Bind to all interfaces
MCP_TOOLS=auto                # Auto-detect capabilities
MCP_LOG_LEVEL=INFO            # Log level (use DEBUG for troubleshooting)
```

### 2. Include Auto-Start Script in Deployment

**Option A: Via deployment-scripts (Recommended)**

Add this line to your node's `main.al` script in the deployment-scripts repo:

```al
# Start MCP server if enabled
process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al
```

**Option B: Via Docker ENTRYPOINT modification**

Modify the Dockerfile to run autostart after main.al:

```dockerfile
ENTRYPOINT python3 /app/EdgeLake/edge_lake/edgelake.py \
    "process /app/deployment-scripts/node-deployment/main.al" \
    and "process /app/EdgeLake/edge_lake/mcp_server/autostart.al"
```

**Option C: Via init script injection**

Create a custom init script and mount it:

```bash
# Create local init script
cat > /tmp/mcp-init.al <<'EOF'
# Your main node initialization here...
process /app/deployment-scripts/node-deployment/main.al

# Start MCP server
process /app/EdgeLake/edge_lake/mcp_server/autostart.al
EOF

# Run container with mounted script
docker run -v /tmp/mcp-init.al:/app/init.al \
    -e MCP_ENABLED=true \
    anylogco/anylog-network:latest \
    process /app/init.al
```

### 3. Build and Deploy

```bash
cd /Users/tviviano/Documents/GitHub/docker-compose

# Build image
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

### 4. Verify MCP Server Started

```bash
# Check logs
docker logs <container-name> | grep -i "mcp"

# Should see:
# Starting EdgeLake MCP Server...
#   Transport: sse
#   Port: 50051
#   Host: 0.0.0.0
#   Tools: auto
# [MCP Server] Started with SSE transport on port 50051
```

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ENABLED` | `false` | Set to `true` to enable auto-start |
| `MCP_PORT` | `50051` | SSE endpoint port |
| `MCP_TRANSPORT` | `sse` | Transport mode (`sse` or `stdio`) |
| `MCP_HOST` | `0.0.0.0` | Host to bind to |
| `MCP_TOOLS` | `auto` | Tool selection (`auto`, `all`, or comma-separated list) |
| `MCP_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Per-Node Type Configuration

Different node types can have different MCP configurations:

**Query Node** (`docker-makefiles/query-configs/advance_configs.env`):
```bash
MCP_ENABLED=true
MCP_TOOLS=auto  # Will enable: query, list_databases, list_tables, etc.
```

**Operator Node** (`docker-makefiles/operator-configs/advance_configs.env`):
```bash
MCP_ENABLED=true
MCP_TOOLS=auto  # Will enable: local query, node_status, server_info
```

**Master Node** (`docker-makefiles/master-configs/advance_configs.env`):
```bash
MCP_ENABLED=true
MCP_TOOLS=auto  # Will enable: blockchain_post, blockchain_get, etc.
```

## Testing Auto-Start

### 1. Start Container

```bash
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

### 2. Check MCP Server Status

```bash
# Via EdgeLake CLI
docker exec -it <container-name> python3 /app/EdgeLake/edge_lake/edgelake.py "get mcp server"

# Expected output:
# MCP Server Status:
#   Mode: embedded
#   Transport: sse
#   Port: 50051
#   Tools: 8 enabled
#   Thread: EdgeLakeMCPServer (alive=True)
```

### 3. Test MCP Endpoint

```bash
# From host machine
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}' | jq '.'
```

## Troubleshooting

### MCP Server Not Starting

**Check if enabled**:
```bash
docker exec <container-name> printenv | grep MCP_ENABLED
# Should show: MCP_ENABLED=true
```

**Check logs**:
```bash
docker logs <container-name> 2>&1 | grep -i mcp
```

**Check if autostart.al was processed**:
```bash
docker exec <container-name> cat /app/EdgeLake/data/anylog.log | grep -i "mcp"
```

### MCP Server Started But Not Accessible

**Check port exposure**:
```bash
docker ps | grep <container-name>
# Should show: 0.0.0.0:50051->50051/tcp
```

**Check binding**:
```bash
docker exec <container-name> netstat -tulpn | grep 50051
```

**Test from inside container**:
```bash
docker exec <container-name> curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Debug Mode

Enable debug logging:

```bash
# Edit advance_configs.env
MCP_LOG_LEVEL=DEBUG

# Rebuild
make down EDGELAKE_TYPE=query
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query

# Check debug logs
docker exec <container-name> tail -f /app/EdgeLake/data/anylog.log | grep -i mcp
```

## Integration with Existing Deployments

### For Production Deployments

1. **Update docker-compose configs**:
   ```bash
   cd /Users/tviviano/Documents/GitHub/docker-compose
   vim docker-makefiles/query-configs/advance_configs.env
   # Set MCP_ENABLED=true
   ```

2. **Update deployment-scripts** (if using custom main.al):
   ```bash
   # Add to your main.al:
   process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al
   ```

3. **Deploy**:
   ```bash
   make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
   ```

### For Development/Testing

Quick test with environment override:

```bash
docker run -it --rm \
  -e MCP_ENABLED=true \
  -e MCP_LOG_LEVEL=DEBUG \
  -p 50051:50051 \
  anylogco/anylog-network:latest
```

## Next Steps

1. ✅ MCP server auto-starts with container
2. Test with Claude Desktop via HTTP proxy
3. Monitor performance in production
4. Add health checks for MCP endpoint
5. Set up monitoring/alerting for MCP service

## Files Modified

- `docker-makefiles/query-configs/advance_configs.env` - Added MCP config
- `edge_lake/mcp_server/autostart.al` - Auto-start script
- `edge_lake/mcp_server/server.py` - Added `MCP_LOG_LEVEL` env var support
- `edge_lake/mcp_server/core/direct_client.py` - Added timeout protection

## See Also

- `MCP_TESTING_GUIDE.md` - Testing with curl/Postman
- `SSE_USAGE.md` - Using SSE transport
- `test-mcp-sse-endpoints.sh` - Automated test script
