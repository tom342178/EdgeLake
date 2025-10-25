# MCP Tool Flow - Complete Sequence Diagrams

## Overview

This document shows the current **JSONPath-based configuration-driven architecture** where ALL tools follow a single execution flow:

1. **Load tool configuration** from `tools.yaml`
2. **Build EdgeLake command** from template with parameter substitution
3. **Execute command** via `direct_client.py` → `member_cmd.process_cmd()`
4. **Parse response** using declarative JSONPath expressions (if configured)

**Key Principle**: The executor contains NO tool-specific code. All behavior (command templates, JSONPath extraction, filtering, sorting) is defined in `tools.yaml` and processed generically.

**Architecture Evolution**: Previous versions used `query_interfaces` with tool-specific modules (BlockchainQuery, NodeQuery). These were removed in Phase 2 refactor (commit 9052858) to eliminate intermediate processors. See `ARCHITECTURE_HISTORY.md` for details.

---

## Flow 1: Simple Tool without Response Parsing (`node_status`)

Executes EdgeLake command and returns raw result.

### Sequence Diagram

```
┌──────────────┐   ┌──────────┐    ┌──────────┐   ┌──────────────┐   ┌──────────────────┐  ┌───────────────┐
│Claude Desktop│   │SSE Server│    │MCP Server│   │ToolExecutor  │   │DirectClient      │  │member_cmd     │
└──────┬───────┘   └────┬─────┘    └────┬─────┘   └──────┬───────┘   └────────┬─────────┘  └──────┬────────┘
       │                │               │                │                     │                   │
       │ 1. HTTP POST /messages/        │                │                     │                   │
       │    {tool: "node_status"}       │                │                     │                   │
       ├───────────────>│               │                │                     │                   │
       │                │               │                │                     │                   │
       │                │ 2. call_tool()│                │                     │                   │
       │                ├──────────────>│                │                     │                   │
       │                │               │                │                     │                   │
       │                │               │ 3. execute_tool("node_status", {})  │                   │
       │                │               ├───────────────>│                     │                   │
       │                │               │                │                     │                   │
       │                │               │                │ 4. Get config from tools.yaml           │
       │                │               │                │    type: "get"                          │
       │                │               │                │    template: "get status"               │
       │                │               │                │    NO response_parser                   │
       │                │               │                │                     │                   │
       │                │               │                │ 5. Check cmd_type   │                   │
       │                │               │                │    "internal"? NO   │                   │
       │                │               │                │    → Use EdgeLake command flow          │
       │                │               │                │                     │                   │
       │                │               │                │ 6. build_command()  │                   │
       │                │               │                │    template = "get status"              │
       │                │               │                │    → command = "get status"             │
       │                │               │                │                     │                   │
       │                │               │                │ 7. execute_command()│                   │
       │                │               │                ├────────────────────>│                   │
       │                │               │                │                     │                   │
       │                │               │                │                     │ 8. process_cmd()  │
       │                │               │                │                     ├──────────────────>│
       │                │               │                │                     │                   │
       │                │               │                │                     │  Executes "get status"
       │                │               │                │                     │  Returns JSON     │
       │                │               │                │                     │<──────────────────┤
       │                │               │                │                     │                   │
       │                │               │                │  9. Returns JSON    │                   │
       │                │               │                │<────────────────────┤                   │
       │                │               │                │                     │                   │
       │                │               │                │ 10. NO response_parser configured       │
       │                │               │                │     → Return raw result                 │
       │                │               │                │                     │                   │
       │                │               │                │ 11. _format_response()                  │
       │                │               │                │     (wrap in MCP)   │                   │
       │                │               │                │                     │                   │
       │                │               │  12. Return MCP TextContent          │                   │
       │                │               │<───────────────┤                     │                   │
       │                │               │                │                     │                   │
       │                │  13. SSE Response              │                     │                   │
       │<───────────────┤               │                │                     │                   │
```

### Configuration (tools.yaml)

```yaml
- name: node_status
  description: "Get the status and health information of the EdgeLake node"
  edgelake_command:
    type: "get"
    method: "status"
    template: "get status"
    # NO response_parser - return raw result
  input_schema:
    type: object
    properties: {}
    required: []
```

### Key Code Flow

**1. Executor routes to command execution** (`tools/executor.py:60-67`):
```python
async def execute_tool(self, name: str, arguments: Dict[str, Any]):
    tool_config = self.config.get_tool_by_name(name)
    edgelake_cmd = tool_config.edgelake_command
    cmd_type = edgelake_cmd.get('type')

    if cmd_type == 'internal':
        result = await self._execute_internal(edgelake_cmd, arguments)
    else:
        # All other tools use EdgeLake command execution
        result = await self._execute_edgelake_command(tool_config, arguments, self.client)
```

**2. Direct client executes via member_cmd** (`core/direct_client.py:51-83`):
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

    # Extract JSON from CLI output (handles prompts, debug messages)
    return self._extract_result(status, io_buff, command)
```

---

## Flow 2: Tool with JSONPath Response Parsing (`list_databases`)

Executes EdgeLake command, then uses JSONPath to extract and transform data.

### Sequence Diagram

```
┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────────────┐  ┌────────────────────┐   ┌─────────────┐
│Claude Desktop│   │MCP Server│   │ToolExecutor  │   │CommandBuilder   │  │EdgeLakeDirectClient│   │member_cmd   │
└──────┬───────┘   └────┬─────┘   └──────┬───────┘   └────────┬────────┘  └─────────┬──────────┘   └──────┬──────┘
       │                │                │                    │                     │                     │
       │ 1. call_tool("list_databases", {})                  │                     │                     │
       ├───────────────>│                │                    │                     │                     │
       │                │                │                    │                     │                     │
       │                │ 2. execute_tool()                   │                     │                     │
       │                ├───────────────>│                    │                     │                     │
       │                │                │                    │                     │                     │
       │                │                │ 3. Get config from tools.yaml            │                     │
       │                │                │    type: "get"                           │                     │
       │                │                │    template: "blockchain get table bring.json"                 │
       │                │                │    response_parser:                      │                     │
       │                │                │      type: "jsonpath"                    │                     │
       │                │                │      extract_path: "$[*].table.dbms"                           │
       │                │                │      unique: true                        │                     │
       │                │                │      sort: true                          │                     │
       │                │                │                    │                     │                     │
       │                │                │ 4. build_command() │                     │                     │
       │                │                ├───────────────────>│                     │                     │
       │                │                │                    │                     │                     │
       │                │                │    template: "blockchain get table bring.json"                 │
       │                │                │    arguments: {}   │                     │                     │
       │                │                │    → command = "blockchain get table bring.json"               │
       │                │                │                    │                     │                     │
       │                │                │<───────────────────┤                     │                     │
       │                │                │                    │                     │                     │
       │                │                │ 5. execute_command()                     │                     │
       │                │                ├─────────────────────────────────────────>│                     │
       │                │                │                                          │                     │
       │                │                │                                          │ 6. process_cmd()    │
       │                │                │                                          ├────────────────────>│
       │                │                │                                          │                     │
       │                │                │                                          │  Executes command   │
       │                │                │                                          │  Returns raw JSON   │
       │                │                │                                          │<────────────────────┤
       │                │                │                                          │                     │
       │                │                │  7. Returns parsed JSON (CLI noise removed by direct_client)    │
       │                │                │     [{"table": {"name": "rand_data", "dbms": "new_company"}}, ...]
       │                │                │<─────────────────────────────────────────┤                     │
       │                │                │                                          │                     │
       │                │                │ 8. _parse_response()                     │                     │
       │                │                │    response_parser configured?           │                     │
       │                │                │    YES → parse with JSONPath             │                     │
       │                │                │                                          │                     │
       │                │                │ 9. _parse_with_jsonpath()                │                     │
       │                │                │    Input already parsed (from direct_client)                   │
       │                │                │    Extract: "$[*].table.dbms"            │                     │
       │                │                │    → ["new_company", "test", "new_company"]                    │
       │                │                │                                          │                     │
       │                │                │ 10. Apply transformations (from config): │                     │
       │                │                │     unique: true → ["new_company", "test"]                     │
       │                │                │     sort: true   → ["new_company", "test"]                     │
       │                │                │                                          │                     │
       │                │                │ 11. json.dumps(result)                   │                     │
       │                │                │     → '["new_company", "test"]'          │                     │
       │                │                │                                          │                     │
       │                │                │ 12. _format_response()                   │                     │
       │                │                │                                          │                     │
       │                │  13. Return MCP TextContent                               │                     │
       │                │<───────────────┤                                          │                     │
```

### Configuration (tools.yaml)

```yaml
- name: list_databases
  description: "List all available databases in EdgeLake. Use this to discover what databases are available before querying."
  edgelake_command:
    type: "get"
    method: "blockchain_table"
    template: "blockchain get table bring.json"
    # Inline response parser with JSONPath
    response_parser:
      type: "jsonpath"
      description: "Extract unique database names from blockchain table response"
      extract_path: "$[*].table.dbms"
      unique: true
      sort: true
  input_schema:
    type: object
    properties: {}
    required: []
```

### Key Code Flow

**1. Command execution** (same as Flow 1):
```python
# Build command from template
command, headers = self.command_builder.build_command(edgelake_cmd, arguments)

# Execute via direct client (CLI noise already removed)
result = await client.execute_command(command, headers=headers)
# result = [{"table": {"name": "rand_data", "dbms": "new_company"}}, ...]
# (direct_client extracts JSON array from EdgeLake stdout, removing CLI prompts/debug)
```

**2. Response parsing** (`tools/executor.py:154-165`):
```python
# Parse response based on inline response_parser configuration
response_parser = edgelake_cmd.get('response_parser')
if response_parser:
    result = self._parse_response(result, response_parser, arguments)

# Format result
if isinstance(result, dict):
    return json.dumps(result, indent=2)
elif isinstance(result, list):
    return json.dumps(result, indent=2)
else:
    return str(result)
```

**3. JSONPath extraction** (`tools/executor.py:190-273`):
```python
def _parse_with_jsonpath(self, result: Any, parser_config: Dict[str, Any],
                        arguments: Dict[str, Any]) -> Any:
    """
    Generic JSONPath-based parser.
    All extraction logic is driven by configuration in tools.yaml.
    This method contains NO tool-specific logic.
    """
    # Ensure result is parsed JSON
    if isinstance(result, str):
        result = json.loads(result)

    # Get JSONPath expression from config
    extract_path = parser_config.get('extract_path')
    # "$[*].table.dbms"

    # Parse and apply JSONPath expression
    jsonpath_expr = jsonpath_parse(extract_path)
    matches = jsonpath_expr.find(result)
    extracted = [match.value for match in matches]
    # ["new_company", "test", "new_company"]

    # Apply filtering (if configured)
    if 'filter' in parser_config:
        # ... filter logic

    # Apply field mapping (if configured)
    if 'map' in parser_config:
        # ... map logic

    # Apply uniqueness (if configured)
    if parser_config.get('unique'):
        extracted = list(set(extracted))
        # ["new_company", "test"]

    # Apply sorting (if configured)
    if parser_config.get('sort'):
        extracted = sorted(extracted)

    return extracted
```

---

## Flow 3: Complex Tool with Filtering and Mapping (`list_tables`)

Shows advanced JSONPath features: extraction, filtering, and field mapping.

### Sequence Diagram

```
┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌────────────────────┐
│Claude Desktop│   │MCP Server│   │ToolExecutor  │   │JSONPath Parser     │
└──────┬───────┘   └────┬─────┘   └──────┬───────┘   └─────────┬──────────┘
       │                │                │                     │
       │ 1. call_tool("list_tables", {database: "new_company"})
       ├───────────────>│                │                     │
       │                │                │                     │
       │                │ 2. execute_tool()                    │
       │                ├───────────────>│                     │
       │                │                │                     │
       │                │                │ 3. Get config:      │
       │                │                │    extract_path: "$[*].table"
       │                │                │    filter:          │
       │                │                │      field: "dbms"  │
       │                │                │      source: "argument"
       │                │                │      argument: "database"
       │                │                │    map: "name"      │
       │                │                │                     │
       │                │                │ 4. Execute EdgeLake command
       │                │                │    (same as Flow 2) │
       │                │                │                     │
       │                │                │ 5. Raw JSON from EdgeLake:
       │                │                │    {"table": [      │
       │                │                │      {"table": {"name": "rand_data", "dbms": "new_company"}},
       │                │                │      {"table": {"name": "other", "dbms": "test"}},
       │                │                │      ...            │
       │                │                │    ]}               │
       │                │                │                     │
       │                │                │ 6. _parse_with_jsonpath()
       │                │                ├────────────────────>│
       │                │                │                     │
       │                │                │  7. Extract with JSONPath:
       │                │                │     "$[*].table"
       │                │                │     → [             │
       │                │                │         {"name": "rand_data", "dbms": "new_company"},
       │                │                │         {"name": "other", "dbms": "test"},
       │                │                │         ...         │
       │                │                │       ]             │
       │                │                │                     │
       │                │                │  8. Apply filter:   │
       │                │                │     where dbms == arguments["database"]
       │                │                │     where dbms == "new_company"
       │                │                │     → [             │
       │                │                │         {"name": "rand_data", "dbms": "new_company"}
       │                │                │       ]             │
       │                │                │                     │
       │                │                │  9. Apply map:      │
       │                │                │     extract "name" field
       │                │                │     → ["rand_data"] │
       │                │                │                     │
       │                │                │<────────────────────┤
       │                │                │                     │
       │                │                │ 10. Return ["rand_data"]
       │                │                │                     │
       │                │  11. MCP Response: '["rand_data"]'  │
       │<───────────────┤                │                     │
```

### Configuration (tools.yaml)

```yaml
- name: list_tables
  description: "List all tables in a specific database. Use this to discover what tables are available in a database before querying."
  edgelake_command:
    type: "get"
    method: "blockchain_table"
    template: "blockchain get table bring.json"
    # Advanced JSONPath with filtering and mapping
    response_parser:
      type: "jsonpath"
      description: "Extract table names for a specific database from blockchain table response"
      extract_path: "$[*].table"
      # Filter extracted items by dbms field matching database argument
      filter:
        field: "dbms"
        source: "argument"
        argument: "database"
      # Map to extract only the name field
      map: "name"
  input_schema:
    type: object
    properties:
      database:
        type: string
        description: "Database name to list tables from"
    required: ["database"]
```

### JSONPath Features

**Supported configuration options:**

```yaml
response_parser:
  type: "jsonpath"
  extract_path: "$.path.to.data"   # JSONPath expression (required)

  # Optional transformations (applied in order):
  filter:                           # Filter extracted items
    field: "field_name"             # Field to check
    source: "argument"              # Value source ("argument" or "literal")
    argument: "arg_name"            # Argument name to get value from

  map: "field_name"                 # Extract single field from objects
  unique: true                      # Remove duplicates (set operation)
  sort: true                        # Sort results alphabetically
```

**Execution order:**
1. Extract with JSONPath
2. Apply filter (if configured)
3. Apply map (if configured)
4. Apply unique (if configured)
5. Apply sort (if configured)

---

## Flow 4: Query Tool with SQL Building (`query`)

Shows dynamic SQL query building and network execution.

### Sequence Diagram

```
┌──────────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────────────┐
│Claude Desktop│   │MCP Server│   │ToolExecutor  │   │QueryBuilder     │
└──────┬───────┘   └────┬─────┘   └──────┬───────┘   └────────┬────────┘
       │                │                │                    │
       │ 1. call_tool("query", {database: "new_company", table: "rand_data", limit: 10})
       ├───────────────>│                │                    │
       │                │                │                    │
       │                │ 2. execute_tool()                   │
       │                ├───────────────>│                    │
       │                │                │                    │
       │                │                │ 3. Get config:     │
       │                │                │    build_sql: true │
       │                │                │    headers:        │
       │                │                │      destination: "network"
       │                │                │                    │
       │                │                │ 4. Check build_sql?│
       │                │                │    YES → build SQL query
       │                │                │                    │
       │                │                │ 5. build_sql_query()
       │                │                ├───────────────────>│
       │                │                │                    │
       │                │                │  6. Build SELECT:  │
       │                │                │     SELECT * FROM rand_data
       │                │                │     LIMIT 10       │
       │                │                │                    │
       │                │                │<───────────────────┤
       │                │                │                    │
       │                │                │ 7. Build full command:
       │                │                │    'sql new_company format = json "SELECT * FROM rand_data LIMIT 10"'
       │                │                │                    │
       │                │                │ 8. Check headers:  │
       │                │                │    destination == "network"?
       │                │                │    YES → prefix with "run client ()"
       │                │                │    → 'run client () sql new_company format = json "SELECT * FROM rand_data LIMIT 10"'
       │                │                │                    │
       │                │                │ 9. execute_command()
       │                │                │    (via DirectClient → member_cmd)
       │                │                │                    │
       │                │                │ 10. Raw result:    │
       │                │                │     {"Query": [...rows...], "Statistics": {...}}
       │                │                │                    │
       │                │                │ 11. Parse with JSONPath:
       │                │                │     extract_path: "$.Query"
       │                │                │     → [...rows...]  │
       │                │                │                    │
       │                │  12. Return query results           │
       │<───────────────┤                │                    │
```

### Configuration (tools.yaml)

```yaml
- name: query
  description: "Execute distributed SQL query across EdgeLake network with advanced filtering, grouping, and ordering options"
  edgelake_command:
    type: "sql"
    method: "query"
    build_sql: true                   # Trigger SQL building
    headers:
      destination: "network"          # Prefix with "run client ()"
    # Extract query results from response
    response_parser:
      type: "jsonpath"
      description: "Extract query results from EdgeLake response"
      extract_path: "$.Query"
  input_schema:
    type: object
    properties:
      database:
        type: string
        description: "Database name to query"
      table:
        type: string
        description: "Table name to query"
      select:
        type: array
        items:
          type: string
        description: "Columns to select (default: all columns with *)"
        default: ["*"]
      where:
        type: string
        description: "WHERE clause conditions (e.g., 'is_active = true AND age > 18'). Supports AND/OR operators"
      limit:
        type: integer
        description: "Maximum number of rows to return"
        minimum: 1
        default: 100
    required: ["database", "table"]
```

### SQL Building

**Query builder** (`core/query_builder.py`):
```python
def build_sql_query(self, arguments: Dict[str, Any]) -> str:
    table = arguments['table']
    select = arguments.get('select', ['*'])
    where = arguments.get('where')
    group_by = arguments.get('group_by')
    order_by = arguments.get('order_by')
    limit = arguments.get('limit', 100)

    # Build SELECT clause
    select_clause = ', '.join(select)
    query = f"SELECT {select_clause} FROM {table}"

    # Add WHERE
    if where:
        query += f" WHERE {where}"

    # Add GROUP BY
    if group_by:
        query += f" GROUP BY {', '.join(group_by)}"

    # Add ORDER BY
    if order_by:
        # ... order by logic

    # Add LIMIT
    query += f" LIMIT {limit}"

    return query
```

---

## Architecture Principles

### 1. Configuration-Driven

**ALL tool behavior is in `tools.yaml`:**
- Command templates
- JSONPath expressions
- Data transformations (filter, map, unique, sort)
- Network routing (headers)

**The executor is purely generic:**
- NO tool-specific methods
- NO tool-specific conditionals
- NO hardcoded extraction logic

### 2. Separation of Concerns

| Layer | Responsibility | Examples |
|-------|---------------|----------|
| **tools.yaml** | Define tool behavior | Command templates, JSONPath expressions |
| **executor.py** | Generic execution engine | Route based on `type`, apply parsers |
| **command_builder.py** | Template substitution | Fill `{placeholders}` with argument values |
| **query_builder.py** | SQL query construction | Build SELECT statements from parameters |
| **direct_client.py** | CLI noise extraction | Remove prompts/debug from EdgeLake stdout |
| **JSONPath parser** | Data extraction | Extract/filter/transform JSON declaratively |

### 3. Clean Layering

```
┌─────────────────────────────────────────────┐
│ tools.yaml (configuration)                  │
│ - Command templates                         │
│ - JSONPath expressions                      │
│ - Transformations (filter, map, sort)       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ executor.py (generic dispatcher)            │
│ - Load config                               │
│ - Route by type                             │
│ - Apply parsers                             │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ direct_client.py (EdgeLake integration)     │
│ - Call member_cmd.process_cmd()             │
│ - Extract JSON from CLI output              │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ EdgeLake (member_cmd.py)                    │
│ - Execute commands                          │
│ - Return results                            │
└─────────────────────────────────────────────┘
```

### 4. No Duplication

**CLI noise handling** is in ONE place:
- `direct_client.py` extracts JSON from EdgeLake stdout (handles prompts, debug messages)
- Special handling for blockchain commands: prefers extracting arrays `[...]` over objects `{...}`
- Executor receives clean, parsed JSON (dict/list), applies JSONPath extraction only

**Configuration is inline:**
- Response parsers are inline with each tool definition
- No separate `response_parsers` section
- Related configuration stays together

---

## Adding New Tools

**To add a new tool:**

1. **Edit `config/tools.yaml` ONLY:**
   ```yaml
   - name: new_tool
     description: "Tool description"
     edgelake_command:
       type: "get"
       template: "get something"
       response_parser:           # Optional
         type: "jsonpath"
         extract_path: "$.data"
     input_schema:
       type: object
       properties: {}
   ```

2. **That's it!** No code changes needed.

**❌ DO NOT:**
- Create tool-specific modules (e.g., `core/xyz_query.py`)
- Add tool-specific methods to executor
- Add tool-specific conditionals (`if name == "xyz"`)
- Create separate response parser configurations

**✅ DO:**
- Define everything in `tools.yaml`
- Use JSONPath for data extraction
- Use template placeholders for parameter substitution
- Keep response parser inline with tool definition

---

## Key Files

| File | Purpose | Tool-Specific Code |
|------|---------|-------------------|
| `config/tools.yaml` | **Single source of truth** for ALL tools | N/A (configuration) |
| `tools/executor.py` | Generic execution engine | ❌ ZERO |
| `core/direct_client.py` | EdgeLake integration (CLI noise removal) | ❌ ZERO |
| `core/command_builder.py` | Template substitution | ❌ ZERO |
| `core/query_builder.py` | SQL query building | ❌ ZERO |
| `server.py` | SSE-based MCP server | ❌ ZERO |

---

## Summary

The EdgeLake MCP server uses a **pure JSONPath-based configuration-driven architecture**:

- ✅ `tools.yaml` defines ALL tool behavior (commands + parsing)
- ✅ Executor routes generically based on `type` field
- ✅ JSONPath handles ALL data extraction declaratively
- ✅ Direct client handles CLI noise extraction in ONE place
- ✅ Adding tools requires ONLY configuration changes
- ✅ NO tool-specific code anywhere
- ✅ NO duplication of CLI noise handling

**See Also:**
- `ARCHITECTURE.md` - Detailed design principles
- `ARCHITECTURE_HISTORY.md` - Evolution from intermediate processors to JSONPath
