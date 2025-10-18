"""
EdgeLake Direct Client

Direct integration client for embedded MCP server - calls member_cmd.process_cmd()
directly without HTTP overhead.

License: Mozilla Public License 2.0
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EdgeLakeDirectClient:
    """
    Direct integration client for EdgeLake MCP server.

    Calls member_cmd.process_cmd() directly instead of using HTTP,
    allowing the MCP server to run embedded within the EdgeLake process.
    """

    def __init__(self, max_workers: int = 10):
        """
        Initialize direct client.

        Args:
            max_workers: Maximum concurrent worker threads
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Import EdgeLake modules
        try:
            from edge_lake.cmd import member_cmd
            from edge_lake.generic import process_status, params

            self.member_cmd = member_cmd
            self.process_status = process_status
            self.params = params

            logger.info("EdgeLake direct client initialized")

        except ImportError as e:
            logger.error(f"Failed to import EdgeLake modules: {e}")
            raise

    async def execute_command(self, command: str, headers: Optional[Dict[str, str]] = None) -> Any:
        """
        Execute an EdgeLake command directly.

        Args:
            command: EdgeLake command string
            headers: Optional headers (for compatibility, mostly ignored in direct mode)

        Returns:
            Command result
        """
        logger.debug(f"Executing command directly: {command}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._sync_execute,
            command,
            headers
        )

    def _sync_execute(self, command: str, headers: Optional[Dict[str, str]] = None) -> Any:
        """
        Synchronous execution in thread pool.

        Args:
            command: EdgeLake command
            headers: Optional headers

        Returns:
            Command result
        """
        # Create status and buffer objects
        status = self.process_status.ProcessStat()

        # Get buffer size
        buff_size = int(self.params.get_param("io_buff_size"))
        io_buff = bytearray(buff_size)

        # Handle special headers (like destination for queries)
        if headers and 'destination' in headers:
            # Set destination in status or command context
            # For network queries, this would typically be handled by the command itself
            pass

        try:
            # Execute command via member_cmd
            ret_val = self.member_cmd.process_cmd(
                status,
                command=command,
                print_cmd=False,
                source_ip=None,
                source_port=None,
                io_buffer_in=io_buff
            )

            if ret_val == self.process_status.SUCCESS:
                # Extract result from status or buffer
                return self._extract_result(status, io_buff, command)
            else:
                # Command failed
                error_msg = status.get_saved_error() or f"Command failed with code {ret_val}"
                logger.error(f"Command execution failed: {error_msg}")
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}", exc_info=True)
            raise

    def _extract_result(self, status, io_buff: bytearray, command: str) -> Any:
        """
        Extract result from status object and buffer.

        Args:
            status: ProcessStat object
            io_buff: IO buffer
            command: Original command

        Returns:
            Extracted result
        """
        # Get result from status if available
        result_str = status.get_result()

        if result_str:
            # Try to parse as JSON
            try:
                return json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                return result_str

        # Try to get from buffer
        try:
            # Find null terminator
            null_pos = io_buff.find(b'\x00')
            if null_pos > 0:
                buffer_str = io_buff[:null_pos].decode('utf-8')
                if buffer_str:
                    try:
                        return json.loads(buffer_str)
                    except (json.JSONDecodeError, TypeError):
                        return buffer_str
        except Exception as e:
            logger.debug(f"Could not extract from buffer: {e}")

        # Return empty result for commands that don't produce output
        return ""

    async def get_databases(self) -> List[str]:
        """
        Get list of all databases from blockchain.

        Returns:
            List of database names
        """
        logger.info("Fetching databases")

        try:
            result = await self.execute_command("blockchain get table")

            # Parse databases from response
            if isinstance(result, str):
                databases = self._parse_databases_from_text(result)
            elif isinstance(result, list):
                databases = self._parse_databases_from_list(result)
            elif isinstance(result, dict):
                databases = self._parse_databases_from_dict(result)
            else:
                databases = []

            logger.info(f"Found {len(databases)} databases")
            return databases

        except Exception as e:
            logger.error(f"Failed to get databases: {e}")
            raise

    def _parse_databases_from_text(self, text: str) -> List[str]:
        """Parse database names from text table response"""
        databases = set()
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('|'):
                continue

            # Skip header lines
            if 'database' in line.lower() and 'table' in line.lower():
                continue

            # Parse table format with |
            if '|' in line:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if parts and len(parts) >= 1:
                    db_name = parts[0]
                    if db_name and not any(kw in db_name.lower() for kw in ['database', 'table', 'local', 'dbms']):
                        databases.add(db_name)
            else:
                # Simple format
                parts = line.split()
                if parts:
                    databases.add(parts[0])

        return sorted(list(databases))

    def _parse_databases_from_list(self, data: list) -> List[str]:
        """Parse database names from list of JSON objects"""
        databases = set()
        for item in data:
            if isinstance(item, dict):
                if "table" in item and isinstance(item["table"], dict):
                    db_name = item["table"].get("dbms")
                    if db_name:
                        databases.add(db_name)
                else:
                    db_name = item.get("dbms") or item.get("database") or item.get("db")
                    if db_name:
                        databases.add(db_name)

        return sorted(list(databases))

    def _parse_databases_from_dict(self, data: dict) -> List[str]:
        """Parse database names from dict response"""
        if "databases" in data:
            return data["databases"]
        elif "Database" in data:
            return data["Database"]
        else:
            return []

    async def get_tables(self, database: str) -> List[str]:
        """
        Get list of tables in a database.

        Args:
            database: Database name

        Returns:
            List of table names
        """
        logger.info(f"Fetching tables for database '{database}'")

        try:
            result = await self.execute_command("blockchain get table")

            # Parse tables from response
            if isinstance(result, str):
                tables = self._parse_tables_from_text(result, database)
            elif isinstance(result, list):
                tables = self._parse_tables_from_list(result, database)
            elif isinstance(result, dict):
                tables = self._parse_tables_from_dict(result)
            else:
                tables = []

            logger.info(f"Found {len(tables)} tables in '{database}'")
            return tables

        except Exception as e:
            logger.error(f"Failed to get tables for '{database}': {e}")
            raise

    def _parse_tables_from_text(self, text: str, database: str) -> List[str]:
        """Parse table names for a specific database from text response"""
        tables = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('|'):
                continue

            # Skip header lines
            if 'database' in line.lower() and 'table' in line.lower():
                continue

            # Parse table format with |
            if '|' in line:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2:
                    db_name = parts[0]
                    table_name = parts[1]
                    if db_name == database:
                        tables.append(table_name)
            else:
                # Simple format
                parts = line.split()
                if len(parts) >= 2 and parts[0] == database:
                    tables.append(parts[1])

        return tables

    def _parse_tables_from_list(self, data: list, database: str) -> List[str]:
        """Parse table names for a specific database from list response"""
        tables = []
        for item in data:
            if isinstance(item, dict):
                if "table" in item and isinstance(item["table"], dict):
                    db_name = item["table"].get("dbms")
                    table_name = item["table"].get("name")
                    if db_name == database and table_name:
                        tables.append(table_name)
                else:
                    db_name = item.get("dbms") or item.get("database") or item.get("db")
                    table_name = item.get("table") or item.get("table_name") or item.get("name")
                    if db_name == database and table_name:
                        tables.append(table_name)

        return tables

    def _parse_tables_from_dict(self, data: dict) -> List[str]:
        """Parse table names from dict response"""
        if "tables" in data:
            return data["tables"]
        elif "Table" in data:
            return data["Table"]
        else:
            return []

    async def get_table_schema(self, database: str, table: str) -> str:
        """
        Get schema for a specific table.

        Args:
            database: Database name
            table: Table name

        Returns:
            JSON string containing table schema
        """
        logger.info(f"Fetching schema for '{database}.{table}'")

        try:
            command = f'get columns where dbms="{database}" and table="{table}" and format=json'
            result = await self.execute_command(command)

            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            elif isinstance(result, str):
                return result
            else:
                return json.dumps({"schema": result}, indent=2)

        except Exception as e:
            logger.error(f"Failed to get schema for '{database}.{table}': {e}")
            raise

    async def execute_query(self, database: str, query: str, output_format: str = "json") -> str:
        """
        Execute SQL query against EdgeLake.

        Args:
            database: Database name
            query: SQL query to execute
            output_format: Output format ('json' or 'table')

        Returns:
            Query results as formatted string
        """
        logger.info(f"Executing query on '{database}': {query}")

        try:
            command = f'sql {database} format = {output_format} "{query}"'
            headers = {"destination": "network"}

            result = await self.execute_command(command, headers=headers)

            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            elif isinstance(result, str):
                return result
            else:
                return json.dumps({"result": result}, indent=2)

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    async def get_node_status(self) -> str:
        """
        Get EdgeLake node status.

        Returns:
            Node status information as JSON string
        """
        logger.info("Fetching node status")

        try:
            result = await self.execute_command("get status")

            if isinstance(result, dict):
                return json.dumps(result, indent=2)
            elif isinstance(result, str):
                return result
            else:
                return json.dumps({"status": result}, indent=2)

        except Exception as e:
            logger.error(f"Failed to get node status: {e}")
            raise

    def close(self):
        """Shutdown the thread pool executor"""
        logger.info("Shutting down EdgeLake direct client")
        self.executor.shutdown(wait=True)
