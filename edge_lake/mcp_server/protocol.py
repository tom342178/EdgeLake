"""
Lightweight MCP Protocol Implementation

This module provides minimal replacements for the official MCP SDK classes,
eliminating the need for the heavyweight 'mcp' package dependency.

This reduces binary size when compiling with Cython/PyInstaller.

License: Mozilla Public License 2.0
"""

from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass


@dataclass
class TextContent:
    """
    Represents text content in MCP protocol responses.

    Lightweight replacement for mcp.types.TextContent
    """
    type: str  # Always "text" for text content
    text: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "text": self.text
        }


@dataclass
class Tool:
    """
    Represents a tool definition in MCP protocol.

    Lightweight replacement for mcp.types.Tool
    """
    name: str
    description: str
    inputSchema: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }


class Server:
    """
    Lightweight MCP Server implementation.

    Provides decorator-based handler registration for MCP protocol methods.
    Replacement for mcp.server.Server without the heavy dependencies.
    """

    def __init__(self, name: str):
        """
        Initialize server.

        Args:
            name: Server name/identifier
        """
        self.name = name
        self._list_tools_handler: Optional[Callable[[], Awaitable]] = None
        self._call_tool_handler: Optional[Callable[[str, dict], Awaitable]] = None

    def list_tools(self):
        """
        Decorator to register the list_tools handler.

        Usage:
            @server.list_tools()
            async def list_tools():
                return [Tool(...), ...]
        """
        def decorator(func: Callable[[], Awaitable]):
            self._list_tools_handler = func
            return func
        return decorator

    def call_tool(self):
        """
        Decorator to register the call_tool handler.

        Usage:
            @server.call_tool()
            async def call_tool(name: str, arguments: dict):
                return [TextContent(...), ...]
        """
        def decorator(func: Callable[[str, dict], Awaitable]):
            self._call_tool_handler = func
            return func
        return decorator

    async def handle_list_tools(self):
        """
        Call the registered list_tools handler.

        Returns:
            List of Tool objects
        """
        if not self._list_tools_handler:
            raise RuntimeError("No list_tools handler registered")
        return await self._list_tools_handler()

    async def handle_call_tool(self, name: str, arguments: dict):
        """
        Call the registered call_tool handler.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            List of TextContent objects
        """
        if not self._call_tool_handler:
            raise RuntimeError("No call_tool handler registered")
        return await self._call_tool_handler(name, arguments)
