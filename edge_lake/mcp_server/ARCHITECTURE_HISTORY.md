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

---

**Last Updated:** 2025-10-24
**Current Branch:** feat-mcp-service
**Correct Architecture Version:** Post-9052858 (configuration-driven, no intermediate processors)
