# EdgeLake Distributed Query Architecture

## Overview

EdgeLake's distributed query system implements a sophisticated **mathematical aggregation architecture** rather than a traditional merge-sort approach. When a Query Node receives a SQL query targeting data across multiple Operator Nodes, it transforms that query into three distinct SQL statements optimized for distributed execution and consolidation.

This architecture enables efficient parallel query execution across edge nodes while maintaining SQL correctness for complex aggregate functions, time-series operations, and statistical calculations.

## High-Level Architecture

```
┌─────────────┐
│ Application │
└──────┬──────┘
       │ SQL Query
       ▼
┌─────────────────────────┐
│    Query Node           │
│  (unify_results.py)     │
└─────────────────────────┘
       │
       ├─ 1. Parse original query
       ├─ 2. Transform into 3 SQL versions:
       │    • remote_query (sent to operators)
       │    • local_create (temp consolidation table)
       │    • local_query (final aggregation)
       │
       ▼
┌──────────────────────────────────────┐
│  Distribute to Operator Nodes        │
│  (MapReduce-style parallel execution)│
└──────────────────────────────────────┘
       │
       ▼
┌────────────┐  ┌────────────┐  ┌────────────┐
│ Operator 1 │  │ Operator 2 │  │ Operator N │
│  (Partial  │  │  (Partial  │  │  (Partial  │
│   Results) │  │   Results) │  │   Results) │
└─────┬──────┘  └─────┬──────┘  └─────┬──────┘
      │               │               │
      └───────────────┴───────────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Query Node      │
            │  Creates temp    │
            │  table (query_N) │
            └─────────┬────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Execute         │
            │  local_query     │
            │  (final aggr.)   │
            └─────────┬────────┘
                      │
                      ▼
            ┌──────────────────┐
            │  Return unified  │
            │  result to app   │
            └──────────────────┘
```

## Query Transformation Process

### Code Reference
**File**: `edge_lake/dbms/unify_results.py`
**Key Function**: `query_prep()` (lines 48-176)

For every user query, EdgeLake generates **three SQL statements**:

1. **`remote_query`**: Sent to each Operator Node for parallel execution
2. **`local_create`**: Creates temporary consolidation table on Query Node
3. **`local_query`** (or `generic_query`): Performs final aggregation on consolidated data

### Example: AVG() Transformation

**Original Query**:
```sql
SELECT device_name, AVG(temperature)
FROM sensor_data
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY device_name;
```

**Transformed Queries**:

**1. `remote_query`** (sent to operators):
```sql
SELECT device_name, SUM(temperature), COUNT(temperature)
FROM sensor_data
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY device_name;
```

**2. `local_create`** (temporary table schema):
```sql
CREATE TABLE query_42 (
    device_name VARCHAR,
    sum__temperature NUMERIC,
    count__temperature INTEGER
);
```

**3. `local_query`** (final consolidation):
```sql
SELECT device_name,
       SUM(sum__temperature) / NULLIF(SUM(count__temperature), 0) AS temperature
FROM query_42
GROUP BY device_name;
```

### Why This Transformation?

The naive approach of sending `AVG(temperature)` to each operator and averaging those averages **would be mathematically incorrect**:

```
❌ WRONG: AVG(AVG(op1), AVG(op2), AVG(op3))
✅ CORRECT: SUM(SUM(op1), SUM(op2), SUM(op3)) / SUM(COUNT(op1), COUNT(op2), COUNT(op3))
```

EdgeLake's transformation ensures **mathematical correctness** across distributed data.

## Function-Specific Consolidation Strategies

### 1. AVG() - Weighted Average

**Code Reference**: `unify_results.py` lines 235-266

```python
def avg_sql(column_name, new_field_name, new_column_name, str_select_local, str_select_remote):
    # Remote operators calculate partial sums and counts
    remote_query = ("SUM" + "(" + column_name + "), COUNT(" + column_name + ")")

    # Local consolidation: sum of sums divided by sum of counts
    local_query = ("SUM(" + new_field_name + ") /NULLIF(SUM(COUNT__" + new_column_name + "),0)")

    return remote_query, local_query
```

**Strategy**:
- Operators return: `(SUM, COUNT)` pairs
- Query Node calculates: `SUM(all_sums) / SUM(all_counts)`
- Handles NULL values with `NULLIF()` to avoid division by zero

### 2. COUNT() - Summation

**Code Reference**: `unify_results.py` lines 268-295

```python
def count_sql(column_name, new_field_name, new_column_name, str_select_local, str_select_remote):
    # Remote operators calculate local counts
    remote_query = ("COUNT(" + column_name + ")")

    # Local consolidation: sum all counts
    local_query = ("SUM(" + new_field_name + ")")

    return remote_query, local_query
```

**Strategy**:
- Operators return: `COUNT(rows)` for their partition
- Query Node calculates: `SUM(all_counts)`
- Simple summation across nodes

### 3. MIN() / MAX() - Preservation

**Code Reference**: `unify_results.py` lines 297-348

```python
def min_max_sql(column_name, new_field_name, new_column_name, str_select_local,
                str_select_remote, command):
    # Remote operators calculate local min/max
    remote_query = (command + "(" + column_name + ")")

    # Local consolidation: min/max of all min/maxes
    local_query = (command + "(" + new_field_name + ")")

    return remote_query, local_query
```

**Strategy**:
- Operators return: `MIN(values)` or `MAX(values)` for their partition
- Query Node calculates: `MIN(all_mins)` or `MAX(all_maxes)`
- Distributive property allows direct application

### 4. SUM() - Direct Summation

**Code Reference**: `unify_results.py` lines 350-377

```python
def sum_sql(column_name, new_field_name, new_column_name, str_select_local, str_select_remote):
    # Remote operators calculate local sums
    remote_query = ("SUM(" + column_name + ")")

    # Local consolidation: sum all sums
    local_query = ("SUM(" + new_field_name + ")")

    return remote_query, local_query
```

**Strategy**:
- Operators return: `SUM(values)` for their partition
- Query Node calculates: `SUM(all_sums)`
- Associative property allows direct summation

### 5. DISTINCT COUNT

**Code Reference**: `unify_results.py` lines 379-408

```python
def count_distinct_sql(column_name, new_field_name, new_column_name,
                       str_select_local, str_select_remote):
    # Remote operators return distinct values
    remote_query = column_name

    # Local consolidation: count distinct across all operators
    local_query = ("COUNT(DISTINCT " + new_field_name + ")")

    return remote_query, local_query
```

**Strategy**:
- Operators return: **Raw values** (not counts!)
- Query Node calculates: `COUNT(DISTINCT all_values)`
- Prevents double-counting values that appear on multiple nodes

### 6. INCREMENTS (Time-Series)

**Code Reference**: `unify_results.py` lines 506-546

```python
def increments_sql(column_name, new_field_name, new_column_name,
                   str_select_local, str_select_remote):
    # Remote operators calculate incremental differences
    remote_query = f"INCREMENTS({column_name})"

    # Local consolidation: sum increments across nodes
    local_query = f"SUM({new_field_name})"

    return remote_query, local_query
```

**Strategy**:
- Operators return: Incremental changes in values (deltas)
- Query Node calculates: `SUM(all_increments)`
- Used for counter-based metrics (packet counts, byte counts, etc.)

### 7. PERIOD (Time-Based Aggregation)

**Code Reference**: `unify_results.py` lines 548-591

**Strategy**:
- Operators return: Time-bucketed aggregations
- Query Node re-buckets and consolidates across time periods
- Supports flexible time windows (1 minute, 1 hour, 1 day, etc.)

## Mathematical Correctness

### Why Not Merge-Sort?

A traditional distributed database might:
1. Send full query to all operators
2. Collect all result sets
3. Merge-sort the results
4. Apply final aggregation

**Problems with this approach**:
- **Incorrect results** for AVG, COUNT DISTINCT, INCREMENTS
- **High memory usage** (full result sets in memory)
- **Network overhead** (transferring complete datasets)

### EdgeLake's Approach

EdgeLake uses **algebraic properties** of SQL aggregate functions:

| Function | Property | Consolidation Method |
|----------|----------|---------------------|
| SUM | Associative | Sum of sums |
| COUNT | Associative | Sum of counts |
| MIN/MAX | Distributive | Min/max of mins/maxes |
| AVG | Decomposable | (Sum of sums) / (Sum of counts) |
| COUNT DISTINCT | Set-based | Distinct of union |
| INCREMENTS | Delta-based | Sum of deltas |

This approach:
- ✅ **Mathematically correct** for all functions
- ✅ **Memory efficient** (only aggregated data transferred)
- ✅ **Network efficient** (minimal data movement)
- ✅ **SQL-native** (uses database engine for consolidation)

## Temporary Consolidation Tables

**Code Reference**: `unify_results.py` lines 177-233

Each distributed query creates a unique temporary table:

```python
# Table naming: query_0, query_1, query_2, ...
temp_table = f"query_{query_id}"

# Schema matches remote_query output
CREATE TABLE query_42 (
    device_name VARCHAR,
    sum__temperature NUMERIC,
    count__temperature INTEGER,
    max__humidity NUMERIC,
    ...
);
```

**Lifecycle**:
1. **Created**: When query starts (using `local_create` SQL)
2. **Populated**: With results from all operators (INSERT INTO)
3. **Queried**: Final aggregation (using `local_query` SQL)
4. **Dropped**: After results returned (cleanup)

**Benefits**:
- Isolates each query's consolidation
- Leverages database engine for final aggregation
- Allows complex SQL operations (GROUP BY, ORDER BY, HAVING)
- Simplifies error recovery (drop table on failure)

## Performance Characteristics

### Parallel Execution
- **Map Phase**: All operators execute simultaneously
- **Network Transfer**: Only aggregated data (not raw rows)
- **Reduce Phase**: SQL-based consolidation (database engine optimized)

### Example Performance

**Scenario**: Query 1M rows across 10 operators

**Naive Merge-Sort**:
- Transfer: 1M rows over network
- Memory: Hold 1M rows on Query Node
- Processing: Application-level aggregation

**EdgeLake**:
- Transfer: 10 aggregated rows (one per operator)
- Memory: 10 rows on Query Node
- Processing: Single SQL query on temp table

**Speedup**: ~100,000x reduction in data transfer for aggregate queries

## Time-Series Optimizations

EdgeLake includes specialized handling for time-series workloads:

### PERIOD Clause

**Code Reference**: `unify_results.py` lines 548-591

```sql
SELECT device_name,
       PERIOD(timestamp, 1 minute) as time_bucket,
       AVG(temperature)
FROM sensor_data
GROUP BY device_name, time_bucket;
```

**Transformation**:
1. Operators bucket data by time period
2. Query Node re-buckets consolidated results
3. Handles timezone conversions and period alignment

### INCREMENTS Function

**Code Reference**: `unify_results.py` lines 506-546

```sql
SELECT device_name,
       INCREMENTS(packet_count) as packets_per_interval
FROM network_stats
GROUP BY device_name;
```

**Use Case**: Counter-based metrics that only increase
- Network packet counts
- Byte counters
- Request counters
- Error counts

## Edge Cases and Error Handling

### NULL Handling

```python
# Division by zero protection
local_query = "SUM(sum_col) / NULLIF(SUM(count_col), 0)"
```

### Empty Result Sets

If an operator returns no rows:
- Temporary table remains valid
- Aggregations handle empty sets correctly
- NULL propagation follows SQL standards

### Operator Failures

If an operator fails to respond:
- Partial results from available operators
- User can configure timeout behavior
- Query marked as incomplete (if configured)

## Code Architecture

### Main Processing Flow

```python
# unify_results.py
def query_prep(dbms_cursor, query_conditions, counter):
    """
    Transform user query into distributed execution plan

    Returns:
        status: Success/failure
        remote_query: SQL for operators
        local_create: Temp table creation SQL
        local_query: Final aggregation SQL
    """
    # 1. Parse original query
    # 2. Identify aggregate functions
    # 3. Transform each function using function-specific strategy
    # 4. Generate three SQL statements
    # 5. Return execution plan
```

### Function Transformation Registry

```python
# Function-specific handlers
transform_functions = {
    'AVG': avg_sql,
    'COUNT': count_sql,
    'MIN': min_max_sql,
    'MAX': min_max_sql,
    'SUM': sum_sql,
    'COUNT DISTINCT': count_distinct_sql,
    'INCREMENTS': increments_sql,
    'PERIOD': period_sql,
}
```

## Comparison to Other Systems

| System | Approach | Correctness | Efficiency |
|--------|----------|-------------|------------|
| **Traditional DB** | Centralized | ✅ Perfect | ❌ No distribution |
| **Hadoop MapReduce** | File-based M/R | ✅ Correct | ⚠️ High latency |
| **Spark SQL** | In-memory M/R | ✅ Correct | ✅ Fast (requires memory) |
| **EdgeLake** | SQL transformation | ✅ Correct | ✅ Fast (minimal transfer) |

**EdgeLake's Advantage**: Operates directly on edge nodes without requiring data centralization or large memory footprint.

## Future Enhancements

Potential areas for optimization:

1. **Streaming Aggregation**: Real-time consolidation as operator results arrive
2. **Pushdown Optimization**: Move more computation to operators (filters, projections)
3. **Adaptive Query Plans**: Choose consolidation strategy based on data distribution
4. **Incremental Consolidation**: Update results as new data arrives
5. **Query Result Caching**: Cache consolidated results for repeated queries

## Related Documentation

- **Main Architecture**: `edge_lake/CLAUDE.md`
- **MCP Server**: `edge_lake/mcp_server/ARCHITECTURE.md`
- **Database Management**: `edge_lake/dbms/README.md` (if exists)
- **Query Processing**: `edge_lake/cmd/member_cmd.py`

## Code References

All code references point to:
- **File**: `edge_lake/dbms/unify_results.py`
- **Lines**: Specific line numbers provided throughout this document
- **Repository**: https://github.com/EdgeLake/EdgeLake

## Summary

EdgeLake's distributed query architecture achieves **mathematically correct aggregate queries across edge nodes** through:

1. **Query Transformation**: Three SQL statements (remote/local_create/local_query)
2. **Function-Specific Strategies**: Tailored consolidation for each aggregate function
3. **Temporary Consolidation Tables**: SQL-based final aggregation
4. **Minimal Data Transfer**: Only aggregated data crosses network
5. **Mathematical Correctness**: Leverages algebraic properties of aggregates

This design enables real-time queries across distributed edge data without moving raw data to a central location, making it ideal for edge computing, IoT, and distributed sensor networks.
