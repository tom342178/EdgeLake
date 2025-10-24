"""
EdgeLake Direct Client

Direct integration client for embedded MCP server - calls member_cmd.process_cmd()
directly without HTTP overhead. For network queries, uses REST API to ensure proper
distributed query handling.

License: Mozilla Public License 2.0
"""

import asyncio
import io
import json
import logging
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
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

    async def execute_command(self, command: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0) -> Any:
        """
        Execute an EdgeLake command.

        For network queries (headers.destination == 'network'), uses REST API to ensure
        proper distributed query handling. For other commands, calls process_cmd() directly.

        Args:
            command: EdgeLake command string
            headers: Optional headers - 'destination: network' triggers REST API
            timeout: Command timeout in seconds (default: 30)

        Returns:
            Command result

        Raises:
            asyncio.TimeoutError: If command execution exceeds timeout
        """
        # Check if this is a network query that should use REST API
        if headers and headers.get('destination') == 'network':
            logger.debug(f"Executing network query via REST API: {command}")
            return await self._execute_via_rest(command, timeout)

        # Otherwise execute directly
        logger.debug(f"Executing command directly: {command}")

        loop = asyncio.get_event_loop()

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor,
                    self._sync_execute,
                    command,
                    headers
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Command timed out after {timeout}s: {command}")
            raise TimeoutError(f"Command execution timed out after {timeout} seconds: {command}")

    def _sync_execute(self, command: str, headers: Optional[Dict[str, str]] = None) -> Any:
        """
        Synchronous execution in thread pool.

        Args:
            command: EdgeLake command
            headers: Optional headers

        Returns:
            Command result
        """
        logger.debug(f"Starting sync execution of: {command}")

        try:
            # Create status and buffer objects
            status = self.process_status.ProcessStat()

            # Get buffer size (use default if not initialized yet)
            buff_size_str = self.params.get_param("io_buff_size")
            if not buff_size_str or buff_size_str == '':
                buff_size = 32768  # Default 32KB buffer
                logger.warning("io_buff_size not initialized, using default: 32768")
            else:
                buff_size = int(buff_size_str)
            io_buff = bytearray(buff_size)

            # Handle special headers (like destination for queries)
            if headers and 'destination' in headers:
                # Set destination in status or command context
                # For network queries, this would typically be handled by the command itself
                pass

            logger.debug(f"Calling member_cmd.process_cmd for: {command}")

            # Capture stdout - some commands print results instead of populating io_buff
            stdout_capture = io.StringIO()

            with redirect_stdout(stdout_capture):
                # Execute command via member_cmd
                ret_val = self.member_cmd.process_cmd(
                    status,
                    command=command,
                    print_cmd=False,
                    source_ip=None,
                    source_port=None,
                    io_buffer_in=io_buff
                )

            logger.debug(f"Command completed with return value: {ret_val}")

            if ret_val == self.process_status.SUCCESS:
                # Extract result from status or buffer
                result = self._extract_result(status, io_buff, command, stdout_capture.getvalue())
                logger.debug(f"Extracted result: {type(result)}")
                return result
            elif ret_val == 141:
                # Error code 141: EdgeLake not ready yet, return empty result
                logger.warning(f"EdgeLake not ready for command '{command}' (code 141), returning empty result")
                return ""
            else:
                # Command failed
                error_msg = status.get_saved_error() or f"Command failed with code {ret_val}"
                logger.error(f"Command execution failed: {error_msg}")
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}", exc_info=True)
            raise

    def _extract_result(self, status, io_buff: bytearray, command: str, stdout_output: str = "") -> Any:
        """
        Extract result from status object, buffer, or captured stdout.

        Args:
            status: ProcessStat object
            io_buff: IO buffer
            command: Original command
            stdout_output: Captured stdout from command execution

        Returns:
            Extracted result
        """
        # Try to get from buffer first
        try:
            # Find null terminator
            null_pos = io_buff.find(b'\x00')
            logger.debug(f"Buffer null position: {null_pos}, buffer size: {len(io_buff)}")

            if null_pos > 0:
                buffer_str = io_buff[:null_pos].decode('utf-8')
                logger.debug(f"Buffer string length: {len(buffer_str)}, first 200 chars: {buffer_str[:200]}")

                if buffer_str:
                    try:
                        result = json.loads(buffer_str)
                        logger.debug(f"Successfully parsed JSON from buffer, type: {type(result)}")
                        return result
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.debug(f"JSON decode failed: {e}, returning raw string")
                        return buffer_str
            else:
                logger.debug(f"No valid data in buffer (null_pos={null_pos})")
        except Exception as e:
            logger.debug(f"Could not extract from buffer: {e}")

        # If buffer is empty, check stdout
        if stdout_output and stdout_output.strip():
            logger.debug(f"Buffer empty, checking stdout. Length: {len(stdout_output)}")
            stdout_trimmed = stdout_output.strip()

            try:
                # Try to parse as JSON
                result = json.loads(stdout_trimmed)
                logger.debug(f"Successfully parsed JSON from stdout, type: {type(result)}")
                return result
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Stdout is not JSON: {e}, returning raw string")
                return stdout_trimmed

        # Return empty result for commands that don't produce output
        logger.debug("Returning empty string - no data in buffer or stdout")
        return ""

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

    async def _execute_via_rest(self, command: str, timeout: float) -> Any:
        """
        Execute command via local REST API.

        This ensures proper distributed query handling by using EdgeLake's
        REST infrastructure which has all the job scheduling and network
        coordination logic built in.

        Args:
            command: EdgeLake command string
            timeout: Command timeout in seconds

        Returns:
            Command result
        """
        # Get REST port from params
        rest_port = self.params.get_param("rest_port") or "32049"
        url = f"http://127.0.0.1:{rest_port}"

        logger.debug(f"Executing via REST API at {url}: {command}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=command,
                    headers={"command": "sql", "User-Agent": "MCP-Server"},
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    result_text = await response.text()
                    logger.debug(f"REST API response ({response.status}): {result_text[:200]}")

                    if response.status == 200:
                        return result_text
                    else:
                        raise Exception(f"REST API returned status {response.status}: {result_text}")

        except asyncio.TimeoutError:
            logger.error(f"REST API request timed out after {timeout}s")
            raise TimeoutError(f"Network query timed out after {timeout} seconds")
        except Exception as e:
            logger.error(f"REST API request failed: {e}")
            raise

    def close(self):
        """Shutdown the thread pool executor"""
        logger.info("Shutting down EdgeLake direct client")
        self.executor.shutdown(wait=True)
