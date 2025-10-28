# JSONPath vs format=mcp: Complex Extraction Cases

This document explains why some tools still require JSONPath extraction and what would be needed to implement `format=mcp` for these cases in EdgeLake core.

---

## Overview

While the `unwrap` parser works great for simple cases (like `query` tool), some tools require complex data transformation that can't be solved by simple unwrapping. These are:

1. **list_databases** - Extract unique database names from table policies
2. **list_tables** - Filter tables by database, extract names

This document shows:
- What the raw EdgeLake response looks like
- How JSONPath currently handles it
- What would be needed in `member_cmd.py` to implement `format=mcp`

---

## Case 1: list_databases

### What We Want
A simple list of unique database names:
```json
["demo", "test", "prod"]
```

### Raw EdgeLake Response
Command: `blockchain get table bring.json`

```json
[
  {
    "table": {
      "dbms": "demo",
      "name": "sensors",
      "create": "CREATE TABLE sensors (timestamp TIMESTAMP, temp REAL, ...)"
    }
  },
  {
    "table": {
      "dbms": "demo",
      "name": "readings",
      "create": "CREATE TABLE readings (timestamp TIMESTAMP, value REAL, ...)"
    }
  },
  {
    "table": {
      "dbms": "test",
      "name": "data",
      "create": "CREATE TABLE data (id INT, ...)"
    }
  },
  {
    "table": {
      "dbms": "demo",
      "name": "alerts",
      "create": "CREATE TABLE alerts (id INT, ...)"
    }
  },
  {
    "table": {
      "dbms": "prod",
      "name": "metrics",
      "create": "CREATE TABLE metrics (timestamp TIMESTAMP, ...)"
    }
  }
]
```

**Challenges:**
1. Data is nested: `[{table: {dbms: "demo"}}, ...]`
2. Multiple tables per database (duplicates)
3. Need unique values only
4. Should be sorted alphabetically

### Current Solution: JSONPath in MCP

**Configuration** (`tools.yaml`):
```yaml
- name: list_databases
  edgelake_command:
    template: "blockchain get table bring.json"
    response_parser:
      type: "jsonpath"
      extract_path: "$[*].table.dbms"  # Navigate nested structure
      unique: true                      # Remove duplicates
      sort: true                        # Sort alphabetically
```

**How JSONPath Works**:
```python
# Step 1: Extract path "$[*].table.dbms"
# Input: [{table: {dbms: "demo"}}, {table: {dbms: "demo"}}, {table: {dbms: "test"}}]
extracted = ["demo", "demo", "test", "demo", "prod"]

# Step 2: Apply unique filter
unique_values = ["demo", "test", "prod"]

# Step 3: Sort
sorted_values = ["demo", "prod", "test"]

# Result
["demo", "prod", "test"]
```

**MCP Server Code** (~30 lines in `executor.py`):
```python
def _parse_with_jsonpath(self, result, parser_config, arguments):
    # Parse JSONPath expression
    jsonpath_expr = jsonpath_parse("$[*].table.dbms")
    matches = jsonpath_expr.find(result)
    extracted = [match.value for match in matches]

    # Apply unique filter
    if parser_config.get('unique'):
        extracted = list(set(extracted))

    # Apply sorting
    if parser_config.get('sort'):
        extracted = sorted(extracted)

    return extracted
```

### Alternative: format=mcp in EdgeLake Core

**Command**: `blockchain get table bring.json and format=mcp and extract=dbms`

**What Would Be Needed in `member_cmd.py`**:

```python
# Location: edge_lake/cmd/member_cmd.py
# Function: blockchain_get() or similar

def blockchain_get(status, cmd_words, blockchain_file, bring_data):
    # ... existing code to get table policies ...

    # Current behavior (format=json):
    # Returns: [{"table": {...}}, {"table": {...}}, ...]

    # NEW: Check for format=mcp
    reply_format = interpreter.get_one_value_or_default(conditions, "format", "json")
    extract_field = interpreter.get_one_value_or_default(conditions, "extract", None)

    if reply_format == "mcp" and extract_field:
        # Extract specific field from nested data
        extracted_values = []

        for policy in table_policies:
            if "table" in policy:
                table_info = policy["table"]
                if extract_field in table_info:
                    value = table_info[extract_field]
                    extracted_values.append(value)

        # Apply unique filter (always for mcp format)
        unique_values = list(set(extracted_values))

        # Sort (always for mcp format)
        sorted_values = sorted(unique_values)

        # Return as JSON array
        return utils_json.to_string(sorted_values)
    else:
        # Existing behavior
        return utils_json.to_string(table_policies)
```

**Changes Required**:
1. Add format parsing to `blockchain_get()` (10-15 lines)
2. Add field extraction logic (15-20 lines)
3. Add unique/sort logic (5-10 lines)
4. **Total**: ~40 lines per command

**Challenges**:
- EdgeLake has **dozens of `get` commands**
- Each would need similar logic
- **Maintenance burden**: Every new field extraction needs core changes

---

## Case 2: list_tables

### What We Want
List of table names for a specific database:
```json
["sensors", "readings", "alerts"]
```

### Raw EdgeLake Response
Command: `blockchain get table bring.json`

Same as Case 1:
```json
[
  {"table": {"dbms": "demo", "name": "sensors", ...}},
  {"table": {"dbms": "demo", "name": "readings", ...}},
  {"table": {"dbms": "test", "name": "data", ...}},
  {"table": {"dbms": "demo", "name": "alerts", ...}},
  {"table": {"dbms": "prod", "name": "metrics", ...}}
]
```

**Challenges:**
1. Data is nested: `[{table: {dbms: "...", name: "..."}}, ...]`
2. Need to **filter** by database name (user argument)
3. Need to **extract** table name field
4. Result should be sorted

### Current Solution: JSONPath in MCP

**Configuration** (`tools.yaml`):
```yaml
- name: list_tables
  edgelake_command:
    template: "blockchain get table bring.json"
    response_parser:
      type: "jsonpath"
      extract_path: "$[*].table"     # Extract all table objects
      filter:
        field: "dbms"                 # Filter by this field
        source: "argument"            # Value comes from user argument
        argument: "database"          # Argument name
      map: "name"                     # Extract 'name' field from filtered items
```

**How JSONPath Works**:
```python
# Step 1: Extract path "$[*].table"
# Input: [{table: {dbms: "demo", name: "sensors"}}, ...]
extracted = [
    {dbms: "demo", name: "sensors"},
    {dbms: "demo", name: "readings"},
    {dbms: "test", name: "data"},
    {dbms: "demo", name: "alerts"},
    {dbms: "prod", name: "metrics"}
]

# Step 2: Filter by dbms="demo" (from user argument)
filtered = [
    {dbms: "demo", name: "sensors"},
    {dbms: "demo", name: "readings"},
    {dbms: "demo", name: "alerts"}
]

# Step 3: Map to 'name' field
mapped = ["sensors", "readings", "alerts"]

# Result
["sensors", "readings", "alerts"]
```

**MCP Server Code** (~50 lines in `executor.py`):
```python
def _parse_with_jsonpath(self, result, parser_config, arguments):
    # Step 1: Extract path
    jsonpath_expr = jsonpath_parse("$[*].table")
    matches = jsonpath_expr.find(result)
    extracted = [match.value for match in matches]

    # Step 2: Apply filtering
    if 'filter' in parser_config:
        filter_config = parser_config['filter']
        field = filter_config.get('field')  # "dbms"
        argument_name = filter_config.get('argument')  # "database"
        filter_value = arguments.get(argument_name)  # "demo"

        extracted = [
            item for item in extracted
            if isinstance(item, dict) and item.get(field) == filter_value
        ]

    # Step 3: Apply field mapping
    if 'map' in parser_config:
        map_field = parser_config['map']  # "name"
        extracted = [
            item.get(map_field) if isinstance(item, dict) else item
            for item in extracted
        ]

    return extracted
```

### Alternative: format=mcp in EdgeLake Core

**Command**: `blockchain get table bring.json where dbms="demo" and format=mcp and extract=name`

**What Would Be Needed in `member_cmd.py`**:

```python
# Location: edge_lake/cmd/member_cmd.py
# Function: blockchain_get() or similar

def blockchain_get(status, cmd_words, blockchain_file, bring_data):
    # ... existing code to get table policies ...

    # NEW: Parse where conditions
    #                               Must     Add      Is
    #                               exists   Counter  Unique
    keywords = {
        "dbms":    ("str", False, False, True),  # Filter by database
        "format":  ("str", False, False, True),  # Output format
        "extract": ("str", False, False, True),  # Field to extract
    }

    ret_val, counter, conditions = interpreter.get_dict_from_words(
        status, cmd_words, offset, 0, keywords, False
    )

    # Get parameters
    reply_format = conditions.get("format", "json")
    extract_field = conditions.get("extract", None)
    filter_dbms = conditions.get("dbms", None)

    if reply_format == "mcp" and extract_field:
        # Filter and extract
        extracted_values = []

        for policy in table_policies:
            if "table" in policy:
                table_info = policy["table"]

                # Apply filter if specified
                if filter_dbms:
                    if table_info.get("dbms") != filter_dbms:
                        continue  # Skip this table

                # Extract field
                if extract_field in table_info:
                    value = table_info[extract_field]
                    extracted_values.append(value)

        # Sort
        sorted_values = sorted(extracted_values)

        # Return as JSON array
        return utils_json.to_string(sorted_values)
    else:
        # Existing behavior
        return utils_json.to_string(table_policies)
```

**Changes Required**:
1. Add keyword definitions for filter/format/extract (10 lines)
2. Parse conditions (5 lines)
3. Add filtering logic (10-15 lines)
4. Add field extraction logic (10-15 lines)
5. Add sorting (5 lines)
6. **Total**: ~50 lines per command

**Challenges**:
- More complex than Case 1 (filtering + extraction)
- Need to handle WHERE conditions properly
- **Syntax**: Would need to support `where dbms="demo"` in blockchain get command
- EdgeLake's `blockchain get` doesn't currently support WHERE filters

---

## Comparison: JSONPath vs format=mcp

| Aspect | JSONPath (Current) | format=mcp (Future) |
|--------|-------------------|---------------------|
| **Where Logic Lives** | MCP Server (executor.py) | EdgeLake Core (member_cmd.py) |
| **Lines of Code** | ~200 (one time, all tools) | ~50 per command |
| **Flexibility** | Very high (config-driven) | Medium (code changes) |
| **EdgeLake Changes** | None | 40-50 lines per command |
| **Maintenance** | MCP server only | EdgeLake core + MCP |
| **New Extractions** | Add to tools.yaml | Modify member_cmd.py |
| **Streaming Ready** | No (processes full result) | Yes (can yield batches) |

---

## Why JSONPath Is Better for Now

### 1. Centralized Logic
All extraction logic lives in one place (`executor.py`):
- Easy to understand
- Easy to maintain
- Easy to extend

### 2. No EdgeLake Core Changes
- Don't need to modify dozens of commands
- Don't need to add WHERE clause support to blockchain get
- Don't need to coordinate changes across MCP and core

### 3. Configuration-Driven
Adding new extraction patterns:
```yaml
# Just add to tools.yaml, no code changes!
- name: list_operators
  response_parser:
    type: "jsonpath"
    extract_path: "$[*].operator.ip"
    unique: true
    sort: true
```

### 4. Handles Complex Cases
JSONPath supports:
- Nested path navigation (`$[*].table.dbms`)
- Filtering by field values
- Field mapping (extract specific field)
- Uniqueness
- Sorting
- All configurable, no code changes

---

## When format=mcp Makes Sense

`format=mcp` is best for **simple unwrapping**:

✅ **Good Cases** (use unwrap parser):
- `{"Query": [...]}` → `[...]`
- `{"Status": {...}}` → `{...}`
- Single key, no transformation

❌ **Bad Cases** (use JSONPath):
- Nested extraction: `$[*].table.dbms`
- Filtering: Only dbms="demo"
- Field mapping: Extract 'name' field
- Uniqueness + sorting
- **Complexity**: Would require 50+ lines per command in EdgeLake

---

## Future: Best of Both Worlds

**Phase 1 (Current)**: Use parsers in MCP
- ✅ Unwrap parser for simple cases (query, node_status)
- ✅ JSONPath parser for complex cases (list_databases, list_tables)

**Phase 2 (Future)**: Implement format=mcp in EdgeLake for simple cases
- Add `format=mcp` to commands that return single-key wrappers
- Example: `run client () sql demo format=mcp "SELECT ..."`
- Returns: `[...]` instead of `{"Query": [...]}`
- **Benefits**: Enables streaming, simpler MCP code

**Phase 3 (Far Future)**: Add complex extraction to EdgeLake
- Add WHERE clause support to blockchain get
- Add extract parameter
- Example: `blockchain get table where dbms="demo" and format=mcp and extract=name`
- **Only if**: We need this for other clients (not just MCP)

---

## Code Examples

### Example 1: Simple Unwrap (Already Implemented)

**EdgeLake Response**:
```json
{"Query": [{"temp": 20}, {"temp": 21}]}
```

**MCP Unwrap Parser**:
```python
# Just extract the "Query" key
result = {"Query": [...]}
unwrapped = result["Query"]  # [...]
```

**Lines of Code**: 5 lines (done!)

---

### Example 2: Complex Extraction (JSONPath - Current)

**EdgeLake Response**:
```json
[
  {"table": {"dbms": "demo", "name": "sensors"}},
  {"table": {"dbms": "demo", "name": "readings"}},
  {"table": {"dbms": "test", "name": "data"}}
]
```

**What We Want** (for list_tables with database="demo"):
```json
["sensors", "readings"]
```

**MCP JSONPath Parser**:
```python
# Step 1: Extract all table objects
extracted = jsonpath("$[*].table")
# [{"dbms": "demo", "name": "sensors"}, {"dbms": "demo", "name": "readings"}, {"dbms": "test", "name": "data"}]

# Step 2: Filter by dbms
filtered = [item for item in extracted if item["dbms"] == "demo"]
# [{"dbms": "demo", "name": "sensors"}, {"dbms": "demo", "name": "readings"}]

# Step 3: Map to name field
mapped = [item["name"] for item in filtered]
# ["sensors", "readings"]
```

**Lines of Code**: 30 lines (already done in executor.py!)

---

### Example 3: Complex Extraction (format=mcp - Not Implemented)

**EdgeLake Command**:
```
blockchain get table where dbms="demo" and format=mcp and extract=name
```

**EdgeLake Code Needed** (member_cmd.py):
```python
def blockchain_get(status, cmd_words, blockchain_file, bring_data):
    # ... get all table policies ...

    # Parse where clause (NEW!)
    conditions = parse_where_clause(cmd_words)  # +10 lines

    filter_dbms = conditions.get("dbms")
    reply_format = conditions.get("format", "json")
    extract_field = conditions.get("extract")

    if reply_format == "mcp" and extract_field:  # +20 lines
        result = []
        for policy in table_policies:
            table = policy.get("table", {})

            # Filter
            if filter_dbms and table.get("dbms") != filter_dbms:
                continue

            # Extract
            if extract_field in table:
                result.append(table[extract_field])

        return json.dumps(sorted(result))
    else:
        # Existing behavior
        return json.dumps(table_policies)
```

**Lines of Code**: 40-50 lines PER COMMAND

**Problem**: EdgeLake has dozens of commands. This adds up fast!

---

## Recommendation

**Keep current approach**:
1. ✅ Use `unwrap` parser for simple cases (10% of tools)
2. ✅ Use `jsonpath` parser for complex cases (20% of tools)
3. ✅ No parser for already-clean responses (70% of tools)

**Why**:
- Works now
- No EdgeLake core changes needed
- Handles all complexity
- Easy to maintain
- Total code: ~200 lines (one time, all tools)

**Future**: Only implement `format=mcp` in EdgeLake when:
- Multiple clients need it (not just MCP)
- Streaming becomes critical (constant memory)
- EdgeLake naturally adds WHERE clause support

**Pragmatic principle**: "Don't let perfect be the enemy of good"

The current JSONPath solution is good enough, especially for the 2-3 tools that need it. Implementing `format=mcp` for complex cases would add 40-50 lines per command to EdgeLake core for minimal benefit.
