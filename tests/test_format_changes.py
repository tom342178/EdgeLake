#!/usr/bin/env python3
"""
Test Suite for Format Changes Validation

This test suite validates that format-related changes to EdgeLake commands
don't break existing functionality while adding new MCP format support.

Usage:
    # Collect baselines from working VM
    python test_format_changes.py --mode baseline --host <vm-ip> --port 32049 --output baselines.json

    # Run tests against current implementation
    python test_format_changes.py --mode test --host localhost --port 32049 --baseline baselines.json

    # Run tests without baseline (just verify commands work)
    python test_format_changes.py --mode test --host localhost --port 32049
"""

import argparse
import json
import sys
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import requests
from requests.exceptions import RequestException


@dataclass
class TestCase:
    """Represents a single test case"""
    name: str
    command: str
    description: str
    expected_format: str  # 'json', 'table', 'mcp', etc.
    should_succeed: bool = True
    min_response_fields: Optional[List[str]] = None


@dataclass
class TestResult:
    """Represents test result"""
    test_name: str
    command: str
    passed: bool
    actual_output: Any
    expected_output: Optional[Any]
    error_message: Optional[str] = None
    execution_time: float = 0.0


class EdgeLakeTestClient:
    """Client for executing EdgeLake commands via REST API"""

    def __init__(self, host: str, port: int, timeout: int = 30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"

    def execute_command(self, command: str) -> Tuple[bool, Any, str]:
        """
        Execute command and return (success, response, error_msg)
        """
        try:
            start_time = time.time()
            response = requests.get(
                self.base_url,
                headers={
                    "User-Agent": "anylog",
                    "command": command,
                },
                timeout=self.timeout,
                verify=False
            )
            execution_time = time.time() - start_time

            if response.status_code != 200:
                return False, None, f"HTTP {response.status_code}: {response.text}"

            # Try to parse as JSON
            try:
                data = response.json()
                return True, data, ""
            except json.JSONDecodeError:
                # Return as text
                return True, response.text, ""

        except RequestException as e:
            return False, None, f"Request failed: {str(e)}"
        except Exception as e:
            return False, None, f"Unexpected error: {str(e)}"


class FormatChangeTestSuite:
    """Test suite for validating format changes"""

    def __init__(self, client: EdgeLakeTestClient, baseline: Optional[Dict] = None):
        self.client = client
        self.baseline = baseline or {}
        self.results: List[TestResult] = []

    def get_test_cases(self) -> List[TestCase]:
        """Define all test cases"""
        return [
            # Existing blockchain get commands (should not break)
            TestCase(
                name="blockchain_get_table_basic",
                command="blockchain get table",
                description="Basic blockchain get table without format",
                expected_format="json",
            ),
            TestCase(
                name="blockchain_get_table_with_bring",
                command="blockchain get table bring.json [*]",
                description="Blockchain get table with bring.json",
                expected_format="json",
            ),
            TestCase(
                name="blockchain_get_operator",
                command="blockchain get operator",
                description="Get operator policies",
                expected_format="json",
            ),
            TestCase(
                name="blockchain_get_cluster",
                command="blockchain get cluster",
                description="Get cluster policies",
                expected_format="json",
            ),
            TestCase(
                name="blockchain_get_all",
                command="blockchain get *",
                description="Get all policies",
                expected_format="json",
            ),

            # New MCP format commands
            TestCase(
                name="blockchain_get_schema_mcp",
                command="blockchain get table where format = mcp",
                description="Get all database/table combinations in MCP format",
                expected_format="mcp",
                min_response_fields=None,  # Should be array of objects with 'database' and 'table'
            ),

            # Get version commands
            TestCase(
                name="get_version_basic",
                command="get version",
                description="Get version without format",
                expected_format="text",
            ),
            TestCase(
                name="get_version_mcp",
                command="get version where format = mcp",
                description="Get version in MCP format",
                expected_format="mcp",
                min_response_fields=["version", "node_name", "node_type"],
            ),

            # Get status commands (if implemented)
            TestCase(
                name="get_status_basic",
                command="get status",
                description="Get status without format",
                expected_format="text",
            ),
            TestCase(
                name="get_status_mcp",
                command="get status where format = mcp include statistics",
                description="Get status in MCP format",
                expected_format="mcp",
                should_succeed=True,  # May not be implemented yet
            ),
        ]

    def run_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case"""
        print(f"  Running: {test_case.name}...", end=" ")

        start_time = time.time()
        success, output, error = self.client.execute_command(test_case.command)
        execution_time = time.time() - start_time

        # Get baseline if available
        baseline_output = self.baseline.get(test_case.name)

        # Validate result
        passed = True
        error_message = None

        if not success:
            if test_case.should_succeed:
                passed = False
                error_message = f"Command failed: {error}"
            else:
                # Expected to fail
                passed = True
        else:
            # Validate output format
            if test_case.expected_format == "mcp":
                if not self._validate_mcp_format(output, test_case):
                    passed = False
                    error_message = "Output doesn't match MCP format expectations"
            elif test_case.expected_format == "json":
                if not self._validate_json_format(output):
                    passed = False
                    error_message = "Output is not valid JSON"

            # Compare with baseline if available
            if passed and baseline_output is not None:
                if not self._compare_with_baseline(output, baseline_output):
                    passed = False
                    error_message = "Output differs from baseline"

        result = TestResult(
            test_name=test_case.name,
            command=test_case.command,
            passed=passed,
            actual_output=output,
            expected_output=baseline_output,
            error_message=error_message,
            execution_time=execution_time,
        )

        self.results.append(result)

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} ({execution_time:.2f}s)")
        if error_message:
            print(f"    Error: {error_message}")

        return result

    def _validate_mcp_format(self, output: Any, test_case: TestCase) -> bool:
        """Validate MCP format output"""
        # MCP format should be valid JSON
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                return False

        # Check for required fields if specified
        if test_case.min_response_fields:
            if not isinstance(output, dict):
                return False
            for field in test_case.min_response_fields:
                if field not in output:
                    return False

        return True

    def _validate_json_format(self, output: Any) -> bool:
        """Validate JSON format output"""
        if isinstance(output, str):
            try:
                json.loads(output)
                return True
            except json.JSONDecodeError:
                return False
        return True

    def _compare_with_baseline(self, actual: Any, baseline: Any) -> bool:
        """Compare actual output with baseline"""
        # For now, just check that types match
        # Could be enhanced for deeper comparison
        if type(actual) != type(baseline):
            return False

        if isinstance(actual, dict):
            # Check that all baseline keys exist in actual
            return all(key in actual for key in baseline.keys())
        elif isinstance(actual, list):
            # Check that lengths match (or actual is longer)
            return len(actual) >= len(baseline)

        return True

    def run_all_tests(self) -> bool:
        """Run all test cases and return overall success"""
        print("\n" + "="*70)
        print("EdgeLake Format Changes Test Suite")
        print("="*70)

        test_cases = self.get_test_cases()
        print(f"\nRunning {len(test_cases)} test cases...\n")

        for test_case in test_cases:
            self.run_test(test_case)

        # Print summary
        print("\n" + "="*70)
        print("Test Summary")
        print("="*70)

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        print(f"Total: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed > 0:
            print("\nFailed Tests:")
            for result in self.results:
                if not result.passed:
                    print(f"  - {result.test_name}: {result.error_message}")

        return failed == 0

    def collect_baselines(self) -> Dict[str, Any]:
        """Collect baseline outputs for all test cases"""
        print("\n" + "="*70)
        print("Collecting Baselines from Working System")
        print("="*70)

        baselines = {}
        test_cases = self.get_test_cases()

        # Only collect baselines for existing commands (not new MCP ones)
        baseline_cases = [tc for tc in test_cases if "mcp" not in tc.name]

        print(f"\nCollecting {len(baseline_cases)} baselines...\n")

        for test_case in baseline_cases:
            print(f"  Collecting: {test_case.name}...", end=" ")
            success, output, error = self.client.execute_command(test_case.command)

            if success:
                baselines[test_case.name] = output
                print("✓")
            else:
                print(f"✗ (skipped: {error})")

        print(f"\nCollected {len(baselines)} baselines")
        return baselines


def main():
    parser = argparse.ArgumentParser(
        description="Test suite for EdgeLake format changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--mode",
        choices=["baseline", "test"],
        required=True,
        help="Mode: 'baseline' to collect from working VM, 'test' to run tests"
    )
    parser.add_argument(
        "--host",
        required=True,
        help="EdgeLake node hostname or IP"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=32049,
        help="EdgeLake REST port (default: 32049)"
    )
    parser.add_argument(
        "--output",
        help="Output file for baselines (required for baseline mode)"
    )
    parser.add_argument(
        "--baseline",
        help="Baseline file to compare against (optional for test mode)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.mode == "baseline" and not args.output:
        parser.error("--output is required in baseline mode")

    # Create client
    client = EdgeLakeTestClient(args.host, args.port, args.timeout)

    # Load baseline if provided
    baseline = None
    if args.baseline:
        try:
            with open(args.baseline, 'r') as f:
                baseline = json.load(f)
            print(f"Loaded baseline from {args.baseline}")
        except Exception as e:
            print(f"Warning: Could not load baseline: {e}")

    # Create test suite
    suite = FormatChangeTestSuite(client, baseline)

    # Run mode-specific operations
    if args.mode == "baseline":
        baselines = suite.collect_baselines()

        # Save baselines
        try:
            with open(args.output, 'w') as f:
                json.dump(baselines, f, indent=2)
            print(f"\nBaselines saved to {args.output}")
            return 0
        except Exception as e:
            print(f"\nError saving baselines: {e}")
            return 1

    else:  # test mode
        success = suite.run_all_tests()

        # Save detailed results
        results_file = "test_results.json"
        try:
            with open(results_file, 'w') as f:
                results_dict = [asdict(r) for r in suite.results]
                json.dump(results_dict, f, indent=2)
            print(f"\nDetailed results saved to {results_file}")
        except Exception as e:
            print(f"\nWarning: Could not save results: {e}")

        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
