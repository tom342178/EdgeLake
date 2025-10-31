# EdgeLake MCP Server

**Model Context Protocol (MCP) integration for EdgeLake distributed database.**

## Overview

EdgeLake MCP Server provides AI agents with access to EdgeLake's distributed query capabilities through the Model Context Protocol. The server integrates seamlessly with EdgeLake's production HTTP infrastructure.

## Architecture

```
AI Agent (Claude Code, etc.)
         ↓
    MCP Protocol (HTTP/SSE)
         ↓
EdgeLake HTTP Server (http_server.py)
         ↓
MCP Server (integrated)
         ↓
EdgeLake Core (queries, metadata, etc.)
```

### Key Components

1. **Transport Layer** (`transport/`)
   - `sse_handler.py` - Server-Sent Events transport over http_server.py
   - Manages SSE connections, keepalive, and message routing
   - Thread-safe connection management

2. **Server** (`server/`)
   - `mcp_server.py` - MCP protocol implementation
   - JSON-RPC message processing
   - Tool registration and execution
   - Lifecycle management

3. **Core Components** (`core/`)
   - `query_builder.py` - SQL query construction from tool parameters
   - `query_executor.py` - Hybrid validation + streaming query execution
   - `direct_client.py` - Direct integration with member_cmd.process_cmd()
   - `command_builder.py` - EdgeLake command construction

4. **Tools** (`tools/`)
   - `generator.py` - Dynamic tool generation from configuration
   - `executor.py` - Tool execution and response formatting

5. **Configuration** (`config/`)
   - `tools.json` - Tool definitions
   - Configuration-driven approach for extensibility

## Quick Start

### 1. Prerequisites

```bash
# Install MCP dependencies
pip install mcp pydantic
```

### 2. Start EdgeLake

```bash
python edge_lake/edgelake.py
```

### 3. Start REST Server

```
AL > run rest server where external_ip = 0.0.0.0 and external_port = 32049 and internal_ip = 127.0.0.1 and internal_port = 32049
```

### 4. Start MCP Server

```
AL > run mcp server
```

Expected output:
```
MCP server started
Endpoints: GET /mcp/sse, POST /mcp/messages/{session_id}
```

### 5. Test SSE Connection

```bash
curl -N http://localhost:32049/mcp/sse
```

### 6. Configure AI Agent

Add to your MCP client configuration:
```json
{
  "mcpServers": {
    "edgelake": {
      "url": "http://localhost:32049/mcp/sse"
    }
  }
}
```

## Commands

### Start MCP Server
```
run mcp server
```

Prerequisites: REST server must be running first.

### Stop MCP Server
```
exit mcp server
```

Gracefully stops the MCP server and cleans up resources.

## Endpoints

- **GET /mcp/sse** - Establish SSE connection for event streaming
- **POST /mcp/messages/{session_id}** - Submit MCP JSON-RPC messages

## Configuration

### Connection Settings

Edit `edge_lake/mcp/transport/sse_handler.py`:
```python
self.keepalive_interval = 30    # Keepalive ping interval (seconds)
self.connection_timeout = 300   # Connection timeout (seconds)
```

### Tool Configuration

Tools are defined in `config/tools.json`. Each tool specifies:
- Name and description
- Input schema (JSON Schema)
- EdgeLake command mapping
- Response formatting

**Configuration-Driven Design**: Adding new tools only requires configuration changes, not code modifications.

## Available Tools

The MCP server dynamically generates tools based on configuration:

1. **Query Tools**
   - `run_query` - Execute SQL queries with filters, grouping, ordering
   - `list_databases` - Discover available databases
   - `list_tables` - List tables in a database
   - `get_schema` - Get table schema information

2. **Metadata Tools**
   - `blockchain_get` - Query blockchain metadata
   - `get_policies` - Retrieve network policies

3. **System Tools**
   - `node_status` - Get node health and status
   - `server_info` - Get MCP server information

## Architecture Principles

### Configuration-Driven

**All tool behavior is defined in configuration files, not hardcoded.**

This ensures:
- **Maintainability**: Add new tools via configuration only
- **Consistency**: All tools follow the same execution pattern
- **Extensibility**: New query types require only registration
- **Testability**: Configuration can be validated independently

### Direct Integration

**Uses EdgeLake's native command processing (`member_cmd.process_cmd()`).**

Benefits:
- No HTTP overhead for internal operations
- Access to all EdgeLake commands
- Consistent validation and error handling
- Real-time command execution

### Streaming Support

**Large query results use streaming to avoid memory issues.**

The query executor:
1. Validates queries via `select_parser()` (EdgeLake core)
2. Streams results via `process_fetch_rows()` (EdgeLake core)
3. Auto-selects streaming vs batch based on query characteristics

### Production Ready

**Integrates with EdgeLake's production HTTP server.**

Features:
- Shared workers pool with REST API
- SSL/TLS support via http_server.py
- Authentication integration
- Logging and error handling
- Thread-safe operations

## Performance

- **Memory**: ~1KB per SSE connection
- **CPU**: Minimal (async processing via thread pool)
- **Network**: Keepalive ping every 30 seconds per connection
- **Latency**: <50ms for tool calls (excluding query execution)

## Development

### File Structure

```
edge_lake/mcp/
├── README.md                   # This file
├── DESIGN.md                   # Architecture documentation
├── IMPLEMENTATION_PLAN.md      # Detailed implementation plan
├── IMPLEMENTATION_STATUS.md    # Current status
├── QUICK_START.md              # 5-minute test guide
├── transport/
│   ├── __init__.py
│   └── sse_handler.py          # SSE transport layer
├── server/
│   ├── __init__.py
│   └── mcp_server.py           # MCP protocol server
├── core/
│   ├── __init__.py
│   ├── query_builder.py        # SQL query construction
│   ├── query_executor.py       # Query execution + streaming
│   ├── direct_client.py        # Direct member_cmd integration
│   └── command_builder.py      # EdgeLake command construction
├── tools/
│   ├── __init__.py
│   ├── generator.py            # Tool generation
│   └── executor.py             # Tool execution
└── config/
    ├── __init__.py
    └── tools.json              # Tool definitions
```

### Adding New Tools

1. Edit `config/tools.json`:
```json
{
  "name": "my_new_tool",
  "description": "What the tool does",
  "category": "query",
  "edgelake_command": {
    "type": "sql",
    "template": "sql {database} \"{query}\""
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "database": {"type": "string"},
      "query": {"type": "string"}
    },
    "required": ["database", "query"]
  }
}
```

2. Restart MCP server - tool is automatically available!

### Debugging

Enable MCP logging:
```python
import logging
logging.getLogger('edge_lake.mcp').setLevel(logging.DEBUG)
```

Check active connections:
```python
# In EdgeLake CLI
AL > get processes
```

Monitor SSE traffic:
```bash
# Terminal 1: Watch SSE events
curl -N http://localhost:32049/mcp/sse

# Terminal 2: Send test message
curl -X POST http://localhost:32049/mcp/messages/{session_id} \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Testing

### Manual Testing

See `QUICK_START.md` for step-by-step testing instructions.

### Integration Testing

```python
# Test with actual MCP client
from mcp import Client

async with Client("http://localhost:32049/mcp/sse") as client:
    # List available tools
    tools = await client.list_tools()

    # Call a tool
    result = await client.call_tool("run_query", {
        "database": "test",
        "table": "readings",
        "limit": 10
    })
```

### Regression Testing

Ensure REST API still works:
```bash
# REST API should be unaffected
curl -X GET http://localhost:32049/get/status \
  -H "User-Agent: AnyLog/1.23" \
  -H "command: get status"
```

## Troubleshooting

### "MCP server is already running"
```
AL > exit mcp server
AL > run mcp server
```

### "REST server must be running first"
Start REST server before MCP server.

### "MCP not available: No module named 'mcp'"
```bash
pip install mcp pydantic
```

### Connection Drops

Check logs and adjust timeout in `sse_handler.py`:
```python
self.connection_timeout = 600  # 10 minutes
```

### High Memory Usage

For large queries, implement block transport (Phase 2):
- See `IMPLEMENTATION_PLAN.md` for details
- Threshold-based selection (>10MB)

## Documentation

- **DESIGN.md** - Complete architecture and technical specifications
- **IMPLEMENTATION_PLAN.md** - 4-week phased implementation plan
- **IMPLEMENTATION_STATUS.md** - Current implementation status
- **QUICK_START.md** - 5-minute test guide

## Future Enhancements

### Phase 2: Block Transport
- Handle large query results (>10MB) via message_server.py
- Chunked delivery for efficiency
- See `IMPLEMENTATION_PLAN.md` for details

### Phase 3: Advanced Features
- Query result caching
- WebSocket transport option
- Metrics and monitoring dashboard
- Multi-tenant support

## License

Mozilla Public License 2.0

## Support

- GitHub Issues: https://github.com/EdgeLake/edgelake/issues
- Documentation: https://edgelake.github.io/
- MCP Specification: https://spec.modelcontextprotocol.io/
