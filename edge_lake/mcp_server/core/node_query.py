"""
Node Query Module

Generic, configuration-driven node data access for EdgeLake MCP server.
Uses direct Python APIs to access node status and information.

License: Mozilla Public License 2.0
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class NodeQuery:
    """
    Generic node query interface driven by configuration.

    Provides direct access to node information without command parsing.
    """

    def __init__(self):
        """Initialize node query interface"""
        # Import node info module on init
        from edge_lake.generic import node_info
        self.node_info = node_info

        logger.info("Node query interface initialized")

    def get_node_status(self) -> Dict[str, Any]:
        """
        Get node status information.

        Returns:
            Dict with node status details
        """
        # Get node name which includes ID (e.g., "edgelake-query@4.1.104.250:32348")
        node_name = self.node_info.get_node_name()

        # Parse the node name to extract components
        # Format: name@ip:port or name@ip
        if '@' in node_name:
            name, node_id = node_name.split('@', 1)
        else:
            name = node_name
            node_id = "unknown"

        # Build status dict
        status = {
            "node_name": node_name,
            "name": name,
            "node_id": node_id,
            "status": "running"
        }

        logger.debug(f"Node status: {status}")
        return status

    def execute_query(self, query_type: str, **kwargs) -> Any:
        """
        Generic query execution driven by configuration.

        Args:
            query_type: Type of query to execute
            **kwargs: Query-specific parameters

        Returns:
            Query result

        Raises:
            ValueError: If query_type is unknown
        """
        query_map = {
            'get_node_status': self.get_node_status,
        }

        if query_type not in query_map:
            raise ValueError(f"Unknown node query type: {query_type}")

        query_func = query_map[query_type]

        # Call with appropriate arguments
        return query_func(**kwargs)