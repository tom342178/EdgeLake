# EdgeLake MCP Server

Configuration-driven MCP (Model Context Protocol) server for EdgeLake distributed database.

## Architecture

This implementation uses a **configuration-driven approach** where tools are defined in YAML files and dynamically generated at runtime. The system integrates with `member_cmd.py` to leverage EdgeLake's command structure.

### Key Components

1. **Configuration System** (`config/`)
   - `tools.yaml` - Defines MCP tools based on EdgeLake commands
   - `nodes.yaml` - Defines EdgeLake nodes with multi-node support
   - `__init__.py` - Configuration loader and manager

2. **Core Engine** (`core/`)
   - Command builder (integrates with `member_cmd.py`)
   - EdgeLake client (HTTP/REST communication)
   - Query builder (SQL query construction)

3. **Tools System** (`tools/`)
   - Dynamic tool generator from configuration
   - Tool executor and response formatter

4. **Server Modes**
   - **Standalone**: Runs as independent MCP server (stdio)
   - **Threaded**: Runs within EdgeLake node as background thread

## Configuration

### Tools Configuration (`config/tools.yaml`)

Each tool is defined with:
- `name`: Tool identifier
- `description`: What the tool does
- `edgelake_command`: How to execute via EdgeLake
  - `type`: Command type (blockchain, sql, get, info)
  - `method`: Command method  
  - `template`: Command template with {placeholders}
  - `parse_response`: How to parse EdgeLake response
- `input_schema`: JSON Schema for tool parameters

Example:
```yaml
- name: list_databases
  description: "List all available databases"
  edgelake_command:
    type: "blockchain"
    method: "get"
    template: "blockchain get table"
    parse_response: "extract_databases"
  input_schema:
    type: object
    properties: {}
    required: []
```

### Nodes Configuration (`config/nodes.yaml`)

Defines EdgeLake nodes that can be connected to:
```yaml
nodes:
  - name: "local"
    description: "Local EdgeLake node"
    host: "127.0.0.1"
    port: 32049
    is_default: true
    
  - name: "production-query"
    description: "Production Query Node"
    host: "10.0.0.25"
    port: 32049
    is_default: false
```

Client configuration:
```yaml
client:
  allow_custom_nodes: true
  custom_node_hint: "You can specify custom nodes..."
  request_timeout: 20
  max_workers: 10
```

## Integration with member_cmd.py

The system integrates with EdgeLake's command structure from `member_cmd.py`:

1. **Command Dictionary**: Tools reference commands defined in `commands` dict
2. **Methods**: Tools can reference `_*_methods` dictionaries for sub-commands
3. **Help Text**: Automatically uses help/usage information from commands
4. **Parameter Validation**: Uses command parameter definitions

## Environment Variables

Override configuration at runtime:
- `EDGELAKE_DEFAULT_NODE` - Set default node by name
- `EDGELAKE_HOST` - Override default node host
- `EDGELAKE_PORT` - Override default node port  
- `EDGELAKE_TIMEOUT` - Request timeout (seconds)
- `EDGELAKE_MAX_WORKERS` - Max concurrent workers

## Usage

### Standalone Mode
```python
from edge_lake.mcp_server import MCPServer

server = MCPServer(mode="standalone")
server.run()
```

### Threaded Mode (within EdgeLake)
```python
from edge_lake.mcp_server import MCPServer
import threading

server = MCPServer(mode="threaded")
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
```

## Implemented Tools

Based on `config/tools.yaml`:

1. **list_databases** - Discover available databases
2. **list_tables** - List tables in a database
3. **get_schema** - Get table column definitions
4. **query** - Execute SQL queries with filtering/grouping/ordering
5. **node_status** - Get EdgeLake node health/status
6. **server_info** - Get MCP server version and config
7. **blockchain_get** - Query blockchain/metadata policies
8. **info_table** - Get detailed table information

## Custom Nodes at Runtime

When `allow_custom_nodes: true`, users can specify custom EdgeLake nodes:

```python
# Via tool parameters
result = await call_tool("query", {
    "node_host": "192.168.1.100",
    "node_port": 32049,
    "database": "mydb",
    "table": "mytable"
})
```

## Response Parsing

The system includes parsers for EdgeLake response formats:
- `extract_databases` - Parse unique databases from `blockchain get table`
- `extract_tables` - Parse tables for specific database
- JSON formatting
- Table formatting

## Next Steps

To complete the implementation:

1. **Implement Core Engine**:
   - `core/client.py` - EdgeLake HTTP client
   - `core/command_builder.py` - Build commands from templates
   - `core/query_builder.py` - SQL query construction

2. **Implement Tools System**:
   - `tools/generator.py` - Generate MCP tools from config
   - `tools/executor.py` - Execute tools and format responses

3. **Implement Server**:
   - `server.py` - Main MCP server with stdio/threaded modes
   - Protocol handlers (list_tools, call_tool, list_resources, read_resource)

4. **Add Startup Scripts**:
   - `scripts/start_standalone.py`
   - `scripts/start_threaded.py`
   - Integration with EdgeLake startup

5. **Testing**:
   - Unit tests for each component
   - Integration tests with EdgeLake
   - End-to-end MCP protocol tests

## Benefits of This Approach

1. **Configuration-Driven**: Add new tools by editing YAML, no code changes
2. **member_cmd.py Integration**: Leverages existing EdgeLake command structure
3. **Multi-Node Support**: Connect to different EdgeLake nodes
4. **Flexible Deployment**: Standalone or embedded in EdgeLake
5. **Runtime Customization**: Environment variables and custom nodes
6. **Maintainability**: Centralized tool definitions
7. **Extensibility**: Easy to add new response parsers and command types

## License

Mozilla Public License 2.0
