"""Validate project structure without dependencies."""

import os
import sys
from pathlib import Path

def validate_structure():
    """Validate that all required files and directories exist."""
    
    required_files = [
        "app/__init__.py",
        "app/main.py",
        "app/core/__init__.py",
        "app/core/config.py",
        "app/core/logging.py",
        "app/core/database.py",
        "app/middleware/__init__.py",
        "app/middleware/logging.py",
        "app/middleware/security.py",
        "app/routers/__init__.py",
        "app/routers/health.py",
        "requirements.txt",
        "run.py",
        "README.md",
        "Dockerfile",
        "docker-compose.yml",
        ".env.example",
        ".gitignore",
        "app/.gitignore",
        "pytest.ini",
        "docs/README.md",
        "docs/INSTALL.md",
        "docs/DEVELOPMENT.md",
        "docs/DEPLOYMENT.md",
        "docs/API.md",
        "docs/TESTING.md",
        "tests/__init__.py",
        "tests/conftest.py",
        "tests/test_requirements.py",
        "tests/test_health.py",
        "tests/test_config.py",
        "tests/test_logging.py",
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return False
    
    print("✅ All required files exist")
    
    # Check that Python files can be compiled
    python_files = [f for f in required_files if f.endswith('.py')]
    
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                compile(f.read(), file_path, 'exec')
        except SyntaxError as e:
            print(f"❌ Syntax error in {file_path}: {e}")
            return False
        except UnicodeDecodeError as e:
            print(f"❌ Encoding error in {file_path}: {e}")
            return False
    
    print("✅ All Python files have valid syntax")
    return True

if __name__ == "__main__":
    if validate_structure():
        print("\n🎉 Project structure validation passed!")
        sys.exit(0)
    else:
        print("\n💥 Project structure validation failed!")
        sys.exit(1)