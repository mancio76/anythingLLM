#!/usr/bin/env python3
"""
Validate test structure and run basic test checks.
"""

import subprocess
import sys
from pathlib import Path


def check_test_structure():
    """Check if test directory structure is correct."""
    print("🔍 Checking test directory structure...")
    
    required_dirs = [
        "tests/unit",
        "tests/unit/services",
        "tests/unit/repositories",
        "tests/integration",
        "tests/integration/api",
        "tests/security",
        "tests/performance",
        "tests/fixtures",
    ]
    
    missing_dirs = []
    for dir_path in required_dirs:
        if not Path(dir_path).exists():
            missing_dirs.append(dir_path)
    
    if missing_dirs:
        print(f"❌ Missing directories: {missing_dirs}")
        return False
    else:
        print("✅ Test directory structure is correct")
        return True


def check_test_files():
    """Check if test files exist and are properly structured."""
    print("\n🔍 Checking test files...")
    
    required_files = [
        "tests/unit/services/test_document_service.py",
        "tests/unit/services/test_workspace_service.py",
        "tests/unit/services/test_question_service.py",
        "tests/unit/services/test_job_service.py",
        "tests/unit/repositories/test_job_repository.py",
        "tests/unit/repositories/test_cache_repository.py",
        "tests/integration/api/test_document_endpoints.py",
        "tests/security/test_authentication.py",
        "tests/performance/test_concurrent_operations.py",
        "tests/fixtures/mock_data.py",
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing test files: {missing_files}")
        return False
    else:
        print("✅ All required test files exist")
        return True


def validate_pytest_config():
    """Validate pytest configuration."""
    print("\n🔍 Validating pytest configuration...")
    
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ Pytest configuration is valid")
            print(f"   Collected tests: {result.stdout.count('test_')} test functions")
            return True
        else:
            print(f"❌ Pytest configuration error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Pytest collection timed out")
        return False
    except Exception as e:
        print(f"❌ Error running pytest: {e}")
        return False


def check_imports():
    """Check if test imports work correctly."""
    print("\n🔍 Checking test imports...")
    
    try:
        # Try importing the mock data module
        sys.path.insert(0, str(Path.cwd()))
        from tests.fixtures.mock_data import mock_data, mock_files
        print("✅ Mock data imports work correctly")
        
        # Try creating some mock data
        job = mock_data.create_mock_job()
        workspace = mock_data.create_mock_workspace()
        questions = mock_data.create_sample_questions()
        
        print(f"✅ Mock data generation works (job: {job.id}, workspace: {workspace.id}, questions: {len(questions)})")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error creating mock data: {e}")
        return False


def main():
    """Run all validation checks."""
    print("🧪 Validating AnythingLLM API Test Suite")
    print("=" * 50)
    
    checks = [
        check_test_structure,
        check_test_files,
        validate_pytest_config,
        check_imports,
    ]
    
    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"❌ Check failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    if all(results):
        print("🎉 All validation checks passed!")
        print("\nYou can now run tests using:")
        print("  python run_tests.py")
        print("  python -m pytest")
        sys.exit(0)
    else:
        print("❌ Some validation checks failed")
        print(f"   Passed: {sum(results)}/{len(results)}")
        sys.exit(1)


if __name__ == "__main__":
    main()