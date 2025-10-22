# EdgeLake MCP Server - Auto-Start Summary

## What We Built

A complete auto-start system for the EdgeLake MCP server in Docker containers.

## How It Works

```
Container Start
    ↓
docker-entrypoint-with-mcp.sh
    ↓
Creates combined init script
    ↓
Runs deployment-scripts/node-deployment/main.al
    ↓
Runs edge_lake/mcp_server/autostart.al
    ↓
Checks MCP_ENABLED environment variable
    ↓
If true: Starts MCP server with SSE transport
    ↓
MCP server running on port 50051
```

## Quick Start

### 1. Build Image with MCP Support

The Dockerfile is already updated. Just build:

```bash
cd /Users/tviviano/Documents/GitHub/docker-compose
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

### 2. MCP Server Starts Automatically

The query node config already has `MCP_ENABLED=true`, so the server will start automatically!

### 3. Test It

```bash
# Wait for container to start (30 seconds)
sleep 30

# Test the endpoint
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list",
  "params": {}
}' | jq '.result.tools[].name'
```

Expected output:
```
"server_info"
"node_status"
"list_databases"
"list_tables"
"get_table_schema"
"query_data"
"execute_command"
"network_query"
```

## Files Created/Modified

### New Files

1. **`edge_lake/mcp_server/autostart.al`**
   - EdgeLake script that reads environment variables
   - Conditionally starts MCP server if `MCP_ENABLED=true`
   - Configures server based on env vars

2. **`docker-entrypoint-with-mcp.sh`**
   - Bash wrapper for Docker ENTRYPOINT
   - Creates combined init script
   - Automatically includes MCP autostart

3. **`DOCKER_MCP_AUTOSTART.md`**
   - Comprehensive documentation
   - Troubleshooting guide
   - Configuration reference

4. **`test-mcp-sse-endpoints.sh`**
   - Automated testing script
   - Tests all MCP endpoints
   - Includes timeout protection

5. **`MCP_TESTING_GUIDE.md`**
   - Manual testing with curl
   - Debug logging setup
   - Expected responses

### Modified Files

1. **`Dockerfile`**
   - Copies autostart script
   - Copies entrypoint wrapper
   - Sets new ENTRYPOINT

2. **`docker-makefiles/query-configs/advance_configs.env`**
   - Added `MCP_ENABLED=true`
   - Added `MCP_PORT=50051`
   - Added `MCP_TRANSPORT=sse`
   - Added `MCP_HOST=0.0.0.0`
   - Added `MCP_TOOLS=auto`
   - Added `MCP_LOG_LEVEL=INFO`

3. **`edge_lake/mcp_server/server.py`**
   - Added `MCP_LOG_LEVEL` environment variable support
   - Enables DEBUG logging when `MCP_LOG_LEVEL=DEBUG`

4. **`edge_lake/mcp_server/core/direct_client.py`**
   - Added timeout protection (30s default)
   - Enhanced debug logging
   - Prevents server hangs

## Configuration

### Environment Variables

All configured in `docker-makefiles/query-configs/advance_configs.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ENABLED` | `true` | Enable/disable auto-start |
| `MCP_PORT` | `50051` | SSE endpoint port |
| `MCP_TRANSPORT` | `sse` | Transport mode (sse recommended) |
| `MCP_HOST` | `0.0.0.0` | Host to bind (0.0.0.0 = all interfaces) |
| `MCP_TOOLS` | `auto` | Tool selection (auto-detect capabilities) |
| `MCP_LOG_LEVEL` | `INFO` | Log level (DEBUG for troubleshooting) |

### To Disable MCP Server

Edit `docker-makefiles/query-configs/advance_configs.env`:

```bash
MCP_ENABLED=false
```

Then rebuild:

```bash
make down EDGELAKE_TYPE=query
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

## Testing

### Automated Test

```bash
cd /Users/tviviano/Documents/GitHub/EdgeLake
./test-mcp-sse-endpoints.sh localhost 50051
```

### Manual Tests

See `MCP_TESTING_GUIDE.md` for individual curl commands.

### Enable Debug Logging

```bash
# Edit config
vim docker-makefiles/query-configs/advance_configs.env

# Change to DEBUG
MCP_LOG_LEVEL=DEBUG

# Rebuild
make down EDGELAKE_TYPE=query
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query

# Watch logs
docker logs -f <container-name> 2>&1 | grep -i mcp
```

## Verification Checklist

After deploying, verify:

- [ ] Container started successfully
- [ ] MCP server auto-started (check logs)
- [ ] Port 50051 is exposed and accessible
- [ ] `tools/list` endpoint works
- [ ] `server_info` tool works (fast, no EdgeLake command)
- [ ] `node_status` tool works (calls EdgeLake "get status")
- [ ] `list_databases` tool works (calls blockchain)
- [ ] No timeout errors in logs
- [ ] Debug logs show command execution flow (if DEBUG enabled)

## Common Issues

### 1. MCP Server Not Starting

**Check**: Is `MCP_ENABLED=true`?
```bash
docker exec <container> printenv | grep MCP_ENABLED
```

**Check**: Logs for errors
```bash
docker logs <container> 2>&1 | grep -i mcp
```

### 2. Port Not Accessible

**Check**: Port exposed in docker-compose
```bash
docker ps | grep <container>
# Should show: 0.0.0.0:50051->50051/tcp
```

**Check**: Firewall rules (if remote)

### 3. Commands Timing Out

**Check**: EdgeLake is fully initialized
```bash
docker exec <container> python3 /app/EdgeLake/edge_lake/edgelake.py "get status"
```

**Check**: Master node connection (for blockchain commands)
```bash
docker exec <container> python3 /app/EdgeLake/edge_lake/edgelake.py "blockchain get *"
```

**Enable**: Debug logging to see where it's hanging
```bash
# Set MCP_LOG_LEVEL=DEBUG in advance_configs.env
# Rebuild and check logs
```

## Next Steps

1. ✅ Build Docker image with MCP auto-start
2. ✅ Deploy to demo environment
3. Test with curl/Postman
4. Configure Claude Desktop to use MCP endpoint
5. Test end-to-end workflows
6. Monitor performance and logs
7. Set up production monitoring/alerting

## Architecture Benefits

### Embedded Mode
- **Zero HTTP overhead** between MCP and EdgeLake core
- Direct function calls via `member_cmd.process_cmd()`
- Shared memory space
- Runs in same process as EdgeLake

### SSE Transport
- Standard HTTP/SSE between client and MCP server
- Works with Claude Desktop via HTTP proxy
- Easy to debug with curl
- No stdio conflicts

### Auto-Start
- No manual intervention needed
- Configured via environment variables
- Same image works for all node types
- Easy to enable/disable per deployment

## Support Files

- `DOCKER_MCP_AUTOSTART.md` - Detailed setup guide
- `MCP_TESTING_GUIDE.md` - Testing procedures
- `test-mcp-sse-endpoints.sh` - Automated tests
- `autostart.al` - Auto-start script
- `docker-entrypoint-with-mcp.sh` - Docker entrypoint

## Contact

For issues or questions:
1. Check the troubleshooting guides
2. Review container logs with DEBUG enabled
3. Test with provided scripts
4. Check MCP server status: `get mcp server`
