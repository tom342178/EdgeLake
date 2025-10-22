#!/usr/bin/env python3
"""
Test script for EdgeLake MCP Direct Client

Tests the direct client integration with proper timeout handling.
"""

import asyncio
import sys
import logging
from pathlib import Path

# Setup logging to see debug output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add edge_lake to path
sys.path.insert(0, str(Path(__file__).parent))

from edge_lake.mcp_server.core.direct_client import EdgeLakeDirectClient


async def test_direct_client():
    """Test the direct client with various commands"""

    logger.info("=" * 60)
    logger.info("Testing EdgeLake Direct Client")
    logger.info("=" * 60)

    try:
        # Initialize client
        logger.info("\n1. Initializing direct client...")
        client = EdgeLakeDirectClient(max_workers=2)
        logger.info("✓ Client initialized successfully")

        # Test simple command with timeout
        logger.info("\n2. Testing simple command: 'get status'")
        try:
            result = await client.execute_command("get status", timeout=5.0)
            logger.info(f"✓ Command succeeded: {type(result)}")
            logger.info(f"Result: {str(result)[:200]}...")
        except TimeoutError as e:
            logger.error(f"✗ Command timed out: {e}")
        except Exception as e:
            logger.error(f"✗ Command failed: {e}")

        # Test get_node_status helper
        logger.info("\n3. Testing get_node_status() helper")
        try:
            status = await client.get_node_status()
            logger.info(f"✓ Node status: {type(status)}")
            logger.info(f"Status: {str(status)[:200]}...")
        except TimeoutError as e:
            logger.error(f"✗ get_node_status timed out: {e}")
        except Exception as e:
            logger.error(f"✗ get_node_status failed: {e}")

        # Test blockchain command
        logger.info("\n4. Testing blockchain command: 'blockchain get table'")
        try:
            result = await client.execute_command("blockchain get table", timeout=10.0)
            logger.info(f"✓ Blockchain command succeeded: {type(result)}")
            logger.info(f"Result: {str(result)[:200]}...")
        except TimeoutError as e:
            logger.error(f"✗ Blockchain command timed out: {e}")
        except Exception as e:
            logger.error(f"✗ Blockchain command failed: {e}")

        # Test get_databases helper
        logger.info("\n5. Testing get_databases() helper")
        try:
            databases = await client.get_databases()
            logger.info(f"✓ Found {len(databases)} databases")
            logger.info(f"Databases: {databases}")
        except TimeoutError as e:
            logger.error(f"✗ get_databases timed out: {e}")
        except Exception as e:
            logger.error(f"✗ get_databases failed: {e}")

        # Cleanup
        logger.info("\n6. Cleaning up...")
        client.close()
        logger.info("✓ Client closed")

        logger.info("\n" + "=" * 60)
        logger.info("Test completed!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\nFatal error: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    # Run the async test
    exit_code = asyncio.run(test_direct_client())
    sys.exit(exit_code)