# MCP Server Architecture History

## Why This Document Exists

This document explains the evolution of the MCP server architecture to prevent confusion in future development sessions.

## The Problem

When starting new Claude Code sessions, the AI was incorrectly suggesting to:
1. Create `core/blockchain_query.py` and `core/node_query.py` modules
2. Add a `query_interfaces` dict to `executor.py`
3. Implement tool-specific routing logic

**These recommendations were WRONG** - they suggested recreating code that was **intentionally deleted**.

## Architecture Evolution

### Phase 1: Initial Implementation (Deleted)
**Commits:** 3010434, f1d4ea8, 865d678

**Pattern:**
```python
# executor.py had query_interfaces dict
self.query_interfaces = {
    'blockchain_query': BlockchainQuery(),
    'node_query': NodeQuery(),
    'sql_query': SqlQuery()
}

# Separate processor modules
core/blockchain_query.py
core/node_query.py
core/sql_query.py
```

**Problem:** This violated the "configuration-driven" principle by adding intermediate tool-specific processors.

### Phase 2: Refactor - Remove Intermediate Processors
**Commit:** `9052858` (2025-10-23)

**Changes:**
```
DELETED: core/blockchain_query.py
DELETED: core/node_query.py
DELETED: core/sql_query.py
REMOVED: query_interfaces dict from executor.py
REMOVED: _execute_query_interface() method
SIMPLIFIED: executor.py to TWO paths only (internal or EdgeLake command)
```

**Rationale:**
- All tool behavior should be in `tools.yaml`, not code
- Executor should be purely generic, no tool-specific logic
- Adding new tools should only require configuration changes

### Phase 3: Current Architecture (Correct)

**Pattern:**
```python
# executor.py - TWO paths ONLY
async def execute_tool(self, name, arguments):
    if cmd_type == 'internal':
        result = await self._execute_internal(...)
    else:
        result = await self._execute_edgelake_command(...)
```

**Flow:**
```
tools.yaml → CommandBuilder → EdgeLakeDirectClient → member_cmd.process_cmd()
```

**Files:**
- `config/tools.yaml`: ALL tool definitions
- `tools/executor.py`: Generic execution engine (NO tool-specific code)
- `core/command_builder.py`: Builds commands from templates
- `core/direct_client.py`: Direct integration with EdgeLake

## Why ARCHITECTURE.md Was Misleading

**The Problem:**
- ARCHITECTURE.md was written during Phase 1
- Commit `9052858` deleted the implementation but didn't update the docs
- ARCHITECTURE.md showed `query_interfaces` pattern as "Correct Pattern"
- This pattern was actually the OLD deleted architecture

**The Fix (2025-10-24):**
- Updated ARCHITECTURE.md to show current (post-refactor) architecture
- Explicitly marked deleted patterns as "NEVER DO THIS"
- Added commit references to explain what was removed

## For Future Development

### ✅ To Add a New Tool:

1. **Edit `config/tools.yaml` ONLY:**
   ```yaml
   - name: new_tool
     description: "Tool description"
     edgelake_command:
       type: "get"
       template: "get something"
     input_schema:
       type: object
       properties: {}
   ```

2. **That's it!** No code changes needed.

### ❌ DO NOT:

1. Create files like `core/xyz_query.py`
2. Add `query_interfaces` dict to executor
3. Add tool-specific methods to executor
4. Add tool-specific conditionals (`if name == "xyz"`)

### If You Think You Need Tool-Specific Code:

**Ask yourself:**
1. Can this be expressed as a command template in tools.yaml?
2. Can this use the `build_sql` flag for dynamic query building?
3. Can this use a `parse_response` parser?
4. Is this truly an internal operation (like `server_info`)?

**If none of these apply,** then you may need to extend the generic capabilities (e.g., add a new parser type), but **NEVER** add tool-specific logic.

## Key Commits

- `9052858`: Refactor - Remove all intermediate query processors
- `b9e6e8f`: docs - Add critical design constraint to ARCHITECTURE.md
- `959d5ab`: Refactor - Remove tool-specific methods and add stdout capture

## References

- Current architecture: `ARCHITECTURE.md`
- Tool definitions: `config/tools.yaml`
- Execution engine: `tools/executor.py`
- Commit history: `git log --oneline edge_lake/mcp_server/`

## Phase 4: JSONPath-Based Declarative Parsing (2025-10-25)

**Problem:** Even after removing intermediate processors, tool-specific logic still existed in executor.py:
- `_extract_unique_databases()` method
- `_extract_tables_for_database()` method
- These violated the "configuration-driven" principle by hiding tool logic in code

**Solution:** Implement generic JSONPath-based parsing driven entirely by tools.yaml

**Changes:**
```
ADDED: jsonpath-ng dependency
ADDED: Generic _parse_with_jsonpath() method (zero tool-specific logic)
ADDED: JSONPath expressions in tools.yaml response_parsers
REMOVED: _parse_blockchain_table()
REMOVED: _extract_unique_databases()
REMOVED: _extract_tables_for_database()
REMOVED: _parse_query_result() (replaced with _extract_json_from_cli_output)
```

**New Configuration Format:**
```yaml
response_parsers:
  extract_databases:
    type: "jsonpath"
    extract_path: "$.(table,tables)[*].table.dbms"
    unique: true
    sort: true

  extract_tables:
    type: "jsonpath"
    extract_path: "$.(table,tables)[*].table"
    filter:
      field: "dbms"
      source: "argument"
      argument: "database"
    map: "name"
```

**Benefits:**
- ALL extraction logic now in tools.yaml
- Adding new data transformations requires ZERO code changes
- Executor is purely generic - no tool-specific knowledge
- Can handle complex nested JSON structures declaratively

## Phase 5: Cleanup - Remove Redundant CLI Noise Handling (2025-10-25)

**Problem:** After implementing JSONPath parsing, we discovered that `direct_client.py` already handles all CLI noise extraction from EdgeLake stdout. The `search_patterns` and `fallback` configuration in `tools.yaml` and the corresponding extraction methods in `executor.py` were redundant.

**Changes:**
```
REMOVED: search_patterns and fallback from tools.yaml query tool
REMOVED: _extract_json_from_cli_output() method from executor.py
REMOVED: _extract_json_from_position() method from executor.py
SIMPLIFIED: _parse_response() no longer checks for search_patterns
```

**Clear Separation of Concerns:**
- `direct_client.py`: Handles **all** CLI noise extraction from EdgeLake stdout
- `executor.py`: Pure JSONPath-based **data extraction** (no CLI noise handling)
- `tools.yaml`: Clean configuration with only JSONPath expressions

**Benefits:**
- No duplicate CLI noise handling logic
- Clearer responsibility boundaries between layers
- Simpler configuration - no need for search_patterns in most tools
- Easier to maintain and understand

---

**Last Updated:** 2025-10-25
**Current Branch:** feat-mcp-service
**Correct Architecture Version:** Post-cleanup (fully declarative, zero duplication, clear separation of concerns)
