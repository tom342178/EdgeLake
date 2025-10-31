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

**MCP Server** (`edge_lake/mcp/`):
- `server/mcp_server.py`: MCP protocol server integrated with http_server.py
- `transport/sse_handler.py`: SSE transport layer for MCP over HTTP
- `core/query_builder.py`: SQL query construction from MCP tool parameters
- `core/query_executor.py`: Hybrid validation + streaming query execution
- `core/direct_client.py`: Direct integration with member_cmd.process_cmd()
- `core/command_builder.py`: EdgeLake command construction
- `tools/`: MCP tool definitions and executors

### Data Flow

1. **Data Ingestion**: Devices → (MQTT/REST/gRPC/JSON Files) → Operator Nodes → Local DBMS
2. **Query Processing**: Application → Query Node → (consult metadata) → Target Operator Nodes → Aggregate → Unified Reply
3. **Metadata Sync**: All nodes sync with shared metadata (Blockchain or Master Node) to coordinate operations

## Development Commands

### Build and Deploy Cycle

**IMPORTANT:** The project uses custom Makefile aliases for build and deploy operations.

```bash
# Build EdgeLake Docker image
mel build

# Deploy to environment
mel deploy work-from=home    # Deploy from local repository
mel deploy work-from=remote  # Deploy from remote repository

# Current working mode: work-from=remote
```

**Notes:**
- These are aliases to `../utilities/edgelake/Makefile` and can be run from anywhere in the project
- The tests in the Makefile are currently incompatible with the refactoring work in progress
- **Do NOT use `make test` commands** - they will not work during this refactoring phase
- Only use `mel build` and `mel deploy` commands

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

## MCP Server Integration (Refactoring In Progress)

### Overview

The MCP (Model Context Protocol) server is being refactored to integrate with EdgeLake's core HTTP infrastructure instead of using a standalone server. This enables unified HTTP handling, better resource management, and support for large query responses.

**Documentation**:
- **Design Document**: `edge_lake/mcp/DESIGN.md` - Complete architecture and technical specifications
- **Implementation Plan**: `edge_lake/mcp/IMPLEMENTATION_PLAN.md` - 4-week phased implementation with detailed tasks

### Current Status

**POC Implementation** (in `edge_lake/mcp/missing-context/`):
- Standalone server.py using Starlette/Uvicorn for SSE transport
- Working MCP protocol implementation
- Functional query builder, executor, and direct client

**Target Architecture** (refactoring to):
- Integrate with `edge_lake/tcpip/http_server.py` (production HTTP server)
- Use existing ThreadedHTTPServer and workers pool
- Leverage ChunkedHTTPRequestHandler for streaming
- Support block transport via message_server.py for large responses

### Key Components

1. **HTTP Server Integration** (`edge_lake/tcpip/http_server.py`):
   - New endpoints: `/mcp/sse` and `/mcp/messages/`
   - Reuses ThreadedHTTPServer infrastructure
   - Shares workers pool with REST API

2. **SSE Transport Layer** (`edge_lake/mcp/transport/sse_handler.py`):
   - SSE protocol implementation on top of http_server
   - MCP message framing and routing
   - Integration with ChunkedHTTPRequestHandler

3. **MCP Server** (`edge_lake/mcp/server/mcp_server.py`):
   - MCP protocol handlers (list_tools, call_tool)
   - Tool execution via direct_client
   - Configuration and lifecycle management

4. **Core Components** (preserved from POC):
   - `query_builder.py`: SQL query construction
   - `query_executor.py`: Hybrid validation + streaming (uses select_parser + process_fetch_rows)
   - `direct_client.py`: Direct member_cmd.process_cmd() integration
   - `command_builder.py`: EdgeLake command construction

5. **Block Transport** (for large results):
   - Uses message_server.py block transport
   - Threshold-based selection (>10MB)
   - Maintains streaming for efficiency

### Architecture Diagram

```
MCP Client (Claude/External)
         ↓ HTTP/SSE
edge_lake/tcpip/http_server.py
  - ThreadedHTTPServer
  - ChunkedHTTPRequestHandler
  - /mcp/sse endpoint
         ↓
edge_lake/mcp/transport/sse_handler.py
  - SSE protocol
  - MCP message framing
         ↓
edge_lake/mcp/server/mcp_server.py
  - list_tools, call_tool handlers
         ↓
edge_lake/mcp/core/
  - query_builder, query_executor
  - direct_client → member_cmd
         ↓
EdgeLake Core (member_cmd, dbms, etc.)
```

### Query Execution Flow

1. **MCP Tool Call** → MCP server receives tool request
2. **Query Building** → query_builder constructs SQL from parameters
3. **Validation** → query_executor.validate_query() calls select_parser()
   - Validates syntax and permissions
   - Transforms distributed queries (e.g., AVG → SUM+COUNT)
4. **Execution** → query_executor chooses mode:
   - **Streaming**: process_fetch_rows() for large results
   - **Batch**: Collect all rows for aggregates
5. **Transport** → Response via:
   - SSE streaming for normal queries
   - Block transport for large results (>10MB)

### Implementation Status

**Current Phase**: Phase 1 - Core Integration (Week 1)

**Next Tasks**:
1. Create SSE transport layer (`edge_lake/mcp/transport/sse_handler.py`)
2. Modify http_server.py for MCP endpoint routing
3. Refactor MCPServer class to remove Starlette/Uvicorn
4. Update member_cmd.py with `run mcp server` command
5. End-to-end integration testing

**Timeline**:
- Phase 1: Core Integration (Week 1) - IN PROGRESS
- Phase 2: Block Transport (Week 2)
- Phase 3: Testing & Documentation (Week 3)
- Phase 4: Production Deployment (Week 4)

See `edge_lake/mcp/IMPLEMENTATION_PLAN.md` for complete task breakdown and dependencies.

### Development Notes

- **Do NOT modify** files in `edge_lake/mcp/missing-context/` - these are the POC reference
- **Core components** (query_builder, query_executor, direct_client) are stable and will be preserved
- **Focus areas**: HTTP integration, SSE transport layer, block transport
- **Testing**: Use existing EdgeLake test infrastructure, not POC tests
- **Code Review**: All http_server.py changes require review to prevent REST API regressions

### Benefits

1. **Unified Infrastructure**: Single HTTP server for REST, data ingestion, and MCP
2. **Production Ready**: Leverages tested http_server.py with SSL, auth, logging
3. **Resource Efficiency**: Shared workers pool reduces overhead
4. **Large Response Support**: Block transport for massive query results
5. **Streaming**: Both SSE and chunked transfer encoding supported
