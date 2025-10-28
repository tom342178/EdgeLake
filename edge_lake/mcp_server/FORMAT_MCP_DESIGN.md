# format=mcp Design Decision

## Overview

This document describes the design decision to add `format=mcp` to EdgeLake's existing format options (`format=json`, `format=table`). This approach simplifies the MCP server architecture and enables future streaming capabilities.

## Problem Statement

Currently, the MCP server performs complex response processing:

1. **EdgeLake returns** wrapped data:
   ```json
   {"Query": [{"temp": 20}, {"temp": 21}]}
   ```

2. **MCP extracts** with JSONPath (`$.Query[*]`):
   ```json
   [{"temp": 20}, {"temp": 21}]
   ```

3. **MCP re-wraps** for protocol:
   ```json
   [{"type": "text", "text": "[{\"temp\": 20}, {\"temp\": 21}]"}]
   ```

**Issues:**
- Complex JSONPath parsing logic in MCP server
- Tool-specific extraction rules in `tools.yaml`
- Difficult to stream (extraction happens after all data collected)
- Duplicates logic (EdgeLake already has format handling)

## Solution: format=mcp

Add a new format option to EdgeLake that returns **clean, extracted data** ready for MCP consumption.

### Design Principles

**Option A (CHOSEN)**: `format=mcp` returns extracted data only
- EdgeLake: Returns clean data (no wrappers, no metadata)
- MCP: Adds protocol wrapper (`[{"type": "text", "text": "..."}]`)

**Option B (REJECTED)**: `format=mcp` returns full MCP response structure
- EdgeLake: Returns MCP-specific format (`[{"type": "text", ...}]`)
- MCP: Passes through directly
- **Rejected because**: Couples EdgeLake to MCP protocol, breaks streaming

### Why Option A?

#### 1. Separation of Concerns
- **EdgeLake**: Formats data (database → presentation)
- **MCP Server**: Wraps for protocol (presentation → MCP)

#### 2. Protocol Agnostic
EdgeLake remains independent of MCP:
- `format=json` → Full JSON with metadata
- `format=table` → Human-readable text table
- `format=mcp` → Clean data (no wrappers)
- Future: `format=graphql`, `format=grpc`, etc.

#### 3. Streaming Compatible (Critical!)
**Current (Batch Only):**
```python
# EdgeLake collects all rows
result = {"Query": [row1, row2, ..., row1000]}

# MCP extracts
rows = jsonpath(result, "$.Query[*]")  # All 1000 rows in memory

# MCP responds
return [{"type": "text", "text": json.dumps(rows)}]
```

**Future (Streaming with format=mcp):**
```python
# EdgeLake yields batches
async for batch in stream_query(sql, format="mcp"):
    # batch = [row1, row2, ..., row100]  (clean data)

    # MCP wraps and sends immediately
    mcp_response = [{"type": "text", "text": json.dumps(batch)}]
    yield mcp_response
```

**Key Benefits:**
- ✅ EdgeLake yields raw data batches
- ✅ MCP wraps each batch as it arrives
- ✅ No protocol knowledge in EdgeLake
- ✅ Constant memory usage (only 1 batch in memory)

#### 4. Backwards Compatible
- Existing `format=json` unchanged
- `format=mcp` is additive (opt-in)
- No breaking changes

## Implementation Strategy

### Phase 1: Add format=mcp to EdgeLake Core (Current)

**Location**: `edge_lake/cmd/member_cmd.py`

**Example - Query Results:**

```python
# Current behavior (format=json):
def format_query_response(rows, columns, format_type):
    if format_type == "json":
        return {"Query": rows}  # Wrapped
    elif format_type == "table":
        return format_as_table(rows, columns)  # Text table
    elif format_type == "mcp":
        return rows  # Clean data (NEW!)
```

**Example - Blockchain Get Table:**

```python
# Current (format=json):
# Returns: [{"table": {"dbms": "demo", "name": "sensors"}}, ...]

# New (format=mcp with extraction):
# Returns: ["demo"]  (just unique database names)
```

**Configuration in tools.yaml:**
```yaml
- name: list_databases
  edgelake_command:
    template: "blockchain get table bring.json and format=mcp"
    # Optionally specify extraction hint in template:
    # template: "blockchain get table bring.json and format=mcp and extract=dbms"
```

### Phase 2: Simplify MCP Server

**Remove from MCP:**
- ❌ JSONPath parsing logic
- ❌ Tool-specific extraction rules
- ❌ Response parsers in `tools.yaml`

**Keep in MCP:**
- ✅ Protocol wrapping (`[{"type": "text", "text": "..."}]`)
- ✅ Error handling
- ✅ Command building

**Before:**
```python
# MCP executor.py
result = execute_edgelake_command("blockchain get table")
# result = [{"table": {"dbms": "demo"}}, ...]

parsed = jsonpath(result, "$[*].table.dbms")  # Complex extraction
unique = list(set(parsed))  # Deduplication
sorted_result = sorted(unique)  # Sorting

return [{"type": "text", "text": json.dumps(sorted_result)}]
```

**After:**
```python
# MCP executor.py
result = execute_edgelake_command("blockchain get table and format=mcp")
# result = ["demo"]  (already extracted, unique, sorted!)

return [{"type": "text", "text": result}]  # Just wrap
```

### Phase 3: Enable Streaming (Future)

**EdgeLake Core:**
```python
# edge_lake/cmd/member_cmd.py

async def stream_query_results(status, dbms, sql, format_type="mcp"):
    """
    Stream query results in batches.

    Args:
        format_type: "json" | "table" | "mcp"

    Yields:
        Batches of rows (format depends on format_type)
    """
    cursor = set_cursor(status, dbms)
    execute_sql(cursor, sql)

    while True:
        get_next, rows_data = process_fetch_rows(cursor, fetch_size=100)

        if format_type == "json":
            # Traditional format with metadata
            yield {"Query": json.loads(rows_data)["Query"]}
        elif format_type == "mcp":
            # Clean data for streaming
            yield json.loads(rows_data)["Query"]  # Just the rows

        if not get_next:
            break

    close_cursor(cursor)
```

**MCP Server:**
```python
# edge_lake/mcp_server/tools/executor.py

async def execute_streaming_query(name, arguments):
    """Execute query with streaming results."""

    sql = build_sql_query(arguments)

    # Stream from EdgeLake
    async for batch in edgelake.stream_query(
        dbms=arguments['database'],
        sql=sql,
        format="mcp"  # Clean data batches
    ):
        # batch = [{"temp": 20}, {"temp": 21}, ...]  (100 rows)

        # Wrap for MCP protocol
        mcp_response = [{
            "type": "text",
            "text": json.dumps(batch)
        }]

        # Send to client immediately
        yield mcp_response
```

## Format Comparison

| Format | Use Case | Output Example | Streaming |
|--------|----------|----------------|-----------|
| `format=json` | REST API, traditional clients | `{"Query": [{...}]}` | Possible (batched) |
| `format=table` | CLI, human viewing | `┌────┬────┐`<br/>`│ temp │ ...│` | No (needs full data) |
| `format=mcp` | MCP protocol, streaming | `[{...}, {...}]` | **Optimized!** |

## Examples

### Example 1: List Databases

**Current (complex):**
```bash
# EdgeLake command
blockchain get table bring.json

# EdgeLake returns
[
  {"table": {"dbms": "demo", "name": "sensors"}},
  {"table": {"dbms": "demo", "name": "readings"}},
  {"table": {"dbms": "test", "name": "data"}}
]

# MCP extracts with JSONPath: $[*].table.dbms
# MCP deduplicates
# MCP sorts
# MCP returns: ["demo", "test"]
```

**New (simple):**
```bash
# EdgeLake command
blockchain get table bring.json and format=mcp and extract=dbms

# EdgeLake returns (already extracted, unique, sorted)
["demo", "test"]

# MCP wraps: [{"type": "text", "text": "[\"demo\", \"test\"]"}]
```

### Example 2: Query Results

**Current (complex):**
```bash
# EdgeLake command
run client () sql demo "SELECT * FROM sensors LIMIT 10"

# EdgeLake returns
{"Query": [{"temp": 20}, {"temp": 21}, ...]}

# MCP extracts with JSONPath: $.Query[*]
# MCP returns: [{"temp": 20}, {"temp": 21}, ...]
```

**New (simple):**
```bash
# EdgeLake command
run client () sql demo format=mcp "SELECT * FROM sensors LIMIT 10"

# EdgeLake returns (already extracted)
[{"temp": 20}, {"temp": 21}, ...]

# MCP wraps: [{"type": "text", "text": "[{...}]"}]
```

### Example 3: Streaming Query (Future)

**With format=mcp:**
```python
# Client requests streaming query
query(database="demo", sql="SELECT * FROM large_table", stream=True)

# EdgeLake streams batches (format=mcp)
Batch 1: [row1, row2, ..., row100]   # 100 rows
Batch 2: [row101, row102, ..., row200]  # 100 rows
...
Batch 100: [row9901, row9902, ..., row10000]  # 100 rows

# MCP wraps and sends each batch immediately
Send 1: [{"type": "text", "text": "[row1, row2, ..., row100]"}]
Send 2: [{"type": "text", "text": "[row101, row102, ..., row200]"}]
...

# Total memory usage: ~100 rows (constant!)
# Time to first result: Immediate (no waiting for all 10,000 rows)
```

## Migration Path

### Step 1: Add format=mcp to EdgeLake Core
- Implement in `member_cmd.py`
- Support extraction hints (e.g., `extract=dbms`)
- Add tests

### Step 2: Update tools.yaml
- Change templates to use `format=mcp`
- Remove `response_parser` sections (no longer needed)

### Step 3: Simplify MCP Executor
- Remove JSONPath parsing code
- Remove extraction logic
- Keep only protocol wrapping

### Step 4: Enable Streaming (Future)
- Implement `stream_query_results()` in EdgeLake
- Update MCP executor for streaming
- Add streaming mode to tools.yaml

## Benefits Summary

### Immediate Benefits (Phase 1-2):
- ✅ **Simpler MCP Server**: Removes 200+ lines of JSONPath code
- ✅ **Fewer Bugs**: Less code = fewer bugs
- ✅ **Easier Maintenance**: Format logic centralized in EdgeLake
- ✅ **Consistent Behavior**: All format handling in one place

### Future Benefits (Phase 3):
- ✅ **True Streaming**: Constant memory usage
- ✅ **Faster Response**: Time to first result reduced
- ✅ **Better UX**: Progress updates for large queries
- ✅ **Scalable**: Can handle queries with millions of rows

## Related Documents

- **Implementation Summary**: `docs/mcp-query-implementation-summary.md`
- **Architecture**: `edge_lake/mcp_server/ARCHITECTURE.md`
- **Tool Execution Flow**: `edge_lake/mcp_server/TOOL_EXECUTION_FLOW.md`

## Decision Record

**Date**: 2025-01-28
**Decision**: Implement `format=mcp` (Option A - extracted data only)
**Rationale**: Enables streaming, maintains separation of concerns, keeps EdgeLake protocol-agnostic
**Status**: Approved for implementation