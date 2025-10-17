"""
Dynamic Tool Generator

Generates MCP Tool objects from configuration.

License: Mozilla Public License 2.0
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ToolGenerator:
    """
    Generates MCP Tool objects from tool configurations.
    """
    
    def __init__(self, tool_configs: List[Any]):
        """
        Initialize tool generator.
        
        Args:
            tool_configs: List of ToolConfig objects from configuration
        """
        self.tool_configs = tool_configs
    
    def generate_tools(self) -> List[Dict[str, Any]]:
        """
        Generate MCP Tool objects from configurations.
        
        Returns:
            List of Tool dictionaries for MCP protocol
        """
        tools = []
        
        for tool_config in self.tool_configs:
            try:
                tool = self._generate_tool(tool_config)
                tools.append(tool)
                logger.debug(f"Generated tool: {tool_config.name}")
            except Exception as e:
                logger.error(f"Failed to generate tool '{tool_config.name}': {e}")
        
        logger.info(f"Generated {len(tools)} tools")
        return tools
    
    def _generate_tool(self, tool_config: Any) -> Dict[str, Any]:
        """
        Generate a single MCP Tool object.
        
        Args:
            tool_config: ToolConfig object
        
        Returns:
            Tool dictionary
        """
        return {
            "name": tool_config.name,
            "description": tool_config.description,
            "inputSchema": tool_config.input_schema
        }
