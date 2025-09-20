#!/usr/bin/env python3
"""
Comprehensive integration test runner for AnythingLLM API.

This script runs all integration tests including API endpoints, database integration,
external service integration, and comprehensive workflow testing.
"""

import asyncio
import argparse
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest


class IntegrationTestRunner:
    """Runner for integration tests with comprehensive reporting."""
    
    def __init__(self, verbose: bool = False, parallel: bool = False, coverage: bool = False):
        self.verbose = verbose
        self.parallel = parallel
        self.coverage = coverage
        self.results: Dict[str, Dict] = {}
    
    def run_all_integration_tests(self) -> bool:
        """Run all integration test suites."""
        print("🚀 Starting Integration Test Suite")
        print("=" * 50)
        
        test_suites = [
            ("api_endpoints", "API Endpoint Tests", self.run_api_endpoint_tests),
            ("database", "Database Integration Tests", self.run_database_tests),
            ("external_services", "External Service Tests", self.run_external_service_tests),
            ("workflow", "End-to-End Workflow Tests", self.run_workflow_tests),
            ("security", "Security Integration Tests", self.run_security_tests),
            ("performance", "Performance Integration Tests", self.run_performance_tests),
        ]
        
        overall_success = True
        
        for suite_id, suite_name, test_func in test_suites:
            print(f"\n📋 Running {suite_name}...")
            start_time = time.time()
            
            try:
                success = test_func()
                duration = time.time() - start_time
                
                self.results[suite_id] = {
                    "name": suite_name,
                    "success": success,
                    "duration": duration,
                    "error": None
                }
                
                status = "✅ PASSED" if success else "❌ FAILED"
                print(f"   {status} ({duration:.2f}s)")
                
                if not success:
                    overall_success = False
                    
            except Exception as e:
                duration = time.time() - start_time
                self.results[suite_id] = {
                    "name": suite_name,
                    "success": False,
                    "duration": duration,
                    "error": str(e)
                }
                print(f"   ❌ FAILED - Error: {e}")
                overall_success = False
        
        self.print_summary()
        return overall_success
    
    def run_api_endpoint_tests(self) -> bool:
        """Run API endpoint integration tests."""
        return self._run_pytest_suite([
            "tests/integration/api/",
            "-m", "integration",
            "--tb=short"
        ])
    
    def run_database_tests(self) -> bool:
        """Run database integration tests."""
        return self._run_pytest_suite([
            "tests/integration/database/",
            "-m", "database",
            "--tb=short"
        ])
    
    def run_external_service_tests(self) -> bool:
        """Run external service integration tests."""
        return self._run_pytest_suite([
            "tests/integration/external/",
            "-m", "external",
            "--tb=short"
        ])
    
    def run_workflow_tests(self) -> bool:
        """Run end-to-end workflow tests."""
        return self._run_pytest_suite([
            "tests/integration/test_end_to_end.py::TestEndToEndWorkflow",
            "-m", "integration",
            "--tb=short"
        ])
    
    def run_security_tests(self) -> bool:
        """Run security integration tests."""
        return self._run_pytest_suite([
            "tests/security/",
            "tests/integration/test_end_to_end.py::TestSecurityValidation",
            "-m", "security",
            "--tb=short"
        ])
    
    def run_performance_tests(self) -> bool:
        """Run performance integration tests."""
        return self._run_pytest_suite([
            "tests/performance/",
            "tests/integration/test_end_to_end.py::TestPerformanceAndLoad",
            "-m", "performance",
            "--tb=short"
        ])
    
    def _run_pytest_suite(self, args: List[str]) -> bool:
        """Run a pytest suite with specified arguments."""
        cmd = ["python", "-m", "pytest"] + args
        
        if self.verbose:
            cmd.append("-v")
        
        if self.parallel:
            cmd.extend(["-n", "auto"])
        
        if self.coverage:
            cmd.extend([
                "--cov=app",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov"
            ])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=Path(__file__).parent.parent,
                capture_output=not self.verbose,
                text=True,
                timeout=900  # 15 minute timeout
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print("   ⏰ Test suite timed out after 15 minutes")
            return False
        except Exception as e:
            print(f"   ❌ Error running test suite: {e}")
            return False
    
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 50)
        print("📊 Integration Test Summary")
        print("=" * 50)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["success"])
        failed_tests = total_tests - passed_tests
        total_duration = sum(r["duration"] for r in self.results.values())
        
        print(f"Total Test Suites: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Total Duration: {total_duration:.2f}s")
        print()
        
        for suite_id, result in self.results.items():
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['name']}: {result['duration']:.2f}s")
            if result["error"]:
                print(f"   Error: {result['error']}")
        
        if failed_tests == 0:
            print("\n🎉 All integration tests passed!")
        else:
            print(f"\n⚠️  {failed_tests} test suite(s) failed")


class TestEnvironmentChecker:
    """Check test environment prerequisites."""
    
    @staticmethod
    def check_prerequisites() -> bool:
        """Check if all prerequisites are met for integration testing."""
        print("🔍 Checking integration test prerequisites...")
        
        checks = [
            ("Python Environment", TestEnvironmentChecker.check_python_env),
            ("Required Packages", TestEnvironmentChecker.check_packages),
            ("Test Database", TestEnvironmentChecker.check_test_database),
            ("Environment Variables", TestEnvironmentChecker.check_env_vars),
            ("File System Access", TestEnvironmentChecker.check_filesystem),
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            try:
                success = check_func()
                status = "✅" if success else "⚠️"
                print(f"  {status} {check_name}")
                if not success and check_name in ["Python Environment", "Required Packages"]:
                    all_passed = False
            except Exception as e:
                print(f"  ❌ {check_name}: {e}")
                if check_name in ["Python Environment", "Required Packages"]:
                    all_passed = False
        
        return all_passed
    
    @staticmethod
    def check_python_env() -> bool:
        """Check Python environment."""
        try:
            import sys
            return sys.version_info >= (3, 8)
        except Exception:
            return False
    
    @staticmethod
    def check_packages() -> bool:
        """Check required packages are installed."""
        required_packages = [
            "pytest",
            "pytest-asyncio",
            "httpx",
            "fastapi",
            "pydantic",
            "sqlalchemy",
        ]
        
        try:
            for package in required_packages:
                __import__(package.replace("-", "_"))
            return True
        except ImportError:
            return False
    
    @staticmethod
    def check_test_database() -> bool:
        """Check test database availability (optional)."""
        try:
            import os
            db_url = os.getenv("DATABASE_URL")
            return db_url is not None
        except Exception:
            return True  # Optional check
    
    @staticmethod
    def check_env_vars() -> bool:
        """Check required environment variables."""
        import os
        required_vars = [
            "SECRET_KEY",
        ]
        
        optional_vars = [
            "DATABASE_URL",
            "ANYTHINGLLM_URL",
            "ANYTHINGLLM_API_KEY",
        ]
        
        # Check required vars
        for var in required_vars:
            if not os.getenv(var):
                return False
        
        return True
    
    @staticmethod
    def check_filesystem() -> bool:
        """Check file system access."""
        try:
            import tempfile
            from pathlib import Path
            
            with tempfile.TemporaryDirectory() as temp_dir:
                test_file = Path(temp_dir) / "test.txt"
                test_file.write_text("test")
                return test_file.read_text() == "test"
        except Exception:
            return False


def run_specific_test_category(category: str, verbose: bool = False) -> bool:
    """Run a specific category of integration tests."""
    runner = IntegrationTestRunner(verbose=verbose)
    
    if category == "api":
        return runner.run_api_endpoint_tests()
    elif category == "database":
        return runner.run_database_tests()
    elif category == "external":
        return runner.run_external_service_tests()
    elif category == "workflow":
        return runner.run_workflow_tests()
    elif category == "security":
        return runner.run_security_tests()
    elif category == "performance":
        return runner.run_performance_tests()
    else:
        print(f"Unknown test category: {category}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run integration tests for AnythingLLM API")
    parser.add_argument(
        "--category",
        choices=["all", "api", "database", "external", "workflow", "security", "performance"],
        default="all",
        help="Test category to run"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--parallel", "-p",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--skip-prereq-check",
        action="store_true",
        help="Skip prerequisite checks"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip slow tests"
    )
    
    args = parser.parse_args()
    
    # Check prerequisites unless skipped
    if not args.skip_prereq_check:
        if not TestEnvironmentChecker.check_prerequisites():
            print("❌ Prerequisites not met. Use --skip-prereq-check to bypass.")
            sys.exit(1)
        print("✅ All prerequisites met\n")
    
    # Initialize test runner
    runner = IntegrationTestRunner(
        verbose=args.verbose,
        parallel=args.parallel,
        coverage=args.coverage
    )
    
    # Run tests
    try:
        if args.category == "all":
            success = runner.run_all_integration_tests()
        else:
            success = run_specific_test_category(args.category, args.verbose)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()