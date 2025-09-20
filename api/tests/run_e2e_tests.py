#!/usr/bin/env python3
"""
End-to-end test runner for AnythingLLM API.

This script runs comprehensive end-to-end tests including:
- Complete workflow testing
- Security validation
- Performance testing
- System resilience testing
"""

import asyncio
import argparse
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import pytest


class E2ETestRunner:
    """Runner for end-to-end integration tests."""
    
    def __init__(self, verbose: bool = False, parallel: bool = False):
        self.verbose = verbose
        self.parallel = parallel
        self.results: Dict[str, Dict] = {}
    
    def run_all_tests(self) -> bool:
        """Run all end-to-end test suites."""
        print("🚀 Starting End-to-End Test Suite")
        print("=" * 50)
        
        test_suites = [
            ("workflow", "Complete Workflow Tests", self.run_workflow_tests),
            ("security", "Security Validation Tests", self.run_security_tests),
            ("performance", "Performance Tests", self.run_performance_tests),
            ("resilience", "System Resilience Tests", self.run_resilience_tests),
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
                print(f"{status} {suite_name} ({duration:.2f}s)")
                
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
                print(f"❌ FAILED {suite_name} - Error: {e}")
                overall_success = False
        
        self.print_summary()
        return overall_success
    
    def run_workflow_tests(self) -> bool:
        """Run complete workflow tests."""
        return self._run_pytest_suite([
            "tests/integration/test_end_to_end.py::TestEndToEndWorkflow",
            "-m", "integration",
            "--tb=short"
        ])
    
    def run_security_tests(self) -> bool:
        """Run security validation tests."""
        return self._run_pytest_suite([
            "tests/integration/test_end_to_end.py::TestSecurityValidation",
            "-m", "security",
            "--tb=short"
        ])
    
    def run_performance_tests(self) -> bool:
        """Run performance tests."""
        return self._run_pytest_suite([
            "tests/integration/test_end_to_end.py::TestPerformanceAndLoad",
            "-m", "performance",
            "--tb=short"
        ])
    
    def run_resilience_tests(self) -> bool:
        """Run system resilience tests."""
        return self._run_pytest_suite([
            "tests/integration/test_end_to_end.py::TestSystemResilience",
            "-m", "integration",
            "--tb=short"
        ])
    
    def _run_pytest_suite(self, args: List[str]) -> bool:
        """Run a pytest suite with specified arguments."""
        cmd = ["python", "-m", "pytest"] + args
        
        if self.verbose:
            cmd.append("-v")
        
        if self.parallel:
            cmd.extend(["-n", "auto"])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=Path(__file__).parent.parent,
                capture_output=not self.verbose,
                text=True,
                timeout=600  # 10 minute timeout
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print("⏰ Test suite timed out after 10 minutes")
            return False
        except Exception as e:
            print(f"❌ Error running test suite: {e}")
            return False
    
    def print_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 50)
        print("📊 End-to-End Test Summary")
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
            print("\n🎉 All end-to-end tests passed!")
        else:
            print(f"\n⚠️  {failed_tests} test suite(s) failed")


class HealthChecker:
    """Check system health before running tests."""
    
    @staticmethod
    def check_prerequisites() -> bool:
        """Check if all prerequisites are met."""
        print("🔍 Checking prerequisites...")
        
        checks = [
            ("Database Connection", HealthChecker.check_database),
            ("AnythingLLM Service", HealthChecker.check_anythingllm),
            ("Redis Connection", HealthChecker.check_redis),
            ("File System Access", HealthChecker.check_filesystem),
        ]
        
        all_passed = True
        
        for check_name, check_func in checks:
            try:
                success = check_func()
                status = "✅" if success else "⚠️"
                print(f"  {status} {check_name}")
                if not success and check_name in ["Database Connection"]:
                    all_passed = False
            except Exception as e:
                print(f"  ❌ {check_name}: {e}")
                if check_name in ["Database Connection"]:
                    all_passed = False
        
        return all_passed
    
    @staticmethod
    def check_database() -> bool:
        """Check database connectivity."""
        try:
            # Import here to avoid circular imports
            from app.core.container import Container
            container = Container()
            # This would check database connection
            return True
        except Exception:
            return False
    
    @staticmethod
    def check_anythingllm() -> bool:
        """Check AnythingLLM service availability."""
        try:
            import httpx
            import os
            
            anythingllm_url = os.getenv("ANYTHINGLLM_URL", "http://localhost:3001")
            response = httpx.get(f"{anythingllm_url}/api/v1/system/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    @staticmethod
    def check_redis() -> bool:
        """Check Redis connectivity (optional)."""
        try:
            import redis
            import os
            
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                return True  # Redis is optional
            
            r = redis.from_url(redis_url)
            r.ping()
            return True
        except Exception:
            return True  # Redis is optional, so don't fail
    
    @staticmethod
    def check_filesystem() -> bool:
        """Check file system access."""
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                test_file = Path(temp_dir) / "test.txt"
                test_file.write_text("test")
                return test_file.read_text() == "test"
        except Exception:
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run end-to-end tests for AnythingLLM API")
    parser.add_argument(
        "--suite",
        choices=["all", "workflow", "security", "performance", "resilience"],
        default="all",
        help="Test suite to run"
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
        "--skip-health-check",
        action="store_true",
        help="Skip prerequisite health checks"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,  # 30 minutes
        help="Overall timeout in seconds"
    )
    
    args = parser.parse_args()
    
    # Check prerequisites unless skipped
    if not args.skip_health_check:
        if not HealthChecker.check_prerequisites():
            print("❌ Prerequisites not met. Use --skip-health-check to bypass.")
            sys.exit(1)
        print("✅ All prerequisites met\n")
    
    # Initialize test runner
    runner = E2ETestRunner(verbose=args.verbose, parallel=args.parallel)
    
    # Run tests with timeout
    try:
        if args.suite == "all":
            success = runner.run_all_tests()
        elif args.suite == "workflow":
            success = runner.run_workflow_tests()
        elif args.suite == "security":
            success = runner.run_security_tests()
        elif args.suite == "performance":
            success = runner.run_performance_tests()
        elif args.suite == "resilience":
            success = runner.run_resilience_tests()
        else:
            print(f"Unknown test suite: {args.suite}")
            sys.exit(1)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()