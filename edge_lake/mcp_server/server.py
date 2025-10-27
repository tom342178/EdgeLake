"""
EdgeLake MCP Server

Main MCP server implementation with support for standalone (stdio) 
and threaded (embedded) modes.

License: Mozilla Public License 2.0
"""

import asyncio
import sys
import os
import logging
import threading
from pathlib import Path

# Setup logging
log_dir = Path.home() / "Library" / "Logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "edgelake_mcp.log"

# Allow log level to be configured via environment variable
log_level = os.getenv('MCP_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('edgelake-mcp-server')

# Import MCP types
try:
    from mcp.server import Server
    from mcp.types import TextContent, Tool
    from pydantic import AnyUrl
    MCP_AVAILABLE = True
except ImportError:
    logger.warning("MCP library not available. Install with: pip install mcp")
    MCP_AVAILABLE = False

# Local imports
from . import __version__
from .config import Config
from .core import EdgeLakeClient, CommandBuilder, QueryBuilder
from .tools import ToolGenerator, ToolExecutor


class EdgeLakeMCPServer:
    """
    EdgeLake MCP Server supporting multiple deployment modes.
    """
    
    def __init__(self, mode: str = "standalone", config_dir: str = None,
                 port: int = None, transport: str = "stdio",
                 enabled_tools: list = None, capabilities: dict = None):
        """
        Initialize MCP server.

        Args:
            mode: Deployment mode ("standalone", "threaded", or "embedded")
            config_dir: Path to configuration directory (optional)
            port: Port number (for future use)
            transport: Transport mode ("stdio" or "sse")
            enabled_tools: List of tool names to enable, or None for all
            capabilities: Node capability dictionary
        """
        self.mode = mode
        self.port = port
        self.transport = transport
        self.enabled_tools = enabled_tools
        self.capabilities = capabilities or {}

        # Load configuration
        if config_dir:
            self.config = Config(Path(config_dir))
        else:
            # Use default config directory
            config_path = Path(__file__).parent / "config"
            self.config = Config(config_path)

        # Initialize client based on mode
        if mode == "embedded":
            # Use direct integration client (no HTTP)
            from .core.direct_client import EdgeLakeDirectClient
            self.client = EdgeLakeDirectClient(
                max_workers=self.config.get_max_workers()
            )
            logger.debug("Using direct EdgeLake integration (embedded mode)")
        else:
            # Use HTTP client for standalone/threaded modes
            default_node = self.config.get_default_node()
            self.client = EdgeLakeClient(
                host=default_node.host,
                port=default_node.port,
                timeout=self.config.get_request_timeout(),
                max_workers=self.config.get_max_workers()
            )
            logger.debug(f"Using HTTP client: {default_node.host}:{default_node.port}")

        # Initialize builders and generators
        self.command_builder = CommandBuilder()
        self.query_builder = QueryBuilder()
        self.tool_generator = ToolGenerator(
            self.config.get_all_tools(),
            enabled_tools=enabled_tools
        )
        self.tool_executor = ToolExecutor(
            self.client,
            self.command_builder,
            self.query_builder,
            self.config
        )

        # Initialize MCP server if available
        if MCP_AVAILABLE:
            self.server = Server("edgelake-mcp-server")
            self._register_handlers()
        else:
            self.server = None
            logger.error("MCP not available - server will not function")

        # Log initialization
        tool_count = len(enabled_tools) if enabled_tools else 'all'
        logger.info(f"EdgeLake MCP Server initialized (mode={mode}, version={__version__})")
        logger.info(f"Transport: {transport}, Tools: {tool_count}")
    
    def _register_handlers(self):
        """Register MCP protocol handlers"""
        
        @self.server.list_tools()
        async def list_tools():
            """List available MCP tools"""
            logger.debug("Listing tools")
            tools = self.tool_generator.generate_tools()

            # Convert to MCP Tool objects
            mcp_tools = []
            for tool_dict in tools:
                mcp_tools.append(Tool(
                    name=tool_dict['name'],
                    description=tool_dict['description'],
                    inputSchema=tool_dict['inputSchema']
                ))

            logger.debug(f"Returning {len(mcp_tools)} tools")
            return mcp_tools
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict):
            """Execute a tool"""
            logger.debug(f"Calling tool '{name}' with arguments: {arguments}")

            try:
                result = await self.tool_executor.execute_tool(name, arguments)
                
                # Convert to MCP TextContent objects
                mcp_result = []
                for item in result:
                    mcp_result.append(TextContent(
                        type="text",
                        text=item['text']
                    ))
                
                return mcp_result
                
            except Exception as e:
                logger.error(f"Error calling tool '{name}': {e}", exc_info=True)
                return [TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
        
        @self.server.list_resources()
        async def list_resources():
            """List available resources (databases and tables)"""
            logger.debug("Listing resources")

            try:
                resources = []

                # Get all databases
                databases = await self.client.get_databases()
                logger.debug(f"Found {len(databases)} databases")
                
                # For each database, get its tables
                for db_name in databases:
                    # Add database-level resource
                    resources.append({
                        "uri": f"database://{db_name}",
                        "name": f"Database: {db_name}",
                        "description": f"All tables in database '{db_name}'",
                        "mimeType": "application/json"
                    })
                    
                    # Get tables
                    tables = await self.client.get_tables(db_name)
                    logger.debug(f"Database '{db_name}' has {len(tables)} tables")
                    
                    # Add table-level resources
                    for table_name in tables:
                        resources.append({
                            "uri": f"database://{db_name}/{table_name}",
                            "name": f"{db_name}.{table_name}",
                            "description": f"Table '{table_name}' in database '{db_name}'",
                            "mimeType": "application/json"
                        })


                logger.debug(f"Returning {len(resources)} resources")
                return resources
                
            except Exception as e:
                logger.error(f"Error listing resources: {e}", exc_info=True)
                return []
        
        @self.server.read_resource()
        async def read_resource(uri: str):
            """Read a resource (table schema)"""
            logger.debug(f"Reading resource: {uri}")

            try:
                # Parse URI
                if not uri.startswith("database://"):
                    raise ValueError(f"Invalid URI scheme: {uri}")
                
                path = uri[11:]  # Remove "database://"
                parts = path.split("/")
                
                if len(parts) == 1:
                    # Database-level resource - return list of tables
                    db_name = parts[0]
                    tables = await self.client.get_tables(db_name)
                    content = f"Tables in database '{db_name}':\n"
                    content += "\n".join(f"  - {t}" for t in tables)
                    return content
                
                elif len(parts) == 2:
                    # Table-level resource - return schema
                    db_name, table_name = parts
                    schema = await self.client.get_table_schema(db_name, table_name)
                    return schema
                
                else:
                    raise ValueError(f"Invalid resource URI format: {uri}")
                    
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}", exc_info=True)
                return f"Error reading resource: {str(e)}"
    
    async def run_standalone(self):
        """Run server in standalone mode using stdio transport"""
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available")

        logger.info("Starting EdgeLake MCP Server in standalone mode")

        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

    async def run_sse_server(self, host: str = "0.0.0.0", port: int = None):
        """
        Run server with SSE (Server-Sent Events) transport.

        This method starts an HTTP server that communicates via SSE, allowing
        external MCP clients to connect over HTTP instead of stdin/stdout.

        Args:
            host: Host to bind to (default: 0.0.0.0)
            port: Port to listen on (from self.port or 50051)
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available")

        # Get port
        listen_port = port or self.port or 50051

        logger.info(f"Starting EdgeLake MCP Server with SSE transport on {host}:{listen_port}")

        try:
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route, Mount
            from starlette.responses import Response
            import uvicorn
        except ImportError as e:
            logger.error(f"SSE dependencies not available: {e}")
            logger.error("Install with: pip install sse-starlette starlette uvicorn")
            raise

        # Create SSE transport
        sse = SseServerTransport("/messages/")

        # Define SSE endpoint handler
        async def handle_sse(request):
            async with sse.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await self.server.run(
                    streams[0], streams[1], self.server.create_initialization_options()
                )
            return Response()

        # Create Starlette app with routes
        app = Starlette(
            routes=[
                Route("/sse", endpoint=handle_sse, methods=["GET"]),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )

        # Configure uvicorn
        config = uvicorn.Config(
            app,
            host=host,
            port=listen_port,
            log_level="info",
            access_log=False  # Reduce noise, we have our own logging
        )

        server = uvicorn.Server(config)

        # Store server reference for shutdown
        self.sse_server = server

        # Run server
        await server.serve()

    def run_embedded(self):
        """
        Run server in embedded mode (within EdgeLake process).

        This method is called from a background thread started by member_cmd.py.
        Chooses transport based on self.transport parameter:
        - "stdio": Uses stdio transport (conflicts with EdgeLake CLI, not recommended)
        - "sse": Uses SSE transport over HTTP (recommended for embedded mode)
        """
        if not MCP_AVAILABLE:
            logger.error("MCP library not available")
            return

        logger.info(f"Starting EdgeLake MCP Server in embedded mode (transport={self.transport})")

        try:
            if self.transport == "sse":
                # Run SSE server - this is the recommended mode for embedded operation
                asyncio.run(self.run_sse_server())
            else:
                # Run stdio server - will conflict with EdgeLake's CLI
                logger.warning("Using stdio transport in embedded mode may conflict with EdgeLake CLI")
                logger.warning("Recommend using transport='sse' instead")
                asyncio.run(self.run_standalone())
        except Exception as e:
            logger.error(f"Error in embedded MCP server: {e}", exc_info=True)

    def run_threaded(self):
        """
        Run server in threaded mode (legacy/deprecated - use run_embedded instead).

        This method is kept for backward compatibility but now just calls run_embedded.
        """
        logger.warning("run_threaded() is deprecated, use run_embedded() instead")
        self.run_embedded()
    
    def close(self):
        """Shutdown server and cleanup resources"""
        logger.info("Shutting down EdgeLake MCP Server")

        # Shutdown SSE server if running
        if hasattr(self, 'sse_server') and self.sse_server:
            logger.debug("Shutting down SSE server")
            try:
                self.sse_server.should_exit = True
            except Exception as e:
                logger.error(f"Error shutting down SSE server: {e}")

        # Close client
        self.client.close()


async def async_main():
    """Async main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='EdgeLake MCP Server')
    parser.add_argument('--mode', choices=['standalone', 'threaded'], 
                       default='standalone',
                       help='Server mode (default: standalone)')
    parser.add_argument('--config-dir', type=str, default=None,
                       help='Configuration directory path')
    parser.add_argument('--version', action='version', 
                       version=f'edgelake-mcp-server {__version__}')
    
    args = parser.parse_args()
    
    # Create and run server
    server = EdgeLakeMCPServer(mode=args.mode, config_dir=args.config_dir)
    
    try:
        if args.mode == 'standalone':
            await server.run_standalone()
        else:
            server.run_threaded()
    except KeyboardInterrupt:
        logger.debug("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        server.close()


def main():
    """Synchronous entry point"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.debug("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
