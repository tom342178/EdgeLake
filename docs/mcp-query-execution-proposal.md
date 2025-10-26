# MCP Server Query Execution Proposal

## Executive Summary

This document proposes a **hybrid approach** for SQL query execution in the EdgeLake MCP server that combines:

1. **Command layer validation** - Full SQL validation, view processing, and distributed query transformation
2. **Low-level streaming API** - True row-by-row or batched streaming with minimal memory footprint
3. **Automatic mode selection** - Intelligent choice between batch and streaming based on query characteristics

This approach provides **maximum flexibility** while maintaining **correctness** for EdgeLake's distributed query architecture.

---

## Problem Statement

The MCP server needs to execute SQL queries and return results to AI assistants (Claude, etc.) through the Model Context Protocol. Key requirements:

### Requirements

1. **Correctness**: Must properly handle EdgeLake's distributed query transformations (AVG→SUM+COUNT, etc.)
2. **Validation**: Must validate SQL syntax, table existence, permissions, and views
3. **Efficiency**: Should stream large result sets without loading everything into memory
4. **Flexibility**: Should support both small aggregate queries and large data scans
5. **User Experience**: Should provide progress feedback for long-running queries

### Current Challenges

**Option A: Command Layer Only** (`member_cmd.process_cmd()`)
- ✅ Full validation and transformation
- ✅ Handles distributed queries correctly
- ❌ Blocks until all results collected
- ❌ High memory usage for large result sets
- ❌ No streaming capability

**Option B: Low-Level API Only** (`db_info.process_fetch_rows()`)
- ✅ True streaming capability
- ✅ Constant memory usage
- ❌ **Missing critical distributed query transformations**
- ❌ No view processing
- ❌ No authorization checks
- ❌ Manual error handling required

---

## Proposed Solution: Hybrid Approach

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ MCP Server Tool: query_sql                              │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │ QueryExecutor.execute_query()│
         └──────────────┬───────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
    ┌─────▼─────┐              ┌──────▼──────┐
    │ VALIDATE  │              │  EXECUTE    │
    │ (Command  │              │  (Choose    │
    │  Layer)   │              │   Mode)     │
    └─────┬─────┘              └──────┬──────┘
          │                           │
          │                           │
          ▼                           ▼
    ┌──────────────────────────────────────────┐
    │ select_parser()                          │
    │ - Validate SQL syntax                    │
    │ - Process views                          │
    │ - Transform for distributed queries      │
    │ - Load table metadata                    │
    │ - Check authorization                    │
    └─────────────────┬────────────────────────┘
                      │
                      │ validated_sql
                      ▼
         ┌────────────────────────┐
         │ Mode Selection         │
         │ - Auto (detect)        │
         │ - Streaming (large)    │
         │ - Batch (small)        │
         └────────┬───────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
┌───────────────┐   ┌──────────────────┐
│ STREAMING     │   │ BATCH            │
│ Low-level API │   │ Command layer    │
│ process_fetch │   │ dest=rest        │
│ _rows()       │   │                  │
└───────────────┘   └──────────────────┘
```

### Key Components

#### 1. Query Validator (Using Command Layer)

**Purpose**: Leverage existing command layer validation without executing the query

**Code Location**: `mcp_server/core/query_validator.py`

```python
import edge_lake.dbms.db_info as db_info
from edge_lake.generic import process_status

class QueryValidator:
    """
    Validates SQL queries using EdgeLake's select_parser.
    Handles all transformation logic for distributed queries.
    """

    def validate_query(self, dbms_name: str, sql_query: str) -> dict:
        """
        Validate SQL query and prepare for execution.

        Returns:
            dict with:
            - validated: bool (True if valid)
            - error: str (error message if validation failed)
            - table_name: str (extracted table name)
            - validated_sql: str (possibly transformed SQL)
            - select_parsed: SelectParsed (metadata object)
        """
        status = process_status.ProcessStat()

        # Create select_parsed object
        select_parsed = status.get_select_parsed()
        select_parsed.reset(False, False)

        # Run validation through command layer's select_parser
        ret_val, table_name, validated_sql = db_info.select_parser(
            status,
            select_parsed,
            dbms_name,
            sql_query,
            False,  # return_no_data
            None    # nodes_safe_ids
        )

        if ret_val != 0:
            # Validation failed
            error = status.get_saved_error() or "SQL validation failed"
            return {
                "validated": False,
                "error": error,
                "error_code": ret_val
            }

        # Success - return validated query and metadata
        return {
            "validated": True,
            "table_name": table_name,
            "validated_sql": validated_sql,  # May be transformed!
            "select_parsed": select_parsed,
            "has_aggregates": self._has_aggregates(select_parsed),
            "has_limit": select_parsed.get_limit() is not None,
            "columns": select_parsed.get_query_title(),
            "data_types": select_parsed.get_query_data_types()
        }

    def _has_aggregates(self, select_parsed) -> bool:
        """Check if query has aggregate functions."""
        # Check if query contains AVG, SUM, COUNT, MIN, MAX
        projection = select_parsed.get_projection()
        if projection:
            projection_str = str(projection).upper()
            return any(func in projection_str for func in
                      ['AVG(', 'SUM(', 'COUNT(', 'MIN(', 'MAX('])
        return False
```

**What This Provides**:
- ✅ Full SQL syntax validation
- ✅ View resolution and processing
- ✅ Table metadata loading from blockchain/local storage
- ✅ **Critical**: Distributed query transformation (AVG→SUM+COUNT)
- ✅ Authorization checks
- ✅ Column and data type extraction
- ✅ Error messages with proper context

---

#### 2. Streaming Executor (Using Low-Level API)

**Purpose**: Stream results with minimal memory footprint

**Code Location**: `mcp_server/core/streaming_executor.py`

```python
import edge_lake.dbms.db_info as db_info
import edge_lake.dbms.cursor_info as cursor_info
from edge_lake.generic import process_status
import json
from typing import AsyncGenerator

class StreamingExecutor:
    """
    Execute validated SQL with streaming results.
    Assumes SQL has already been validated and transformed.
    """

    async def execute_streaming(
        self,
        dbms_name: str,
        validated_sql: str,
        select_parsed,
        fetch_size: int = 100
    ) -> AsyncGenerator[dict, None]:
        """
        Execute validated SQL and stream results.

        Args:
            dbms_name: Database name
            validated_sql: Already validated and transformed SQL
            select_parsed: Metadata from validation step
            fetch_size: Rows per fetch (1=row-by-row, 100=batches)

        Yields:
            dict: Chunks of data with metadata
        """
        status = process_status.ProcessStat()
        cursor = cursor_info.CursorInfo()

        try:
            # Create cursor
            if not db_info.set_cursor(status, cursor, dbms_name):
                error = status.get_saved_error() or "Failed to create cursor"
                raise Exception(error)

            # Execute validated SQL
            if not db_info.process_sql_stmt(status, cursor, validated_sql):
                error = status.get_saved_error() or "SQL execution failed"
                raise Exception(error)

            # Update cursor with metadata
            db_info.update_cusrosr(status, cursor)

            # Get column info from select_parsed (already validated)
            title_list = select_parsed.get_query_title()
            data_types_list = select_parsed.get_query_data_types()

            # Yield metadata first
            yield {
                "type": "metadata",
                "columns": title_list,
                "data_types": data_types_list,
                "fetch_size": fetch_size
            }

            # Stream data in chunks
            row_count = 0
            block_count = 0

            while True:
                # Fetch next chunk
                get_next, rows_data = db_info.process_fetch_rows(
                    status,
                    cursor,
                    "Query",        # JSON prefix
                    fetch_size,
                    title_list,
                    data_types_list
                )

                if not rows_data:
                    break

                # Parse JSON
                data = json.loads(rows_data)
                rows = data.get("Query", [])

                if not rows:
                    break

                # Yield data chunk
                block_count += 1
                row_count += len(rows)

                yield {
                    "type": "data",
                    "block": block_count,
                    "rows": rows,
                    "row_count": len(rows),
                    "total_rows_so_far": row_count,
                    "has_more": get_next
                }

                if not get_next:
                    break

            # Yield completion
            yield {
                "type": "complete",
                "total_rows": row_count,
                "total_blocks": block_count
            }

        finally:
            # Always close cursor
            db_info.close_cursor(status, cursor)
```

**What This Provides**:
- ✅ True streaming (constant memory)
- ✅ Configurable chunk size
- ✅ Progress tracking (block count, row count)
- ✅ Proper resource cleanup (cursor closed in finally block)
- ✅ Works with already-validated/transformed SQL

---

#### 3. Batch Executor (Using Command Layer)

**Purpose**: Simple execution for small result sets

**Code Location**: `mcp_server/core/batch_executor.py`

```python
import edge_lake.cmd.member_cmd as member_cmd
from edge_lake.generic import process_status

class BatchExecutor:
    """
    Execute queries using command layer with dest=rest.
    Good for small result sets that don't need streaming.
    """

    def execute_batch(self, dbms_name: str, sql_query: str) -> dict:
        """
        Execute query and return all results at once.

        Returns:
            dict with:
            - success: bool
            - data: list of rows (if successful)
            - error: str (if failed)
        """
        status = process_status.ProcessStat()
        io_buff = bytearray(4096)

        # Build command with REST destination
        cmd = f'sql {dbms_name} format=json dest=rest "{sql_query}"'

        # Execute (blocks until complete)
        ret_val = member_cmd.process_cmd(
            status, cmd, io_buff, None, None, None
        )

        if ret_val != 0:
            error = status.get_saved_error() or "Query execution failed"
            return {
                "success": False,
                "error": error,
                "error_code": ret_val
            }

        # Get results from job handle
        j_handle = status.get_active_job_handle()
        result_set = j_handle.get_result_set()

        # Parse JSON
        data = json.loads(result_set)
        rows = data.get("Query", [])

        return {
            "success": True,
            "total_rows": len(rows),
            "data": rows
        }
```

**What This Provides**:
- ✅ Simple implementation
- ✅ All EdgeLake features (validation, transformation, etc.)
- ✅ Good for small result sets
- ✅ Single blocking call

---

#### 4. Unified Query Executor (Orchestrator)

**Purpose**: Combine all components with intelligent mode selection

**Code Location**: `mcp_server/core/query_executor.py`

```python
from .query_validator import QueryValidator
from .streaming_executor import StreamingExecutor
from .batch_executor import BatchExecutor
from typing import AsyncGenerator, Union

class QueryExecutor:
    """
    Unified query executor with automatic mode selection.
    Combines validation, streaming, and batch execution.
    """

    def __init__(self):
        self.validator = QueryValidator()
        self.streaming_executor = StreamingExecutor()
        self.batch_executor = BatchExecutor()

    async def execute_query(
        self,
        dbms_name: str,
        sql_query: str,
        mode: str = "auto",
        fetch_size: int = 100
    ) -> Union[dict, AsyncGenerator[dict, None]]:
        """
        Execute SQL query with validation and optional streaming.

        Args:
            dbms_name: EdgeLake database name
            sql_query: SQL query to execute
            mode: Execution mode
                - "auto": Automatically choose based on query
                - "streaming": Always stream results
                - "batch": Always return all at once
            fetch_size: Rows per chunk for streaming mode

        Returns:
            Generator for streaming mode, dict for batch mode
        """

        # Step 1: ALWAYS validate first
        validation_result = self.validator.validate_query(dbms_name, sql_query)

        if not validation_result["validated"]:
            # Validation failed - return error
            return {
                "success": False,
                "error": validation_result["error"],
                "error_code": validation_result.get("error_code")
            }

        # Extract validated components
        validated_sql = validation_result["validated_sql"]
        select_parsed = validation_result["select_parsed"]
        table_name = validation_result["table_name"]

        # Step 2: Determine execution mode
        if mode == "auto":
            mode = self._select_mode(validation_result, sql_query)

        # Step 3: Execute based on mode
        if mode == "streaming":
            # Use streaming executor
            return self.streaming_executor.execute_streaming(
                dbms_name,
                validated_sql,
                select_parsed,
                fetch_size
            )
        else:
            # Use batch executor
            # Note: Use original sql_query, not validated_sql
            # Command layer will do its own validation/transformation
            return self.batch_executor.execute_batch(dbms_name, sql_query)

    def _select_mode(self, validation_result: dict, sql_query: str) -> str:
        """
        Automatically select execution mode based on query characteristics.

        Logic:
        - Use BATCH for: Simple aggregates, queries with LIMIT
        - Use STREAMING for: SELECT *, large scans, no LIMIT
        """
        has_aggregates = validation_result.get("has_aggregates", False)
        has_limit = validation_result.get("has_limit", False)

        sql_lower = sql_query.lower()

        # Simple aggregate with no LIMIT - probably small result
        if has_aggregates and not has_limit:
            # e.g., "SELECT COUNT(*) FROM table"
            return "batch"

        # Has LIMIT - probably small result
        if has_limit:
            # e.g., "SELECT * FROM table LIMIT 100"
            return "batch"

        # SELECT * without LIMIT - potentially large
        if "select *" in sql_lower and not has_limit:
            return "streaming"

        # Default to batch for safety
        return "batch"
```

**What This Provides**:
- ✅ Single entry point for all queries
- ✅ Automatic mode selection (smart defaults)
- ✅ Manual mode override when needed
- ✅ Consistent validation for both modes

---

## Integration with MCP Server

### Tool Definitions

**File**: `mcp_server/config/tools.yaml`

```yaml
- name: query_sql
  description: |
    Execute SQL query against EdgeLake database with automatic optimization.
    For large result sets, results are streamed. For small aggregates, returns all at once.
  edgelake_command:
    type: "query_sql"
  input_schema:
    type: object
    properties:
      dbms_name:
        type: string
        description: "EdgeLake database name (e.g., 'litsanleandro')"
      sql_query:
        type: string
        description: "SQL query to execute"
      mode:
        type: string
        enum: ["auto", "streaming", "batch"]
        default: "auto"
        description: |
          Execution mode:
          - auto: Automatically choose (recommended)
          - streaming: Stream large results
          - batch: Return all results at once
      fetch_size:
        type: integer
        default: 100
        description: "Rows per chunk for streaming (only used in streaming mode)"
    required: [dbms_name, sql_query]

- name: query_sql_streaming
  description: |
    Execute SQL query with forced streaming (good for large datasets).
    Results returned in chunks with progress updates.
  edgelake_command:
    type: "query_sql_streaming"
  input_schema:
    type: object
    properties:
      dbms_name:
        type: string
      sql_query:
        type: string
      fetch_size:
        type: integer
        default: 100
    required: [dbms_name, sql_query]

- name: query_sql_batch
  description: |
    Execute SQL query and return all results (good for small datasets, aggregates).
  edgelake_command:
    type: "query_sql_batch"
  input_schema:
    type: object
    properties:
      dbms_name:
        type: string
      sql_query:
        type: string
    required: [dbms_name, sql_query]
```

### Tool Executor Integration

**File**: `mcp_server/tools/executor.py`

```python
from ..core.query_executor import QueryExecutor

class ToolExecutor:
    def __init__(self, direct_client):
        self.direct_client = direct_client
        self.query_executor = QueryExecutor()

        self.query_interfaces = {
            'blockchain_query': BlockchainQuery(),
            'node_query': NodeQuery(),
            'query_sql': self.query_executor,  # NEW
        }

    async def execute_tool(self, name: str, arguments: dict):
        tool_config = self._get_tool_config(name)
        cmd_type = tool_config['edgelake_command']['type']

        if cmd_type in ["query_sql", "query_sql_streaming", "query_sql_batch"]:
            # Handle SQL queries
            dbms_name = arguments['dbms_name']
            sql_query = arguments['sql_query']

            # Determine mode from tool type
            if cmd_type == "query_sql":
                mode = arguments.get('mode', 'auto')
            elif cmd_type == "query_sql_streaming":
                mode = "streaming"
            else:  # query_sql_batch
                mode = "batch"

            fetch_size = arguments.get('fetch_size', 100)

            # Execute query
            result = await self.query_executor.execute_query(
                dbms_name, sql_query, mode, fetch_size
            )

            # Format for MCP response
            return self._format_query_result(result, mode)

        # ... rest of executor

    def _format_query_result(self, result, mode):
        """Format query results for MCP response."""
        if mode == "streaming":
            # Stream results as they arrive
            all_rows = []
            metadata = None

            async for chunk in result:
                if chunk["type"] == "metadata":
                    metadata = chunk
                elif chunk["type"] == "data":
                    all_rows.extend(chunk["rows"])
                elif chunk["type"] == "complete":
                    # Return final result
                    return {
                        "content": [{
                            "type": "text",
                            "text": json.dumps({
                                "total_rows": chunk["total_rows"],
                                "columns": metadata["columns"],
                                "data": all_rows[:100],  # First 100 for preview
                                "preview": True if len(all_rows) > 100 else False
                            }, indent=2)
                        }]
                    }
        else:
            # Batch mode - return all at once
            if result["success"]:
                return {
                    "content": [{
                        "type": "text",
                        "text": json.dumps({
                            "total_rows": result["total_rows"],
                            "data": result["data"]
                        }, indent=2)
                    }]
                }
            else:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error: {result['error']}"
                    }],
                    "isError": True
                }
```

---

## Usage Examples

### Example 1: Simple Aggregate (Auto-Selected Batch)

**User**: "What's the average temperature?"

**MCP Call**:
```json
{
  "name": "query_sql",
  "arguments": {
    "dbms_name": "litsanleandro",
    "sql_query": "SELECT AVG(temperature) as avg_temp FROM sensor_data"
  }
}
```

**Flow**:
1. Validator runs `select_parser()`:
   - Validates SQL
   - Transforms: `AVG(temperature)` → `SUM(temperature), COUNT(temperature)`
   - Detects: Has aggregates, no LIMIT
2. Executor selects **BATCH mode** (small result expected)
3. Batch executor runs via command layer
4. Returns: `{"avg_temp": 23.5}`

---

### Example 2: Large Scan (Auto-Selected Streaming)

**User**: "Show me all sensor readings"

**MCP Call**:
```json
{
  "name": "query_sql",
  "arguments": {
    "dbms_name": "litsanleandro",
    "sql_query": "SELECT * FROM sensor_data"
  }
}
```

**Flow**:
1. Validator runs `select_parser()`:
   - Validates SQL
   - Detects: SELECT *, no LIMIT
2. Executor selects **STREAMING mode** (large result expected)
3. Streaming executor:
   - Fetches 100 rows at a time
   - Yields chunks as they arrive
   - Shows progress: "Block 1: 100 rows", "Block 2: 100 rows", etc.
4. Returns: Preview of first 100 rows + total count

---

### Example 3: Forced Streaming

**User**: "I need all the data, stream it to me"

**MCP Call**:
```json
{
  "name": "query_sql_streaming",
  "arguments": {
    "dbms_name": "litsanleandro",
    "sql_query": "SELECT device_name, timestamp, temperature FROM sensor_data WHERE timestamp > NOW() - INTERVAL '1 day'",
    "fetch_size": 50
  }
}
```

**Flow**:
1. Validator runs (same validation as always)
2. Executor uses **STREAMING mode** (forced by tool)
3. Streams 50 rows at a time
4. Returns chunked results with progress

---

### Example 4: Distributed Query (Critical Test Case)

**User**: "What's the average temperature across all nodes?"

**MCP Call**:
```json
{
  "name": "query_sql",
  "arguments": {
    "dbms_name": "litsanleandro",
    "sql_query": "SELECT device_name, AVG(temperature) FROM sensor_data GROUP BY device_name"
  }
}
```

**Flow**:
1. Validator runs `select_parser()`:
   - **CRITICAL**: Transforms query for distributed execution
   - Remote query: `SELECT device_name, SUM(temperature), COUNT(temperature) ...`
   - Local query: `SELECT device_name, SUM(sum_temp)/SUM(count_temp) ...`
2. Executor detects: Has aggregates → **BATCH mode**
3. Batch executor runs via command layer (handles distributed coordination)
4. Returns: **Mathematically correct** averages across all nodes

**Without validation layer**: ❌ Would average the averages (WRONG!)
**With validation layer**: ✅ Correctly aggregates (RIGHT!)

---

## Performance Characteristics

### Memory Usage

**Batch Mode**:
```
Memory = N rows × row_size
Example: 10,000 rows × 500 bytes = 5 MB
```

**Streaming Mode**:
```
Memory = fetch_size × row_size (constant)
Example: 100 rows × 500 bytes = 50 KB (constant, regardless of total rows!)
```

### Network Efficiency

**Batch Mode**:
- Single response after all data collected
- Good for: Aggregates, small result sets (<1000 rows)

**Streaming Mode**:
- Progressive responses as data arrives
- Good for: Large scans, data exploration (>1000 rows)

### Query Execution Time

**Both modes have same execution time** (database processing is identical).

Difference is in **time to first result**:
- **Streaming**: User sees first chunk immediately
- **Batch**: User waits for complete result

---

## Error Handling

### Validation Errors (Caught Early)

```python
# Example: Invalid SQL syntax
{
  "name": "query_sql",
  "arguments": {
    "sql_query": "SELCT * FROM table"  # Typo
  }
}

# Response
{
  "success": False,
  "error": "Failed to parse SQL: Invalid SELECT syntax",
  "error_code": 123
}
```

### Execution Errors (Caught During Execution)

```python
# Example: Table doesn't exist
{
  "name": "query_sql",
  "arguments": {
    "sql_query": "SELECT * FROM nonexistent_table"
  }
}

# Response (after validation passes, execution fails)
{
  "success": False,
  "error": "Table 'nonexistent_table' not found in database 'litsanleandro'"
}
```

### Stream Interruption (Cleanup Guaranteed)

```python
# Even if error occurs mid-stream, cursor is closed
try:
    async for chunk in execute_streaming(...):
        yield chunk
finally:
    db_info.close_cursor(status, cursor)  # Always executes
```

---

## Testing Strategy

### Unit Tests

**Test 1: Validation Works**
```python
def test_validator():
    validator = QueryValidator()

    # Valid query
    result = validator.validate_query("test_db", "SELECT * FROM sensor_data")
    assert result["validated"] == True

    # Invalid query
    result = validator.validate_query("test_db", "SELCT * FROM table")
    assert result["validated"] == False
    assert "syntax" in result["error"].lower()
```

**Test 2: Mode Selection**
```python
def test_mode_selection():
    executor = QueryExecutor()

    # Aggregate → batch
    validation = {"has_aggregates": True, "has_limit": False}
    assert executor._select_mode(validation, "SELECT COUNT(*)") == "batch"

    # SELECT * → streaming
    validation = {"has_aggregates": False, "has_limit": False}
    assert executor._select_mode(validation, "SELECT * FROM table") == "streaming"
```

**Test 3: Distributed Query Transformation**
```python
def test_distributed_transformation():
    validator = QueryValidator()

    # Query with AVG should be transformed
    result = validator.validate_query("test_db",
        "SELECT device_name, AVG(temperature) FROM sensor_data GROUP BY device_name")

    # Validated SQL should contain SUM and COUNT
    assert "SUM" in result["validated_sql"].upper()
    assert "COUNT" in result["validated_sql"].upper()
```

### Integration Tests

**Test 4: End-to-End Streaming**
```python
async def test_streaming_execution():
    executor = QueryExecutor()

    result = await executor.execute_query(
        "test_db",
        "SELECT * FROM large_table",
        mode="streaming",
        fetch_size=10
    )

    chunks = []
    async for chunk in result:
        chunks.append(chunk)

    # Should have metadata, data, and complete chunks
    assert chunks[0]["type"] == "metadata"
    assert chunks[-1]["type"] == "complete"
    assert sum(1 for c in chunks if c["type"] == "data") > 0
```

**Test 5: End-to-End Batch**
```python
def test_batch_execution():
    executor = QueryExecutor()

    result = executor.execute_query(
        "test_db",
        "SELECT COUNT(*) FROM sensor_data",
        mode="batch"
    )

    assert result["success"] == True
    assert "data" in result
    assert len(result["data"]) > 0
```

---

## Migration Path

### Phase 1: MVP (Week 1-2)

**Implement**:
- QueryValidator (validation only)
- BatchExecutor (simple command layer wrapper)
- Basic QueryExecutor with auto-mode

**Tools**:
- `query_sql` (auto mode only)

**Testing**:
- Validate against existing queries
- Confirm distributed queries work correctly

---

### Phase 2: Streaming (Week 3-4)

**Add**:
- StreamingExecutor
- Streaming mode to QueryExecutor

**Tools**:
- `query_sql_streaming`
- Update `query_sql` to support streaming mode

**Testing**:
- Large result set tests
- Memory profiling
- Performance benchmarking

---

### Phase 3: Optimization (Week 5+)

**Enhance**:
- Smart mode selection tuning
- Progress callbacks
- Cancellation support
- Result caching

**Tools**:
- Additional parameters (timeout, max_rows, etc.)

---

## Risks and Mitigations

### Risk 1: Validation Overhead

**Risk**: Running `select_parser()` adds overhead

**Mitigation**:
- Overhead is minimal (< 1ms for typical queries)
- Far outweighed by correctness guarantees
- Can cache validation results for repeated queries

### Risk 2: Complexity

**Risk**: Hybrid approach is more complex than pure command layer

**Mitigation**:
- Well-defined interfaces
- Comprehensive testing
- Clear documentation
- Phased rollout (batch first, then streaming)

### Risk 3: Streaming Mode Bugs

**Risk**: Streaming mode might have edge cases not in batch mode

**Mitigation**:
- Start with batch mode only (Phase 1)
- Add streaming incrementally
- Extensive testing before production
- `finally` blocks ensure cleanup

---

## Recommendation

**Implement the hybrid approach with phased rollout:**

1. **Phase 1 (MVP)**: Validation + Batch execution only
   - Gets validation/transformation correctness immediately
   - Uses proven command layer for execution
   - Low risk, high value

2. **Phase 2**: Add streaming for large results
   - Addresses memory concerns
   - Better UX for data exploration
   - Can be tested independently

3. **Phase 3**: Optimize mode selection
   - Tune auto-detection heuristics
   - Add advanced features (caching, progress, etc.)

This approach:
- ✅ Maintains correctness for distributed queries
- ✅ Provides streaming benefits when needed
- ✅ Allows incremental development
- ✅ Minimizes risk

---

## Appendix: Code File Structure

```
mcp_server/
├── core/
│   ├── query_validator.py       # NEW: Validation using select_parser
│   ├── streaming_executor.py    # NEW: Low-level streaming
│   ├── batch_executor.py        # NEW: Command layer wrapper
│   ├── query_executor.py        # NEW: Unified orchestrator
│   ├── blockchain_query.py      # Existing
│   ├── node_query.py            # Existing
│   └── direct_client.py         # Existing
├── tools/
│   ├── executor.py              # MODIFIED: Add query execution
│   └── ...
├── config/
│   └── tools.yaml               # MODIFIED: Add query tools
└── server.py                    # Existing
```

---

## Appendix: Alternative Considered

### Alternative: Pure Command Layer (Rejected)

**Approach**: Use only `member_cmd.process_cmd()` with `dest=rest`

**Rejected Because**:
- ❌ No streaming capability
- ❌ High memory usage for large results
- ❌ Poor UX for data exploration

### Alternative: Pure Low-Level API (Rejected)

**Approach**: Use only `db_info.process_fetch_rows()` directly

**Rejected Because**:
- ❌ **Missing distributed query transformations** (CRITICAL!)
- ❌ No view processing
- ❌ Manual validation required
- ❌ Authorization bypassed

### Why Hybrid is Best

Combines strengths of both:
- ✅ Validation and transformation from command layer
- ✅ Streaming and efficiency from low-level API
- ✅ Best of both worlds

---

## Conclusion

The proposed hybrid approach provides a **production-ready solution** that:

1. **Maintains correctness** through proper validation and transformation
2. **Enables streaming** for large result sets
3. **Optimizes automatically** based on query characteristics
4. **Minimizes risk** through phased implementation

This approach is **recommended for implementation** starting with Phase 1 (batch mode with validation) and expanding to streaming in Phase 2.
