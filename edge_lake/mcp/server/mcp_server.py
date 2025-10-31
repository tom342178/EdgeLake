"""
MCP Server integrated with EdgeLake http_server.py

Refactored from POC to integrate with EdgeLake's production HTTP infrastructure.
Removed Starlette/Uvicorn dependencies in favor of SSE transport over http_server.py.

License: Mozilla Public License 2.0
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

# MCP imports
try:
    from mcp.server import Server
    from mcp.types import TextContent, Tool
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None
    TextContent = None
    Tool = None

# EdgeLake imports
from ..config import Config
from ..core import CommandBuilder, QueryBuilder, QueryExecutor
from ..core.direct_client import EdgeLakeDirectClient
from ..tools import ToolGenerator, ToolExecutor
from .. import __version__

logger = logging.getLogger(__name__)


class MCPServer:
    """
    MCP Server integrated with EdgeLake's http_server.py.

    Instead of running its own HTTP server (Starlette/Uvicorn), this version
    integrates with the existing EdgeLake HTTP infrastructure by registering
    endpoints with http_server.py and using SSETransport for communication.
    """

    def __init__(self, config_dir: str = None, enabled_tools: list = None,
                 capabilities: dict = None):
        """
        Initialize MCP server.

        Args:
            config_dir: Path to configuration directory (optional)
            enabled_tools: List of tool names to enable, or None for all
            capabilities: Node capability dictionary
        """
        self.enabled_tools = enabled_tools
        self.capabilities = capabilities or {}
        self.transport = None  # Will be set by start()

        # Load configuration
        if config_dir:
            self.config = Config(Path(config_dir))
        else:
            # Use default config directory
            config_path = Path(__file__).parent.parent / "config"
            self.config = Config(config_path)

        # Initialize direct client
        self.client = EdgeLakeDirectClient(
            max_workers=self.config.get_max_workers()
        )
        logger.debug("Direct EdgeLake client initialized")

        # Initialize builders
        self.command_builder = CommandBuilder()
        self.query_builder = QueryBuilder()
        self.query_executor = QueryExecutor()

        # Initialize tools
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

        # Initialize MCP protocol server
        if MCP_AVAILABLE:
            self.server = Server("edgelake-mcp-server")
            self._register_handlers()
            logger.info(f"MCP Server initialized (version={__version__})")
        else:
            self.server = None
            logger.error("MCP library not available - install with: pip install mcp")

    def _register_handlers(self):
        """Register MCP protocol handlers."""

        @self.server.list_tools()
        async def list_tools():
            """List available MCP tools."""
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
            """Execute a tool."""
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

    def start(self):
        """
        Start MCP server (register with http_server).

        Called by 'run mcp server' command in member_cmd.py.
        This initializes the SSE transport which integrates with http_server.py.
        """
        if not MCP_AVAILABLE:
            raise RuntimeError("MCP library not available - install with: pip install mcp")

        # Initialize SSE transport
        from ..transport.sse_handler import initialize as init_sse
        self.transport = init_sse(self)

        logger.info("MCP Server started and integrated with http_server.py")
        logger.info(f"Endpoints: GET /mcp/sse, POST /mcp/messages/{{session_id}}")

    def stop(self):
        """
        Stop MCP server and cleanup.

        Called by 'exit mcp server' command in member_cmd.py.
        """
        logger.info("Shutting down MCP Server")

        # Shutdown SSE transport
        if self.transport:
            from ..transport.sse_handler import shutdown as shutdown_sse
            shutdown_sse()
            self.transport = None

        # Close direct client
        if self.client:
            self.client.close()

        logger.info("MCP Server shutdown complete")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming MCP message (JSON-RPC).

        This method is called by SSETransport when a message is received
        via POST /mcp/messages/{session_id}.

        Args:
            message: JSON-RPC message from client

        Returns:
            JSON-RPC response
        """
        if not self.server:
            return {
                "jsonrpc": "2.0",
                "id": message.get('id'),
                "error": {
                    "code": -32603,
                    "message": "MCP server not initialized"
                }
            }

        # Extract method
        method = message.get('method')
        params = message.get('params', {})
        msg_id = message.get('id')

        logger.debug(f"Processing MCP method: {method}")

        try:
            # Route to appropriate handler
            if method == 'tools/list':
                # Call list_tools handler
                result = asyncio.run(self._call_list_tools())
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result
                }

            elif method == 'tools/call':
                # Call call_tool handler
                tool_name = params.get('name')
                arguments = params.get('arguments', {})

                result = asyncio.run(self._call_tool(tool_name, arguments))
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": result
                }

            else:
                # Unknown method
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

    async def _call_list_tools(self) -> List[Dict[str, Any]]:
        """
        Internal wrapper for list_tools handler.

        Returns:
            List of tool definitions as dicts
        """
        tools = self.tool_generator.generate_tools()

        # Convert Tool objects to dicts for JSON-RPC
        result = []
        for tool_dict in tools:
            result.append({
                "name": tool_dict['name'],
                "description": tool_dict['description'],
                "inputSchema": tool_dict['inputSchema']
            })

        return result

    async def _call_tool(self, name: str, arguments: dict) -> List[Dict[str, Any]]:
        """
        Internal wrapper for call_tool handler.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            List of content items as dicts
        """
        result = await self.tool_executor.execute_tool(name, arguments)

        # Convert to JSON-RPC format
        json_result = []
        for item in result:
            json_result.append({
                "type": "text",
                "text": item['text']
            })

        return json_result

    def get_info(self) -> Dict[str, Any]:
        """
        Get server information (for debugging/monitoring).

        Returns:
            Server info dict
        """
        active_connections = []
        if self.transport:
            active_connections = self.transport.get_active_connections()

        return {
            "version": __version__,
            "mcp_available": MCP_AVAILABLE,
            "active_connections": len(active_connections),
            "connection_ids": active_connections,
            "enabled_tools": self.enabled_tools or "all",
            "transport": "SSE over http_server.py"
        }
