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

            # Execute based on command type
            edgelake_cmd = tool_config.edgelake_command
            cmd_type = edgelake_cmd.get('type')

            if cmd_type == 'internal':
                result = await self._execute_internal(edgelake_cmd, arguments)
            else:
                # All other tools: build command from template and execute
                result = await self._execute_edgelake_command(tool_config, arguments, self.client)

            # Format response
            return self._format_response(result)

        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            return self._format_error(str(e))
    
    
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
        """Get MCP server information (embedded mode)"""
        from .. import __version__

        info = {
            "version": __version__,
            "server_name": "edgelake-mcp-server",
            "mode": "embedded",
            "configuration": {
                "total_tools": len(self.config.tools),
                "request_timeout": self.config.get_request_timeout(),
                "max_workers": self.config.get_max_workers()
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
        edgelake_cmd = tool_config.edgelake_command

        # Check if we need to build SQL query
        if edgelake_cmd.get('build_sql'):
            # Build SQL query from arguments
            sql_query = self.command_builder.build_sql_query(arguments)

            # Build full SQL command
            database = arguments.get('database')
            output_format = arguments.get('format', 'json')
            command = f'sql {database} format = {output_format} "{sql_query}"'

            # Get headers
            headers = edgelake_cmd.get('headers')

            logger.debug(f"Built SQL command: {command}")
        else:
            # Build command from template
            command, headers = self.command_builder.build_command(
                edgelake_cmd,
                arguments
            )

        # Execute command
        result = await client.execute_command(command, headers=headers)

        # Parse response based on configuration
        parse_response = edgelake_cmd.get('parse_response')
        if parse_response:
            result = self._parse_response(result, parse_response, arguments)

        # Format result
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        elif isinstance(result, list):
            return json.dumps(result, indent=2)
        else:
            return str(result)
    
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
            return self._extract_unique_databases(result)
        elif extract == 'tables_for_database':
            database = arguments.get('database')
            return self._extract_tables_for_database(result, database)

        return result

    def _extract_unique_databases(self, result: Any) -> List[str]:
        """
        Extract unique database names from blockchain table response.

        Args:
            result: Response data (list of dicts with 'table' key)

        Returns:
            List of unique database names
        """
        databases = set()

        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and 'table' in item:
                    table_info = item['table']
                    if isinstance(table_info, dict):
                        dbms = table_info.get('dbms')
                        if dbms:
                            databases.add(dbms)

        return sorted(list(databases))

    def _extract_tables_for_database(self, result: Any, database: str) -> List[str]:
        """
        Extract table names for a specific database from blockchain table response.

        Args:
            result: Response data (list of dicts with 'table' key)
            database: Database name to filter by

        Returns:
            List of table names for the database
        """
        if not database:
            return []

        tables = []

        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and 'table' in item:
                    table_info = item['table']
                    if isinstance(table_info, dict):
                        dbms = table_info.get('dbms')
                        table_name = table_info.get('name')
                        if dbms == database and table_name:
                            tables.append(table_name)

        return tables
    
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
