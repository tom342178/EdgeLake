  EdgeLake's Distributed Query Architecture

  High-Level Flow (from lines 19-25):

  1. Query Node receives user query
  2. Query Node creates a TEMPORARY LOCAL TABLE (named query_N where N is job number)
  3. Query is distributed to all relevant Operator nodes
  4. Each Operator executes the query and returns results
  5. Results from EACH operator are INSERTED into the local table
  6. When all operators respond, Query Node executes a FINAL QUERY on the local table
  7. Unified result returned to user/app

  The Sophisticated Parts:

  1. Query Transformation (Not Simple Forwarding)

  EdgeLake rewrites the SQL into THREE versions (lines 897-1332):

  - remote_query: SQL sent to Operator nodes (transformed)
  - local_create: CREATE TABLE statement for consolidation table
  - local_query: Final SQL to execute on consolidated results

  Example - User query:
  SELECT AVG(temperature), COUNT(*) FROM sensor_data WHERE timestamp > '2024-01-01'

  Remote query (lines 235-266 - avg_sql function):
  -- EdgeLake REPLACES avg() with sum() and count() to enable proper consolidation
  SELECT SUM(temperature), COUNT(temperature), COUNT(*) FROM sensor_data WHERE timestamp >
  '2024-01-01'

  Local query (line 257-259):
  -- Query Node recalculates the REAL average from aggregated sums/counts
  SELECT SUM(SUM__temperature) / NULLIF(SUM(COUNT__temperature), 0) FROM query_13

  2. Function-Specific Consolidation Strategies

  Different SQL functions require different consolidation logic:

  COUNT (lines 191-229):
  - Remote: Each Operator returns COUNT(...)
  - Local: Query Node executes SUM(count_func_N) to add up all counts

  AVG (lines 235-273):
  - Remote: Returns SUM() and COUNT() separately
  - Local: Calculates SUM(all_sums) / SUM(all_counts) for correct average

  MIN/MAX (lines 631-633):
  - Remote: Each Operator returns local MIN/MAX
  - Local: Query Node executes MIN() or MAX() of all operator mins/maxes

  RANGE (lines 277-303):
  - Remote: Each Operator returns MIN() and MAX()
  - Local: Calculates |MAX(all_maxes) - MIN(all_mins)|

  COUNT(DISTINCT) (lines 193-209):
  - Remote: Each Operator returns DISTINCT values (NOT counts)
  - Local: Query Node executes COUNT(DISTINCT ...) on combined unique values

  INCREMENTS (Time-series bucketing, lines 478-575):
  - Handles time-based aggregation (hourly, daily, etc.)
  - Remote: Groups by time buckets using date_trunc() and extract()
  - Local: Re-groups by time intervals across all nodes

  3. ORDER BY and GROUP BY Handling

  Lines 1233-1300:
  - User's GROUP BY columns are transformed for both remote and local queries
  - Extended columns (like @table_name, @ip) are added automatically
  - ORDER BY is applied BOTH at Operator level AND final consolidation

  Example:
  -- User query:
  SELECT device_id, AVG(temp) FROM sensors GROUP BY device_id ORDER BY device_id

  -- Remote (to operators):
  SELECT device_id, SUM(temp), COUNT(temp) FROM sensors GROUP BY device_id ORDER BY device_id

  -- Local (on Query Node):
  SELECT device_id, SUM(SUM__temp) / SUM(COUNT__temp) FROM query_17
  GROUP BY device_id ORDER BY device_id

  4. Special Time-Series Functions

  PERIOD function (lines 691-867):
  - Finds data within a time window RELATIVE to a specific timestamp
  - Uses leading queries to find the boundary timestamp
  - Then applies time range filter

  INCREMENTS function (lines 478-575):
  - Automatic time bucket optimization
  - If user asks for 1000 data points over 30 days, EdgeLake calculates optimal bucket size
  (e.g., hourly)
  - Consolidates time-bucketed data across nodes

  Key Insight: It's NOT a Merge Sort

  EdgeLake uses mathematical aggregation rather than sorting:

  1. Parallel Execution: All Operators execute simultaneously (MapReduce-style)
  2. INSERT into Local Table: Results are inserted as they arrive (no waiting for all)
  3. SQL-Based Consolidation: Final query leverages SQL engine for consolidation
  4. Intelligent Aggregation: Different functions use mathematically correct consolidation:
    - Averages: Σ(sums) / Σ(counts)
    - Counts: Σ(counts)
    - Min/Max: MIN(mins) or MAX(maxes)
    - Distinct: COUNT(DISTINCT(union_of_distincts))

  This is much more efficient than a merge sort because:
  - No need to sort massive datasets
  - Can leverage database indexes on the consolidation table
  - Mathematically correct for statistical aggregations
  - Supports complex SQL operations (GROUP BY, HAVING, nested queries)

  Architecture Advantage: By creating a temporary local table and using SQL for consolidation,
  EdgeLake can handle:
  - Arbitrarily complex queries
  - Missing/delayed operator responses
  - Partial results
  - Re-execution of failed queries

  This is essentially a distributed SQL engine with smart query rewriting, similar to systems
  like Presto/Trino, but optimized for edge environments with potentially unreliable
  connectivity.