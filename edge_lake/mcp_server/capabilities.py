"""
MCP Capability Detection

Determines which MCP tools should be enabled based on EdgeLake node configuration.

License: Mozilla Public License 2.0
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def detect_node_capabilities() -> Dict[str, Any]:
    """
    Detect what capabilities this EdgeLake node has.

    This function inspects the running EdgeLake node to determine:
    - What type of node it is (operator, query, master)
    - What services are running (REST, TCP, blockchain)
    - What databases are available
    - What operations it can perform

    Returns:
        Dictionary of capability flags and values
    """
    capabilities = {}

    try:
        # Import EdgeLake modules dynamically
        from edge_lake.members import aloperator
        from edge_lake.cmd import member_cmd

        # Node type detection
        capabilities['is_operator'] = _is_operator_active()
        capabilities['is_publisher'] = _is_publisher_active()
        capabilities['is_query'] = _is_query_pool_active()
        capabilities['is_master'] = _is_master_active()

        # Service detection
        capabilities['has_blockchain'] = _has_blockchain()
        capabilities['has_rest_server'] = _is_rest_server_active()
        capabilities['has_tcp_server'] = _is_tcp_server_active()

        # Data capabilities
        capabilities['local_databases'] = _get_local_databases()
        capabilities['can_write_blockchain'] = _can_write_blockchain()

        # Query capabilities
        capabilities['can_query_local'] = True  # All nodes can query local
        capabilities['can_query_network'] = _is_query_pool_active()

        # Operator capabilities
        if capabilities['is_operator']:
            capabilities['operator_clusters'] = _get_operator_clusters()

        logger.debug(f"Detected node capabilities: {capabilities}")

    except Exception as e:
        logger.error(f"Error detecting capabilities: {e}", exc_info=True)
        # Return safe defaults
        capabilities = {
            'is_operator': False,
            'is_publisher': False,
            'is_query': False,
            'is_master': False,
            'has_blockchain': False,
            'has_rest_server': False,
            'has_tcp_server': False,
            'local_databases': [],
            'can_write_blockchain': False,
            'can_query_local': True,
            'can_query_network': False,
        }

    return capabilities


def filter_tools_by_capability(capabilities: Dict[str, Any]) -> List[str]:
    """
    Determine which MCP tools to enable based on node capabilities.

    Args:
        capabilities: Node capability dictionary from detect_node_capabilities()

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

    # Blockchain tools (read-only for all nodes with blockchain)
    if capabilities.get('has_blockchain', False):
        enabled_tools.append('blockchain_get')
        enabled_tools.append('info_table')

    # Blockchain write (master nodes only)
    if capabilities.get('is_master', False) and capabilities.get('can_write_blockchain', False):
        enabled_tools.append('blockchain_post')

    # Query tools - local queries
    if capabilities.get('can_query_local', False):
        enabled_tools.append('query_local')

    # Query tools - network queries
    if capabilities.get('can_query_network', False):
        enabled_tools.append('query')

    # Operator-specific tools
    if capabilities.get('is_operator', False):
        enabled_tools.extend([
            'operator_status',
            'cluster_info',
        ])

    # Publisher-specific tools
    if capabilities.get('is_publisher', False):
        enabled_tools.append('publisher_status')

    # Query node specific tools
    if capabilities.get('is_query', False):
        enabled_tools.extend([
            'query_status',
        ])
        if not capabilities.get('is_operator', False):
            # Only add cluster_info if not already added
            enabled_tools.append('cluster_info')

    logger.debug(f"Enabled {len(enabled_tools)} MCP tools based on capabilities")
    logger.debug(f"Enabled tools: {enabled_tools}")

    return enabled_tools


def _is_operator_active() -> bool:
    """Check if operator service is active"""
    try:
        from edge_lake.members import aloperator
        return aloperator.is_active()
    except Exception as e:
        logger.debug(f"Error checking operator status: {e}")
        return False


def _is_publisher_active() -> bool:
    """Check if publisher service is active"""
    try:
        from edge_lake.cmd import member_cmd
        # Check if publisher is in the services dictionary and active
        if 'publisher' in member_cmd.services_:
            service_info = member_cmd.services_['publisher']
            if len(service_info) >= 2:
                is_active_func = service_info[1]
                return is_active_func()
        return False
    except Exception as e:
        logger.debug(f"Error checking publisher status: {e}")
        return False


def _is_query_pool_active() -> bool:
    """Check if query pool is active"""
    try:
        from edge_lake.cmd import member_cmd
        return member_cmd.is_query_pool_active()
    except Exception as e:
        logger.debug(f"Error checking query pool status: {e}")
        return False


def _is_master_active() -> bool:
    """Check if this is a master node"""
    try:
        # A master node typically has blockchain sync process running
        # and is configured to accept blockchain updates
        from edge_lake.cmd import member_cmd

        # Check if master node service is running
        master_cmd = member_cmd.commands.get("run blockchain sync")
        if master_cmd and master_cmd.get('thread'):
            thread = master_cmd['thread']
            if thread and hasattr(thread, 'is_alive') and thread.is_alive():
                return True

        return False
    except Exception as e:
        logger.debug(f"Error checking master node status: {e}")
        return False


def _has_blockchain() -> bool:
    """Check if blockchain/metadata layer is connected"""
    try:
        from edge_lake.cmd import member_cmd

        # Check if blockchain is configured
        blockchain_cmd = member_cmd.commands.get("run blockchain sync")
        if blockchain_cmd:
            return True

        # Alternative: check if local blockchain file exists
        from edge_lake.generic import params
        blockchain_file = params.get_value_if_available("!blockchain_file")
        if blockchain_file:
            import os
            return os.path.exists(blockchain_file)

        return False
    except Exception as e:
        logger.debug(f"Error checking blockchain status: {e}")
        return False


def _is_rest_server_active() -> bool:
    """Check if REST server is running"""
    try:
        from edge_lake.cmd import member_cmd
        rest_cmd = member_cmd.commands.get("run rest server")
        if rest_cmd:
            thread = rest_cmd.get('thread')
            if thread and hasattr(thread, 'is_alive'):
                return thread.is_alive()
        return False
    except Exception as e:
        logger.debug(f"Error checking REST server status: {e}")
        return False


def _is_tcp_server_active() -> bool:
    """Check if TCP server is running"""
    try:
        from edge_lake.cmd import member_cmd
        tcp_cmd = member_cmd.commands.get("run tcp server")
        if tcp_cmd:
            thread = tcp_cmd.get('thread')
            if thread and hasattr(thread, 'is_alive'):
                return thread.is_alive()
        return False
    except Exception as e:
        logger.debug(f"Error checking TCP server status: {e}")
        return False


def _get_local_databases() -> List[str]:
    """Get list of locally connected databases"""
    try:
        from edge_lake.dbms import db_info
        databases = db_info.get_connected_databases()
        return databases if databases else []
    except Exception as e:
        logger.debug(f"Error getting local databases: {e}")
        return []


def _can_write_blockchain() -> bool:
    """Check if node can write to blockchain"""
    try:
        # Master nodes can write
        # Also check if node has write permissions
        if _is_master_active():
            return True

        # Could also check for specific permissions here
        return False
    except Exception as e:
        logger.debug(f"Error checking blockchain write capability: {e}")
        return False


def _get_operator_clusters() -> List[str]:
    """Get list of clusters this operator participates in"""
    try:
        from edge_lake.members import aloperator
        if aloperator.is_active():
            # Get cluster information from operator
            clusters = aloperator.get_clusters()
            return clusters if clusters else []
        return []
    except Exception as e:
        logger.debug(f"Error getting operator clusters: {e}")
        return []


def get_capability_summary(capabilities: Dict[str, Any]) -> str:
    """
    Generate human-readable summary of node capabilities.

    Args:
        capabilities: Node capability dictionary

    Returns:
        Formatted string describing capabilities
    """
    lines = ["EdgeLake Node Capabilities:"]

    # Node type
    node_types = []
    if capabilities.get('is_operator'):
        node_types.append("Operator")
    if capabilities.get('is_query'):
        node_types.append("Query")
    if capabilities.get('is_publisher'):
        node_types.append("Publisher")
    if capabilities.get('is_master'):
        node_types.append("Master")

    if node_types:
        lines.append(f"  Node Type: {', '.join(node_types)}")
    else:
        lines.append("  Node Type: Generic")

    # Services
    lines.append("  Services:")
    lines.append(f"    REST Server: {'Active' if capabilities.get('has_rest_server') else 'Inactive'}")
    lines.append(f"    TCP Server: {'Active' if capabilities.get('has_tcp_server') else 'Inactive'}")
    lines.append(f"    Blockchain: {'Connected' if capabilities.get('has_blockchain') else 'Not Connected'}")

    # Data
    databases = capabilities.get('local_databases', [])
    if databases:
        lines.append(f"  Local Databases: {', '.join(databases)}")
    else:
        lines.append("  Local Databases: None")

    # Query capabilities
    lines.append("  Query Capabilities:")
    lines.append(f"    Local Queries: {'Yes' if capabilities.get('can_query_local') else 'No'}")
    lines.append(f"    Network Queries: {'Yes' if capabilities.get('can_query_network') else 'No'}")

    # Blockchain write
    if capabilities.get('can_write_blockchain'):
        lines.append("  Blockchain: Read/Write")
    elif capabilities.get('has_blockchain'):
        lines.append("  Blockchain: Read-Only")

    return "\n".join(lines)
