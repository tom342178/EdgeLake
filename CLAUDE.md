# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EdgeLake is a decentralized, peer-to-peer network platform that transforms edge nodes into a permissioned network enabling real-time data management, monitoring, and querying without moving data off-device. The system uses a shared metadata layer (blockchain or Master Node) to coordinate distributed data operations across edge nodes.

## Architecture

### Node Types

EdgeLake supports three primary node types, each configurable via environment variables and policies:

- **Operator Node** (`aloperator.py`): Captures data from devices/PLCs/applications and hosts it on a local DBMS (PostgreSQL, SQLite, MongoDB). Handles data ingestion and participates in distributed query execution.

- **Query Node**: Orchestrates distributed queries across Operator Nodes. Receives queries from applications, determines target nodes using shared metadata, aggregates results, and returns unified replies (MapReduce-style).

- **Master Node**: Stores network metadata policies as an alternative to blockchain. Serves as the central metadata repository when blockchain is not used.

### Core Components

**Command Processing** (`edge_lake/cmd/`):
- `member_cmd.py`: Main command processor (1000+ lines). Handles all EdgeLake commands via CLI
- `user_cmd.py`: Entry point for user input, CLI management, and interactive/background mode handling
- `data_monitor.py`: Data monitoring and tracking
- `native_api.py`: Native API interface

**Networking** (`edge_lake/tcpip/`):
- `message_server.py`, `tcpip_server.py`: TCP-based node-to-node communication
- `http_server.py`, `http_client.py`: REST API for queries and management
- `mqtt_client.py`: MQTT protocol support for IoT data streaming
- `grpc_client.py`: gRPC protocol support

**Database Management** (`edge_lake/dbms/`):
- `psql_dbms.py`: PostgreSQL adapter (recommended for larger nodes)
- `sqlite_dbms.py`: SQLite adapter (recommended for smaller nodes and in-memory data)
- `mongodb_dbms.py`: MongoDB adapter for blob storage
- `partitions.py`: Data partitioning and management
- `pi_dbms.py`: Performance indexing

**Blockchain/Metadata** (`edge_lake/blockchain/`):
- `blockchain.py`, `metadata.py`: Core metadata management
- `ethereum.py`, `hyperledger.py`: Blockchain platform integrations
- `bsync.py`: Blockchain synchronization
- Subdirectories for specific blockchain platforms: `alethereum/`, `alhyperledger/`, `aleos/`

**Data Processing** (`edge_lake/json_to_sql/`):
- `map_json_to_insert.py`: Maps JSON data to SQL inserts
- `mapping_policy.py`: Data mapping policies
- `suggest_create_table.py`: Auto-generates table schemas from JSON

**Job Scheduling** (`edge_lake/job/`):
- `job_scheduler.py`, `task_scheduler.py`: Schedule and execute recurring tasks
- `job_instance.py`: Job execution management

**API Integrations** (`edge_lake/api/`):
- `al_grafana.py`: Grafana integration for visualization
- `opcua_client.py`, `plc_client.py`: Industrial protocol support (OPC UA, PLC)
- `al_kafka.py`: Kafka integration
- `etherip_client.py`: EtherNet/IP protocol support

**Utilities** (`edge_lake/generic/`):
- `al_parser.py`: Command parsing
- `interpreter.py`: Command interpretation
- `params.py`: Parameter management (65k+ lines)
- `utils_*.py`: Various utilities for I/O, JSON, SQL, data handling, printing
- `streaming_data.py`: Data streaming management

### Data Flow

1. **Data Ingestion**: Devices → (MQTT/REST/gRPC/JSON Files) → Operator Nodes → Local DBMS
2. **Query Processing**: Application → Query Node → (consult metadata) → Target Operator Nodes → Aggregate → Unified Reply
3. **Metadata Sync**: All nodes sync with shared metadata (Blockchain or Master Node) to coordinate operations

## Development Commands

### Installation

Via Docker (recommended):
```bash
# Clone docker-compose repository
git clone https://github.com/EdgeLake/docker-compose
cd docker-compose

# Configure .env files for your node type
# Update LEDGER_CONN for Query and Operator nodes

# Deploy node
make up master    # Master node
make up operator  # Operator node
make up query     # Query node
```

Via Python (development):
```bash
# Install dependencies
pip install -r requirements.txt

# Run EdgeLake
python edge_lake/edgelake.py [arguments]
```

### Running EdgeLake

The main entry point is `edge_lake/edgelake.py`:
```bash
# Interactive mode
python edge_lake/edgelake.py

# Process script file
python edge_lake/edgelake.py process /path/to/script.al

# Execute commands
python edge_lake/edgelake.py "command1" and "command2"
```

### Environment Variables

Key environment variables (typically set via Docker .env files):
- `EDGELAKE_LIB`: Path to EdgeLake source directory
- `EDGELAKE_HOME`: Path to EdgeLake data directory
- `NODE_TYPE`: master, operator, query, or generic
- `NODE_NAME`: Name of the EdgeLake instance
- `ANYLOG_SERVER_PORT`: TCP protocol port (default: 32048)
- `ANYLOG_REST_PORT`: REST protocol port (default: 32049)
- `LEDGER_CONN`: Master node connection (format: ip:port)

## Key Technical Details

### Command Structure

EdgeLake uses a custom command language processed by `member_cmd.py`. Commands support:
- Multi-line commands using `< >` brackets
- Command chaining with `&` separator
- Variable substitution with `!variable` syntax
- JSON/dictionary parameters within commands

### Configuration Sources

Nodes can be configured via:
1. CLI commands (interactive or scripted)
2. Script files (`.al` files)
3. Policies stored in shared metadata (blockchain or Master Node)

### Database Support

Multiple databases can run on the same node. Database selection:
- SQLite: Default, no installation, good for smaller nodes
- PostgreSQL: Recommended for larger nodes with high data volume
- MongoDB: Only for blob storage requirements

### Security

The system uses a permissioned network model:
- Network policies control node participation
- Data ownership defined in metadata
- Supports JWT authentication (`pyjwt`)
- Cryptography support for secure communications

## Code Style

- Python 3.11+
- Mozilla Public License 2.0
- Uses Cython compilation for release builds
- Minimal external dependencies (see requirements.txt)
- Custom parameter/dictionary system (`params.py`) for configuration management

## MCP Server Architecture (CRITICAL)

**MCP Server Location**: `edge_lake/mcp_server/`

### Fundamental Design Constraint

**ALL tool behavior MUST be defined in `tools.yaml` and processed through generic handlers.**

**The executor (`tools/executor.py`) MUST NEVER contain tool-specific or hardcoded logic for individual tools.**

This is a non-negotiable architectural principle. When working on the MCP server:

#### ✅ Correct Approach
```python
# executor.py - Generic dispatcher
self.query_interfaces = {
    'blockchain_query': BlockchainQuery(),
    'node_query': NodeQuery()
}

async def execute_tool(self, name, arguments):
    if cmd_type in self.query_interfaces:
        # Generic routing - works for ALL query types
        result = await self._execute_query_interface(cmd_type, edgelake_cmd, arguments)
```

```yaml
# tools.yaml - Configuration defines behavior
- name: node_status
  edgelake_command:
    type: "node_query"
    query_type: "get_node_status"
```

#### ❌ Incorrect Approach (NEVER DO)
```python
# ❌ BAD: Tool-specific methods
async def _execute_blockchain_query(self, ...):
async def _execute_node_query(self, ...):

# ❌ BAD: Tool-specific conditionals
if name == "node_status":
    return await self._get_node_status()
```

### Adding New MCP Tools

1. **Create query module** (if new type needed): `core/new_query.py` with `execute_query()` method
2. **Register interface**: Add to `executor.py` `query_interfaces` dict
3. **Configure in tools.yaml**: Define tool with appropriate `type` and `query_type`

**NO changes to executor logic required** - it routes automatically.

### MCP Server Modes

- **Embedded Mode** (current): MCP server runs inside EdgeLake process, uses `direct_client.py` to call `member_cmd.process_cmd()` directly. Does NOT use `nodes.yaml`. Single node only.
- **Standalone Mode** (future): Separate process, HTTP client, multi-node support via `nodes.yaml`.

### Key MCP Files

- `server.py`: SSE-based MCP server entry point
- `autostart.al`: Autostart script for embedded mode
- `config/tools.yaml`: **Single source of truth** for ALL tool definitions
- `tools/executor.py`: Generic tool execution engine (NO tool-specific code)
- `core/blockchain_query.py`: Direct Python API access to blockchain metadata
- `core/node_query.py`: Direct Python API access to node information
- `core/direct_client.py`: Direct `member_cmd.process_cmd()` integration

### Why Direct Python APIs?

Commands like `blockchain get table` and `get status` print to stdout instead of populating `io_buff` when called via `member_cmd.process_cmd()`. Direct Python API access (e.g., `metadata.table_to_cluster_`) bypasses this limitation.

**Full details**: See `edge_lake/mcp_server/ARCHITECTURE.md`
