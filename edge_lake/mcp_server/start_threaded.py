"""
EdgeLake MCP Server - Threaded Mode Startup

This module provides functions to start the EdgeLake MCP server in threaded mode,
allowing it to run as a background service within the EdgeLake node process.

Usage in EdgeLake startup:
    from edge_lake.mcp_server.start_threaded import start_mcp_server_threaded

    # Start MCP server in background thread
    mcp_thread = start_mcp_server_threaded(config_dir=None)

License: Mozilla Public License 2.0
"""

import threading
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger('edgelake-mcp-server')

# Global server instance for status queries
_mcp_server_instance = None
_mcp_thread = None


def start_mcp_server_threaded(config_dir: Optional[str] = None) -> threading.Thread:
    """
    Start EdgeLake MCP server in a background thread.

    Args:
        config_dir: Path to configuration directory (optional)

    Returns:
        threading.Thread: The background thread running the server

    Example:
        >>> mcp_thread = start_mcp_server_threaded()
        >>> # Server now running in background
        >>> # To stop: (requires implementing stop mechanism in server)
    """
    global _mcp_server_instance, _mcp_thread

    try:
        from .server import EdgeLakeMCPServer

        logger.debug("Starting EdgeLake MCP Server in threaded mode")

        # Create server instance
        server = EdgeLakeMCPServer(mode="threaded", config_dir=config_dir)
        _mcp_server_instance = server

        # Create and start thread
        mcp_thread = threading.Thread(
            target=server.run_threaded,
            name="EdgeLakeMCPServer",
            daemon=True
        )
        mcp_thread.start()
        _mcp_thread = mcp_thread

        logger.debug(f"EdgeLake MCP Server thread started (thread_id={mcp_thread.ident})")
        return mcp_thread

    except ImportError as e:
        logger.error(f"Failed to import EdgeLake MCP Server: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to start EdgeLake MCP Server thread: {e}", exc_info=True)
        raise


def main():
    """
    Main entry point for running threaded mode from command line.
    This keeps the main thread alive while the MCP server runs in background.
    """
    import argparse
    import time

    parser = argparse.ArgumentParser(description='EdgeLake MCP Server - Threaded Mode')
    parser.add_argument('--config-dir', type=str, default=None,
                       help='Configuration directory path')

    args = parser.parse_args()

    # Start server thread
    mcp_thread = start_mcp_server_threaded(config_dir=args.config_dir)

    print(f"EdgeLake MCP Server running in background (thread_id={mcp_thread.ident})")
    print("Press Ctrl+C to stop...")

    try:
        # Keep main thread alive
        while mcp_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping EdgeLake MCP Server...")
        logger.debug("EdgeLake MCP Server stopped by user")


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


if __name__ == "__main__":
    main()
