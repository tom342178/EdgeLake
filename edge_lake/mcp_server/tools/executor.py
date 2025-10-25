"""
Tool Executor

Executes MCP tools and formats responses.

License: Mozilla Public License 2.0
"""

import json
import logging
from typing import Any, Dict, List, Optional
from jsonpath_ng import parse as jsonpath_parse

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

        # For network queries, wrap with 'run client ()' to distribute across network
        if headers and headers.get('destination') == 'network':
            command = f'run client () {command}'
            logger.debug(f"Network query - wrapped with run client: {command}")

        # Execute command
        result = await client.execute_command(command, headers=headers)

        # Parse response based on inline response_parser configuration
        response_parser = edgelake_cmd.get('response_parser')
        if response_parser:
            result = self._parse_response(result, response_parser, arguments)

        # Format result
        if isinstance(result, dict):
            return json.dumps(result, indent=2)
        elif isinstance(result, list):
            return json.dumps(result, indent=2)
        else:
            return str(result)
    
    def _parse_response(self, result: Any, parser_config: Dict[str, Any],
                       arguments: Dict[str, Any]) -> Any:
        """
        Parse EdgeLake response using configured parser.

        Args:
            result: Raw EdgeLake response
            parser_config: Parser configuration (inline from tool definition)
            arguments: Original arguments (for filtering)

        Returns:
            Parsed result
        """
        parser_type = parser_config.get('type')

        if parser_type == 'jsonpath':
            logger.info(f"Parsing response with JSONPath parser")
            # Apply JSONPath extraction (direct_client already handled CLI noise)
            return self._parse_with_jsonpath(result, parser_config, arguments)
        else:
            logger.warning(f"Unknown parser type: {parser_type}")
            return result
    
    def _parse_with_jsonpath(self, result: Any, parser_config: Dict[str, Any],
                            arguments: Dict[str, Any]) -> Any:
        """
        Generic JSONPath-based parser.

        All extraction logic is driven by configuration in tools.yaml.
        This method contains NO tool-specific logic.

        Args:
            result: Data to parse (must be dict/list, not string)
            parser_config: Parser configuration from tools.yaml
            arguments: Original tool arguments (for filtering)

        Returns:
            Extracted data
        """
        # Ensure result is parsed JSON
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse result as JSON: {e}")
                return result

        # Get JSONPath expression from config
        extract_path = parser_config.get('extract_path')
        if not extract_path:
            logger.warning("JSONPath parser missing 'extract_path'")
            return result

        try:
            # Log the input data structure for debugging
            logger.debug(f"Input to JSONPath: {json.dumps(result, indent=2) if len(json.dumps(result)) < 2000 else str(result)[:2000] + '...'}")

            # Parse and apply JSONPath expression
            jsonpath_expr = jsonpath_parse(extract_path)
            matches = jsonpath_expr.find(result)

            # Extract values from matches
            extracted = [match.value for match in matches]

            logger.info(f"JSONPath '{extract_path}' extracted {len(extracted)} items")
            logger.debug(f"Extracted data: {json.dumps(extracted, indent=2) if len(json.dumps(extracted)) < 1000 else str(extracted)[:1000] + '...'}")

            # Apply filtering if configured
            if 'filter' in parser_config:
                filter_config = parser_config['filter']
                field = filter_config.get('field')
                source = filter_config.get('source')
                argument_name = filter_config.get('argument')

                if source == 'argument' and argument_name:
                    filter_value = arguments.get(argument_name)
                    if filter_value:
                        extracted = [
                            item for item in extracted
                            if isinstance(item, dict) and item.get(field) == filter_value
                        ]
                        logger.debug(f"Filtered to {len(extracted)} items where {field}={filter_value}")

            # Apply field mapping if configured
            if 'map' in parser_config:
                map_field = parser_config['map']
                extracted = [
                    item.get(map_field) if isinstance(item, dict) else item
                    for item in extracted
                ]
                logger.debug(f"Mapped to field '{map_field}'")

            # Apply uniqueness if configured
            if parser_config.get('unique'):
                extracted = list(set(extracted))
                logger.debug(f"Applied unique filter, {len(extracted)} unique items")

            # Apply sorting if configured
            if parser_config.get('sort'):
                extracted = sorted(extracted)
                logger.debug("Applied sorting")

            # Log final result at INFO level
            logger.info(f"JSONPath extraction complete: returning {len(extracted) if isinstance(extracted, list) else 1} items")

            return extracted

        except Exception as e:
            logger.error(f"JSONPath extraction failed: {e}", exc_info=True)
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
