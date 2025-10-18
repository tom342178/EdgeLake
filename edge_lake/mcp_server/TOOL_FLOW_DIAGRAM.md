# MCP Tool Flow - Complete Sequence Diagram

## Example: `list_databases` Tool Execution

This diagram shows the complete flow from an MCP client request to EdgeLake command execution and response.

## Sequence Diagram

```
┌──────────────┐   ┌──────────┐    ┌──────────┐   ┌──────────────┐   ┌─────────────────┐  ┌────────────────────┐   ┌─────────────┐
│Claude Desktop│   │SSE Server│    │MCP Server│   │ToolExecutor  │   │CommandBuilder   │  │EdgeLakeDirectClient│   │member_cmd   │
└──────┬───────┘   └────┬─────┘    └────┬─────┘   └──────┬───────┘   └────────┬────────┘  └─────────┬──────────┘   └──────┬──────┘
       │                │               │                │                    │                     │                     │
       │ 1. HTTP POST   │               │                │                    │                     │                     │
       │ /messages/     │               │                │                    │                     │                     │
       │ {tool: "list_databases"}       │                │                    │                     │                     │
       ├───────────────>│               │                │                    │                     │                     │
       │                │               │                │                    │                     │                     │
       │                │ 2. call_tool()│                │                    │                     │                     │
       │                │  name="list_databases"         │                    │                     │                     │ 
       │                │  arguments={} │                │                    │                     │                     │
       │                ├──────────────>│                │                    │                     │                     │
       │                │               │                │                    │                     │                     │
       │                │               │ 3. execute_tool()                   │                     │                     │
       │                │               │  name="list_databases"              │                     │                     │
       │                │               │  arguments={}  │                    │                     │                     │
       │                │               ├───────────────>│                    │                     │                     │
       │                │               │                │                    │                     │                     │
       │                │               │                │ 4. get_tool_by_name("list_databases")    │                     │
       │                │               │                │ Returns: ToolConfig from tools.yaml      │                     │
       │                │               │                │<──────────────────────────────────────── │                     │
       │                │               │                │                    │                     │                     │
       │                │               │                │ 5. build_command() │                     │                     │
       │                │               │                │  tool_config.edgelake_command            │                     │
       │                │               │                │  arguments={}      │                     │                     │
       │                │               │                ├───────────────────>│                     │                     │
       │                │               │                │                    │                     │                     │
       │                │               │                │  FROM tools.yaml:  │                     │                     │
       │                │               │                │  template: "blockchain get table"        │                     │
       │                │               │                │  parse_response: "extract_databases"     │                     │
       │                │               │                │                    │                     │                     │
       │                │               │                │  Returns:          │                     │                     │
       │                │               │                │  command="blockchain get table"          │                     │
       │                │               │                │  headers=None      │                     │                     │
       │                │               │                │<───────────────────┘                     │                     │
       │                │               │                │                                          │                     │
       │                │               │                │ 6. execute_command()                     │                     │
       │                │               │                │  "blockchain get table"                  │                     │
       │                │               │                ├─────────────────────────────────────────>│                     │
       │                │               │                │                                          │                     │
       │                │               │                │                                          │ 7. process_cmd()    │
       │                │               │                │                                          │  "blockchain get table"
       │                │               │                │                                          ├────────────────────>│
       │                │               │                │                                          │                     │
       │                │               │                │                                          │  Executes:          │
       │                │               │                │                                          │  _blockchain_get()  │
       │                │               │                │                                          │  in member_cmd.py   │
       │                │               │                │                                          │                     │
       │                │               │                │                                          │   Returns raw text: │
       │                │               │                │                                          │  | Database | Table |
       │                │               │                │                                          │  | lsl_demo | ping  |
       │                │               │                │                                          │  | test_db  | data  |
       │                │               │                │                  Result (text)           │<────────────────────┘
       │                │               │                │<─────────────────────────────────────────┤
       │                │               │                │                                          │
       │                │               │                │ 8. _parse_response()                     │
       │                │               │                │  parser_name="extract_databases"         │
       │                │               │                │  result=raw_text                         │
       │                │               │                │                                          │
       │                │               │                │  FROM tools.yaml:                        │
       │                │               │                │  response_parsers:                       │
       │                │               │                │    extract_databases:                    │
       │                │               │                │      type: "blockchain_table"            │
       │                │               │                │      extract: "unique_databases"         │
       │                │               │                │                                          │
       │                │               │                │  Calls:                                  │
       │                │               │                │  _parse_blockchain_table()               │
       │                │               │                │    → client._parse_databases_from_text() │
       │                │               │                │                                          │
       │                │               │                │  Returns parsed:                         │
       │                │               │                │  ["lsl_demo", "test_db"]                 │
       │                │               │                │                                          │
       │                │               │                │ 9. _format_response()                    │
       │                │               │                │  Wraps in MCP format                     │
       │                │               │                │  [{"type":"text","text":"[...]"}]        │
       │                │               │                │                                          │
       │                │               │  Returns MCP formatted result                             │
       │                │               │<───────────────┤                                          │
       │                │               │                │                                          │
       │                │  Returns      │                │                                          │
       │                │  [TextContent]│                │                                          │
       │                │<──────────────┤                │                                          │
       │                │               │                │                                          │
       │  10. SSE       │               │                │                                          │
       │  Response      │               │                │                                          │
       │  {databases:["lsl_demo","test_db"]}             │                                          │
       │<───────────────┤               │                │                                          │
       │                │               │                │                                          │
```

## Detailed Step-by-Step Breakdown

### Step 1: Client Request
**Claude Desktop** sends HTTP POST to SSE server:
```json
POST http://127.0.0.1:50051/messages/
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "list_databases",
    "arguments": {}
  },
  "id": 1
}
```

### Step 2: MCP Server Handler
**server.py** `@self.server.call_tool()` decorator catches the request:
```python
async def call_tool(name: str, arguments: dict):
    logger.info(f"Calling tool '{name}' with arguments: {arguments}")
    result = await self.tool_executor.execute_tool(name, arguments)
    # ... convert to MCP TextContent
```
- **File**: `edge_lake/mcp_server/server.py:150`
- **Purpose**: Route MCP protocol call to tool executor

### Step 3: Tool Executor
**ToolExecutor** looks up tool configuration and orchestrates execution:
```python
async def execute_tool(self, name: str, arguments: Dict) -> List[Dict]:
    # Get tool configuration from config
    tool_config = self.config.get_tool_by_name(name)  # Step 4

    # Build EdgeLake command
    command, headers = self.command_builder.build_command(...)  # Step 5

    # Execute command
    result = await client.execute_command(command, headers)  # Step 6

    # Parse response
    if tool_config.edgelake_command.get('parse_response'):
        result = self._parse_response(result, ...)  # Step 8

    # Format for MCP
    return self._format_response(result)  # Step 9
```
- **File**: `edge_lake/mcp_server/tools/executor.py:36`

### Step 4: Get Tool Configuration
**Config** returns the tool definition from `tools.yaml`:
```python
# From tools.yaml:
{
    'name': 'list_databases',
    'description': 'List all available databases...',
    'edgelake_command': {
        'type': 'blockchain',
        'method': 'get',
        'template': 'blockchain get table',
        'parse_response': 'extract_databases'
    },
    'input_schema': { ... }
}
```
- **File**: `edge_lake/mcp_server/config/tools.yaml:8-18`
- **File**: `edge_lake/mcp_server/config/__init__.py:180`

### Step 5: Build Command
**CommandBuilder** constructs EdgeLake command from template:
```python
def build_command(self, tool_config: Dict, arguments: Dict):
    template = tool_config.get('template')  # "blockchain get table"

    # No placeholders in this template, return as-is
    command = template
    headers = tool_config.get('headers')  # None for this tool

    return (command, headers)
```
- **File**: `edge_lake/mcp_server/core/command_builder.py:25`
- **Template from**: `tools.yaml:13`

### Step 6: Execute Command (Direct Integration)
**EdgeLakeDirectClient** calls member_cmd directly:
```python
async def execute_command(self, command: str, headers: Optional[Dict]):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        self.executor,
        self._sync_execute,
        command,
        headers
    )

def _sync_execute(self, command: str, headers: Optional[Dict]):
    status = self.process_status.ProcessStat()
    io_buff = bytearray(buff_size)

    # Direct call - NO HTTP!
    ret_val = self.member_cmd.process_cmd(
        status,
        command="blockchain get table",  # The command
        print_cmd=False,
        source_ip=None,
        source_port=None,
        io_buffer_in=io_buff
    )

    return self._extract_result(status, io_buff, command)
```
- **File**: `edge_lake/mcp_server/core/direct_client.py:44-76`

### Step 7: EdgeLake Command Execution
**member_cmd.process_cmd()** executes the command:
```python
# In member_cmd.py
def process_cmd(status, command, ...):
    # Parse command: "blockchain get table"
    cmd_words = ["blockchain", "get", "table"]

    # Look up in commands dictionary
    cmd_key = "blockchain get"
    func = commands[cmd_key]['command']  # _blockchain_get

    # Execute
    ret_val = func(status, io_buff, cmd_words, trace)

    # Returns raw text table:
    # | Database | Table    |
    # | lsl_demo | ping     |
    # | lsl_demo | sensor   |
    # | test_db  | data     |
```
- **File**: `edge_lake/cmd/member_cmd.py:~10000+` (process_cmd function)
- **Command function**: `_blockchain_get()` in member_cmd.py

### Step 8: Parse Response
**ToolExecutor** parses the raw EdgeLake response:
```python
def _parse_response(self, result: Any, parser_name: str, arguments: Dict):
    # parser_name = "extract_databases"
    # Get parser config from tools.yaml
    parser_config = self.config.response_parsers.get("extract_databases")
    # {
    #   'type': 'blockchain_table',
    #   'extract': 'unique_databases'
    # }

    # Route to appropriate parser
    if parser_config['type'] == 'blockchain_table':
        return self._parse_blockchain_table(result, parser_config, arguments)

def _parse_blockchain_table(self, result, parser_config, arguments):
    extract = parser_config.get('extract')  # 'unique_databases'

    if extract == 'unique_databases':
        # Extract unique databases from the table
        if isinstance(result, str):
            return self.client._parse_databases_from_text(result)
        # Returns: ["lsl_demo", "test_db"]
```
- **File**: `edge_lake/mcp_server/tools/executor.py:217-280`
- **Parser config from**: `tools.yaml:185-188`

### Step 9: Format Response
**ToolExecutor** wraps in MCP protocol format:
```python
def _format_response(self, result: str) -> List[Dict]:
    return [{
        "type": "text",
        "text": result  # JSON stringified list
    }]
```
- **File**: `edge_lake/mcp_server/tools/executor.py:282`

### Step 10: SSE Response
**SSE Server** sends back to client:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "[\"lsl_demo\", \"test_db\"]"
      }
    ]
  },
  "id": 1
}
```

## Configuration Mapping

### tools.yaml Entry
```yaml
- name: list_databases
  description: "List all available databases in EdgeLake..."
  edgelake_command:
    type: "blockchain"
    method: "get"
    template: "blockchain get table"     # ← Used in Step 5
    parse_response: "extract_databases"  # ← Used in Step 8
  input_schema:
    type: object
    properties: {}
    required: []

response_parsers:
  extract_databases:                     # ← Referenced by parse_response
    type: "blockchain_table"             # ← Parser type
    extract: "unique_databases"          # ← Extraction method
    from_column: 0
```

### How Each Field is Used

| Field | Used By | Purpose |
|-------|---------|---------|
| `name` | ToolExecutor (Step 3) | Tool lookup key |
| `description` | ToolGenerator | MCP tool description shown to Claude |
| `edgelake_command.template` | CommandBuilder (Step 5) | EdgeLake command to execute |
| `edgelake_command.parse_response` | ToolExecutor (Step 8) | Which parser to use |
| `edgelake_command.headers` | CommandBuilder (Step 5) | HTTP headers for EdgeLake REST API |
| `input_schema` | ToolGenerator | MCP tool parameter validation |
| `response_parsers.*` | ToolExecutor (Step 8) | How to parse EdgeLake responses |

## Key Files and Line Numbers

| Component | File | Key Lines |
|-----------|------|-----------|
| Tool Config | `config/tools.yaml` | 8-18 (list_databases) |
| Parser Config | `config/tools.yaml` | 185-188 (extract_databases) |
| SSE Handler | `server.py` | 300-307 (handle_sse) |
| call_tool() | `server.py` | 150-172 |
| execute_tool() | `tools/executor.py` | 36-72 |
| build_command() | `core/command_builder.py` | 25-89 |
| execute_command() | `core/direct_client.py` | 44-76 |
| _parse_response() | `tools/executor.py` | 217-241 |
| _parse_blockchain_table() | `tools/executor.py` | 243-280 |
| _format_response() | `tools/executor.py` | 282-295 |

## Example with Parameters: `query` Tool

For a more complex example with parameters:

### tools.yaml
```yaml
- name: query
  edgelake_command:
    template: 'sql {database} format = {format} "{sql_query}"'
    headers:
      destination: "network"
  input_schema:
    properties:
      database: {type: string}
      table: {type: string}
      limit: {type: integer, default: 100}
```

### Flow
```
1. Client sends: {database: "lsl_demo", table: "ping", limit: 10}
2. QueryBuilder creates SQL: "SELECT * FROM ping LIMIT 10"
3. CommandBuilder substitutes:
   'sql lsl_demo format = json "SELECT * FROM ping LIMIT 10"'
4. DirectClient executes via member_cmd.process_cmd()
5. Returns JSON results (no parsing needed)
6. Wrapped in MCP format
```

## Summary

The `tools.yaml` configuration drives the entire flow:
- **Template** → Command construction
- **parse_response** → Result parsing
- **input_schema** → Parameter validation
- **headers** → EdgeLake API options

This configuration-driven approach means adding new tools is just a matter of adding YAML entries - no code changes needed!
