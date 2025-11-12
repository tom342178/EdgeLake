# EdgeLake MCP Server Architecture

**Version:** 2.0 (Protocol Exec Integration)
**Date:** 2025-01-11
**Status:** Production

## Executive Summary

The EdgeLake MCP (Model Context Protocol) server provides AI agents with access to EdgeLake's distributed query capabilities through a standardized protocol. The architecture uses **Server-Sent Events (SSE) over HTTP** for transport and shares core execution logic with EdgeLake's REST API through a unified **protocol_exec** layer.

**Key Features:**
- **Unified Execution Path**: HTTP REST and MCP/SSE share 90%+ of command execution logic
- **Zero Duplication**: Single codebase for command preparation, execution, and result handling
- **Transport Agnostic**: Protocol callbacks abstract transport-specific concerns
- **Production Ready**: Integrated with EdgeLake's production http_server.py infrastructure

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
├─────────────────────────┬───────────────────────────────────────┤
│   HTTP REST Clients     │     MCP Clients (Claude, etc.)        │
│   (curl, apps, etc.)    │                                        │
└──────────┬──────────────┴────────────────┬──────────────────────┘
           │                                │
           │ HTTP POST                      │ SSE + POST
           │ /command                       │ /mcp/sse + /mcp/messages/
           │                                │
┌──────────▼────────────────────────────────▼──────────────────────┐
│                    http_server.py (Port 32049)                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ ChunkedHTTPRequestHandler                                │   │
│  │  - do_GET()  → Route requests                            │   │
│  │  - do_POST() → Route requests                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────┬──────────────────────────────────────┬──────────────────┘
         │                                       │
         │ /command                              │ /mcp/*
         │                                       │
         ▼                                       ▼
┌────────────────────┐              ┌─────────────────────────────┐
│   al_exec()        │              │   SSE Transport             │
│   (HTTP Layer)     │              │   (MCP Layer)               │
├────────────────────┤              ├─────────────────────────────┤
│ 1. Validate cmd    │              │ 1. SSE connection mgmt      │
│ 2. Check method    │              │ 2. Session management       │
│ 3. Build headers   │              │ 3. Message routing:         │
│ 4. Create callbacks│              │    - initialize → mcp_server│
│ 5. Call protocol_  │              │    - tools/list → mcp_server│
│    exec            │              │    - tools/call → protocol_ │
│                    │              │                    exec      │
└────────┬───────────┘              └──────────┬──────────────────┘
         │                                     │
         │ HTTPProtocolCallbacks               │ MCPProtocolCallbacks
         │                                     │
         └─────────────────┬───────────────────┘
                           │
         ┌─────────────────▼────────────────────────────┐
         │         protocol_exec                        │
         │         (Shared Execution Layer)             │
         ├──────────────────────────────────────────────┤
         │ 1. Validate command                          │
         │ 2. Parse into words                          │
         │ 3. Validate via callbacks                    │
         │ 4. Prepare commands (prepare_commands)       │
         │ 5. Execute commands (execute_al_commands)    │
         │ 6. Handle results:                           │
         │    - Local queries                           │
         │    - Distributed queries                     │
         │    - Regular commands                        │
         │    - Stream files                            │
         │ 7. Send via callbacks                        │
         └──────────────────────────────────────────────┘
                           │
         ┌─────────────────▼────────────────────────────┐
         │         command_execution.py                 │
         │         (EdgeLake Core)                      │
         ├──────────────────────────────────────────────┤
         │ - get_run_client() - Build network wrapper   │
         │ - prepare_commands() - Parse & validate      │
         │ - execute_al_commands() - Execute via        │
         │                           member_cmd         │
         │ - local_table_query() - Query local tables   │
         └──────────────────────────────────────────────┘
                           │
         ┌─────────────────▼────────────────────────────┐
         │         member_cmd.py                        │
         │         (Command Processor)                  │
         ├──────────────────────────────────────────────┤
         │ - process_cmd() - Main command dispatcher    │
         │ - 1000+ EdgeLake commands                    │
         │ - SQL query execution                        │
         │ - Distributed operations                     │
         └──────────────────────────────────────────────┘
```

## Component Details

### 1. HTTP Server Integration

**File:** `edge_lake/tcpip/http_server.py`

EdgeLake's production HTTP server handles both REST API and MCP traffic on the same port (default 32049).

**Endpoints:**

| Endpoint | Method | Purpose | Handler |
|----------|--------|---------|---------|
| `/command` | POST/GET/PUT | REST API commands | `al_exec()` |
| `/mcp/sse` | GET | Establish SSE connection | `SSETransport.handle_sse_endpoint()` |
| `/mcp/messages/{session_id}` | POST | Submit MCP messages | `SSETransport.handle_post_message()` |

**Request Flow (REST):**
1. Client sends HTTP request to `/command`
2. `do_POST()` calls `al_exec()`
3. `al_exec()` validates command and HTTP method
4. Creates `HTTPProtocolCallbacks`
5. Delegates to `protocol_exec()`
6. Results sent via HTTP response

**Request Flow (MCP):**
1. Client establishes SSE: `GET /mcp/sse`
2. Server creates session and returns endpoint path
3. Client posts messages: `POST /mcp/messages/{session_id}`
4. SSE transport routes to appropriate handler
5. Results queued and sent via SSE events

### 2. MCP Server Core

**File:** `edge_lake/mcp_server/mcp_server.py`

Handles MCP protocol operations (initialization, tool listing).

**Responsibilities:**
- **Protocol Handshake**: Handle `initialize` method
- **Tool Discovery**: Handle `tools/list` method
- **Configuration**: Load tool definitions from YAML
- **Lifecycle**: Start/stop MCP server

**Methods:**

```python
class MCPServer:
    def __init__(self, config_dir, enabled_tools, capabilities)
        # Load config, initialize tool generator

    def start(self)
        # Initialize SSE transport
        # Register with http_server

    def stop(self)
        # Shutdown SSE transport
        # Cleanup resources

    def process_message(self, message, socket) -> dict
        # Handle: initialize, tools/list, notifications
        # Route JSON-RPC messages

    def _list_tools(self) -> List[dict]
        # Generate tool definitions from config

    def get_info(self) -> dict
        # Return server status and metadata
```

**Note:** `tools/call` is NOT handled by `mcp_server.py`. It goes directly to `protocol_exec` via `protocol_integration.py`.

### 3. SSE Transport Layer

**File:** `edge_lake/mcp_server/transport/sse_handler.py`

Manages SSE connections and routes MCP messages.

**Classes:**

#### SSEConnection
Represents a single client connection.

```python
class SSEConnection:
    def __init__(self, session_id, handler)
        # Create connection with unique session ID

    def queue_message(self, event_type, data)
        # Queue message for delivery

    def send_event(self, event_type, data, event_id) -> bool
        # Send SSE event immediately

    def send_keepalive(self) -> bool
        # Send keepalive ping

    def close(self)
        # Close connection
```

#### SSETransport
Manages all active connections.

```python
class SSETransport:
    def __init__(self, mcp_server)
        # Initialize transport
        # Create protocol_integration
        # Start keepalive thread

    def handle_sse_endpoint(self, handler) -> bool
        # GET /mcp/sse
        # Create new SSE connection
        # Send endpoint event

    def handle_post_message(self, handler, session_id, message) -> bool
        # POST /mcp/messages/{session_id}
        # Route message to _process_message_sync

    def _process_message_sync(self, session_id, message, socket)
        # Route by method:
        #   initialize → mcp_server.process_message()
        #   tools/list → mcp_server.process_message()
        #   tools/call → protocol_integration.execute_tool_via_protocol_exec()
        #   notifications/* → ignore

    def _keepalive_loop(self)
        # Background thread
        # Send keepalive pings every 30 seconds
        # Cleanup stale connections
```

**SSE Event Format:**
```
data: {"jsonrpc": "2.0", "id": 1, "result": {...}}
event: message
id: 123

```

### 4. Protocol Integration Layer

**File:** `edge_lake/mcp_server/transport/protocol_integration.py`

Bridges MCP tools to protocol_exec.

**Class:**

```python
class MCPProtocolIntegration:
    def __init__(self, command_builder, config)
        # Store references to shared components

    async def execute_tool_via_protocol_exec(
        self, sse_connection, json_rpc_id,
        tool_name, arguments
    )
        # 1. Get tool config
        # 2. Handle internal tools (server_info)
        # 3. Build EdgeLake command
        # 4. Create MCPProtocolCallbacks
        # 5. Create ProcessStat
        # 6. Call protocol_exec()
        # 7. Results sent via callbacks

    def _build_edgelake_command(self, tool_config, arguments) -> tuple
        # Build command from tool definition
        # Extract headers (destination, subset, timeout)
        # Return (command, headers)
```

**Flow:**
```
MCP Tool Call
    ↓
_build_edgelake_command()
    ↓
Create MCPProtocolCallbacks
    ↓
protocol_exec(status, command, callbacks, headers)
    ↓
Results queued via callbacks.send_success()
    ↓
SSE delivers to client
```

### 5. Protocol Exec (Shared Execution)

**File:** `edge_lake/cmd/protocol_exec.py`

Transport-agnostic command execution engine. Shared by HTTP and MCP.

**Function Signature:**
```python
def protocol_exec(
    status: ProcessStat,
    command: str,
    protocol_callbacks: ProtocolCallbacks,
    http_method: str = "get",
    into_output: Optional[str] = None,
    headers: Optional[dict] = None
) -> int
```

**Execution Steps:**

1. **Validation**
   - Check command exists
   - Parse into words
   - Validate via `callbacks.validate_command()`

2. **Preparation**
   - Extract destination/subset/timeout from headers
   - Build `run_client` wrapper (local vs network)
   - Call `prepare_commands()` from command_execution

3. **Execution**
   - Create I/O buffer
   - Get output socket from callbacks
   - Call `execute_al_commands()` from command_execution

4. **Result Handling** (based on command type):
   - **Local SELECT**: Query local tables, stream results
   - **Distributed SELECT**: Aggregate from operators, stream results
   - **Distributed Command**: Collect messages from operators
   - **Stream File**: Deliver file content
   - **Regular Command**: Return result set

5. **Delivery**
   - Call `callbacks.send_success()` or `callbacks.send_error()`
   - Transport-specific formatting and delivery

**Shared Logic:**
- ~90% of al_exec logic extracted to protocol_exec
- Zero code duplication between HTTP and MCP
- Single maintenance point for all execution logic

### 6. Protocol Callbacks

**File:** `edge_lake/generic/protocol_callbacks.py`

Abstract interface for transport-specific operations.

**Interface:**

```python
class ProtocolCallbacks(ABC):
    @abstractmethod
    def send_error(status, error_code, error_message, error_details)
        # Send error response

    @abstractmethod
    def send_success(status, result_data, content_type, metadata)
        # Send success response

    @abstractmethod
    def get_output_socket(status)
        # Return output stream (wfile, BytesIO, etc.)

    @abstractmethod
    def send_headers(status, content_type, is_chunked)
        # Send protocol headers (if applicable)

    @abstractmethod
    def get_protocol_name() -> str
        # Return protocol name for logging

    @abstractmethod
    def supports_streaming() -> bool
        # Whether protocol supports streaming

    def validate_command(status, http_method, cmd_words) -> Optional[int]
        # Validate command for protocol (default: no-op)
```

**Implementations:**

#### HTTPProtocolCallbacks
Wraps HTTP handler methods.

```python
class HTTPProtocolCallbacks:
    def send_error(...)
        # Call http_handler.error_failed_process()

    def send_success(...)
        # Call http_handler.write_headers_and_msg()
        # Or utils_io.write_to_stream() if streaming

    def get_output_socket(status)
        # Return http_handler.wfile (direct socket)

    def send_headers(...)
        # Call http_handler.send_reply_headers()

    def validate_command(...)
        # Call http_handler.is_correct_method()
        # Validates GET/POST/PUT matches command
```

#### MCPProtocolCallbacks
Queues JSON-RPC messages for SSE delivery.

```python
class MCPProtocolCallbacks:
    def send_error(...)
        # Build JSON-RPC error response
        # Queue via sse_connection.queue_message()

    def send_success(...)
        # Build JSON-RPC success response
        # Queue via sse_connection.queue_message()

    def get_output_socket(status)
        # Return BytesIO buffer

    def send_headers(...)
        # No-op (SSE has no separate headers)

    def validate_command(...)
        # No-op (MCP doesn't have HTTP method restrictions)
```

**Key Difference:**
- **HTTP**: Direct socket writes, streaming
- **MCP**: Buffered writes, queued messages

### 7. Command Execution (EdgeLake Core)

**File:** `edge_lake/cmd/command_execution.py`

Core EdgeLake command execution logic extracted from http_server.

**Functions:**

```python
def get_run_client(destination, subset, timeout) -> str
    # Build "run client" wrapper for network execution
    # destination: "local", "network", or "ip:port"
    # Returns: "" (local) or "run client (...) " (network)

def prepare_commands(
    status, command, cmd_words, commands_list,
    into_output, run_client, msg_body,
    format_type, pass_through, file_data
) -> tuple
    # Parse and validate commands
    # Determine execution mode (with_wait, is_select, is_stream)
    # Handle "body" commands (multiple commands in body)
    # Returns: (ret_val, with_wait, content_type, is_select, is_stream, file_data)

def execute_al_commands(
    status, io_buff, commands_list,
    into_output, file_data, output_socket
) -> int
    # Execute commands via member_cmd.process_cmd()
    # Write output to output_socket
    # Returns: process_status code

def local_table_query(
    status, j_handle, with_wait,
    nodes_count, nodes_replied, send_headers_callback
) -> int
    # Execute local SELECT query
    # Stream results via send_headers_callback or to socket
    # Returns: write status
```

**These functions are called by protocol_exec and shared by HTTP/MCP.**

### 8. Tool System

**Files:**
- `edge_lake/mcp_server/tools/generator.py`
- `edge_lake/mcp_server/config/tools.yaml`

**ToolGenerator:**
Generates MCP tool definitions from YAML configuration.

```python
class ToolGenerator:
    def __init__(self, tools_config, enabled_tools)
        # Load tool definitions
        # Filter by enabled_tools

    def generate_tools(self) -> List[dict]
        # Convert YAML to MCP tool format
        # Return list of tool definitions
```

**Tool Definition (YAML):**
```yaml
- name: query
  description: Execute SQL query on distributed data
  input_schema:
    type: object
    properties:
      database:
        type: string
        description: Database name
      query:
        type: string
        description: SQL query
  edgelake_command:
    template: 'sql {database} format = mcp "{query}"'
    headers:
      destination: network  # Route to operator nodes
```

**Tool Definition (MCP Format):**
```json
{
  "name": "query",
  "description": "Execute SQL query on distributed data",
  "inputSchema": {
    "type": "object",
    "properties": {
      "database": {"type": "string", "description": "Database name"},
      "query": {"type": "string", "description": "SQL query"}
    },
    "required": ["database", "query"]
  }
}
```

## Message Flow

### HTTP REST Request Flow

```
1. Client: POST /command
   Headers: command: get status

2. http_server.do_POST()
   ↓
3. al_exec(status, "post", "get status")
   - Validate command exists
   - Validate POST is correct method
   - Extract headers (destination, subset, timeout, into)
   - Create HTTPProtocolCallbacks(self, "post")
   ↓
4. protocol_exec(status, "get status", callbacks, "post", into_output, headers)
   - Parse: ["get", "status"]
   - Validate via callbacks.validate_command()
   - Prepare: get_run_client(), prepare_commands()
   - Execute: execute_al_commands() → member_cmd.process_cmd()
   - Result: j_handle.get_result_set()
   ↓
5. callbacks.send_success(status, result_set, "text/json")
   ↓
6. http_handler.write_headers_and_msg(status, 200, "text/json", result_set)
   ↓
7. Client receives: HTTP 200 with JSON result
```

### MCP Tool Call Flow

```
1. Client: POST /mcp/messages/{session_id}
   Body: {
     "jsonrpc": "2.0",
     "id": 1,
     "method": "tools/call",
     "params": {
       "name": "node_status",
       "arguments": {}
     }
   }

2. http_server.do_POST()
   ↓
3. SSETransport.handle_post_message(handler, session_id, message)
   ↓
4. _process_message_sync(session_id, message, socket=None)
   - method == "tools/call"
   - tool_name = "node_status"
   - arguments = {}
   ↓
5. protocol_integration.execute_tool_via_protocol_exec(
      sse_connection, msg_id=1, "node_status", {}
   )
   - Get tool config
   - Build command: "get status"
   - Extract headers: None (local execution)
   - Create MCPProtocolCallbacks(sse_connection, 1)
   ↓
6. protocol_exec(status, "get status", callbacks, "get", None, None)
   - Parse: ["get", "status"]
   - Validate: callbacks.validate_command() → None (OK)
   - Prepare: get_run_client("local") → ""
   - Execute: execute_al_commands() → member_cmd.process_cmd()
   - Result: j_handle.get_result_set()
   ↓
7. callbacks.send_success(status, result_set, "text/json")
   - Format JSON-RPC response
   - Queue: sse_connection.queue_message('message', response)
   ↓
8. SSE delivers queued message to client:
   data: {"jsonrpc": "2.0", "id": 1, "result": {"content": [...]}}
   event: message
   id: 123

9. Client receives result via SSE stream
```

### Distributed Query Flow (MCP)

```
1. Client: tools/call with name="query"
   arguments: {
     "database": "new_company",
     "query": "SELECT AVG(value) FROM sensor_data"
   }

2. protocol_integration._build_edgelake_command()
   - Build: 'sql new_company format = mcp "SELECT AVG(value) FROM sensor_data"'
   - Extract headers: {"destination": "network"}
   ↓
3. protocol_exec(..., headers={"destination": "network"})
   - get_run_client("network", False, None) → "run client () "
   - prepare_commands() → with_wait=True, is_select=True
   - Command becomes: "run client () sql new_company format = mcp ..."
   ↓
4. execute_al_commands()
   - member_cmd.process_cmd("run client () sql ...")
   - Distributes query to operator nodes
   - Waits for responses
   - Aggregates results in system_query database
   ↓
5. protocol_exec handles result (with_wait=True, is_select=True)
   - Query system_query for aggregated results
   - local_table_query() writes to output_socket (BytesIO)
   ↓
6. callbacks.send_success()
   - Read from BytesIO buffer
   - Format as JSON-RPC response
   - Queue for SSE delivery
   ↓
7. Client receives aggregated query result
```

## Configuration

### Server Configuration

**File:** `edge_lake/mcp_server/config/config.yaml`

```yaml
server:
  max_workers: 4  # Thread pool size
  timeout: 300    # Query timeout (seconds)

tools:
  enabled:
    - node_status
    - query
    - list_database_schema
    # ... more tools
```

### Tool Configuration

**File:** `edge_lake/mcp_server/config/tools.yaml`

```yaml
- name: node_status
  description: Get EdgeLake node status
  input_schema:
    type: object
    properties: {}
  edgelake_command:
    template: 'get status'

- name: query
  description: Execute SQL query on distributed data
  input_schema:
    type: object
    properties:
      database:
        type: string
      query:
        type: string
    required: [database, query]
  edgelake_command:
    template: 'sql {database} format = mcp "{query}"'
    headers:
      destination: network  # Execute on operator nodes
```

**Headers:**
- `destination`: "local" (run on query node) or "network" (distribute to operators)
- `subset`: Allow partial results if some nodes fail
- `timeout`: Command timeout in seconds

## Design Decisions

### 1. Why SSE over WebSockets?

**SSE Advantages:**
- **Simpler Protocol**: One-way server-to-client streaming
- **HTTP Compatible**: Works with existing http_server.py
- **Firewall Friendly**: Standard HTTP/HTTPS ports
- **Auto Reconnect**: Built into browser SSE API
- **No New Dependencies**: No websocket library needed

**MCP Requirements:**
- Bidirectional communication needed (client sends, server responds)
- Achieved via dual channels: POST for requests + SSE for responses

### 2. Why Protocol Callbacks?

**Problem:** HTTP and MCP need different response mechanisms:
- HTTP: Direct socket writes, streaming
- MCP: JSON-RPC messages queued for SSE

**Solution:** Abstract transport via callbacks:
- `send_success()` / `send_error()` hide transport details
- `get_output_socket()` provides appropriate buffer type
- Single execution path works for both protocols

**Benefits:**
- Zero code duplication
- Single maintenance point
- Easy to add new transports (stdio, WebSocket, gRPC)

### 3. Why Separate initialize/tools/list from tools/call?

**MCP Protocol Operations:**
- `initialize`: Protocol handshake, exchange capabilities
- `tools/list`: Enumerate available tools
- `tools/call`: Execute a tool

**Routing:**
- `initialize` and `tools/list`: Handled by `mcp_server.py` (protocol-specific)
- `tools/call`: Routed to `protocol_exec` (command execution)

**Rationale:**
- Protocol operations (init, list) are MCP-specific
- Tool execution (call) is EdgeLake command execution (shared with HTTP)
- Clean separation of concerns

### 4. Why BytesIO for MCP vs Direct Socket for HTTP?

**HTTP REST:**
- Client expects immediate streaming response
- Direct socket writes (`wfile`) for low latency
- Chunked transfer encoding

**MCP/SSE:**
- Multiple messages may be queued before delivery
- Need to buffer complete response before formatting JSON-RPC
- BytesIO allows reading back buffer contents
- SSE delivers when ready

**Trade-off:** MCP adds slight latency (~1-5ms) for buffering, but enables proper JSON-RPC formatting.

### 5. Why Keep mcp_server.py After Protocol Exec?

`mcp_server.py` still handles:
- **Protocol Handshake**: `initialize` method
- **Tool Discovery**: `tools/list` method
- **Tool Generation**: Via `ToolGenerator`
- **Server Lifecycle**: start/stop

Only `tools/call` moved to protocol_exec. The rest is MCP-specific protocol handling.

## Performance

### Latency

**HTTP REST:**
- Validation: <1ms
- Execution: Variable (command-dependent)
- Response: Immediate streaming

**MCP/SSE:**
- Connection setup: ~10-20ms (one-time)
- Message parsing: <1ms
- Execution: Same as HTTP (shared path)
- Response queuing: <1ms
- SSE delivery: ~5-10ms

**Overhead:** ~15-30ms for MCP vs HTTP for same command.

### Memory

**Per HTTP Request:**
- ProcessStat: ~1KB
- I/O buffer: 256KB (configurable)
- Result set: Variable

**Per MCP Connection:**
- SSEConnection: ~1KB
- Message queue: ~10KB (typical)
- BytesIO buffer: 256KB per active tool call

**Scalability:** Hundreds of concurrent connections supported.

### Threading

**HTTP Server:**
- Thread pool: Configurable (default 10-20 threads)
- Each request gets a worker thread

**MCP Server:**
- Keepalive thread: 1 (shared across all connections)
- Message processing: Uses HTTP server thread pool
- Tool execution: Async via thread pool

**No New Threads:** MCP reuses existing http_server thread pool.

## Error Handling

### HTTP Errors

**Format:** HTTP status codes + error message
```
HTTP/1.1 400 Bad Request
Content-Type: text/plain

Missing 'command' attribute in header
```

**Error Codes:**
- 400: Bad request (invalid command, wrong method)
- 500: Internal error (execution failure)

### MCP Errors

**Format:** JSON-RPC error responses
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32603,
    "message": "Internal error: Command failed with code 175",
    "data": {
      "edgelake_code": 175,
      "command": "sql dbname SELECT ...",
      "operator_msg": "Database not found"
    }
  }
}
```

**Error Codes:**
- -32700: Parse error
- -32600: Invalid request
- -32601: Method not found
- -32603: Internal error
- -32602: Invalid params

**EdgeLake Error Codes:** Preserved in `error.data.edgelake_code`

### Connection Errors

**SSE Connection Loss:**
- Detected by `send_keepalive()` failure
- Connection marked as closed
- Session cleaned up after timeout (5 minutes)

**Client Reconnect:**
- Client establishes new SSE connection
- Gets new session ID
- Previous session garbage collected

## Security Considerations

### Authentication

**Current:** No authentication in MCP layer (relies on HTTP server)

**HTTP Server:**
- Can be configured with JWT authentication
- SSL/TLS support via certificates

**MCP Inherits HTTP Security:**
- Same port, same SSL, same auth
- No separate MCP authentication needed

### Authorization

**Tool Access:** Controlled via `enabled_tools` list

**Command Restrictions:**
- HTTP method validation (GET/POST/PUT)
- MCP: No method restrictions

### Input Validation

**Command Injection:** Protected by:
- EdgeLake command parser in `member_cmd.py`
- No shell execution in tool layer
- SQL queries use format=mcp (safe JSON output)

**Path Traversal:** N/A (no file operations in MCP layer)

## Monitoring

### Server Status

**Endpoint (HTTP):** `GET /command?command=get%20mcp%20server`

**Response:**
```json
{
  "version": "2.0.0",
  "protocol": "MCP via SSE",
  "execution_path": "protocol_exec",
  "active_connections": 2,
  "connection_ids": ["uuid1", "uuid2"],
  "enabled_tools": ["query", "node_status", ...],
  "transport": "SSE over http_server.py",
  "tools_count": 15
}
```

### Logging

**Log Levels:**
- ERROR: Failed operations, connection errors
- WARNING: Deprecated features (none currently)
- INFO: Server start/stop, connection events
- DEBUG: Message routing, command execution (disabled in production)

**Key Log Messages:**
```
[INFO] MCP Server initialized (version=2.0.0)
[INFO] SSE connection established: {session_id}
[ERROR] Client disconnected during keepalive: {session_id}
[INFO] SSE connection closed: {session_id}
```

### Metrics

**Available via `get_info()`:**
- Active connections count
- Tool execution count (via EdgeLake metrics)
- Error rates (via EdgeLake error tracking)

## Testing

### Unit Tests

**File:** `test_protocol_exec_integration.py`

Tests:
- Protocol callbacks (HTTP, MCP)
- Command building
- Error handling
- Integration flow

### Integration Tests

**Script:** `mel test-mcp-tools`

Tests:
- SSE connection establishment
- MCP protocol handshake
- Tool listing
- Tool execution (all tools)
- Error scenarios

### Manual Testing

```bash
# Test SSE connection
curl -N http://localhost:32049/mcp/sse

# Test via Claude Code MCP client
# Configure in claude_desktop_config.json
```

## Deployment

### Requirements

- Python 3.11+
- EdgeLake instance running
- HTTP server enabled (port 32049)

### Starting MCP Server

```
AL > run rest server where external_ip = 0.0.0.0 and external_port = 32049
AL > run mcp server
```

### Stopping MCP Server

```
AL > exit mcp server
```

### Configuration

**Enable specific tools:**
```python
from edge_lake.mcp_server import MCPServer

server = MCPServer(
    enabled_tools=['query', 'node_status']
)
```

## Future Enhancements

### Planned

1. **Authentication Layer**
   - MCP-specific API keys
   - Per-tool access control

2. **Rate Limiting**
   - Per-connection limits
   - Per-tool limits

3. **Metrics Dashboard**
   - Real-time connection monitoring
   - Tool usage statistics

4. **Block Transport** (Optional)
   - Handle results >10MB
   - Chunked delivery via message_server

### Possible

1. **WebSocket Transport**
   - Alternative to SSE
   - Full bidirectional in single connection

2. **gRPC Support**
   - For high-performance scenarios
   - Binary protocol

3. **Prompts/Resources**
   - MCP prompts for query templates
   - MCP resources for data access

## Appendix

### File Inventory

**Core Files:**
- `edge_lake/cmd/protocol_exec.py` - Shared execution engine (298 lines)
- `edge_lake/generic/protocol_callbacks.py` - Callback interface (280 lines)
- `edge_lake/cmd/command_execution.py` - EdgeLake core execution (400 lines)

**MCP Files:**
- `edge_lake/mcp_server/mcp_server.py` - MCP protocol server (210 lines)
- `edge_lake/mcp_server/transport/sse_handler.py` - SSE transport (665 lines)
- `edge_lake/mcp_server/transport/protocol_integration.py` - MCP→protocol_exec bridge (207 lines)
- `edge_lake/mcp_server/core/command_builder.py` - Command construction (250 lines)
- `edge_lake/mcp_server/tools/generator.py` - Tool generation (200 lines)
- `edge_lake/mcp_server/config/config.py` - Configuration loader (150 lines)

**HTTP Integration:**
- `edge_lake/tcpip/http_server.py` - Production HTTP server (~3000 lines, 25 lines for al_exec)

**Total:** ~2,700 lines for complete MCP+HTTP integration

### Related Documentation

- **Protocol Callbacks Design:** `PROTOCOL_CALLBACKS_DESIGN.md`
- **SSE/MCP Protocol Guide:** `SSE_MCP_PROTOCOL_GUIDE.md`
- **Integration History:** `AL_EXEC_MCP_INTEGRATION.md`

### Glossary

- **MCP**: Model Context Protocol - Standard protocol for AI agent tool access
- **SSE**: Server-Sent Events - HTTP-based server-to-client streaming
- **JSON-RPC**: JSON Remote Procedure Call - Message format for MCP
- **Protocol Callbacks**: Abstract interface for transport-agnostic execution
- **protocol_exec**: Shared execution function for HTTP and MCP
- **Tool**: MCP concept - Callable function exposed to AI agents
- **EdgeLake Command**: Internal command format (e.g., "get status", "sql dbname ...")

### Version History

- **v1.0** (2025-01-04): Initial MCP implementation with direct_client
- **v2.0** (2025-01-11): Protocol exec integration, dead code removal

---

**Document Maintained By:** EdgeLake MCP Team
**Last Updated:** 2025-01-11
**Status:** Production Ready
