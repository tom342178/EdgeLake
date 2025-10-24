#!/bin/bash
#
# EdgeLake MCP SSE Server - Test Script
#
# This script tests the MCP server's SSE endpoint using curl.
# Based on the MCP SSE protocol specification.
#
# Usage:
#   ./test-mcp-sse-endpoints.sh [HOST] [PORT]
#
# Examples:
#   ./test-mcp-sse-endpoints.sh localhost 50051
#   ./test-mcp-sse-endpoints.sh 192.168.1.100 50051
#

set -e  # Exit on error

# Default values
HOST="${1:-localhost}"
PORT="${2:-50051}"
BASE_URL="http://${HOST}:${PORT}"
SSE_ENDPOINT="${BASE_URL}/sse"
MESSAGES_ENDPOINT="${BASE_URL}/messages/"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================================"
echo "EdgeLake MCP SSE Server - Test Script"
echo "======================================================"
echo "Server: ${BASE_URL}"
echo "SSE Endpoint: ${SSE_ENDPOINT}"
echo ""

# Test 1: Initialize connection and list tools
echo -e "${YELLOW}Test 1: Initialize connection and list tools${NC}"
echo "-------------------------------------------------------"
echo "Request:"
cat <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "curl-test",
      "version": "1.0"
    }
  }
}
EOF
echo ""
echo "Sending to ${MESSAGES_ENDPOINT}..."
curl -s -X POST "${MESSAGES_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "curl-test",
      "version": "1.0"
    }
  }
}' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""
sleep 1

# Test 2: List available tools
echo -e "${YELLOW}Test 2: List available tools${NC}"
echo "-------------------------------------------------------"
echo "Request:"
cat <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
EOF
echo ""
echo "Sending..."
curl -s -X POST "${MESSAGES_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""
sleep 1

# Test 3: Call server_info tool (should be fast, doesn't call EdgeLake)
echo -e "${YELLOW}Test 3: Call server_info tool${NC}"
echo "-------------------------------------------------------"
echo "Request:"
cat <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "server_info",
    "arguments": {}
  }
}
EOF
echo ""
echo "Sending..."
curl -s -X POST "${MESSAGES_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "server_info",
    "arguments": {}
  }
}' | jq '.' || echo -e "${RED}Failed${NC}"
echo ""
sleep 1

# Test 4: Call node_status tool (calls EdgeLake "get status")
echo -e "${YELLOW}Test 4: Call node_status tool (with timeout protection)${NC}"
echo "-------------------------------------------------------"
echo "Request:"
cat <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "node_status",
    "arguments": {}
  }
}
EOF
echo ""
echo "Sending... (will timeout after 30s if EdgeLake hangs)"
curl -s --max-time 35 -X POST "${MESSAGES_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "node_status",
    "arguments": {}
  }
}' | jq '.' || echo -e "${RED}Failed or timed out${NC}"
echo ""
sleep 1

# Test 5: Call list_databases tool
echo -e "${YELLOW}Test 5: Call list_databases tool${NC}"
echo "-------------------------------------------------------"
echo "Request:"
cat <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "list_databases",
    "arguments": {}
  }
}
EOF
echo ""
echo "Sending... (will timeout after 30s if EdgeLake hangs)"
curl -s --max-time 35 -X POST "${MESSAGES_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 5,
  "method": "tools/call",
  "params": {
    "name": "list_databases",
    "arguments": {}
  }
}' | jq '.' || echo -e "${RED}Failed or timed out${NC}"
echo ""
sleep 1

# Test 6: Test with verbose output (no jq parsing)
echo -e "${YELLOW}Test 6: server_info with raw response${NC}"
echo "-------------------------------------------------------"
echo "Sending request without jq parsing to see raw response..."
curl -v -X POST "${MESSAGES_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc": "2.0",
  "id": 6,
  "method": "tools/call",
  "params": {
    "name": "server_info",
    "arguments": {}
  }
}' || echo -e "${RED}Failed${NC}"
echo ""

echo "======================================================"
echo -e "${GREEN}Tests complete!${NC}"
echo "======================================================"
echo ""
echo "Notes:"
echo "  - If node_status or list_databases timeout, check EdgeLake logs"
echo "  - Log file: ~/Library/Logs/edgelake_mcp.log"
echo "  - For debug logs, set MCP_LOG_LEVEL=DEBUG in environment"
echo ""