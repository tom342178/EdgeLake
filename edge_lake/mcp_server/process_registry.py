"""
EdgeLake MCP Server - Process Registry Integration

This module provides process registry functions for EdgeLake's 'get processes' command.
It maintains references to the MCP server instance and thread for status queries.

The MCP server itself is started via member_cmd.py's 'run mcp server' command,
not through this module.

License: Mozilla Public License 2.0
"""

# Global server instance and thread for status queries
_mcp_server_instance = None
_mcp_thread = None


def is_running() -> bool:
    """
    Check if MCP server is running.

    Returns:
        bool: True if server is running, False otherwise
    """
    global _mcp_thread
    return _mcp_thread is not None and _mcp_thread.is_alive()


def get_info(status=None) -> str:
    """
    Get MCP server status information for 'get processes' command.

    Args:
        status: ProcessStat object (for compatibility with EdgeLake pattern, not used)

    Returns:
        str: Status information string
    """
    global _mcp_server_instance

    if not is_running() or _mcp_server_instance is None:
        return "Not configured"

    server = _mcp_server_instance

    # Build info string similar to HTTP server pattern
    info_parts = []

    # Transport and listening info
    if server.transport == "sse" and server.port:
        info_parts.append(f"Listening on: 0.0.0.0:{server.port}")
    else:
        info_parts.append(f"Transport: {server.transport}")

    # Mode
    info_parts.append(f"Mode: {server.mode}")

    # Tool count
    if hasattr(server, 'config') and server.config:
        tool_count = len(server.config.tools)
        info_parts.append(f"Tools: {tool_count}")

    # Testing mode
    if hasattr(server, 'config') and server.config and server.config.testing_mode:
        info_parts.append("Testing: ON")

    return ", ".join(info_parts)
