#!/usr/bin/env python3
"""
Standalone EdgeLake MCP Server with SSE Transport

This script runs the MCP server in standalone mode using SSE transport,
suitable for Docker containers and remote connections.

Usage:
    python run-mcp-sse-server.py [--port PORT] [--host HOST]

Example:
    python run-mcp-sse-server.py --port 50051 --host 0.0.0.0
"""

import asyncio
import argparse
import sys
import os

# Add EdgeLake to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from edge_lake.mcp_server.server import EdgeLakeMCPServer


async def main():
    parser = argparse.ArgumentParser(description='EdgeLake MCP Server (SSE Mode)')
    parser.add_argument('--port', type=int, default=50051,
                       help='Port to listen on (default: 50051)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                       help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--config-dir', type=str, default=None,
                       help='Configuration directory path')

    args = parser.parse_args()

    print(f"Starting EdgeLake MCP Server (SSE mode)")
    print(f"  Host: {args.host}")
    print(f"  Port: {args.port}")
    print(f"  Endpoint: http://{args.host}:{args.port}/sse")
    print()

    # Create server with SSE transport in embedded mode (uses direct client)
    server = EdgeLakeMCPServer(
        mode="embedded",
        config_dir=args.config_dir,
        port=args.port,
        transport="sse"
    )

    try:
        # Run SSE server
        await server.run_sse_server(host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        server.close()


if __name__ == "__main__":
    asyncio.run(main())
