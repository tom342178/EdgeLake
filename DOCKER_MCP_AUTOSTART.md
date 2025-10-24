# EdgeLake MCP Server - Docker Auto-Start Guide

This guide explains how to automatically start the MCP server when an EdgeLake Docker container starts.

## Overview

The MCP server now starts automatically when EdgeLake initializes, running as an internal EdgeLake process. This provides:
- ✅ Automatic MCP server startup via `autostart.al` script
- ✅ Preserved CLI access via `docker attach`
- ✅ Embedded mode (direct integration, no HTTP overhead)
- ✅ Configuration via environment variables

The MCP server is managed like any other EdgeLake service (TCP server, REST server, etc.) and can be controlled via EdgeLake CLI commands.

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

### 2. Deployment-Scripts Integration (Automatic)

The MCP auto-start is integrated into the deployment-scripts repository. The Dockerfile automatically clones the deployment-scripts fork that includes MCP autostart integration.

**How it works:**

The `config_policy.al` file in deployment-scripts automatically includes the MCP autostart script for all node types:

```al
# In deployment-scripts/node-deployment/policies/config_policy.al
# The script array for each node type includes:
"process !anylog_path/EdgeLake/edge_lake/mcp_server/autostart.al"
```

**Deployment-Scripts Repository:**

The Dockerfile clones from the public fork with MCP integration:

```dockerfile
# Clone deployment-scripts from fork (includes MCP autostart integration)
RUN git clone https://github.com/tviv/deployment-scripts
```

This ensures:
- ✅ MCP autostart is included in all node types (generic, master, query, operator, publisher)
- ✅ Automatic startup when `MCP_ENABLED=true`
- ✅ No manual script modifications needed

**Alternative: Using upstream deployment-scripts**

If you want to use the upstream EdgeLake version (without MCP autostart), modify the Dockerfile:

```dockerfile
# Use upstream (no MCP autostart)
RUN git clone https://github.com/EdgeLake/deployment-scripts

# Or use fork with MCP autostart
# RUN git clone https://github.com/tviv/deployment-scripts
```

### 3. Build Docker Image

Build from the EdgeLake directory:

```bash
cd /Users/tviviano/Documents/GitHub/EdgeLake

# Build image with MCP autostart integration
docker build -t edgelake-mcp:latest .
```

The build will:
1. Copy EdgeLake source code
2. Clone deployment-scripts from https://github.com/tviv/deployment-scripts (includes MCP autostart)
3. Install MCP server requirements
4. Configure entrypoint for CLI access

**Note**: The deployment-scripts are cloned during the Docker build, so you don't need to have them locally.

### 4. Deploy with Docker Compose

```bash
cd /Users/tviviano/Documents/GitHub/docker-compose

# Deploy query node with MCP enabled
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

### 5. Access CLI and Verify MCP Server

**Attach to container CLI:**

```bash
docker attach edgelake-query

# You should see the EdgeLake CLI prompt:
# EL edgelake-query >

# Check MCP server status
get mcp server

# Detach without stopping: Ctrl+P, then Ctrl+Q
```

### 6. Verify MCP Server Started

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

## Architecture Details

### How Auto-Start Works

1. **Docker Entrypoint** (`docker-entrypoint-with-mcp.sh`):
   - Exports MCP environment variables
   - Starts EdgeLake in foreground mode: `exec python3 edgelake.py process main.al`
   - EdgeLake becomes PID 1 (enables `docker attach` CLI access)

2. **Deployment Script** (`main.al`):
   - Processes configuration: `process !local_scripts/policies/config_policy.al`

3. **Configuration Policy** (`config_policy.al`):
   - Each node type's script array includes: `process !anylog_path/EdgeLake/edge_lake/mcp_server/autostart.al`

4. **Auto-Start Script** (`autostart.al`):
   - Checks `MCP_ENABLED` environment variable
   - If true, executes: `run mcp server where transport = sse and port = 50051 ...`
   - MCP server starts as EdgeLake background thread

5. **MCP Server** (embedded mode):
   - Uses direct client (calls `member_cmd.process_cmd()` directly)
   - No HTTP overhead - pure in-process integration
   - Accessible via SSE endpoint: `http://0.0.0.0:50051/sse`

### Why This Approach?

**Previous attempt** (external Python script):
- ❌ Complex process management (backgrounding, nohup, etc.)
- ❌ Lost CLI access (stdout captured by MCP server)
- ❌ Difficult to monitor/control from EdgeLake

**Current approach** (internal EdgeLake service):
- ✅ MCP runs as EdgeLake background process
- ✅ CLI remains accessible via `docker attach`
- ✅ Can manage via EdgeLake commands (`get mcp server`, `stop mcp server`)
- ✅ Proper integration with EdgeLake lifecycle
- ✅ No external process management needed

### Deployment-Scripts Repository

The deployment-scripts are automatically cloned from GitHub during the Docker build:

```dockerfile
# In Dockerfile
RUN git clone https://github.com/tviv/deployment-scripts
```

This public fork includes the MCP autostart integration in `config_policy.al` for all node types. No local copy needed.

## Files Modified

### EdgeLake Repository

- `Dockerfile` - Copy local deployment-scripts, simplified entrypoint
- `docker-entrypoint-with-mcp.sh` - Simplified to start EdgeLake in foreground
- `edge_lake/mcp_server/autostart.al` - Auto-start script
- `edge_lake/mcp_server/server.py` - Added `MCP_LOG_LEVEL` env var support
- `edge_lake/mcp_server/core/direct_client.py` - Added timeout protection, error code 141 handling
- `run-mcp-sse-server.py` - Changed to embedded mode

### Deployment-Scripts Repository (Forked)

- `node-deployment/policies/config_policy.al` - Added MCP autostart to all node types:
  - Line 100: generic node
  - Line 115: master/query nodes
  - Line 134: publisher node
  - Line 155: operator node

### Docker-Compose Repository

- `docker-makefiles/query-configs/advance_configs.env` - Added MCP configuration variables

## See Also

- `edge_lake/mcp_server/MCP_AUTOSTART.md` - Detailed MCP autostart documentation
- `MCP_TESTING_GUIDE.md` - Testing with curl/Postman
- `SSE_USAGE.md` - Using SSE transport
- `test-mcp-sse-endpoints.sh` - Automated test script
- `../utilities/edgelake/test-mcp-sse.py` - Python SSE protocol tester
