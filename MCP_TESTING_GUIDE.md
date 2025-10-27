# EdgeLake MCP Server - Testing Guide

## Overview

This guide shows how to test the EdgeLake MCP server using the comprehensive Python test suite (`test-mcp-sse.py`) and enable debug logging for troubleshooting.

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

### 3. Run Test Suite

The comprehensive Python test suite (`test-mcp-sse.py`) tests all 6 MCP tools using proper SSE protocol:

```bash
cd /Users/tviviano/Documents/GitHub/EdgeLake
python3 test-mcp-sse.py --host localhost --port 50051
```

#### Test Suite Features

- **Proper SSE Protocol**: Establishes SSE connection, receives session endpoint, sends/receives messages
- **All 6 Tools Tested**:
  1. Initialize (MCP handshake)
  2. List Tools (discover available tools)
  3. server_info (internal tool)
  4. node_status (EdgeLake status)
  5. list_databases (discover databases)
  6. list_tables (discover tables in a database)
  7. get_schema (table column definitions)
  8. query (distributed SQL query)

#### Usage Examples

**Basic test (localhost)**:
```bash
python3 test-mcp-sse.py --host localhost --port 50051
```

**Remote server test**:
```bash
python3 test-mcp-sse.py --host 192.168.1.106 --port 50051
```

**Custom database/table**:
```bash
python3 test-mcp-sse.py --host localhost --port 50051 \
  --database new_company --table rand_data
```

**Verbose output**:
```bash
python3 test-mcp-sse.py --host localhost --port 50051 --verbose
```

#### Expected Output

```
############################################################
# EdgeLake MCP SSE Comprehensive Test Suite
# Host: localhost:50051
# Using proper MCP SSE protocol
############################################################

============================================================
Establishing SSE session with http://localhost:50051/sse
============================================================
✓ SSE connection established
✓ Received message endpoint: /messages/?session_id=abc123
✓ Session established successfully

============================================================
Test 1: MCP Initialize
============================================================
→ Sending initialize request
✓ Initialize successful
  Protocol Version: 2024-11-05
  Server Name: edgelake-mcp-server
  Server Version: 1.19.0

============================================================
Test 2: MCP tools/list
============================================================
✓ Found 6 tools
  Tool: list_databases
  Tool: list_tables
  Tool: get_schema
  Tool: query
  Tool: node_status
  Tool: server_info

[... more tests ...]

============================================================
Test Summary
============================================================
✓ PASS: 1. Initialize
✓ PASS: 2. List Tools
✓ PASS: 3. Tool: server_info
✓ PASS: 4. Tool: node_status
✓ PASS: 5. Tool: list_databases
✓ PASS: 6. Tool: list_tables
✓ PASS: 7. Tool: get_schema
✓ PASS: 8. Tool: query

Total: 8/8 tests passed
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

## Using the Test Suite with Makefile (Utilities)

If you have the utilities repository set up, you can use convenient Makefile targets:

### From utilities/edgelake directory

```bash
cd /path/to/utilities/edgelake

# Test if SSE endpoint is up
make test-sse-up

# Run full MCP tools test suite
make test-sse-tools
```

### Makefile Targets

**`make test-sse-up`**: Quick health check
- Connects to SSE endpoint
- Verifies server is responding
- Useful for confirming deployment

**`make test-sse-tools`**: Full test suite
- Runs all 8 tests (initialize + 7 tools)
- Tests proper MCP SSE protocol
- Validates query functionality
- Reports pass/fail for each test

## Manual Testing with curl (Advanced)

**Note**: The test suite (`test-mcp-sse.py`) uses proper MCP SSE protocol which is more reliable than direct curl calls. The curl examples below are for reference only.

### SSE Connection Flow

The MCP SSE protocol requires:
1. Connect to `/sse` endpoint (GET with Accept: text/event-stream)
2. Receive `endpoint` event with message URL
3. Send JSON-RPC requests to message URL (POST)
4. Receive responses via SSE `message` events

This is **not possible with simple curl POST** because:
- SSE requires persistent connection for events
- Message endpoint is dynamically assigned per session
- Responses come via SSE stream, not HTTP response body

**For manual testing, use the Python test suite instead.**

### curl Examples (Informational Only)

These won't work for SSE but show the JSON-RPC format:

**Initialize** (won't receive response):
```bash
# This connects but can't receive the SSE endpoint event
curl -N http://localhost:50051/sse \
  -H "Accept: text/event-stream"
```

**List Tools** (requires session):
```bash
# This would need the session endpoint from SSE
# Example format only:
curl -X POST "http://localhost:50051/messages/?session_id=SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}'
```

**Call Tool** (requires session):
```bash
# Example format only - requires active SSE session
curl -X POST "http://localhost:50051/messages/?session_id=SESSION_ID" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "server_info",
    "arguments": {}
  }
}'
```

## Test Suite Architecture

### How test-mcp-sse.py Works

The Python test suite properly implements the MCP SSE protocol:

1. **Establish SSE Connection**
   - Opens persistent connection to `/sse` endpoint
   - Runs background thread to listen for events
   - Receives dynamically-assigned message endpoint

2. **Send Requests**
   - Posts JSON-RPC messages to session-specific endpoint
   - Each request has unique ID for correlation
   - Timeout protection (35 seconds per request)

3. **Receive Responses**
   - Listens for SSE `message` events
   - Matches responses to requests by ID
   - Queues responses for main thread processing

4. **Execute Tests**
   - Tests run sequentially
   - Each test validates response format
   - Reports pass/fail with detailed output

### Timeout Protection

The test suite and MCP server both have timeout protection:

**Test Suite**:
- Default: 35 seconds per request
- Prevents hanging on unresponsive server
- Reports timeout errors clearly

**MCP Server**:
- Default: 30 seconds per EdgeLake command
- Returns JSON-RPC error on timeout
- EdgeLake process continues running

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

### Issue: Test suite can't connect

**Symptoms**:
```
✗ Failed to establish SSE connection
```

**Check**:
1. Is MCP server running?
   ```bash
   # Check container logs
   docker logs edgelake-query | grep MCP

   # Should see:
   # MCP Server | Running | Listening on: 0.0.0.0:50051
   ```

2. Is port 50051 accessible?
   ```bash
   # Test basic connectivity
   curl http://localhost:50051/sse

   # Should get SSE stream (won't close until Ctrl+C)
   ```

3. Check firewall/network:
   ```bash
   # On macOS
   sudo lsof -i :50051

   # On Linux
   sudo netstat -tulpn | grep 50051
   ```

### Issue: Commands timing out

**Symptoms**:
```
✗ node_status failed: timeout
```

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

### Issue: Query tool fails validation

**Symptoms**:
```
✗ query failed: Query validation failed: DBMS "new_company" not connected
```

**Solution**:
This is now fixed! Network queries route through `run client ()` and don't require local database connectivity.

**If still happening**:
1. Pull latest code (commit `4901572` or later)
2. Rebuild Docker image
3. Redeploy container

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

### Testing Individual Tools

You can modify `test-mcp-sse.py` to test specific tools:

```python
# Edit test-mcp-sse.py, comment out tests you don't want:
def run_all_tests(self) -> bool:
    print(f"\n{'#'*60}")
    print(f"# EdgeLake MCP SSE Comprehensive Test Suite")
    # ...

    # Comment out tests you don't want
    # results["1. Initialize"] = self.test_initialize()
    # results["2. List Tools"] = self.test_list_tools()
    results["3. Tool: server_info"] = self.test_server_info()
    # results["4. Tool: node_status"] = self.test_node_status()
    # ...
```

### Testing from Claude Desktop

See MCP documentation for configuring Claude Desktop to use EdgeLake MCP server.

### Using with Other MCP Clients

The test suite demonstrates proper MCP SSE protocol. Use it as reference for implementing other clients:

1. SSE connection establishment
2. Endpoint discovery
3. Message posting
4. Response handling
5. Error handling

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

## Quick Reference

### Running Tests

```bash
# From EdgeLake repository
cd /Users/tviviano/Documents/GitHub/EdgeLake
python3 test-mcp-sse.py --host localhost --port 50051

# From utilities repository
cd /Users/tviviano/Documents/GitHub/utilities/edgelake
make test-sse-tools

# With custom database/table
python3 test-mcp-sse.py --host 192.168.1.106 --port 50051 \
  --database new_company --table rand_data
```

### Checking Logs

```bash
# Docker container logs
docker logs edgelake-query | grep MCP

# Last 50 lines with MCP context
docker logs edgelake-query | tail -50

# Follow logs in real-time
docker logs -f edgelake-query
```

### Common Commands

```bash
# Check if MCP server is running (inside container)
docker exec edgelake-query python3 -c "
from edge_lake.cmd import member_cmd
print(member_cmd.commands['run mcp server'].get('thread'))
"

# Get MCP server status (via EdgeLake CLI)
docker exec -it edgelake-query /bin/bash
python3 /app/EdgeLake/edge_lake/edgelake.py "get mcp server"

# Stop MCP server
python3 /app/EdgeLake/edge_lake/edgelake.py "exit mcp server"

# Start MCP server
python3 /app/EdgeLake/edge_lake/edgelake.py "run mcp server"
```

## Next Steps

1. **Run Test Suite**: Verify all tools work with `make test-sse-tools`
2. **Enable Debug Logging**: Set `MCP_LOG_LEVEL=DEBUG` to troubleshoot
3. **Monitor Logs**: Watch for errors during test execution
4. **Test with Real Data**: Use your actual database/table names
5. **Integration Testing**: Test with Claude Desktop or other MCP clients

## Additional Resources

- **`test-mcp-sse.py`**: Comprehensive test suite source code
- **`edge_lake/mcp_server/ARCHITECTURE.md`**: MCP server architecture
- **`MCP_QUICKSTART.md`**: Quick start guide
- **`DOCKER_MCP_AUTOSTART.md`**: Auto-start configuration
- **Utilities Makefile**: `utilities/edgelake/Makefile` for test targets