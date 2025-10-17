"""
EdgeLake MCP Server

Provides MCP (Model Context Protocol) interface to EdgeLake distributed database.

License: Mozilla Public License 2.0
"""

__version__ = "1.0.0"
__author__ = "EdgeLake"

from .config import Config, NodeConfig, ToolConfig

__all__ = ['Config', 'NodeConfig', 'ToolConfig', '__version__']
