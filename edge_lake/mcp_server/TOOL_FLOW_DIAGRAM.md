# MCP Tool Flow - Complete Sequence Diagrams

## Overview

This document shows two types of tool execution flows based on the **configuration-driven architecture**:

1. **Query Interface Flow** (e.g., `list_databases`, `node_status`) - Direct Python API access via `query_interfaces`
2. **Command Flow** (e.g., `query`, `get_schema`) - EdgeLake command execution via `member_cmd.process_cmd()`

**Key Principle**: The executor contains NO tool-specific code. All behavior is defined in `tools.yaml` and routed generically.

---

## Flow 1: Query Interface (`list_databases`)

Direct Python API access - bypasses command parsing.

### Sequence Diagram

```
┌──────────────┐   ┌──────────┐    ┌──────────┐   ┌──────────────┐   ┌──────────────────┐  ┌───────────────────┐
│Claude Desktop│   │SSE Server│    │MCP Server│   │ToolExecutor  │   │BlockchainQuery   │  │metadata module    │
└──────┬───────┘   └────┬─────┘    └────┬─────┘   └──────┬───────┘   └────────┬─────────┘  └─────────┬─────────┘
       │                │               │                │                     │                       │
       │ 1. HTTP POST /messages/        │                │                     │                       │
       │    {tool: "list_databases"}    │                │                     │                       │
       ├───────────────>│               │                │                     │                       │
       │                │               │                │                     │                       │
       │                │ 2. call_tool()│                │                     │                       │
       │                ├──────────────>│                │                     │                       │
       │                │               │                │                     │                       │
       │                │               │ 3. execute_tool("list_databases", {})│                       │
       │                │               ├───────────────>│                     │                       │
       │                │               │                │                     │                       │
       │                │               │                │ 4. Get config from tools.yaml               │
       │                │               │                │    type: "blockchain_query"                 │
       │                │               │                │    query_type: "get_all_databases"          │
       │                │               │                │                     │                       │
       │                │               │                │ 5. Check: type in query_interfaces?         │
       │                │               │                │    → YES: "blockchain_query" registered     │
       │                │               │                │                     │                       │
       │                │               │                │ 6. _execute_query_interface()               │
       │                │               │                │    (GENERIC METHOD)│                       │
       │                │               │                ├────────────────────>│                       │
       │                │               │                │                     │                       │
       │                │               │                │                     │ 7. execute_query()    │
       │                │               │                │                     │    query_type=        │
       │                │               │                │                     │    "get_all_databases"│
       │                │               │                │                     │                       │
       │                │               │                │                     │ 8. get_all_databases()│
       │                │               │                │                     ├──────────────────────>│
       │                │               │                │                     │                       │
       │                │               │                │                     │  Direct access:       │
       │                │               │                │                     │  table_to_cluster_    │
       │                │               │                │                     │  {company:{dbms:{}}}  │
       │                │               │                │                     │                       │
       │                │               │                │                     │  Returns:             │
       │                │               │                │                     │  ["new_company"]      │
       │                │               │                │                     │<──────────────────────┤
       │                │               │                │                     │                       │
       │                │               │                │  9. json.dumps()    │                       │
       │                │               │                │<────────────────────┤                       │
       │                │               │                │                     │                       │
       │                │               │                │ 10. _format_response()                      │
       │                │               │                │     (wrap in MCP)   │                       │
       │                │               │                │                     │                       │
       │                │               │  11. Return MCP TextContent          │                       │
       │                │               │<───────────────┤                     │                       │
       │                │               │                │                     │                       │
       │                │  12. SSE Response              │                     │                       │
       │<───────────────┤               │                │                     │                       │
```

### Configuration (tools.yaml)

```yaml
- name: list_databases
  edgelake_command:
    type: "blockchain_query"           # ← Routes to query_interfaces['blockchain_query']
    query_type: "get_all_databases"    # ← Passed to BlockchainQuery.execute_query()
  input_schema:
    type: object
    properties: {}
    required: []
```

### Key Code Flow

**1. Executor routes generically** (`tools/executor.py:70-72`):
```python
if cmd_type in self.query_interfaces:
    # Generic routing - NO tool-specific code!
    result = await self._execute_query_interface(cmd_type, edgelake_cmd, arguments)
```

**2. Query interface executes** (`tools/executor.py:104-140`):
```python
async def _execute_query_interface(self, interface_type: str, edgelake_cmd, arguments):
    query_type = edgelake_cmd.get('query_type')  # "get_all_databases"

    # Get registered interface
    query_interface = self.query_interfaces[interface_type]  # BlockchainQuery()

    # Execute generically
    result = query_interface.execute_query(query_type, **params)
    return json.dumps(result, indent=2)
```

**3. Blockchain query accesses Python API** (`core/blockchain_query.py:31-50`):
```python
def get_all_databases(self) -> List[str]:
    databases = set()
    table_to_cluster = self.metadata.table_to_cluster_  # Direct Python access!

    for company, dbms_dict in table_to_cluster.items():
        for dbms in dbms_dict.keys():
            databases.add(dbms)

    return sorted(list(databases))
```

### Why This Approach?

Commands like `blockchain get table` print to stdout instead of populating `io_buff`. Direct Python API access bypasses this limitation.

---

## Flow 2: Command Execution (`query`)

EdgeLake command execution via `member_cmd.process_cmd()`.

### Sequence Diagram

```
┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────────────┐  ┌────────────────────┐   ┌─────────────┐
│Claude Desktop│   │MCP Server│   │ToolExecutor  │   │CommandBuilder   │  │EdgeLakeDirectClient│   │member_cmd   │
└──────┬───────┘   └────┬─────┘   └──────┬───────┘   └────────┬────────┘  └─────────┬──────────┘   └──────┬──────┘
       │                │                │                    │                     │                     │
       │ 1. call_tool("query", {database, table, limit})     │                     │                     │
       ├───────────────>│                │                    │                     │                     │
       │                │                │                    │                     │                     │
       │                │ 2. execute_tool()                   │                     │                     │
       │                ├───────────────>│                    │                     │                     │
       │                │                │                    │                     │                     │
       │                │                │ 3. Get config:     │                     │                     │
       │                │                │    type: "sql"     │                     │                     │
       │                │                │    template: "sql {database}..."         │                     │
       │                │                │                    │                     │                     │
       │                │                │ 4. build_command() │                     │                     │
       │                │                ├───────────────────>│                     │                     │
       │                │                │                    │                     │                     │
       │                │                │    Substitutes placeholders:             │                     │
       │                │                │    sql {database} format={format} "{sql_query}"                │
       │                │                │    → sql new_company format=json "SELECT * FROM rand_data LIMIT 10"
       │                │                │                    │                     │                     │
       │                │                │<───────────────────┤                     │                     │
       │                │                │                    │                     │                     │
       │                │                │ 5. execute_command()                     │                     │
       │                │                ├─────────────────────────────────────────>│                     │
       │                │                │                                          │                     │
       │                │                │                                          │ 6. process_cmd()    │
       │                │                │                                          ├────────────────────>│
       │                │                │                                          │                     │
       │                │                │                                          │  Executes SQL       │
       │                │                │                                          │  Returns JSON       │
       │                │                │                                          │<────────────────────┤
       │                │                │                                          │                     │
       │                │                │  7. Returns JSON result                  │                     │
       │                │                │<─────────────────────────────────────────┤                     │
       │                │                │                                          │                     │
       │                │                │ 8. _format_response()                    │                     │
       │                │                │                                          │                     │
       │                │  9. Return MCP TextContent                                │                     │
       │                │<───────────────┤                                          │                     │
```

### Configuration (tools.yaml)

```yaml
- name: query
  edgelake_command:
    type: "sql"                        # ← Not in query_interfaces, uses command flow
    template: 'sql {database} format = {format} "{sql_query}"'
    headers:
      destination: "network"
  input_schema:
    properties:
      database: {type: string}
      table: {type: string}
      limit: {type: integer, default: 100}
    required: ["database", "table"]
```

### Key Code Flow

**1. Executor routes to command execution** (`tools/executor.py:73-75`):
```python
else:
    # Not a query interface - use command execution
    result = await self._execute_edgelake_command(tool_config, arguments, self.client)
```

**2. Command builder substitutes template** (`core/command_builder.py:25-58`):
```python
def build_command(self, edgelake_command, arguments):
    template = edgelake_command.get('template')
    # 'sql {database} format = {format} "{sql_query}"'

    # Replace placeholders
    command = self._fill_template(template, arguments)
    # → 'sql new_company format = json "SELECT * FROM rand_data LIMIT 10"'

    headers = edgelake_command.get('headers')
    return command, headers
```

**3. Direct client executes via member_cmd** (`core/direct_client.py:51-83`):
```python
async def execute_command(self, command: str, headers):
    return await loop.run_in_executor(
        self.executor,
        self._sync_execute,
        command,
        headers
    )

def _sync_execute(self, command, headers):
    status = self.process_status.ProcessStat()
    io_buff = bytearray(buff_size)

    # Direct call to EdgeLake
    ret_val = self.member_cmd.process_cmd(
        status,
        command=command,
        io_buffer_in=io_buff
    )

    return self._extract_result(status, io_buff, command)
```

---

## Architecture Comparison

| Aspect | Query Interface Flow | Command Flow |
|--------|---------------------|--------------|
| **Example Tools** | `list_databases`, `node_status` | `query`, `get_schema` |
| **Configuration Type** | `type: "blockchain_query"` or `"node_query"` | `type: "sql"`, `"get"`, etc. |
| **Execution Path** | Direct Python API (e.g., `metadata.table_to_cluster_`) | `member_cmd.process_cmd()` |
| **Why Used** | Commands that print to stdout instead of io_buff | Commands that properly populate io_buff |
| **Extensibility** | Add to `query_interfaces` dict | Uses existing command system |
| **Code Location** | `core/blockchain_query.py`, `core/node_query.py` | `core/direct_client.py` |

---

## Configuration-Driven Design

**Critical Principle**: The executor (`tools/executor.py`) contains **ZERO tool-specific code**.

### Generic Routing

```python
# In tools/executor.py __init__
self.query_interfaces = {
    'blockchain_query': BlockchainQuery(),
    'node_query': NodeQuery()
}

# In execute_tool()
if cmd_type in self.query_interfaces:
    # Generic - works for ANY query type!
    result = await self._execute_query_interface(cmd_type, edgelake_cmd, arguments)
else:
    # Generic - works for ANY command type!
    result = await self._execute_edgelake_command(tool_config, arguments, self.client)
```

### Adding New Tools

**To add a new query type** (e.g., `metrics_query`):

1. Create `core/metrics_query.py`:
```python
class MetricsQuery:
    def execute_query(self, query_type: str, **kwargs):
        # Implementation
```

2. Register in `tools/executor.py`:
```python
self.query_interfaces = {
    'blockchain_query': BlockchainQuery(),
    'node_query': NodeQuery(),
    'metrics_query': MetricsQuery()  # Just add here!
}
```

3. Define in `config/tools.yaml`:
```yaml
- name: get_metrics
  edgelake_command:
    type: "metrics_query"
    query_type: "get_system_metrics"
```

**NO changes to executor logic needed** - it routes automatically!

---

## Key Files

| File | Purpose | Lines |
|------|---------|-------|
| `config/tools.yaml` | **Single source of truth** for all tool definitions | All tools |
| `tools/executor.py` | Generic tool execution engine (NO tool-specific code) | 40-180 |
| `core/blockchain_query.py` | Direct Python API access to blockchain metadata | 31-134 |
| `core/node_query.py` | Direct Python API access to node information | 31-74 |
| `core/direct_client.py` | Direct `member_cmd.process_cmd()` integration | 51-186 |
| `core/command_builder.py` | Template substitution for commands | 25-157 |
| `server.py` | SSE-based MCP server entry point | 300-400 |

---

## Summary

The EdgeLake MCP server uses a **pure configuration-driven architecture**:

- ✅ `tools.yaml` defines ALL tool behavior
- ✅ Executor routes generically based on `type` field
- ✅ Query interfaces provide direct Python API access
- ✅ Command flow uses EdgeLake's existing command system
- ✅ Adding tools requires only configuration changes
- ✅ NO tool-specific code in executor

**See Also**: `ARCHITECTURE.md` for detailed design principles
