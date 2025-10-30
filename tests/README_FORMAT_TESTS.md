# Format Changes Test Suite

Test suite for validating that MCP format changes don't break existing EdgeLake command behavior.

## Overview

This test suite ensures:
- ✅ Existing commands continue to work (no regressions)
- ✅ New MCP format support works correctly
- ✅ Output matches baseline from known-good system
- ✅ Performance doesn't degrade

## Quick Start

### Step 1: Collect Baselines from Working VM

First, collect baseline outputs from a working EdgeLake instance (before your changes):

```bash
# Install dependencies
pip install requests

# Collect baselines from working VM
python tests/test_format_changes.py \
  --mode baseline \
  --host <vm-ip-address> \
  --port 32049 \
  --output tests/baselines.json
```

This will:
- Connect to the working VM
- Run all existing commands
- Save outputs to `baselines.json`

### Step 2: Run Tests Against Your Changes

After making changes, test against the baseline:

```bash
# Run tests with baseline comparison
python tests/test_format_changes.py \
  --mode test \
  --host localhost \
  --port 32049 \
  --baseline tests/baselines.json
```

Or test without baseline (just verify commands work):

```bash
# Run tests without baseline
python tests/test_format_changes.py \
  --mode test \
  --host localhost \
  --port 32049
```

## Test Cases

The suite includes:

### Regression Tests (Existing Commands)
- `blockchain get table` - Basic table retrieval
- `blockchain get table bring.json [*]` - With bring clause
- `blockchain get operator` - Operator policies
- `blockchain get cluster` - Cluster policies
- `blockchain get *` - All policies
- `get version` - Version info
- `get status` - Status info

### New MCP Format Tests
- `blockchain get table where format = mcp` - List databases
- `blockchain get table where format = mcp and dbms = xxx` - List tables
- `get version where format = mcp` - Version in MCP format
- `get status where format = mcp include statistics` - Status in MCP format

## VM Access Information

### Working VM Details
**To be filled in by user:**
- IP Address: `_____________`
- REST Port: `32049` (default)
- SSH Access: `_____________`
- Notes: `_____________`

### Connecting to VM

```bash
# SSH into VM
ssh user@<vm-ip>

# Verify EdgeLake is running
docker ps | grep edgelake

# Test REST endpoint
curl -H "User-Agent: anylog" -H "command: get version" http://localhost:32049
```

## Test Output

### Successful Run
```
======================================================================
EdgeLake Format Changes Test Suite
======================================================================

Running 12 test cases...

  Running: blockchain_get_table_basic... ✓ PASS (0.15s)
  Running: blockchain_get_table_with_bring... ✓ PASS (0.18s)
  Running: blockchain_get_table_mcp_format... ✓ PASS (0.16s)
  ...

======================================================================
Test Summary
======================================================================
Total: 12
Passed: 12
Failed: 0
```

### Failed Run
```
  Running: blockchain_get_table_mcp_format... ✗ FAIL (0.16s)
    Error: Output doesn't match MCP format expectations

======================================================================
Test Summary
======================================================================
Total: 12
Passed: 10
Failed: 2

Failed Tests:
  - blockchain_get_table_mcp_format: Output doesn't match MCP format expectations
  - get_version_mcp: Output differs from baseline
```

## Adding New Test Cases

To add a new test case, edit `test_format_changes.py` and add to `get_test_cases()`:

```python
TestCase(
    name="your_test_name",
    command="your edgelake command",
    description="What this test validates",
    expected_format="mcp",  # or "json", "text"
    should_succeed=True,
    min_response_fields=["field1", "field2"],  # optional
),
```

## CI/CD Integration

Add to your CI pipeline:

```yaml
# Example GitHub Actions
- name: Run Format Tests
  run: |
    pip install requests
    python tests/test_format_changes.py \
      --mode test \
      --host localhost \
      --port 32049 \
      --baseline tests/baselines.json
```

## Troubleshooting

### Connection Refused
- Verify EdgeLake is running: `docker ps`
- Check REST port: `netstat -an | grep 32049`
- Test connectivity: `curl http://localhost:32049`

### Baseline Differences
Review detailed output in `test_results.json`:
```bash
cat test_results.json | jq '.[] | select(.passed == false)'
```

### Timeout Errors
Increase timeout for slow systems:
```bash
python tests/test_format_changes.py --mode test --host localhost --port 32049 --timeout 60
```

## Best Practices

1. **Always collect baselines before making changes**
2. **Run tests after each significant change**
3. **Review failed tests carefully** - some differences may be expected
4. **Update baselines** when you intentionally change output format
5. **Add tests for new features** as you develop them

## Files

- `test_format_changes.py` - Main test suite
- `baselines.json` - Baseline outputs from working system
- `test_results.json` - Detailed test results (auto-generated)
- `README_FORMAT_TESTS.md` - This file

## Support

For issues or questions:
1. Check test output and `test_results.json`
2. Verify VM connectivity
3. Review EdgeLake logs: `docker logs <container>`
4. Check command syntax in test cases
