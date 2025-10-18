# MCP Server with SSE Transport - Usage Guide

## ✅ SSE Transport is Now Implemented!

The EdgeLake MCP server now supports **SSE (Server-Sent Events)** transport, which allows it to run embedded within the EdgeLake process without conflicting with the EdgeLake CLI.

## How It Works

```
┌──────────────────┐
│  Claude Desktop  │  (or any MCP client)
└────────┬─────────┘
         │
         │ HTTP/SSE
         │ Port 50051
         │
┌────────▼────────────────────────────┐
│  EdgeLake Process                   │
│                                     │
│  ┌──────────────────────────────┐   │
│  │ EdgeLake CLI (stdin/stdout)  │   │
│  └──────────────────────────────┘   │
│                                     │
│  ┌──────────────────────────────┐   │
│  │ MCP Server Thread (SSE)      │   │
│  │  - Listens on HTTP :50051    │   │
│  │  - GET /sse (SSE endpoint)   │   │
│  │  - POST /messages/           │   │
│  └───────────┬──────────────────┘   │
│              │                      │
│              │ Direct function calls│
│              │ (No HTTP overhead)   │
│              │                      │
│  ┌───────────▼──────────────────┐   │
│  │ EdgeLakeDirectClient         │   │
│  └───────────┬──────────────────┘   │
│              │                      │
│  ┌───────────▼──────────────────┐   │
│  │ member_cmd.process_cmd()     │   │
│  └──────────────────────────────┘   │
│                                     │
└─────────────────────────────────────┘
```

## Starting the MCP Server

### Default (Recommended) - SSE Transport

```al
# From EdgeLake CLI - uses SSE by default
AL > run mcp server

# Or explicitly specify SSE with auto-capability detection
AL > run mcp server where transport = sse and tools = auto

# Custom port
AL > run mcp server where port = 50051 and transport = sse
```

This will:
- ✅ Start HTTP server on port 50051
- ✅ Listen for SSE connections at `http://127.0.0.1:50051/sse`
- ✅ Accept POST messages at `http://127.0.0.1:50051/messages/`
- ✅ Use direct integration (no HTTP between MCP server and EdgeLake core)
- ✅ No conflict with EdgeLake's CLI (which uses stdin/stdout)

### Alternative - stdio Transport (Not Recommended for Embedded)

```al
# Only use stdio if you understand the limitations
AL > run mcp server where transport = stdio
```

**Warning**: stdio transport will conflict with EdgeLake's interactive CLI.

## Checking Server Status

```al
AL > get mcp server

MCP Server Status:
  Transport: sse
  Port: 50051
  Endpoint: http://127.0.0.1:50051/sse
  Thread: EdgeLakeMCPServer (alive=True)
  Tools: auto (8 enabled)

Node Capabilities:
  Node Type: Operator, Query
  Services:
    REST: Active
    TCP: Active
    Blockchain: Connected
  Local Databases: lsl_demo, test_db
  Query Capabilities:
    Local: Yes
    Network: Yes
```

## Stopping the Server

```al
AL > exit mcp server
[MCP Server] Stopped
```

## Connecting from MCP Clients

### Claude Desktop Configuration

Add to your Claude Desktop config file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "edgelake": {
      "url": "http://127.0.0.1:50051/sse"
    }
  }
}
```

**That's it!** No need to manage a separate process - the MCP server runs inside EdgeLake.

### Python MCP Client Example

```python
from mcp.client.sse import sse_client
import asyncio

async def connect_to_edgelake():
    async with sse_client("http://127.0.0.1:50051/sse") as (read, write):
        # Use the MCP client
        # read/write are the communication streams
        pass

asyncio.run(connect_to_edgelake())
```

## Tool Capabilities

The MCP server automatically enables tools based on the EdgeLake node type:

**All Nodes Get:**
- `list_databases`
- `list_tables`
- `get_schema`
- `node_status`
- `server_info`

**Operator Nodes Also Get:**
- `operator_status`
- `cluster_info`
- `query_local` (local queries only)

**Query Nodes Also Get:**
- `query` (network queries)
- `query_status`
- `cluster_info`

**Master Nodes Also Get:**
- `blockchain_post` (write to blockchain)

**Custom Tool Selection:**
```al
# Enable specific tools only
AL > run mcp server where tools = "list_databases,query,node_status"

# Enable all tools (ignores capability detection)
AL > run mcp server where tools = all
```

## Startup Script Integration

Add to your EdgeLake `.al` startup script:

```al
# File: operator-node.al

# Set variables
<set node_name = operator1>
<set ip = 0.0.0.0>

# Start core services
<run tcp server where internal_ip = !ip and internal_port = !anylog_server_port>
<run rest server where internal_ip = !ip and internal_port = !anylog_rest_port>

# Connect to blockchain
<run blockchain sync where source = !ledger_conn and time = 30 seconds>

# Start operator
<run operator where ...>

# Start MCP service with auto-capability detection
<run mcp server where transport = sse and port = 50051 and tools = auto>
```

## Dependencies

The SSE transport requires additional Python packages. Install with:

```bash
pip install -r edge_lake/mcp_server/requirements.txt
```

Or manually:
```bash
pip install sse-starlette starlette uvicorn anyio
```

## Troubleshooting

### "SSE dependencies not available"

**Solution**: Install SSE dependencies
```bash
pip install sse-starlette starlette uvicorn
```

### "Address already in use"

**Solution**: Port 50051 is already taken. Use a different port:
```al
AL > run mcp server where port = 50052
```

### MCP client can't connect

**Check**:
1. MCP server is running: `get mcp server`
2. Port is correct in client configuration
3. Firewall isn't blocking the port
4. Using correct URL: `http://127.0.0.1:50051/sse`

### Tools not appearing in Claude Desktop

**Solution**: Check which tools are enabled:
```al
AL > get mcp server
```

If tools list is empty or wrong, restart with correct configuration:
```al
AL > exit mcp server
AL > run mcp server where tools = auto
```

## Benefits of SSE Transport

1. ✅ **No stdin/stdout conflicts** - EdgeLake CLI works normally
2. ✅ **External client support** - Claude Desktop, VS Code, etc can connect
3. ✅ **Network capable** - Can accept remote connections (if needed)
4. ✅ **Direct integration** - Still uses EdgeLakeDirectClient internally
5. ✅ **Standard HTTP** - Easy to debug with curl/browser
6. ✅ **Bidirectional** - SSE for server→client, POST for client→server

## Performance

The SSE transport adds minimal overhead:
- **External**: HTTP/SSE between MCP client and server (~1ms)
- **Internal**: Direct Python function calls (negligible)

Total latency is dominated by EdgeLake command execution time, not transport.

## Security Considerations

By default, the MCP server binds to `127.0.0.1` (localhost only).

**To allow remote connections** (not recommended without authentication):
```python
# Modify server.py run_sse_server() to bind to 0.0.0.0
await self.run_sse_server(host="0.0.0.0", port=port)
```

**Note**: The current implementation has no authentication. Only expose on localhost or behind a trusted network/VPN.

## Example Session

```bash
# Start EdgeLake
$ python edge_lake/edgelake.py

AL > run tcp server where internal_ip = 127.0.0.1 and internal_port = 32048
AL > run rest server where internal_ip = 127.0.0.1 and internal_port = 32049
AL > run mcp server
[MCP Server] Started with SSE transport on port 50051, 8 tools enabled

# In another terminal or in Claude Desktop
# Connect to http://127.0.0.1:50051/sse
# Use MCP tools to interact with EdgeLake

AL > get mcp server
MCP Server Status:
  Transport: sse
  Port: 50051
  Endpoint: http://127.0.0.1:50051/sse
  Thread: EdgeLakeMCPServer (alive=True)
  ...

AL > exit mcp server
[MCP Server] Stopped
```

## Next Steps

- Configure Claude Desktop to use your EdgeLake MCP server
- Test tool discovery and execution
- Add MCP server startup to your node's initialization script
- Monitor logs at `~/Library/Logs/edgelake_mcp.log`
