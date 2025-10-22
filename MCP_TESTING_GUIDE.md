# EdgeLake MCP Server - Testing Guide

## Overview

This guide shows how to test the EdgeLake MCP server using curl commands and enable debug logging.

## Quick Start

### 1. Build Docker Image with MCP Support

```bash
cd /Users/tviviano/Documents/GitHub/docker-compose
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

### 2. Enable Debug Logging

#### Option A: Set in Environment File (Recommended for Docker)

Edit the query node's advance config:
```bash
vim docker-makefiles/query-configs/advance_configs.env
```

Add this line:
```bash
# Enable debug logging for MCP server
MCP_LOG_LEVEL=DEBUG
```

Then rebuild/restart:
```bash
make down EDGELAKE_TYPE=query
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query
```

#### Option B: Set in Running Container

```bash
# Find container name
docker ps | grep query

# Set environment variable in running container (only works until restart)
docker exec -it <container-name> sh -c 'export MCP_LOG_LEVEL=DEBUG'
```

### 3. Run Test Script

```bash
cd /Users/tviviano/Documents/GitHub/EdgeLake
./test-mcp-sse-endpoints.sh <host> <port>
```

Examples:
```bash
# Test localhost
./test-mcp-sse-endpoints.sh localhost 50051

# Test remote server
./test-mcp-sse-endpoints.sh 192.168.1.100 50051
```

### 4. Check Logs

#### On macOS (development):
```bash
tail -f ~/Library/Logs/edgelake_mcp.log
```

#### In Docker container:
```bash
docker exec -it <container-name> tail -f /app/EdgeLake/data/anylog.log
```

Or check the MCP log if configured separately:
```bash
docker exec -it <container-name> tail -f /var/log/edgelake_mcp.log
```

## Manual Testing with curl

### Test 1: Initialize Connection

```bash
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "curl-test",
      "version": "1.0"
    }
  }
}' | jq '.'
```

### Test 2: List Available Tools

```bash
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}' | jq '.'
```

### Test 3: Call server_info Tool (Fast - No EdgeLake Command)

```bash
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "server_info",
    "arguments": {}
  }
}' | jq '.'
```

### Test 4: Call node_status Tool (Calls EdgeLake "get status")

This test will timeout after 30 seconds if EdgeLake hangs:

```bash
curl -s --max-time 35 -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "node_status",
    "arguments": {}
  }
}' | jq '.'
```

### Test 5: Call list_databases Tool

```bash
curl -s --max-time 35 -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "list_databases",
    "arguments": {}
  }
}' | jq '.'
```

### Test 6: Execute SQL Query

```bash
curl -s --max-time 60 -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "query_data",
    "arguments": {
      "database": "your_db_name",
      "query": "SELECT * FROM your_table LIMIT 10"
    }
  }
}' | jq '.'
```

## Understanding the Timeout Protection

The MCP server now has timeout protection to prevent hangs:

- **Default timeout**: 30 seconds per command
- **Configurable**: Can be adjusted in the code if needed
- **Error handling**: Returns `TimeoutError` instead of hanging

### What Happens on Timeout

1. Command starts executing
2. After 30 seconds, if no response:
   - `asyncio.TimeoutError` is raised
   - Error is logged to MCP log file
   - Error response returned to client
3. EdgeLake process continues running (not killed)

### Debug Logging Output

With `MCP_LOG_LEVEL=DEBUG`, you'll see:

```
2025-10-21 12:34:56 - edge_lake.mcp_server.core.direct_client - DEBUG - Executing command directly: get status
2025-10-21 12:34:56 - edge_lake.mcp_server.core.direct_client - DEBUG - Starting sync execution of: get status
2025-10-21 12:34:56 - edge_lake.mcp_server.core.direct_client - DEBUG - Calling member_cmd.process_cmd for: get status
2025-10-21 12:34:57 - edge_lake.mcp_server.core.direct_client - DEBUG - Command completed with return value: 0
2025-10-21 12:34:57 - edge_lake.mcp_server.core.direct_client - DEBUG - Extracted result: <class 'str'>
```

If a command times out:

```
2025-10-21 12:35:26 - edge_lake.mcp_server.core.direct_client - ERROR - Command timed out after 30.0s: get status
```

## Troubleshooting

### Issue: Commands timing out

**Check**:
1. Is EdgeLake initialized? (`get status` should work)
2. Is blockchain/master connected? (`blockchain get *` needs this)
3. Check EdgeLake logs for errors

**Debug**:
```bash
# In container, check if EdgeLake is responsive
docker exec -it <container> /bin/bash
python3 /app/EdgeLake/edge_lake/edgelake.py "get status"
```

### Issue: MCP server not starting

**Check**:
1. Is port 50051 available?
   ```bash
   docker ps | grep 50051
   netstat -an | grep 50051
   ```

2. Check MCP server logs:
   ```bash
   tail -f ~/Library/Logs/edgelake_mcp.log
   ```

3. Check Docker logs:
   ```bash
   docker logs <container-name>
   ```

### Issue: Can't see debug logs

**Check**:
1. Environment variable is set:
   ```bash
   docker exec <container> printenv | grep MCP_LOG_LEVEL
   ```

2. Container was restarted after adding variable

3. Log file location is correct for your environment

## Advanced Testing

### Using Postman

1. Import the curl commands as Postman requests
2. Set base URL: `http://localhost:50051`
3. Use POST method with `/sse` endpoint
4. Set `Content-Type: application/json` header
5. Use JSON body from examples above

### Testing from Claude Desktop

See `SSE_USAGE.md` for instructions on configuring Claude Desktop to use the MCP server via HTTP proxy.

## Expected Results

### Successful Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Server information: ..."
      }
    ]
  }
}
```

### Error Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "error": {
    "code": -32603,
    "message": "Command execution timed out after 30 seconds: get status"
  }
}
```

## Next Steps

1. Test with your actual demo environment
2. Verify timeout protection works correctly
3. Test Claude Desktop integration via HTTP proxy
4. Monitor performance with debug logging enabled
5. Adjust timeouts if needed for slow blockchain queries