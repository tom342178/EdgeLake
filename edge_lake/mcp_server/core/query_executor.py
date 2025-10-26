"""
Query Executor for MCP Server

Implements hybrid approach: validation through select_parser() + streaming through
low-level database APIs.

Architecture:
    1. QueryValidator: Validates SQL and performs query transformations
    2. StreamingExecutor: Streams results row-by-row using process_fetch_rows()
    3. BatchExecutor: Returns full results at once
    4. QueryExecutor: Orchestrator with auto-mode selection

License: Mozilla Public License 2.0
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class QueryValidator:
    """
    Validates SQL queries using EdgeLake's select_parser().

    This ensures all validation, authorization, and distributed query
    transformations are applied before execution.
    """

    def __init__(self):
        """Initialize query validator with EdgeLake modules."""
        try:
            from edge_lake.dbms import db_info
            from edge_lake.generic import process_status

            self.db_info = db_info
            self.process_status = process_status

            logger.debug("QueryValidator initialized")

        except ImportError as e:
            logger.error(f"Failed to import EdgeLake modules: {e}")
            raise

    def validate_query(self, dbms_name: str, sql_query: str) -> Dict[str, Any]:
        """
        Validate SQL query and get transformed version.

        This method calls select_parser() which:
        - Validates SQL syntax
        - Checks permissions and authorization
        - Resolves views to physical tables
        - Transforms distributed queries (e.g., AVG → SUM+COUNT)
        - Applies query optimizations

        Args:
            dbms_name: Database name
            sql_query: SQL query to validate

        Returns:
            Dictionary with validation result:
                {
                    "validated": bool,
                    "error": str (if validation failed),
                    "table_name": str (if validated),
                    "validated_sql": str (if validated),
                    "select_parsed": SelectParsed object (if validated)
                }
        """
        logger.debug(f"Validating query for database '{dbms_name}': {sql_query}")

        try:
            # Create status object
            status = self.process_status.ProcessStat()

            # Get or create select_parsed object
            select_parsed = status.get_select_parsed()
            select_parsed.reset(False, False)

            # Call select_parser for validation and transformation
            ret_val, table_name, validated_sql = self.db_info.select_parser(
                status,
                select_parsed,
                dbms_name,
                sql_query,
                False,  # is_subprocess
                None    # trace_level
            )

            if ret_val != 0:
                error_msg = status.get_saved_error() or f"Query validation failed with code {ret_val}"
                logger.warning(f"Query validation failed: {error_msg}")
                return {
                    "validated": False,
                    "error": error_msg
                }

            logger.debug(f"Query validated successfully. Table: {table_name}")

            return {
                "validated": True,
                "table_name": table_name,
                "validated_sql": validated_sql,
                "select_parsed": select_parsed
            }

        except Exception as e:
            logger.error(f"Error during query validation: {e}", exc_info=True)
            return {
                "validated": False,
                "error": str(e)
            }


class StreamingExecutor:
    """
    Executes queries with row-by-row streaming using process_fetch_rows().

    This allows efficient handling of large result sets without loading
    everything into memory.
    """

    def __init__(self):
        """Initialize streaming executor with EdgeLake modules."""
        try:
            from edge_lake.dbms import db_info, cursor_info
            from edge_lake.generic import process_status

            self.db_info = db_info
            self.cursor_info = cursor_info
            self.process_status = process_status

            logger.debug("StreamingExecutor initialized")

        except ImportError as e:
            logger.error(f"Failed to import EdgeLake modules: {e}")
            raise

    async def execute_streaming(
        self,
        dbms_name: str,
        validated_sql: str,
        select_parsed,
        fetch_size: int = 100
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute query and stream results in batches.

        Args:
            dbms_name: Database name
            validated_sql: Validated SQL from select_parser()
            select_parsed: SelectParsed object from validation
            fetch_size: Number of rows to fetch per batch

        Yields:
            Dictionary with batch data:
                {
                    "type": "data",
                    "rows": List[Dict],  # Parsed JSON rows
                    "row_count": int     # Number of rows in this batch
                }

            Last message:
                {
                    "type": "complete",
                    "total_rows": int
                }

        Raises:
            Exception: If query execution fails
        """
        logger.debug(f"Starting streaming execution for database '{dbms_name}'")

        status = self.process_status.ProcessStat()
        cursor = self.cursor_info.CursorInfo()
        total_rows = 0

        try:
            # Set cursor for database
            ret_val = self.db_info.set_cursor(status, cursor, dbms_name)
            if ret_val != 0:
                error_msg = status.get_saved_error() or f"Failed to set cursor (code {ret_val})"
                logger.error(f"set_cursor failed: {error_msg}")
                raise Exception(error_msg)

            # Execute SQL statement
            ret_val = self.db_info.process_sql_stmt(status, cursor, validated_sql)
            if ret_val != 0:
                error_msg = status.get_saved_error() or f"Query execution failed (code {ret_val})"
                logger.error(f"process_sql_stmt failed: {error_msg}")
                raise Exception(error_msg)

            # Get column metadata
            title_list = select_parsed.get_title_list()
            data_types_list = select_parsed.get_data_types()

            logger.debug(f"Query executed successfully. Fetching results in batches of {fetch_size}")

            # Fetch rows in batches
            while True:
                # Fetch next batch
                get_next, rows_data = self.db_info.process_fetch_rows(
                    status,
                    cursor,
                    "Query",  # output_prefix
                    fetch_size,
                    title_list,
                    data_types_list
                )

                # Check if we have data
                if not rows_data or rows_data.strip() == "":
                    logger.debug("No more data to fetch")
                    break

                # Parse JSON response
                try:
                    parsed_result = json.loads(rows_data)
                    rows = parsed_result.get("Query", [])

                    if not rows:
                        logger.debug("Empty batch received")
                        break

                    batch_size = len(rows)
                    total_rows += batch_size

                    logger.debug(f"Fetched batch of {batch_size} rows (total so far: {total_rows})")

                    # Yield batch
                    yield {
                        "type": "data",
                        "rows": rows,
                        "row_count": batch_size
                    }

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse batch JSON: {e}")
                    logger.debug(f"Raw data: {rows_data[:500]}")
                    raise Exception(f"Failed to parse query results: {e}")

                # Check if there are more rows
                if not get_next:
                    logger.debug("Last batch fetched (get_next=False)")
                    break

            # Send completion message
            logger.debug(f"Streaming complete. Total rows: {total_rows}")
            yield {
                "type": "complete",
                "total_rows": total_rows
            }

        finally:
            # Always close cursor
            try:
                self.db_info.close_cursor(status, cursor)
                logger.debug("Cursor closed")
            except Exception as e:
                logger.warning(f"Error closing cursor: {e}")


class BatchExecutor:
    """
    Executes queries and returns all results at once.

    Uses the same validation path but collects all rows before returning.
    Suitable for small result sets or when streaming is not needed.
    """

    def __init__(self):
        """Initialize batch executor with EdgeLake modules."""
        try:
            from edge_lake.dbms import db_info, cursor_info
            from edge_lake.generic import process_status

            self.db_info = db_info
            self.cursor_info = cursor_info
            self.process_status = process_status

            logger.debug("BatchExecutor initialized")

        except ImportError as e:
            logger.error(f"Failed to import EdgeLake modules: {e}")
            raise

    async def execute_batch(
        self,
        dbms_name: str,
        validated_sql: str,
        select_parsed,
        fetch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Execute query and return all results.

        Args:
            dbms_name: Database name
            validated_sql: Validated SQL from select_parser()
            select_parsed: SelectParsed object from validation
            fetch_size: Number of rows to fetch per batch (internal)

        Returns:
            Dictionary with complete results:
                {
                    "success": True,
                    "rows": List[Dict],
                    "total_rows": int
                }

        Raises:
            Exception: If query execution fails
        """
        logger.debug(f"Starting batch execution for database '{dbms_name}'")

        status = self.process_status.ProcessStat()
        cursor = self.cursor_info.CursorInfo()
        all_rows = []

        try:
            # Set cursor for database
            ret_val = self.db_info.set_cursor(status, cursor, dbms_name)
            if ret_val != 0:
                error_msg = status.get_saved_error() or f"Failed to set cursor (code {ret_val})"
                logger.error(f"set_cursor failed: {error_msg}")
                raise Exception(error_msg)

            # Execute SQL statement
            ret_val = self.db_info.process_sql_stmt(status, cursor, validated_sql)
            if ret_val != 0:
                error_msg = status.get_saved_error() or f"Query execution failed (code {ret_val})"
                logger.error(f"process_sql_stmt failed: {error_msg}")
                raise Exception(error_msg)

            # Get column metadata
            title_list = select_parsed.get_title_list()
            data_types_list = select_parsed.get_data_types()

            logger.debug(f"Query executed successfully. Fetching all results")

            # Fetch all rows
            while True:
                get_next, rows_data = self.db_info.process_fetch_rows(
                    status,
                    cursor,
                    "Query",
                    fetch_size,
                    title_list,
                    data_types_list
                )

                if not rows_data or rows_data.strip() == "":
                    break

                try:
                    parsed_result = json.loads(rows_data)
                    rows = parsed_result.get("Query", [])

                    if rows:
                        all_rows.extend(rows)
                        logger.debug(f"Fetched {len(rows)} rows (total: {len(all_rows)})")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse batch JSON: {e}")
                    raise Exception(f"Failed to parse query results: {e}")

                if not get_next:
                    break

            logger.debug(f"Batch execution complete. Total rows: {len(all_rows)}")

            return {
                "success": True,
                "rows": all_rows,
                "total_rows": len(all_rows)
            }

        finally:
            try:
                self.db_info.close_cursor(status, cursor)
                logger.debug("Cursor closed")
            except Exception as e:
                logger.warning(f"Error closing cursor: {e}")


class QueryExecutor:
    """
    Main query executor with automatic mode selection.

    Orchestrates validation and execution with choice of streaming or batch mode.
    """

    def __init__(self):
        """Initialize query executor."""
        self.validator = QueryValidator()
        self.streaming_executor = StreamingExecutor()
        self.batch_executor = BatchExecutor()

        logger.info("QueryExecutor initialized with hybrid validation + streaming approach")

    async def execute_query(
        self,
        dbms_name: str,
        sql_query: str,
        mode: str = "auto",
        fetch_size: int = 100
    ) -> Any:
        """
        Execute query with automatic or manual mode selection.

        Args:
            dbms_name: Database name
            sql_query: SQL query to execute
            mode: Execution mode:
                - "auto": Automatically choose streaming vs batch
                - "streaming": Force streaming mode
                - "batch": Force batch mode
            fetch_size: Rows per batch for streaming mode

        Returns:
            For streaming mode: AsyncGenerator yielding batches
            For batch mode: Dictionary with all results

        Raises:
            Exception: If validation or execution fails
        """
        logger.debug(f"Executing query in '{mode}' mode: {sql_query}")

        # Step 1: Always validate first
        validation_result = self.validator.validate_query(dbms_name, sql_query)

        if not validation_result["validated"]:
            error_msg = validation_result["error"]
            logger.error(f"Query validation failed: {error_msg}")
            raise Exception(f"Query validation failed: {error_msg}")

        validated_sql = validation_result["validated_sql"]
        select_parsed = validation_result["select_parsed"]

        # Step 2: Select execution mode
        if mode == "auto":
            mode = self._select_mode(sql_query)
            logger.debug(f"Auto-selected mode: {mode}")

        # Step 3: Execute based on mode
        if mode == "streaming":
            return self.streaming_executor.execute_streaming(
                dbms_name,
                validated_sql,
                select_parsed,
                fetch_size
            )
        else:  # batch
            return await self.batch_executor.execute_batch(
                dbms_name,
                validated_sql,
                select_parsed,
                fetch_size
            )

    def _select_mode(self, sql_query: str) -> str:
        """
        Automatically select execution mode based on query characteristics.

        Args:
            sql_query: SQL query

        Returns:
            "streaming" or "batch"
        """
        sql_lower = sql_query.lower()

        # Use batch mode for:
        # - Aggregate queries (likely small results)
        # - COUNT queries
        # - Queries with LIMIT clause
        batch_indicators = [
            'count(',
            'avg(',
            'sum(',
            'min(',
            'max(',
            'limit ',
            'group by'
        ]

        if any(indicator in sql_lower for indicator in batch_indicators):
            return "batch"

        # Use streaming for:
        # - SELECT * queries (potentially large)
        # - No aggregates or limits
        return "streaming"
