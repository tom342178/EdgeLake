# MCP Tool Execution Flow - Sequence Diagrams

This document shows the execution flow for MCP tools from client to EdgeLake core.

## Path 1: Standard Tools (list_databases, list_tables, get_schema, node_status, server_info)

```mermaid
sequenceDiagram
    participant Client as MCP Client<br/>(Claude Desktop)
    participant SSE as SSE Transport<br/>(server.py)
    participant Server as MCP Server<br/>(server.py)
    participant Executor as ToolExecutor<br/>(executor.py)
    participant Builder as CommandBuilder<br/>(command_builder.py)
    participant DirectClient as EdgeLakeDirectClient<br/>(direct_client.py)
    participant MemberCmd as member_cmd.py<br/>(EdgeLake Core)

    Client->>SSE: POST /messages/?session_id=xyz<br/>{"method": "tools/call", "params": {"name": "list_databases"}}
    SSE->>Server: handle_call_tool(name, arguments)
    Server->>Executor: execute_tool(name, arguments)

    Note over Executor: Load tool config from tools.yaml

    Executor->>Builder: build_command(edgelake_cmd, arguments)
    Builder-->>Executor: "blockchain get table bring.json"

    Executor->>DirectClient: execute_command(command, headers)

    Note over DirectClient: Capture stdout + io_buff
    DirectClient->>MemberCmd: process_cmd(status, command)
    Note over MemberCmd: Execute EdgeLake command<br/>Populate io_buff or print to stdout
    MemberCmd-->>DirectClient: return_code, result

    DirectClient-->>Executor: result (string or JSON)

    Note over Executor: Apply response_parser if configured<br/>(JSONPath extraction)

    Executor-->>Server: [{"type": "text", "text": result}]
    Server-->>SSE: JSON-RPC response
    SSE-->>Client: SSE message event
```

### Key Points - Standard Tools:

1. **Configuration-Driven**: Tool behavior defined in `tools.yaml`
2. **Generic Path**: All tools use `_execute_edgelake_command()`
3. **Command Building**: `CommandBuilder` fills template from `tools.yaml`
4. **Direct Integration**: `EdgeLakeDirectClient` calls `member_cmd.process_cmd()` directly
5. **Response Parsing**: JSONPath extraction applied per `tools.yaml` config

### Example Tool Configuration (list_databases):
```yaml
- name: list_databases
  description: "List all available databases"
  edgelake_command:
    type: "get"
    method: "blockchain_table"
    template: "blockchain get table bring.json"
    response_parser:
      type: "jsonpath"
      extract_path: "$[*].table.dbms"
      unique: true
      sort: true
```

---

## Path 2: Query Tool (Distributed SQL Queries)

```mermaid
sequenceDiagram
    participant Client as MCP Client<br/>(Claude Desktop)
    participant SSE as SSE Transport<br/>(server.py)
    participant Server as MCP Server<br/>(server.py)
    participant Executor as ToolExecutor<br/>(executor.py)
    participant QueryBuilder as QueryBuilder<br/>(query_builder.py)
    participant QueryExecutor as QueryExecutor<br/>(query_executor.py)
    participant DirectClient as EdgeLakeDirectClient<br/>(direct_client.py)
    participant MemberCmd as member_cmd.py<br/>(EdgeLake Core)

    Client->>SSE: POST /messages/?session_id=xyz<br/>{"method": "tools/call", "params": {"name": "query", ...}}
    SSE->>Server: handle_call_tool("query", arguments)
    Server->>Executor: execute_tool("query", arguments)

    Note over Executor: Check tool type = "sql"<br/>Check headers.destination = "network"

    alt Network Query (Distributed)
        Note over Executor: Route to standard command path
        Executor->>QueryBuilder: build_sql_query(arguments)
        QueryBuilder-->>Executor: "SELECT * FROM sensors LIMIT 100"

        Note over Executor: Build full command
        Executor->>Executor: command = 'run client () sql {db} format=json "{sql}"'

        Executor->>DirectClient: execute_command(command, headers)
        DirectClient->>MemberCmd: process_cmd(status, "run client () sql ...")

        Note over MemberCmd: Distribute query to network<br/>Execute on operator nodes<br/>Consolidate results (MapReduce)

        MemberCmd-->>DirectClient: {"Query": [{row1}, {row2}, ...]}
        DirectClient-->>Executor: result

        Note over Executor: Apply JSONPath: $.Query[*]
        Executor-->>Server: [{"type": "text", "text": "[{...}, {...}]"}]

    else Local Query (Single Node)
        Note over Executor: Route to QueryExecutor
        Executor->>QueryBuilder: build_sql_query(arguments)
        QueryBuilder-->>Executor: "SELECT * FROM sensors LIMIT 100"

        Executor->>QueryExecutor: execute_query(dbms_name, sql_query, mode="batch")

        Note over QueryExecutor: Validate SQL with select_parser()
        QueryExecutor->>QueryExecutor: select_parser(status, sql_query, ...)

        Note over QueryExecutor: Execute via member_cmd
        QueryExecutor->>DirectClient: execute_command(f'sql {db} format=json "{sql}"')
        DirectClient->>MemberCmd: process_cmd(status, "sql ...")

        MemberCmd-->>DirectClient: {"Query": [{row1}, {row2}, ...]}
        DirectClient-->>QueryExecutor: result

        QueryExecutor-->>Executor: {"rows": [...], "total_rows": N}

        Note over Executor: Extract rows, apply JSONPath
        Executor-->>Server: [{"type": "text", "text": "[{...}, {...}]"}]
    end

    Server-->>SSE: JSON-RPC response
    SSE-->>Client: SSE message event
```

### Key Points - Query Tool:

1. **Dual Path**:
   - **Network Queries**: `destination: network` → Standard command path with `run client ()`
   - **Local Queries**: No network destination → QueryExecutor for validation + streaming

2. **Network Query Flow** (Most Common):
   - Uses `run client ()` wrapper for distributed execution
   - No local database connectivity required
   - Results consolidated by EdgeLake's query node
   - Supports MapReduce-style aggregation

3. **Local Query Flow** (Rare):
   - Validates SQL via `select_parser()` first
   - Requires local database connection
   - Used for single-node queries only

4. **SQL Building**: `QueryBuilder` constructs SQL from:
   - `select`: Column list
   - `where`: Filter conditions
   - `group_by`: Grouping columns
   - `order_by`: Sorting
   - `limit`: Row limit

### Query Tool Configuration:
```yaml
- name: query
  description: "Execute distributed SQL query"
  edgelake_command:
    type: "sql"
    method: "query"
    build_sql: true
    headers:
      destination: "network"  # Routes to network
    response_parser:
      type: "jsonpath"
      extract_path: "$.Query[*]"
```

---

## Comparison: Standard Tools vs Query Tool

| Aspect | Standard Tools | Query Tool |
|--------|---------------|------------|
| **Execution Path** | Always `_execute_edgelake_command()` | Checks `destination: network` |
| **Command Building** | `CommandBuilder` (template fill) | `QueryBuilder` (SQL construction) |
| **EdgeLake Command** | Direct (e.g., `blockchain get table`) | Wrapped with `run client ()` for network |
| **Validation** | None (EdgeLake handles) | Optional via `select_parser()` (local only) |
| **Database Required** | No | No (for network), Yes (for local) |
| **Response Format** | Varies by command | Always `{"Query": [...]}` |
| **JSONPath Parsing** | Tool-specific paths | `$.Query[*]` extraction |

---

## First Level in Non-MCP Code: member_cmd.py

Both paths converge at `edge_lake/cmd/member_cmd.py`:

```python
def process_cmd(status: ProcessStat, command: str, ...) -> int:
    """
    Main command processor for EdgeLake.

    This is the entry point from MCP server's EdgeLakeDirectClient.

    Flow:
    1. Parse command string
    2. Look up command in commands dict
    3. Execute command function
    4. Populate io_buff or print to stdout
    5. Return status code
    """
```

### Commands Called by MCP Tools:

| MCP Tool | EdgeLake Command | Command Function |
|----------|------------------|------------------|
| `list_databases` | `blockchain get table` | `_blockchain_get()` |
| `list_tables` | `blockchain get table` | `_blockchain_get()` |
| `get_schema` | `get columns where ...` | `_get_columns()` |
| `node_status` | `get status` | `_get_status()` |
| `query` (network) | `run client () sql ...` | `_run_client()` → `_sql_parse()` |
| `query` (local) | `sql {db} format=json "..."` | `_sql_parse()` |

---

## Architecture Principles Enforced:

✅ **All tool behavior in tools.yaml** - No hardcoded tool logic
✅ **Generic handlers only** - Executor has NO tool-specific methods
✅ **Direct integration** - No HTTP overhead in embedded mode
✅ **Configuration-driven parsing** - JSONPath defined in tools.yaml
✅ **Single source of truth** - EdgeLake's member_cmd.py

---

## Reference Files:

- **Tool Definitions**: `edge_lake/mcp_server/config/tools.yaml`
- **Executor**: `edge_lake/mcp_server/tools/executor.py`
- **Command Builder**: `edge_lake/mcp_server/core/command_builder.py`
- **Query Builder**: `edge_lake/mcp_server/core/query_builder.py`
- **Query Executor**: `edge_lake/mcp_server/core/query_executor.py`
- **Direct Client**: `edge_lake/mcp_server/core/direct_client.py`
- **EdgeLake Core**: `edge_lake/cmd/member_cmd.py`
