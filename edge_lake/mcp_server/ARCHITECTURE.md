# EdgeLake MCP Service Architecture

## Overview

This document describes the integration of MCP (Model Context Protocol) as a **native EdgeLake service**, similar to REST and TCP services. The MCP service dynamically adapts its capabilities based on node type and configuration.

## Node-Aware MCP Services

### Capability Matrix

Different EdgeLake node types expose different MCP tools based on their role:

| MCP Tool | Master Node | Query Node | Operator Node | Description |
|----------|-------------|------------|---------------|-------------|
| `list_databases` | ✅ | ✅ | ✅ | List all databases in network |
| `list_tables` | ✅ | ✅ | ✅ | List tables in a database |
| `get_schema` | ✅ | ✅ | ✅ | Get table schema |
| `query` | ❌ | ✅ | ✅ (local only) | Execute SQL queries |
| `node_status` | ✅ | ✅ | ✅ | Get node status |
| `blockchain_get` | ✅ | ✅ | ✅ | Query blockchain metadata |
| `blockchain_post` | ✅ | ❌ | ❌ | Post policy to blockchain |
| `operator_status` | ❌ | ✅ | ✅ | Get operator statistics |
| `cluster_info` | ❌ | ✅ | ✅ | Get cluster information |
| `publisher_status` | ❌ | ❌ | ✅ | Get publisher status |
| `server_info` | ✅ | ✅ | ✅ | Get MCP server info |

### Node Type Detection

The MCP server automatically detects node capabilities:

```python
# Detect what services are running
def detect_node_capabilities():
    capabilities = {
        'is_master': is_master_node_active(),
        'is_operator': aloperator.is_active(),
        'is_publisher': is_publisher_active(),
        'is_query': is_query_pool_active(),
        'has_blockchain': blockchain.is_connected(),
        'local_dbms': get_connected_databases()
    }
    return capabilities
```

## Integration Points

### 1. Command Registration in `member_cmd.py`

Add MCP server command to the commands dictionary:

```python
'run mcp server': {
    'command': _run_mcp_server,
    'words_min': 3,
    'help': {
        'usage': 'run mcp server where port = [port] and mode = [stdio/sse] and tools = [auto/all/tool1,tool2]',
        'example': 'run mcp server where port = 50051 and mode = stdio and tools = auto',
        'text': 'Enable MCP (Model Context Protocol) service\n'
                '[port] - MCP service port (default: 50051)\n'
                '[mode] - Transport mode: stdio (default) or sse (Server-Sent Events)\n'
                '[tools] - Tool selection: auto (based on node type), all, or comma-separated list',
        'link': 'blob/master/mcp_integration.md',
        'keywords': ["configuration", "background processes", "mcp", "ai"],
    },
    'trace': 0,
    'mode': None,
    'port': 0,
    'thread': None,
    'tools': [],
    'capabilities': {},
},

'get mcp server': {
    'command': _get_mcp_server_status,
    'words_count': 3,
    'help': {
        'usage': 'get mcp server',
        'example': 'get mcp server',
        'text': 'Get MCP server status and enabled tools',
    },
},

'exit mcp server': {
    'command': _exit_mcp_server,
    'words_count': 3,
    'help': {
        'usage': 'exit mcp server',
        'example': 'exit mcp server',
        'text': 'Stop the MCP server',
    },
},
```

### 2. Service Lifecycle Management

#### Start MCP Server

```python
def _run_mcp_server(status, io_buff_in, cmd_words, trace):
    """
    Start MCP server as EdgeLake background service.

    Example: run mcp server where port = 50051 and tools = auto
    """
    global commands

    # Check if already running
    if commands["run mcp server"]['thread'] and commands["run mcp server"]['thread'].is_alive():
        status.add_error("MCP server already running")
        return process_status.ERR_process_status

    # Parse parameters
    ret_val, counter, conditions = interpreter.get_dict_from_words(
        status, cmd_words, 4, 0, mcp_server_params, False
    )
    if ret_val:
        return ret_val

    port = conditions.get('port', 50051)
    mode = conditions.get('mode', 'stdio')
    tools_config = conditions.get('tools', 'auto')

    # Import MCP server
    try:
        from edge_lake.mcp_server.server import EdgeLakeMCPServer
        from edge_lake.mcp_server.capabilities import detect_node_capabilities, filter_tools_by_capability
    except ImportError as e:
        status.add_error(f"Failed to import MCP server: {e}")
        return process_status.ERR_process_status

    # Detect node capabilities
    capabilities = detect_node_capabilities()

    # Determine which tools to enable
    if tools_config == 'auto':
        enabled_tools = filter_tools_by_capability(capabilities)
    elif tools_config == 'all':
        enabled_tools = None  # Enable all tools
    else:
        enabled_tools = tools_config.split(',')

    # Create server with direct integration
    try:
        mcp_server = EdgeLakeMCPServer(
            mode='embedded',
            port=port,
            transport=mode,
            enabled_tools=enabled_tools,
            capabilities=capabilities
        )

        # Start in background thread
        mcp_thread = threading.Thread(
            target=mcp_server.run_embedded,
            name="EdgeLakeMCPServer",
            daemon=True
        )
        mcp_thread.start()

        # Store server state
        commands["run mcp server"]['mode'] = mode
        commands["run mcp server"]['port'] = port
        commands["run mcp server"]['thread'] = mcp_thread
        commands["run mcp server"]['tools'] = enabled_tools or 'all'
        commands["run mcp server"]['capabilities'] = capabilities

        # Log startup
        if trace:
            utils_print.output(f"\r\n[MCP Server] Started on port {port} with {len(enabled_tools) if enabled_tools else 'all'} tools", True)

        return process_status.SUCCESS

    except Exception as e:
        status.add_error(f"Failed to start MCP server: {e}")
        return process_status.ERR_process_status


def _get_mcp_server_status(status, io_buff_in, cmd_words, trace):
    """Get MCP server status"""
    global commands

    mcp_cmd = commands["run mcp server"]

    if not mcp_cmd['thread'] or not mcp_cmd['thread'].is_alive():
        utils_print.output("\r\nMCP server is not running", True)
        return process_status.SUCCESS

    # Build status message
    output = [
        "\r\nMCP Server Status:",
        f"  Mode: {mcp_cmd['mode']}",
        f"  Port: {mcp_cmd['port']}",
        f"  Thread: {mcp_cmd['thread'].name} (alive={mcp_cmd['thread'].is_alive()})",
        f"  Tools: {mcp_cmd['tools']}",
        "\r\nNode Capabilities:",
    ]

    for capability, value in mcp_cmd['capabilities'].items():
        output.append(f"  {capability}: {value}")

    utils_print.output("\r\n".join(output), True)
    return process_status.SUCCESS


def _exit_mcp_server(status, io_buff_in, cmd_words, trace):
    """Stop MCP server"""
    global commands

    mcp_cmd = commands["run mcp server"]

    if not mcp_cmd['thread'] or not mcp_cmd['thread'].is_alive():
        status.add_error("MCP server is not running")
        return process_status.ERR_process_status

    # TODO: Implement graceful shutdown
    # For now, thread will stop when daemon thread exits

    mcp_cmd['thread'] = None
    mcp_cmd['mode'] = None
    mcp_cmd['port'] = 0
    mcp_cmd['tools'] = []

    if trace:
        utils_print.output("\r\n[MCP Server] Stopped", True)

    return process_status.SUCCESS
```

### 3. Capability Detection Module

Create `edge_lake/mcp_server/capabilities.py`:

```python
"""
MCP Capability Detection

Determines which MCP tools should be enabled based on EdgeLake node configuration.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def detect_node_capabilities() -> Dict[str, any]:
    """
    Detect what capabilities this EdgeLake node has.

    Returns:
        Dictionary of capability flags
    """
    # Import EdgeLake modules
    from edge_lake.members import aloperator
    from edge_lake.cmd import member_cmd
    from edge_lake.blockchain import metadata
    from edge_lake.dbms import db_info

    capabilities = {
        # Node type flags
        'is_operator': aloperator.is_active(),
        'is_publisher': _is_publisher_active(),
        'is_query': member_cmd.is_query_pool_active(),
        'is_master': _is_master_active(),

        # Service flags
        'has_blockchain': metadata.is_connected(),
        'has_rest_server': _is_rest_server_active(),
        'has_tcp_server': _is_tcp_server_active(),

        # Data capabilities
        'local_databases': db_info.get_connected_databases(),
        'can_write_blockchain': _can_write_blockchain(),

        # Query capabilities
        'can_query_local': True,  # All nodes can query local
        'can_query_network': member_cmd.is_query_pool_active(),
    }

    logger.info(f"Detected node capabilities: {capabilities}")
    return capabilities


def filter_tools_by_capability(capabilities: Dict[str, any]) -> List[str]:
    """
    Determine which MCP tools to enable based on capabilities.

    Args:
        capabilities: Node capability dictionary

    Returns:
        List of tool names to enable
    """
    enabled_tools = []

    # Tools available to all nodes
    enabled_tools.extend([
        'list_databases',
        'list_tables',
        'get_schema',
        'node_status',
        'server_info',
    ])

    # Blockchain tools (read-only for all)
    if capabilities['has_blockchain']:
        enabled_tools.append('blockchain_get')
        enabled_tools.append('info_table')

    # Blockchain write (master nodes only)
    if capabilities['is_master'] and capabilities['can_write_blockchain']:
        enabled_tools.append('blockchain_post')

    # Query tools
    if capabilities['can_query_local']:
        enabled_tools.append('query_local')

    if capabilities['can_query_network']:
        enabled_tools.append('query')

    # Operator-specific tools
    if capabilities['is_operator']:
        enabled_tools.extend([
            'operator_status',
            'cluster_info',
        ])

    # Publisher-specific tools
    if capabilities['is_publisher']:
        enabled_tools.append('publisher_status')

    # Query node specific tools
    if capabilities['is_query']:
        enabled_tools.extend([
            'query_status',
            'cluster_info',
        ])

    logger.info(f"Enabled {len(enabled_tools)} MCP tools: {enabled_tools}")
    return enabled_tools


def _is_publisher_active() -> bool:
    """Check if publisher service is active"""
    try:
        from edge_lake.cmd import member_cmd
        return member_cmd.is_service_active('publisher')
    except:
        return False


def _is_master_active() -> bool:
    """Check if this is a master node"""
    try:
        from edge_lake.blockchain import metadata
        return metadata.is_master_node()
    except:
        return False


def _is_rest_server_active() -> bool:
    """Check if REST server is running"""
    try:
        from edge_lake.cmd import member_cmd
        return member_cmd.commands["run rest server"].get('thread') is not None
    except:
        return False


def _is_tcp_server_active() -> bool:
    """Check if TCP server is running"""
    try:
        from edge_lake.cmd import member_cmd
        return member_cmd.commands["run tcp server"].get('thread') is not None
    except:
        return False


def _can_write_blockchain() -> bool:
    """Check if node can write to blockchain"""
    try:
        from edge_lake.blockchain import metadata
        return metadata.can_write()
    except:
        return False
```

### 4. Dynamic Tool Registration

Modify `edge_lake/mcp_server/tools/generator.py`:

```python
def generate_tools(self, enabled_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Generate MCP Tool objects from configurations.

    Args:
        enabled_tools: List of tool names to enable, or None for all

    Returns:
        List of Tool dictionaries for MCP protocol
    """
    tools = []

    for tool_config in self.tool_configs:
        # Filter by enabled tools
        if enabled_tools is not None and tool_config.name not in enabled_tools:
            logger.debug(f"Skipping tool '{tool_config.name}' (not enabled)")
            continue

        try:
            tool = self._generate_tool(tool_config)
            tools.append(tool)
            logger.debug(f"Generated tool: {tool_config.name}")
        except Exception as e:
            logger.error(f"Failed to generate tool '{tool_config.name}': {e}")

    logger.info(f"Generated {len(tools)} tools")
    return tools
```

## Configuration Examples

### Master Node

```bash
# Start MCP server with auto-detection (enables blockchain_post)
run mcp server where mode = stdio and tools = auto

# Enabled tools:
# - list_databases, list_tables, get_schema
# - blockchain_get, blockchain_post, info_table
# - node_status, server_info
```

### Query Node

```bash
# Start MCP server with auto-detection
run mcp server where port = 50051 and tools = auto

# Enabled tools:
# - list_databases, list_tables, get_schema
# - query, query_status
# - blockchain_get, info_table
# - cluster_info
# - node_status, server_info
```

### Operator Node

```bash
# Start MCP server with auto-detection
run mcp server where tools = auto

# Enabled tools:
# - list_databases, list_tables, get_schema
# - query_local (local queries only)
# - blockchain_get, info_table
# - operator_status, cluster_info
# - node_status, server_info
```

### Custom Tool Selection

```bash
# Enable specific tools only
run mcp server where tools = "list_databases,query,node_status"

# Enable all tools regardless of node type
run mcp server where tools = all
```

## Startup Script Integration

### In `.al` Initialization Files

```
# EdgeLake node startup script

# Start core services
<run tcp server where internal_ip = !ip and internal_port = !anylog_server_port>
<run rest server where internal_ip = !ip and internal_port = !anylog_rest_port>

# Start MCP service (auto-detect capabilities)
<run mcp server where mode = stdio and tools = auto>
```

### Docker Environment Variables

```bash
# Add to docker-compose .env
ENABLE_MCP_SERVER=true
MCP_SERVER_PORT=50051
MCP_SERVER_MODE=stdio
MCP_TOOLS=auto
```

## Benefits

1. ✅ **Node-Aware**: Automatically adapts to node type and capabilities
2. ✅ **Secure**: Only exposes appropriate tools per node type
3. ✅ **Flexible**: Can override with custom tool selection
4. ✅ **Consistent**: Uses same patterns as other EdgeLake services
5. ✅ **Observable**: `get mcp server` shows current state
6. ✅ **Configurable**: Works in startup scripts and interactively

## Future Enhancements

- Dynamic tool reloading when services start/stop
- Permission-based tool access control
- MCP tool metrics and usage tracking
- Multi-client MCP server support
- WebSocket transport in addition to stdio/SSE
