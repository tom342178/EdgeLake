# MCP Transport Modes - Clarification

## Current Implementation Reality

### ⚠️ Important Limitation

The current implementation has a **transport mode limitation** that needs to be addressed:

## Transport Modes Explained

### 1. **Standalone Mode** ✅ WORKS
```bash
# Run as separate process
python3 edge_lake/mcp_server/server.py --mode=standalone

# Claude Desktop config:
{
  "mcpServers": {
    "edgelake": {
      "command": "python3",
      "args": ["/path/to/edge_lake/mcp_server/server.py", "--mode=standalone"]
    }
  }
}
```

**How it works:**
- MCP server runs as independent process
- Uses stdio transport (reads stdin, writes stdout)
- Claude Desktop manages the process lifecycle
- ✅ **This mode is fully functional**

### 2. **Embedded Mode** ⚠️ NEEDS SSE TRANSPORT

```bash
# From EdgeLake CLI:
AL > run mcp server where tools = auto
```

**Current Issue:**
- Server runs in background thread within EdgeLake process
- Currently tries to use stdio transport
- **PROBLEM**: EdgeLake's CLI already owns stdin/stdout
- **RESULT**: MCP clients cannot connect (stdin/stdout conflict)

**What's Needed:**
The embedded mode needs to use **SSE (Server-Sent Events)** or **WebSocket** transport instead of stdio:

```python
# Future implementation needed:
run mcp server where transport = sse and port = 50051
```

This would:
- Listen on HTTP endpoint (e.g., `http://localhost:50051/mcp`)
- Use SSE for server-to-client streaming
- Use HTTP POST for client-to-server requests
- No stdin/stdout conflicts

## Direct Integration Still Works!

The **key benefit** of embedded mode is still achieved:

```
MCP Client → (SSE/HTTP) → MCP Server Thread → EdgeLakeDirectClient → member_cmd.process_cmd()
                                                                              ↓
                                                                         EdgeLake Core
```

**Zero HTTP overhead** between MCP server and EdgeLake core (uses direct function calls).

The HTTP/SSE is only between the external MCP client and the server, not within EdgeLake.

## Recommended Usage (Current State)

### For Development/Testing:
Use **standalone mode** with direct integration:

```bash
# Terminal 1: Start EdgeLake
python3 edge_lake/edgelake.py

# Terminal 2: Start MCP server (standalone with direct integration)
# Modify server.py to use EdgeLakeDirectClient even in standalone mode
python3 edge_lake/mcp_server/server.py --mode=standalone
```

### For Production (After SSE Implementation):
Use **embedded mode** with SSE transport:

```al
# In EdgeLake startup script:
<run mcp server where transport = sse and port = 50051 and tools = auto>
```

## Implementation Status

| Feature | Status | Notes |
|---------|--------|-------|
| Capability Detection | ✅ Complete | Automatic node type detection works |
| Direct Integration Client | ✅ Complete | EdgeLakeDirectClient works perfectly |
| Tool Filtering | ✅ Complete | Capability-based tool selection works |
| Standalone Mode (stdio) | ✅ Works | For separate process |
| Embedded Mode (stdio) | ⚠️ Limited | stdin/stdout conflict |
| Embedded Mode (SSE) | ❌ Not Implemented | **Needed for true embedded operation** |
| Embedded Mode (WebSocket) | ❌ Not Implemented | Alternative to SSE |

## Next Steps to Fix

### Option A: Implement SSE Transport (Recommended)

```python
# Add to server.py
async def run_sse_server(self, port: int):
    """Run MCP server with SSE transport"""
    from mcp.server.sse import sse_server

    # Create HTTP server with SSE endpoints
    app = create_sse_app(self.server)

    # Run on specified port
    await run_http_server(app, port=port)
```

### Option B: Use Separate Process for Now

Keep using standalone mode but configure it to use direct integration:

```python
# Modify standalone mode initialization
if mode == "standalone_direct":
    # Use direct client even in standalone
    self.client = EdgeLakeDirectClient()
```

### Option C: Unix Domain Socket

```python
async def run_socket_server(self, socket_path: str):
    """Run MCP server over Unix domain socket"""
    # Bind to socket file instead of stdin/stdout
```

## Conclusion

The architecture is **conceptually correct**:
- ✅ Capability detection works
- ✅ Direct integration works
- ✅ Tool filtering works
- ✅ Command integration works

The **transport layer** needs refinement:
- ⚠️ stdio only works for standalone (separate process)
- ❌ Embedded mode needs SSE/WebSocket/Socket transport
- 🎯 This is a known limitation that can be addressed

**For now, use standalone mode for testing.** The direct integration benefits can still be achieved by making standalone mode use EdgeLakeDirectClient.
