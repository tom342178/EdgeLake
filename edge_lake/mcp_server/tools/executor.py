"""
Tool Executor

Executes MCP tools and formats responses.

License: Mozilla Public License 2.0
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Executes MCP tools using EdgeLake client and formats responses.
    """
    
    def __init__(self, client, command_builder, query_builder, config):
        """
        Initialize tool executor.
        
        Args:
            client: EdgeLakeClient instance
            command_builder: CommandBuilder instance
            query_builder: QueryBuilder instance
            config: Config instance
        """
        self.client = client
        self.command_builder = command_builder
        self.query_builder = query_builder
        self.config = config
    
    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Execute a tool by name with given arguments.
        
        Args:
            name: Tool name
            arguments: Tool arguments
        
        Returns:
            List of TextContent dicts for MCP response
        """
        logger.info(f"Executing tool '{name}' with arguments: {arguments}")
        
        try:
            # Get tool configuration
            tool_config = self.config.get_tool_by_name(name)
            if not tool_config:
                raise ValueError(f"Unknown tool: {name}")
            
            # Handle node switching if custom node specified
            client = self._get_client_for_arguments(arguments)
            
            # Execute based on command type
            edgelake_cmd = tool_config.edgelake_command
            cmd_type = edgelake_cmd.get('type')
            
            if cmd_type == 'internal':
                result = await self._execute_internal(edgelake_cmd, arguments)
            else:
                result = await self._execute_edgelake_command(tool_config, arguments, client)
            
            # Format response
            return self._format_response(result)
            
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            return self._format_error(str(e))
    
    def _get_client_for_arguments(self, arguments: Dict[str, Any]):
        """
        Get appropriate client based on arguments (supports custom nodes).
        
        Args:
            arguments: Tool arguments
        
        Returns:
            EdgeLakeClient instance
        """
        # Check if custom node specified
        node_host = arguments.get('node_host')
        node_port = arguments.get('node_port')
        
        if node_host or node_port:
            if not self.config.allows_custom_nodes():
                logger.warning("Custom nodes not allowed, using default")
                return self.client
            
            # Use custom node
            host = node_host or self.config.get_default_node().host
            port = node_port or self.config.get_default_node().port
            
            logger.info(f"Using custom node: {host}:{port}")
            
            # Import here to avoid circular dependency
            from ..core.client import EdgeLakeClient
            return EdgeLakeClient(
                host=host,
                port=port,
                timeout=self.config.get_request_timeout(),
                max_workers=self.config.get_max_workers()
            )
        
        return self.client
    
    async def _execute_internal(self, edgelake_cmd: Dict[str, Any], 
                                arguments: Dict[str, Any]) -> str:
        """
        Execute internal command (handled by server, not EdgeLake).
        
        Args:
            edgelake_cmd: Command configuration
            arguments: Arguments
        
        Returns:
            Result string
        """
        method = edgelake_cmd.get('method', '')
        
        if method == 'server_info':
            return self._get_server_info()
        else:
            raise ValueError(f"Unknown internal method: {method}")
    
    def _get_server_info(self) -> str:
        """Get MCP server information"""
        from .. import __version__
        
        default_node = self.config.get_default_node()
        
        info = {
            "version": __version__,
            "server_name": "edgelake-mcp-server",
            "configuration": {
                "default_node": {
                    "name": default_node.name,
                    "host": default_node.host,
                    "port": default_node.port
                },
                "total_nodes": len(self.config.nodes),
                "total_tools": len(self.config.tools),
                "request_timeout": self.config.get_request_timeout(),
                "max_workers": self.config.get_max_workers(),
                "allows_custom_nodes": self.config.allows_custom_nodes()
            }
        }
        
        return json.dumps(info, indent=2)
    
    async def _execute_edgelake_command(self, tool_config, arguments: Dict[str, Any],
                                       client) -> str:
        """
        Execute EdgeLake command.
        
        Args:
            tool_config: Tool configuration
            arguments: Tool arguments
            client: EdgeLake client to use
        
        Returns:
            Result string
        """
        # Special handling for query tool
        if tool_config.name == 'query':
            return await self._execute_query(arguments, client)
        
        # Build command from template
        command, headers = self.command_builder.build_command(
            tool_config.edgelake_command,
            arguments
        )
        
        # Execute command
        result = await client.execute_command(command, headers=headers)
        
        # Parse response based on configuration
        parse_response = tool_config.edgelake_command.get('parse_response')
        if parse_response:
            result = self._parse_response(result, parse_response, arguments)
        
        # Format result
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        elif isinstance(result, list):
            return json.dumps(result, indent=2)
        else:
            return str(result)
    
    async def _execute_query(self, arguments: Dict[str, Any], client) -> str:
        """
        Execute SQL query tool.
        
        Args:
            arguments: Query arguments
            client: EdgeLake client
        
        Returns:
            Query results
        """
        database = arguments.get('database')
        output_format = arguments.get('format', 'json')
        
        # Build SQL query
        sql_query = self.query_builder.build_query(arguments)
        
        logger.info(f"Executing SQL: {sql_query}")
        
        # Execute query
        result = await client.execute_query(database, sql_query, output_format)
        
        return result
    
    def _parse_response(self, result: Any, parser_name: str, 
                       arguments: Dict[str, Any]) -> Any:
        """
        Parse EdgeLake response using configured parser.
        
        Args:
            result: Raw EdgeLake response
            parser_name: Name of parser to use
            arguments: Original arguments (for filtering)
        
        Returns:
            Parsed result
        """
        parser_config = self.config.response_parsers.get(parser_name)
        if not parser_config:
            logger.warning(f"Parser '{parser_name}' not found")
            return result
        
        parser_type = parser_config.get('type')
        
        if parser_type == 'blockchain_table':
            return self._parse_blockchain_table(result, parser_config, arguments)
        else:
            logger.warning(f"Unknown parser type: {parser_type}")
            return result
    
    def _parse_blockchain_table(self, result: Any, parser_config: Dict[str, Any],
                                arguments: Dict[str, Any]) -> Any:
        """
        Parse blockchain table response.
        
        Args:
            result: Response data
            parser_config: Parser configuration
            arguments: Original arguments
        
        Returns:
            Parsed data
        """
        extract = parser_config.get('extract')
        
        if extract == 'unique_databases':
            # Extract unique databases
            if isinstance(result, str):
                return self.client._parse_databases_from_text(result)
            elif isinstance(result, list):
                return self.client._parse_databases_from_list(result)
            else:
                return []
        
        elif extract == 'tables_for_database':
            # Extract tables for specific database
            database = arguments.get('database')
            if not database:
                return []
            
            if isinstance(result, str):
                return self.client._parse_tables_from_text(result, database)
            elif isinstance(result, list):
                return self.client._parse_tables_from_list(result, database)
            else:
                return []
        
        return result
    
    def _format_response(self, result: str) -> List[Dict[str, Any]]:
        """
        Format result as MCP TextContent.
        
        Args:
            result: Result string
        
        Returns:
            List of TextContent dicts
        """
        return [{
            "type": "text",
            "text": result
        }]
    
    def _format_error(self, error_message: str) -> List[Dict[str, Any]]:
        """
        Format error as MCP TextContent.
        
        Args:
            error_message: Error message
        
        Returns:
            List of TextContent dicts
        """
        return [{
            "type": "text",
            "text": f"Error: {error_message}"
        }]
