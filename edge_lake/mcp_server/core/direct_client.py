"""
EdgeLake Direct Client

Direct integration client for embedded MCP server - calls member_cmd.process_cmd()
directly without HTTP overhead.

License: Mozilla Public License 2.0
"""

import asyncio
import io
import json
import logging
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
        self._shutdown = False

        # Import EdgeLake modules
        try:
            from edge_lake.cmd import member_cmd
            from edge_lake.generic import process_status, params

            self.member_cmd = member_cmd
            self.process_status = process_status
            self.params = params

            logger.debug("EdgeLake direct client initialized")

        except ImportError as e:
            logger.error(f"Failed to import EdgeLake modules: {e}")
            raise

    async def execute_command(self, command: str, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0) -> Any:
        """
        Execute an EdgeLake command directly.

        Args:
            command: EdgeLake command string
            headers: Optional headers (for compatibility, mostly ignored in direct mode)
            timeout: Command timeout in seconds (default: 30)

        Returns:
            Command result (returns empty string during shutdown instead of raising)

        Raises:
            asyncio.TimeoutError: If command execution exceeds timeout
        """
        logger.debug(f"Executing command directly: {command}")

        # Check if client is shutting down - return empty result instead of raising
        if self._shutdown:
            logger.debug(f"Client is shutting down, returning empty result for: {command}")
            return ""

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
        except RuntimeError as e:
            # Handle executor shutdown gracefully - return empty instead of raising
            if "shutdown" in str(e).lower() or "interpreter shutdown" in str(e).lower():
                logger.debug(f"Executor shutting down during command execution, returning empty result: {command}")
                return ""
            # Re-raise other RuntimeErrors with full context
            raise
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

            # Check if this is an async command (run client)
            is_async_command = 'run client' in command.lower()

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

                # For async commands (run client), poll for results with exponential backoff
                if is_async_command and ret_val == self.process_status.SUCCESS:
                    import time
                    logger.debug("Async command detected, polling for results...")

                    max_wait = 5.0  # Maximum 5 seconds
                    poll_interval = 0.05  # Start with 50ms
                    elapsed = 0

                    while elapsed < max_wait:
                        # Check if JSON results have appeared
                        current_output = stdout_capture.getvalue()
                        if '{"Query"' in current_output or '{"Statistics"' in current_output:
                            logger.debug(f"Results appeared after {elapsed:.3f}s")
                            break

                        time.sleep(poll_interval)
                        elapsed += poll_interval
                        # Exponential backoff, max 500ms per poll
                        poll_interval = min(poll_interval * 1.5, 0.5)

                    if elapsed >= max_wait:
                        logger.warning(f"Async command timed out after {max_wait}s")

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

            # Try to extract JSON from stdout (may contain CLI prompts and other noise)
            try:
                # First, try to parse the whole output as JSON
                result = json.loads(stdout_trimmed)
                logger.debug(f"Successfully parsed JSON from stdout, type: {type(result)}")
                return result
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Stdout is not valid JSON: {e}")

                # Try to find JSON object in the output
                # Look for query result patterns like {"Query":[... or {"Statistics":[...
                # Prefer finding objects over arrays to avoid matching noise like [7]

                # Strategy: Look for '{"Query"' or '{"Statistics"' patterns first
                result_patterns = [
                    '{"Query"',
                    '{"Statistics"',
                    '{"result"',
                    '{"data"',
                ]

                json_start = -1
                for pattern in result_patterns:
                    pos = stdout_trimmed.find(pattern)
                    if pos >= 0:
                        json_start = pos
                        logger.debug(f"Found query result pattern '{pattern}' at position {pos}")
                        break

                # If no pattern found, fall back to finding first [ or {
                # Prefer arrays for blockchain commands, objects for others
                if json_start < 0:
                    logger.debug("No query result pattern found, searching for first JSON structure")
                    # Check if this is a blockchain command (arrays are common)
                    is_blockchain_cmd = 'blockchain' in command.lower()

                    if is_blockchain_cmd:
                        # For blockchain commands, try array first
                        for i, char in enumerate(stdout_trimmed):
                            if char == '[':
                                json_start = i
                                break
                        # If no [, try {
                        if json_start < 0:
                            for i, char in enumerate(stdout_trimmed):
                                if char == '{':
                                    json_start = i
                                    break
                    else:
                        # For other commands, prefer objects over arrays
                        for i, char in enumerate(stdout_trimmed):
                            if char == '{':
                                json_start = i
                                break
                        # If still no {, try [
                        if json_start < 0:
                            for i, char in enumerate(stdout_trimmed):
                                if char == '[':
                                    json_start = i
                                    break

                if json_start >= 0:
                    # Find matching closing bracket
                    bracket_count = 0
                    is_object = stdout_trimmed[json_start] == '{'
                    open_bracket = '{' if is_object else '['
                    close_bracket = '}' if is_object else ']'
                    json_end = -1

                    for i in range(json_start, len(stdout_trimmed)):
                        if stdout_trimmed[i] == open_bracket:
                            bracket_count += 1
                        elif stdout_trimmed[i] == close_bracket:
                            bracket_count -= 1
                            if bracket_count == 0:
                                json_end = i + 1
                                break

                    if json_end > json_start:
                        json_str = stdout_trimmed[json_start:json_end]
                        try:
                            result = json.loads(json_str)
                            logger.debug(f"Extracted JSON from stdout (chars {json_start}:{json_end}), type: {type(result)}")
                            return result
                        except (json.JSONDecodeError, TypeError) as e2:
                            logger.debug(f"Failed to parse extracted JSON: {e2}")

                # If we can't extract JSON, return the raw stdout (CLI prompts and all)
                logger.debug("Could not extract valid JSON from stdout, returning raw string")
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
        logger.debug(f"Executing query on '{database}': {query}")

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

    def close(self):
        """Shutdown the thread pool executor"""
        logger.debug("Shutting down EdgeLake direct client")
        self._shutdown = True
        try:
            self.executor.shutdown(wait=True, cancel_futures=True)
        except Exception as e:
            logger.warning(f"Error during executor shutdown: {e}")
