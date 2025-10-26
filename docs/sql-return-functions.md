# EdgeLake SQL Return Functions

## Overview

This document describes the core data retrieval mechanism in EdgeLake, specifically how query results are fetched from the database and returned to callers. The architecture supports both **distributed query results** (Operator → Query Node) and **local query results** (direct execution), using a streaming, row-by-row approach that minimizes memory footprint.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Query Execution Flow                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  query_row_by_row()   │
                │  (member_cmd.py:4290) │
                └───────────┬───────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
        [message=True]              [message=False]
        Network Mode                 Local Mode
              │                           │
              ▼                           ▼
    ┌──────────────────┐        ┌──────────────────┐
    │ Operator Node    │        │ Query Node or    │
    │ Send to Query    │        │ Direct Execution │
    └─────────┬────────┘        └─────────┬────────┘
              │                           │
              └─────────────┬─────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │ process_fetch_rows()  │
                │   (db_info.py:566)    │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │ DBMS-Specific         │
                │ fetch_rows()          │
                │ (psql/sqlite/mongo)   │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │ Database Cursor       │
                │ fetchone()/fetchall() │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │ format_db_rows()      │
                │ (utils_sql.py:2082)   │
                └───────────┬───────────┘
                            │
                            ▼
                      JSON Result
```

## Core Functions

### 1. `query_row_by_row()` - Main Query Execution Loop

**Location**: `edge_lake/cmd/member_cmd.py:4290-4627`

This is the primary function that fetches and transmits query results. It operates in two distinct modes based on the `message` parameter.

#### Function Signature

```python
def query_row_by_row(status, dbms_cursor, io_buff_in, conditions, sql_time,
                     sql_command, nodes_count, nodes_replied):
```

#### Parameters

- `status`: Process status object for error tracking
- `dbms_cursor`: EdgeLake's generic database cursor
- `io_buff_in`: Network message buffer (for network mode)
- `conditions`: Query execution conditions (format, destination, etc.)
- `sql_time`: Time taken to execute the SQL statement
- `sql_command`: The SQL query being executed
- `nodes_count`: Total number of nodes participating in query
- `nodes_replied`: Number of nodes that have responded

#### Mode 1: Network Mode (`message=True`) - Operator Node

When an Operator Node receives a query from a Query Node, it executes in **network mode**.

**Setup Phase** (lines 4316-4356):

```python
if message:
    # Extract source Query Node information from message header
    ip, port = message_header.get_source_ip_port(mem_view)
    Job_location = message_header.get_job_location(mem_view)
    job_id = message_header.get_job_id(mem_view)

    # Open TCP socket back to Query Node
    soc = net_client.socket_open(ip, port, "job reply", 6, 3)

    # Setup encryption if enabled
    f_object = None
    if version.al_auth_is_node_encryption():
        public_str = message_header.get_public_str(mem_view)
        if public_str:
            encrypted_key, f_object = version.al_auth_setup_encryption(status, public_str)

    # Prepare message header
    message_header.set_info_type(mem_view, message_header.BLOCK_INFO_RESULT_SET)
    message_header.set_block_struct(mem_view, message_header.BLOCK_STRUCT_JSON_MULTIPLE)
    message_header.prep_command(mem_view, "job reply")
    message_header.set_data_segment_to_command(mem_view)
```

**Main Fetch Loop** (lines 4428-4520):

```python
while get_next:  # Fetch and send rows
    # Start database timer
    timers.start(0)

    # Fetch ONE row from database
    get_next, rows_data = db_info.process_fetch_rows(
        status,
        dbms_cursor,
        "Query",        # JSON prefix
        1,              # Fetch size: 1 row at a time
        title_list,     # Column names
        data_types_list # Column types
    )

    # Stop database timer
    timers.pause(0)

    if not rows_data:
        break

    dbms_rows += 1

    # Encode the row data
    if f_object:
        # Symmetric encryption
        data_encoded = version.al_auth_symetric_encryption(status, f_object, rows_data)
    else:
        data_encoded = rows_data.encode()

    bytes_not_copied = 0

    # Pack row(s) into network blocks
    while True:
        rows_counter += 1

        # Try to copy data into current block
        block_full, bytes_not_copied = message_header.copy_data(
            mem_view,
            data_encoded,
            bytes_not_copied
        )

        if block_full:
            # Block is full - send it
            message_header.set_block_number(mem_view, block_number, False)
            message_header.set_counter_jsons(mem_view, rows_counter)

            # Start network timer
            timers.start(1)

            # Send the block via TCP
            if not net_client.mem_view_send(soc, mem_view):
                ret_val = process_status.ERR_network
                break

            # Stop network timer
            timers.pause(1)

            block_number += 1
            message_header.set_data_segment_to_command(mem_view)
            rows_counter = 0

            if not bytes_not_copied:
                # All data transferred for this row
                break

        if not bytes_not_copied:
            break
```

**Finalization** (lines 4565-4607):

```python
# Send final block with completion flag
message_header.set_error(mem_view, ret_val)
message_header.set_block_number(mem_view, block_number, True)  # Last block flag
message_header.set_counter_jsons(mem_view, rows_counter)
message_header.set_operator_time(mem_view, dbms_time, network_time)

if net_client.mem_view_send(soc, mem_view):
    ret_val = process_status.SUCCESS
else:
    ret_val = process_status.ERR_network

net_client.socket_close(soc)
```

**Network Block Structure**:
- Each block contains multiple JSON-encoded rows
- Blocks sent immediately when full (streaming)
- Last block marked with special flag
- Includes timing metadata (dbms_time, network_time)
- Optional symmetric encryption

#### Mode 2: Local Mode (`message=False`) - Query Node

When executing locally or consolidating results on a Query Node.

**Setup Phase** (lines 4358-4392):

```python
else:  # Local execution mode
    j_handle = status.get_active_job_handle()

    if j_handle.is_with_job_instance():
        # Query Node unifying data from operators
        select_parsed = j_handle.get_select_parsed()
        operator_time = j_handle.get_operator_time()
    else:
        # Local SQL on this Operator node
        select_parsed = status.get_select_parsed()

    # Get column metadata
    title_list = select_parsed.get_query_title()
    time_columns = select_parsed.get_date_types()
    data_types_list = select_parsed.get_query_data_types()
    casting_list = select_parsed.get_casting_list()
    casting_columns = select_parsed.get_casting_columns()

    # Setup output manager
    output_manager = output_data.OutputManager(
        conditions,
        j_handle.get_output_socket(),
        j_handle.get_output_into(),
        add_stat,
        nodes_count
    )

    # Initialize and output header
    output_manager.init(status, select_parsed.get_source_query(),
                        title_list, data_types_list,
                        select_parsed.get_dbms_name())
    output_manager.output_header(status)  # Output header once
```

**Main Processing Loop** (lines 4521-4549):

```python
else:  # Local output mode
    # Fetch row
    get_next, rows_data = db_info.process_fetch_rows(...)

    # Transform timestamps if needed
    query_data = None
    if (len(time_columns) and timezone != "utc") or len(casting_columns):
        # Convert time from UTC to current timezone
        query_data = utils_json.str_to_json(rows_data)
        if query_data:
            ret_val = utils_columns.change_columns_values(
                status,
                timezone,
                time_columns,
                casting_columns,
                casting_list,
                title_list,
                query_data['Query']
            )
            if not ret_val:
                rows_data = utils_json.to_string(query_data)

    # Apply per-column limits if specified
    # Example: "limit 1 per table" with extended tables
    if per_column:
        if not query_data:
            query_data = utils_json.str_to_json(rows_data)
        if query_data:
            if not process_limit(query_data["Query"], per_column,
                                per_counter_dict, limit):
                continue  # Skip this row (above limit)

    fetch_counter += 1

    # Output the row to destination (stdout, REST, file, etc.)
    ret_val = output_manager.new_rows(status, rows_data, query_data,
                                      next_offset, False)
```

**Finalization** (lines 4618-4625):

```python
j_handle.set_query_completed()
if not ret_val or ret_val > process_status.NON_ERROR_RET_VALUE:
    ret_val = output_manager.finalize(status, io_buff_in, fetch_counter,
                                      dbms_time, False, True, nodes_replied)

if output_manager.is_with_result_set():
    j_handle.set_outpu_buff(output_manager.get_result_set())
```

#### Performance Monitoring

**Timing Components** (lines 4557-4573):

```python
fetch_time = timers.get_timer(0)    # Time fetching rows from DBMS
network_time = timers.get_timer(1)  # Time sending data over network
dbms_time = operator_time + sql_time + fetch_time

# Update query monitor
job_instance.get_query_monitor().update_monitor(dbms_time)

# Log slow queries if enabled
query_log_time = job_instance.get_query_log_time()
if query_log_time >= 0 and query_log_time <= dbms_time:
    query_info = (f"Sec: {dbms_time:>4,} Rows: {fetch_counter:>6,} "
                  f"DBMS: {dbms_cursor.get_table_name()} SQL: {sql_command}")
    process_log.add("query", query_info)
```

**Example Log Entry**:
```
Sec: 2.34 Rows: 10,245 DBMS: sensor_data SQL: SELECT device_name, AVG(temperature) FROM ...
```

**Time Breakdown**:
- `sql_time`: Initial SQL statement execution
- `fetch_time`: Total time fetching all rows (timer[0])
- `network_time`: Total time sending data (timer[1])
- `operator_time`: Time operators spent processing (from message header)
- `dbms_time = operator_time + sql_time + fetch_time`

---

### 2. `process_fetch_rows()` - Database Abstraction Layer

**Location**: `edge_lake/dbms/db_info.py:566-572`

This function provides a **thin abstraction layer** over DBMS-specific implementations.

#### Function Signature

```python
def process_fetch_rows(status, dbms_cursor, output_prefix, fetch_size,
                      title_list, type_list):
```

#### Parameters

- `status`: Process status object
- `dbms_cursor`: EdgeLake's generic cursor wrapper (contains db_connect and db_cursor)
- `output_prefix`: JSON root key (typically "Query")
- `fetch_size`: Number of rows to fetch
  - `1` = fetch one row (via `fetchone()`)
  - `N` = fetch N rows (via `fetchmany(N)`)
  - `0` = fetch all remaining rows (via `fetchall()`)
- `title_list`: List of column names for result set
- `type_list`: List of column data types for proper formatting

#### Returns

A list containing:
- `[0]`: Boolean - `True` if more rows available, `False` if done
- `[1]`: String - JSON-formatted row data

#### Implementation

```python
def process_fetch_rows(status, dbms_cursor, output_prefix, fetch_size,
                      title_list, type_list):
    # Get the database connection object
    db_connect = dbms_cursor.get_db_connect()

    # Get the database-specific cursor
    db_cursor = dbms_cursor.get_cursor()

    # Delegate to DBMS-specific implementation
    get_next, str_data = db_connect.fetch_rows(
        status,
        db_cursor,
        output_prefix,
        fetch_size,
        title_list,
        type_list
    )

    return [get_next, str_data]
```

**Role**: Acts as a **dispatcher** that routes to the appropriate DBMS implementation (PostgreSQL, SQLite, MongoDB, etc.).

---

### 3. DBMS-Specific `fetch_rows()` Implementations

Each DBMS adapter implements its own `fetch_rows()` method.

#### PostgreSQL Implementation

**Location**: `edge_lake/dbms/psql_dbms.py:690-705`

```python
def fetch_rows(self, status: process_status, db_cursor, output_prefix: str,
               fetch_size: int, title_list, type_list):

    # Fetch raw rows from PostgreSQL database
    ret_val, output = self.fetch_list(status, db_cursor, fetch_size)

    output_len = len(output)

    if ret_val and output_len:
        if output_prefix:
            # Format as JSON using utils_sql.format_db_rows()
            string_data = utils_sql.format_db_rows(
                status,
                db_cursor[1],  # Database cursor
                output_prefix,
                output,        # Raw rows
                title_list,
                type_list
            )
        else:
            # Return raw Python list representation
            string_data = str(output)
    else:
        string_data = ""

    return [ret_val, string_data]
```

**Key Method**: `fetch_list()` calls:
- `cursor.fetchone()` if `fetch_size == 1`
- `cursor.fetchmany(fetch_size)` if `fetch_size > 1`
- `cursor.fetchall()` if `fetch_size == 0`

#### SQLite Implementation

**Location**: `edge_lake/dbms/sqlite_dbms.py:437`

Same structure as PostgreSQL, but using SQLite3's cursor API.

#### MongoDB Implementation

**Location**: `edge_lake/dbms/mongodb_dbms.py`

Adapts MongoDB cursor operations to the same interface.

---

### 4. `format_db_rows()` - JSON Formatting

**Location**: `edge_lake/generic/utils_sql.py:2082-2161`

This function transforms raw database rows into EdgeLake's standardized JSON format.

#### Function Signature

```python
def format_db_rows(status, db_cursor, output_prefix, rows_data,
                   title_list, type_list):
```

#### Parameters

- `status`: Process status object
- `db_cursor`: Physical database cursor (contains column metadata)
- `output_prefix`: JSON root key (e.g., "Query")
- `rows_data`: Raw rows from database (list of tuples)
- `title_list`: Column names for projection
- `type_list`: Data types for each column

#### Returns

JSON-formatted string representing the rows.

#### Implementation

```python
def format_db_rows(status, db_cursor, output_prefix, rows_data,
                   title_list, type_list):

    # Start JSON structure
    data = "{\"" + output_prefix + "\":[{"

    entries_title = len(title_list)
    formatted_row = ""
    first_row = True

    # Handle column numbering
    if entries_title == 1 and isinstance(title_list[0], int):
        # Column numbering starts from this value
        first_column = title_list[0]
        entries_title = 0
    else:
        first_column = 0

    # Process each row
    for row in rows_data:
        if not first_row:
            formatted_row = ",{"

        # Process each column in the row
        for i, value in enumerate(row):
            # Normalize data format (handle special types)
            new_value = unify_data_format(value)

            # Determine column name
            if output_prefix == "Query":
                if i < entries_title:
                    description = title_list[i]
                else:
                    description = str(first_column + i)
            elif db_cursor:
                description = db_cursor.description[i][0]
            else:
                if i == 0:
                    description = "column_name"
                else:
                    description = "data_type"

            # Format value according to data type
            if new_value == None:
                formatted_row += "\"" + description + "\":" + "\"\""
            else:
                if type_list:
                    data_type = type_list[i]

                    if data_type in get_value_by_type_:
                        method = get_value_by_type_[data_type]
                    else:
                        method = get_value_by_type_["string"]
                else:
                    method = get_value_by_type_["string"]

                str_value = str(new_value)

                # Escape double quotes in strings
                if id(method) == id(rep_value_as_str) and '"' in str_value:
                    str_value = esc_quotations(str_value)

                # Apply formatter (adds quotes for strings, leaves numbers unquoted)
                projected_value = method(str_value)

                formatted_row += "\"" + description + "\":" + projected_value

            data += formatted_row
            formatted_row = ","

        first_row = False
        data += "}"

    data += "]}"
    return data
```

#### Type Formatters

The `get_value_by_type_` dictionary maps data types to formatting functions:

```python
get_value_by_type_ = {
    "string": rep_value_as_str,      # Adds quotes: "value"
    "int": rep_value_as_number,      # No quotes: 123
    "float": rep_value_as_number,    # No quotes: 123.45
    "bool": rep_value_as_bool,       # true/false (lowercase)
    "timestamp": rep_value_as_str,   # Quoted timestamp
    # ... etc
}
```

#### Example Output

**Input**:
```python
rows_data = [
    ("sensor1", 23.5, "2025-01-15T10:30:00"),
    ("sensor2", 24.1, "2025-01-15T10:30:05")
]
title_list = ["device_name", "temperature", "timestamp"]
type_list = ["string", "float", "string"]
```

**Output**:
```json
{
  "Query": [
    {
      "device_name": "sensor1",
      "temperature": 23.5,
      "timestamp": "2025-01-15T10:30:00"
    },
    {
      "device_name": "sensor2",
      "temperature": 24.1,
      "timestamp": "2025-01-15T10:30:05"
    }
  ]
}
```

---

## Complete Data Flow Example

### Scenario: Query Node Consolidating Results from 3 Operators

```
┌─────────────────────────────────────────────────────────────┐
│ Query Node: Execute local_query on temp table query_42      │
│ SQL: SELECT device_name, SUM(sum_temp)/SUM(count_temp)      │
│      FROM query_42 GROUP BY device_name                     │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Operator 1   │    │ Operator 2   │    │ Operator 3   │
│ SUM=235      │    │ SUM=471      │    │ SUM=294      │
│ COUNT=10     │    │ COUNT=20     │    │ COUNT=12     │
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │ Inserted into query_42  │
              │ (temporary table)       │
              └─────────────────────────┘
```

**Step-by-Step Execution at Query Node**:

```python
# 1. All operators have replied and inserted data into query_42
# 2. Query Node calls query_local_table()
#    → process_query_sequence()
#      → query_local_dbms()
#        → query_row_by_row()  ← WE ARE HERE

# Initialize (message=False for local mode)
message = False
output_manager = OutputManager(conditions, ...)
output_manager.init(status, "SELECT device_name, ...", title_list, data_types_list, "system_query")
output_manager.output_header(status)  # Print: | device_name | avg_temperature |

# Main loop
get_next = True
rows_counter = 0

while get_next:
    # Fetch one row from system_query.query_42
    get_next, rows_data = db_info.process_fetch_rows(
        status,
        anylog_cursor,    # Points to query_42 table
        "Query",
        1,                # Fetch one row at a time
        ["device_name", "avg_temperature"],
        ["string", "float"]
    )

    # rows_data = '{"Query":[{"device_name":"sensor1","avg_temperature":23.5}]}'

    if not rows_data:
        break

    # Apply timezone transformations if needed
    if time_columns and timezone != "utc":
        query_data = utils_json.str_to_json(rows_data)
        utils_columns.change_columns_values(status, timezone, time_columns,
                                           casting_columns, casting_list,
                                           title_list, query_data['Query'])
        rows_data = utils_json.to_string(query_data)

    # Output to destination (stdout, REST API, file, etc.)
    output_manager.new_rows(status, rows_data, query_data, next_offset, False)

    rows_counter += 1

# Finalize output
output_manager.finalize(status, io_buff_in, rows_counter, dbms_time,
                       False, True, nodes_replied)
```

**Output** (if destination is stdout with format=table):
```
| device_name | avg_temperature |
|-------------|-----------------|
| sensor1     | 23.5            |
| sensor2     | 24.1            |
| sensor3     | 22.8            |
```

---

## Key Design Decisions

### 1. Streaming Architecture

**Rows are fetched and sent one at a time**, not buffered in memory.

**Rationale**:
- ✅ **Constant Memory Usage**: Memory footprint doesn't grow with result set size
- ✅ **Works with Large Datasets**: Can handle arbitrarily large result sets
- ✅ **Low Latency**: First rows arrive quickly (no wait for full result set)
- ⚠️ **Higher Overhead**: More context switches, more function calls

**Code Reference**:
```python
# member_cmd.py:4428
while get_next:
    get_next, rows_data = db_info.process_fetch_rows(
        status, dbms_cursor, "Query", 1, title_list, data_types_list
    )  # Fetch ONE row at a time
```

### 2. Dual Mode Operation

**Same function handles both network transmission and local output**.

**Rationale**:
- ✅ **Code Reuse**: Single codebase for both modes
- ✅ **Consistent Behavior**: Same formatting, same timing, same error handling
- ⚠️ **Complex Conditionals**: if/else branches throughout function

**Code Reference**:
```python
# member_cmd.py:4316
if message:  # Network mode (Operator → Query Node)
    # Open socket, send blocks over TCP
else:  # Local mode (Query Node or direct execution)
    # Use output_manager for local formatting
```

### 3. JSON Serialization

**All data formatted as JSON**, even for network transport.

**Rationale**:
- ✅ **Self-Describing**: Column names embedded in data
- ✅ **Easy Debugging**: Human-readable format
- ✅ **REST API Consistency**: Same format for internal and external APIs
- ⚠️ **Larger Payload**: JSON overhead vs. binary serialization
- ⚠️ **Parse Overhead**: JSON parsing on both ends

**Example**:
```json
{"Query":[{"device_name":"sensor1","temperature":23.5}]}
```

### 4. Block-Based Network Transfer

**Multiple rows packed into network blocks before sending**.

**Rationale**:
- ✅ **Reduces TCP Overhead**: Fewer TCP segments
- ✅ **Better Network Utilization**: Larger payloads
- ✅ **Buffered I/O**: Amortizes system call overhead
- ⚠️ **Complexity**: Row-to-block mapping logic

**Code Reference**:
```python
# member_cmd.py:4475-4517
while True:  # Pack rows into blocks
    block_full, bytes_not_copied = message_header.copy_data(mem_view, data_encoded, bytes_not_copied)

    if block_full:
        net_client.mem_view_send(soc, mem_view)  # Send full block
        block_number += 1
```

### 5. Optional Encryption

**Supports symmetric encryption for data in transit**.

**Rationale**:
- ✅ **Security**: Protects sensitive data between nodes
- ✅ **Configurable**: Can be enabled/disabled per deployment
- ⚠️ **Performance Overhead**: Encryption/decryption cost

**Code Reference**:
```python
# member_cmd.py:4340-4346
if version.al_auth_is_node_encryption():
    public_str = message_header.get_public_str(mem_view)
    if public_str:
        encrypted_key, f_object = version.al_auth_setup_encryption(status, public_str)

# member_cmd.py:4462-4469
if f_object:
    data_encoded = version.al_auth_symetric_encryption(status, f_object, rows_data)
else:
    data_encoded = rows_data.encode()
```

---

## Performance Characteristics

### Timing Breakdown

**Tracked Timers** (member_cmd.py:4297):
```python
timers = utils_timer.ProcessTimer(2)
# timer[0]: Database fetch time
# timer[1]: Network send time
```

**Time Components**:
- `sql_time`: Time to execute initial SQL statement
- `fetch_time`: Total time fetching all rows (`timers.get_timer(0)`)
- `network_time`: Total time sending data over network (`timers.get_timer(1)`)
- `operator_time`: Time operators spent processing (from message header)
- `dbms_time = operator_time + sql_time + fetch_time`

**Example Calculation**:
```
Operator Node:
  sql_time = 0.15 sec  (execute SELECT ...)
  fetch_time = 1.89 sec  (fetch 10,000 rows)
  network_time = 0.30 sec  (send data to Query Node)
  dbms_time = 0 + 0.15 + 1.89 = 2.04 sec

Query Node:
  operator_time = 2.04 sec  (from Operator)
  sql_time = 0.05 sec  (execute consolidation query)
  fetch_time = 0.02 sec  (fetch 10 aggregated rows)
  dbms_time = 2.04 + 0.05 + 0.02 = 2.11 sec
```

### Query Logging

**Slow Query Detection** (member_cmd.py:4568-4573):

```python
query_log_time = job_instance.get_query_log_time()
# -1 = no logging
#  0 = log all queries
# >0 = log queries slower than N seconds

if query_log_time >= 0 and query_log_time <= dbms_time:
    query_info = (f"Sec: {dbms_time:>4,} Rows: {fetch_counter:>6,} "
                  f"DBMS: {dbms_cursor.get_table_name()} SQL: {sql_command}")
    process_log.add("query", query_info)
```

**Example Log Entries**:
```
Sec:    2 Rows:  1,234 DBMS: sensor_data SQL: SELECT device_name, AVG(temperature) FROM sensor_data GROUP BY device_name
Sec:   12 Rows: 45,678 DBMS: query_42 SQL: SELECT * FROM query_42 WHERE timestamp > NOW() - INTERVAL '1 hour'
```

### Memory Usage

**Constant Memory Footprint**:
- Each row fetched individually (no buffering)
- Block size limited (typically 64KB)
- Old blocks released after sending

**Example**:
```
Query with 1,000,000 rows:
  Memory per row: ~500 bytes
  Block size: 64KB (holds ~128 rows)
  Total memory: ~64KB (constant, not 500MB)
```

### Network Efficiency

**Block Packing**:
- Multiple small rows packed into single TCP segment
- Reduces TCP overhead (headers, acknowledgments)
- Better utilization of network bandwidth

**Example**:
```
Without block packing:
  10,000 rows × 200 bytes/row = 2MB data
  10,000 TCP segments × 40 bytes/header = 400KB overhead
  Total: 2.4MB transferred

With block packing (64KB blocks):
  10,000 rows × 200 bytes/row = 2MB data
  31 blocks × 40 bytes/header = 1.24KB overhead
  Total: ~2MB transferred (17% less!)
```

---

## Error Handling

### Network Errors

**Socket Failures** (member_cmd.py:4332-4334):
```python
soc = net_client.socket_open(ip, port, "job reply", 6, 3)
if soc == None:
    status.add_error("Query process failed to open socket on: %s:%u" % (ip, port))
    return process_status.ERR_network
```

**Send Failures** (member_cmd.py:4492-4497):
```python
if not net_client.mem_view_send(soc, mem_view):
    timers.pause(1)
    ret_val = process_status.ERR_network
    break
```

### Database Errors

**Fetch Failures**:
```python
get_next, rows_data = db_info.process_fetch_rows(...)
if not rows_data:
    break  # No more rows or error
```

### Encryption Errors

**Setup Failures** (member_cmd.py:4344-4346):
```python
encrypted_key, f_object = version.al_auth_setup_encryption(status, public_str)
if not encrypted_key or not f_object:
    return process_status.Encryption_failed
```

**Encryption Failures** (member_cmd.py:4464-4467):
```python
data_encoded = version.al_auth_symetric_encryption(status, f_object, rows_data)
if not data_encoded:
    ret_val = process_status.Encryption_failed
    break
```

### Timeout Handling

**Query Timeouts** (member_cmd.py:4431-4438):
```python
max_time = interpreter.get_one_value(query_mode, "timeout")
max_volume = interpreter.get_one_value(query_mode, "max_volume")

if max_time:
    if timers.get_timer(0) > max_time:
        ret_val = process_status.QUERY_TIME_ABOVE_LIMIT
        break

if max_volume:
    if data_volume > max_volume:
        ret_val = process_status.QUERY_VOLUME_ABOVE_LIMIT
        break
```

---

## Advanced Features

### Extended Columns

**Adding Node Metadata** (member_cmd.py:4393-4419):

```python
if "extend" in conditions:
    # Example: extend = (@ip as Node IP, @port, @DBMS, @table)
    extend_columns = conditions["extend"]
    source_ip_port = net_utils.get_source_addr(dest_type, dest_ip)

    # Add metadata to each row
    extended_data = get_extend_data(
        source_ip_port,
        dbms_cursor.get_dbms_name(),
        dbms_cursor.get_table_name(),
        extend_columns,
        title_list,
        with_title
    )

    rows_data = rows_data[:11] + extended_data + rows_data[11:]
```

**Example**:
```sql
-- Query with extended metadata
SELECT device_name, temperature
FROM sensor_data
extend=(@ip as node_ip, @dbms as database_name);

-- Result includes metadata
{
  "Query": [
    {
      "node_ip": "192.168.1.10",
      "database_name": "iot_data",
      "device_name": "sensor1",
      "temperature": 23.5
    }
  ]
}
```

### Per-Column Limits

**Limiting Results Per Group** (member_cmd.py:4387-4391, 4537-4543):

```python
per_column = select_parsed.get_per_column()
# Example: "limit 1 per table" with extended tables

if per_column:
    per_counter_dict = {}
    limit = select_parsed.get_limit()

# In processing loop
if per_column:
    if not query_data:
        query_data = utils_json.str_to_json(rows_data)
    if query_data:
        if not process_limit(query_data["Query"], per_column,
                           per_counter_dict, limit):
            continue  # Skip this row (above limit for this group)
```

**Example**:
```sql
-- Return only 1 row per table
SELECT table_name, timestamp, value
FROM ping_sensor
extend=(@table_name as table)
ORDER BY timestamp DESC
LIMIT 1 per table;
```

### Timezone Conversion

**UTC to Local Time** (member_cmd.py:4525-4535):

```python
time_columns = select_parsed.get_date_types()  # List of timestamp columns
timezone = conditions.get("timezone")  # Target timezone

if (len(time_columns) and timezone != "utc"):
    query_data = utils_json.str_to_json(rows_data)
    if query_data:
        ret_val = utils_columns.change_columns_values(
            status,
            timezone,       # Target timezone (e.g., "America/New_York")
            time_columns,   # Which columns to convert
            casting_columns,
            casting_list,
            title_list,
            query_data['Query']
        )
```

---

## Integration with Query Flow

### Distributed Query Execution

```
┌─────────────────────────────────────────────────────────┐
│ 1. User Issues Query                                    │
│    run client () sql my_db "SELECT AVG(temp) FROM ..."  │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Query Transformation (Query Node)                    │
│    - unify_results.query_prep()                         │
│    - Generates: remote_query, local_create, local_query │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Send to Operators (Parallel)                         │
│    - send_command_message()                             │
│    - TCP message with remote_query                      │
└───────────────────────┬─────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    ┌─────────┐   ┌─────────┐   ┌─────────┐
    │ Op 1    │   │ Op 2    │   │ Op 3    │
    └────┬────┘   └────┬────┘   └────┬────┘
         │             │             │
         │  4. Execute Query (Each Operator)
         │     - _issue_sql()
         │     - query_local_dbms()
         │     - query_row_by_row()  ← NETWORK MODE
         │     - Fetch rows, send via TCP
         │
         └─────────────┼─────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 5. Receive Results (Query Node)                         │
│    - insert_query_rows()                                │
│    - Insert into temp table (query_N)                   │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│ 6. Consolidate (Query Node)                             │
│    - query_local_table()                                │
│    - Execute local_query on query_N                     │
│    - query_row_by_row()  ← LOCAL MODE                   │
│    - Fetch consolidated rows, output to user           │
└─────────────────────────────────────────────────────────┘
```

---

## Code References

All code references point to:
- **Repository**: https://github.com/EdgeLake/EdgeLake
- **Main Files**:
  - `edge_lake/cmd/member_cmd.py` - Query execution
  - `edge_lake/dbms/db_info.py` - Database abstraction
  - `edge_lake/dbms/psql_dbms.py` - PostgreSQL adapter
  - `edge_lake/dbms/sqlite_dbms.py` - SQLite adapter
  - `edge_lake/generic/utils_sql.py` - SQL utilities and formatting

---

## Summary

EdgeLake's SQL return functions implement a **sophisticated, streaming architecture** for query result retrieval:

1. **`query_row_by_row()`**: Main execution loop supporting both distributed (network) and local modes
2. **`process_fetch_rows()`**: Thin abstraction layer over DBMS-specific implementations
3. **DBMS `fetch_rows()`**: Database-specific fetching (PostgreSQL, SQLite, MongoDB, etc.)
4. **`format_db_rows()`**: JSON formatting with type-aware value representation

**Key Characteristics**:
- ✅ **Streaming**: Row-by-row processing, constant memory usage
- ✅ **Efficient**: Block-based network transfer, minimal overhead
- ✅ **Flexible**: Supports multiple output formats and destinations
- ✅ **Observable**: Comprehensive timing and logging
- ✅ **Secure**: Optional encryption for data in transit
- ✅ **Scalable**: Works with arbitrarily large result sets

This architecture enables EdgeLake to efficiently handle both local queries and distributed queries across edge nodes while maintaining a small memory footprint and providing comprehensive observability.
