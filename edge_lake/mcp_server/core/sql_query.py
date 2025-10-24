"""
SQL Query Interface

Executes SQL queries using EdgeLake's native query execution paths.
Supports both distributed (network) and local query execution.

License: Mozilla Public License 2.0
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SqlQuery:
    """
    SQL query interface for MCP server.

    Routes SQL queries to appropriate EdgeLake entry points:
    - network: Distributed queries using native_api (like REST/HTTP)
    - local: Local-only queries using direct execution
    """

    def __init__(self, client, query_builder):
        """
        Initialize SQL query interface.

        Args:
            client: EdgeLakeDirectClient instance
            query_builder: QueryBuilder instance for building SQL
        """
        self.client = client
        self.query_builder = query_builder

        # Import EdgeLake native_api for distributed queries
        try:
            from edge_lake.cmd import native_api
            self.native_api = native_api
            logger.info("SQL query interface initialized with native_api support")
        except ImportError as e:
            logger.error(f"Failed to import native_api: {e}")
            self.native_api = None

    async def execute_query(self, query_type: str, **params) -> Dict[str, Any]:
        """
        Execute SQL query based on type.

        Args:
            query_type: Type of query execution ("network" or "local")
            **params: Query parameters including:
                - database: Database name
                - table: Table name
                - select: Columns to select
                - where: WHERE clause
                - group_by: GROUP BY columns
                - order_by: ORDER BY specifications
                - limit: Row limit
                - format: Output format (json/table)

        Returns:
            Query results as dict
        """
        logger.info(f"Executing {query_type} SQL query")

        # Extract parameters
        database = params.get('database')
        output_format = params.get('format', 'json')

        if not database:
            raise ValueError("Database name is required for SQL queries")

        # Build SQL from parameters
        sql_query = self.query_builder.build_query(params)
        logger.info(f"Built SQL: {sql_query}")

        if query_type == "network":
            return await self._execute_network_query(database, sql_query, output_format, params)
        elif query_type == "local":
            return await self._execute_local_query(database, sql_query, output_format)
        else:
            raise ValueError(f"Unknown query type: {query_type}")

    async def _execute_network_query(self, database: str, sql_query: str,
                                     output_format: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute distributed query across EdgeLake network.

        Uses native_api.exec_sql_stmt() which handles:
        - Job context setup
        - Distributed execution
        - Waiting for operator replies
        - Result aggregation

        Args:
            database: Database name
            sql_query: SQL query string
            output_format: Output format
            params: Additional parameters

        Returns:
            Query results
        """
        if not self.native_api:
            raise RuntimeError("native_api not available - cannot execute network queries")

        logger.info(f"Executing network query on database '{database}'")

        # Note: For now, we'll use the simpler direct_client approach
        # In the future, we can integrate with native_api.exec_sql_stmt()
        # for full distributed query support with job scheduling

        # TODO: Integrate with native_api.exec_sql_stmt() for proper distributed execution
        # This requires:
        # 1. Creating a status object
        # 2. Setting up job handle
        # 3. Calling exec_sql_stmt with servers parameter
        # 4. Waiting for distributed replies

        # For now, use the existing execute_query method which calls execute_command
        result = await self.client.execute_query(database, sql_query, output_format)

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"result": result}

    async def _execute_local_query(self, database: str, sql_query: str,
                                   output_format: str) -> Dict[str, Any]:
        """
        Execute query on local node only.

        Args:
            database: Database name
            sql_query: SQL query string
            output_format: Output format

        Returns:
            Query results
        """
        logger.info(f"Executing local query on database '{database}'")

        # Build command for local execution (no network routing)
        command = f'sql {database} format = {output_format} "{sql_query}"'

        # Execute directly via client
        result = await self.client.execute_command(command)

        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"result": result}
