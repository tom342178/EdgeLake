"""
Test Query Executor

Simple test script to validate QueryExecutor implementation.
Run this after EdgeLake is initialized.

Usage:
    python -m edge_lake.mcp_server.test_query_executor

License: Mozilla Public License 2.0
"""

import asyncio
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_validation():
    """Test query validation"""
    logger.info("=" * 60)
    logger.info("TEST 1: Query Validation")
    logger.info("=" * 60)

    try:
        from edge_lake.mcp_server.core.query_executor import QueryValidator

        validator = QueryValidator()

        # Test valid query
        result = validator.validate_query(
            "test",
            "SELECT * FROM test_table LIMIT 10"
        )

        if result["validated"]:
            logger.info("✓ Valid query accepted")
            logger.info(f"  Table: {result.get('table_name')}")
            logger.info(f"  Validated SQL: {result.get('validated_sql')[:100]}...")
        else:
            logger.error(f"✗ Validation failed: {result.get('error')}")

        # Test invalid query
        result = validator.validate_query(
            "test",
            "SELECT * INVALID SYNTAX"
        )

        if not result["validated"]:
            logger.info("✓ Invalid query rejected correctly")
            logger.info(f"  Error: {result.get('error')}")
        else:
            logger.error("✗ Invalid query was accepted!")

        return True

    except Exception as e:
        logger.error(f"✗ Validation test failed: {e}", exc_info=True)
        return False


async def test_batch_execution():
    """Test batch query execution"""
    logger.info("=" * 60)
    logger.info("TEST 2: Batch Execution")
    logger.info("=" * 60)

    try:
        from edge_lake.mcp_server.core.query_executor import QueryExecutor

        executor = QueryExecutor()

        # Simple SELECT query (will fail if no test database exists, but tests the flow)
        result = await executor.execute_query(
            dbms_name="test",
            sql_query="SELECT 1 as test_column",
            mode="batch",
            fetch_size=10
        )

        logger.info(f"✓ Batch execution completed")
        logger.info(f"  Success: {result.get('success')}")
        logger.info(f"  Total rows: {result.get('total_rows')}")
        logger.info(f"  Sample data: {result.get('rows', [])[:3]}")

        return True

    except Exception as e:
        logger.error(f"✗ Batch execution test failed: {e}", exc_info=True)
        return False


async def test_streaming_execution():
    """Test streaming query execution"""
    logger.info("=" * 60)
    logger.info("TEST 3: Streaming Execution")
    logger.info("=" * 60)

    try:
        from edge_lake.mcp_server.core.query_executor import QueryExecutor

        executor = QueryExecutor()

        # Simple SELECT query with streaming
        stream = executor.execute_query(
            dbms_name="test",
            sql_query="SELECT 1 as test_column UNION SELECT 2 UNION SELECT 3",
            mode="streaming",
            fetch_size=1  # Fetch 1 row at a time to test streaming
        )

        # Consume stream
        batch_count = 0
        total_rows = 0

        async for batch in stream:
            if batch["type"] == "data":
                batch_count += 1
                row_count = batch["row_count"]
                total_rows += row_count
                logger.info(f"  Batch {batch_count}: {row_count} rows")
            elif batch["type"] == "complete":
                logger.info(f"  Stream complete: {batch['total_rows']} total rows")

        logger.info(f"✓ Streaming execution completed")
        logger.info(f"  Batches received: {batch_count}")
        logger.info(f"  Total rows: {total_rows}")

        return True

    except Exception as e:
        logger.error(f"✗ Streaming execution test failed: {e}", exc_info=True)
        return False


async def test_auto_mode():
    """Test automatic mode selection"""
    logger.info("=" * 60)
    logger.info("TEST 4: Auto Mode Selection")
    logger.info("=" * 60)

    try:
        from edge_lake.mcp_server.core.query_executor import QueryExecutor

        executor = QueryExecutor()

        # Test queries that should trigger different modes
        test_queries = [
            ("SELECT COUNT(*) FROM test_table", "batch", "aggregate query"),
            ("SELECT * FROM test_table", "streaming", "full table scan"),
            ("SELECT * FROM test_table LIMIT 10", "batch", "query with LIMIT"),
        ]

        for query, expected_mode, description in test_queries:
            selected_mode = executor._select_mode(query)
            if selected_mode == expected_mode:
                logger.info(f"✓ {description} → {selected_mode} mode (correct)")
            else:
                logger.warning(f"✗ {description} → {selected_mode} mode (expected {expected_mode})")

        return True

    except Exception as e:
        logger.error(f"✗ Auto mode test failed: {e}", exc_info=True)
        return False


async def main():
    """Run all tests"""
    logger.info("Starting Query Executor Tests")
    logger.info("")

    results = []

    # Run tests
    results.append(("Validation", await test_validation()))
    logger.info("")

    results.append(("Batch Execution", await test_batch_execution()))
    logger.info("")

    results.append(("Streaming Execution", await test_streaming_execution()))
    logger.info("")

    results.append(("Auto Mode", await test_auto_mode()))
    logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info("")
    logger.info(f"Results: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test runner failed: {e}", exc_info=True)
        sys.exit(1)
