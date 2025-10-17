"""
EdgeLake HTTP Client

Multi-threaded async client for EdgeLake REST API communication.

License: Mozilla Public License 2.0
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests.exceptions import HTTPError, RequestException
except ImportError:
    # If requests not available, use urllib as fallback
    import urllib.request
    import urllib.error
    requests = None

logger = logging.getLogger(__name__)


class EdgeLakeClient:
    """
    Async HTTP client for EdgeLake REST API with thread pool execution.
    """
    
    def __init__(self, host: str, port: int, timeout: int = 20, max_workers: int = 10):
        """
        Initialize EdgeLake client.
        
        Args:
            host: EdgeLake node IP/hostname
            port: EdgeLake REST API port (typically 32049)
            timeout: Request timeout in seconds
            max_workers: Maximum concurrent worker threads
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        logger.info(f"EdgeLake client initialized: {self.base_url}")
    
    def _execute_request_with_requests(self, method: str, command: str, 
                                       headers: Optional[Dict[str, str]] = None) -> Any:
        """Execute request using requests library"""
        request_headers = {
            "User-Agent": "anylog",
            "command": command,
        }
        
        if headers:
            request_headers.update(headers)
        
        logger.debug(f"Request: {method} {self.base_url}, command='{command}'")
        
        try:
            if method.upper() == "GET":
                response = requests.get(
                    url=self.base_url,
                    headers=request_headers,
                    timeout=self.timeout,
                    verify=False
                )
            elif method.upper() == "POST":
                response = requests.post(
                    url=self.base_url,
                    headers=request_headers,
                    timeout=self.timeout,
                    verify=False
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            if response.status_code != 200:
                error_msg = f"EdgeLake returned status {response.status_code}"
                if hasattr(response, 'text'):
                    error_msg += f": {response.text}"
                raise Exception(error_msg)
            
            # Try to parse as JSON
            try:
                return response.json()
            except ValueError:
                return response.text
                
        except HTTPError as e:
            logger.error(f"HTTP error: {e}")
            raise Exception(f"HTTP error: {str(e)}")
        except RequestException as e:
            logger.error(f"Request error: {e}")
            raise Exception(f"Request error: {str(e)}")
    
    def _execute_request_with_urllib(self, method: str, command: str,
                                     headers: Optional[Dict[str, str]] = None) -> Any:
        """Execute request using urllib as fallback"""
        request_headers = {
            "User-Agent": "anylog",
            "command": command,
        }
        
        if headers:
            request_headers.update(headers)
        
        logger.debug(f"Request (urllib): {method} {self.base_url}, command='{command}'")
        
        try:
            req = urllib.request.Request(
                self.base_url,
                headers=request_headers,
                method=method.upper()
            )
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = response.read().decode('utf-8')
                
                # Try to parse as JSON
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return data
                    
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP error {e.code}: {e.reason}"
            logger.error(error_msg)
            raise Exception(error_msg)
        except urllib.error.URLError as e:
            logger.error(f"URL error: {e.reason}")
            raise Exception(f"URL error: {e.reason}")
    
    def _execute_request(self, method: str, command: str,
                        headers: Optional[Dict[str, str]] = None) -> Any:
        """
        Execute HTTP request to EdgeLake (synchronous, runs in thread pool).
        
        Args:
            method: HTTP method (GET, POST)
            command: EdgeLake command to execute
            headers: Optional additional headers
        
        Returns:
            Response data (parsed JSON or text)
        
        Raises:
            Exception: On request failure
        """
        if requests is not None:
            return self._execute_request_with_requests(method, command, headers)
        else:
            return self._execute_request_with_urllib(method, command, headers)
    
    async def _async_request(self, method: str, command: str,
                             headers: Optional[Dict[str, str]] = None) -> Any:
        """
        Execute HTTP request asynchronously using thread pool.
        
        Args:
            method: HTTP method
            command: EdgeLake command
            headers: Optional headers
        
        Returns:
            Response data
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._execute_request,
            method,
            command,
            headers
        )
    
    async def execute_command(self, command: str, method: str = "GET",
                             headers: Optional[Dict[str, str]] = None) -> Any:
        """
        Execute an EdgeLake command.
        
        Args:
            command: EdgeLake command string
            method: HTTP method (default: GET)
            headers: Optional headers
        
        Returns:
            Response data
        """
        return await self._async_request(method, command, headers)
    
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
        logger.info("Shutting down EdgeLake client")
        self.executor.shutdown(wait=True)
