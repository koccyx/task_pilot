#!/bin/bash
# Basic MCP Inspector-style test script
# Tests MCP server via HTTP calls

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
MCP_SERVER_URL="${MCP_SERVER_URL:-http://localhost:8000/mcp}"
PYTHON_SCRIPT="${0%/*}/test_mcp_basic.py"

echo "=========================================="
echo "MCP Inspector - Basic Tool Call Tests"
echo "=========================================="
echo "Server URL: $MCP_SERVER_URL"
echo ""

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}Error: Python script not found at $PYTHON_SCRIPT${NC}"
    exit 1
fi

# Run Python test script
python3 "$PYTHON_SCRIPT"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
else
    echo -e "\n${RED}❌ Some tests failed${NC}"
fi

exit $EXIT_CODE
