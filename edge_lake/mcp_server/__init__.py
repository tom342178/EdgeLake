"""
EdgeLake MCP Server

Provides MCP (Model Context Protocol) interface to EdgeLake distributed database.

License: Mozilla Public License 2.0
"""

__version__ = "1.0.0"
__author__ = "EdgeLake"

from .config import Config, ToolConfig
from .capabilities import detect_node_capabilities, filter_tools_by_capability, get_capability_summary
from .server import EdgeLakeMCPServer

__all__ = [
    'Config',
    'ToolConfig',
    'EdgeLakeMCPServer',
    'detect_node_capabilities',
    'filter_tools_by_capability',
    'get_capability_summary',
    '__version__',
]
