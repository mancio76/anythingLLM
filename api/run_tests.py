#!/usr/bin/env python3
"""
Comprehensive test runner for the AnythingLLM API.

This script provides different test execution modes:
- Unit tests only
- Integration tests only
- Security tests only
- Performance tests only
- All tests
- Coverage reporting
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, capture_output=False)
    
    if result.returncode != 0:
        print(f"\n❌ {description} failed with exit code {result.returncode}")
        return False
    else:
        print(f"\n✅ {description} completed successfully")
        return True


def main():
    parser = argparse.ArgumentParser(description="Run AnythingLLM API tests")
    parser.add_argument(
        "--type",
        choices=["unit", "integration", "security", "performance", "all"],
        default="all",
        help="Type of tests to run (default: all)"
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run tests with coverage reporting"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel (requires pytest-xdist)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip slow tests"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        help="Run tests matching pattern"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test type selection
    if args.type == "unit":
        cmd.extend(["tests/unit/", "-m", "unit"])
    elif args.type == "integration":
        cmd.extend(["tests/integration/", "-m", "integration"])
    elif args.type == "security":
        cmd.extend(["tests/security/", "-m", "security"])
    elif args.type == "performance":
        cmd.extend(["tests/performance/", "-m", "performance"])
    else:  # all
        cmd.append("tests/")
    
    # Add coverage if requested
    if args.coverage:
        cmd.extend([
            "--cov=app",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-report=xml",
            "--cov-fail-under=80"
        ])
    
    # Add parallel execution if requested
    if args.parallel:
        cmd.extend(["-n", "auto"])
    
    # Add verbose output if requested
    if args.verbose:
        cmd.append("-vv")
    
    # Skip slow tests if requested
    if args.fast:
        cmd.extend(["-m", "not slow"])
    
    # Add pattern matching if specified
    if args.pattern:
        cmd.extend(["-k", args.pattern])
    
    # Run the tests
    success = run_command(cmd, f"{args.type.title()} Tests")
    
    if args.coverage and success:
        print(f"\n📊 Coverage report generated:")
        print(f"   - HTML: htmlcov/index.html")
        print(f"   - XML: coverage.xml")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()