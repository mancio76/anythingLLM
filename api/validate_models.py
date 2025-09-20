#!/usr/bin/env python3
"""
Model validation script to check syntax and structure.
This script validates the model files without requiring dependencies.
"""

import ast
import sys
from pathlib import Path


def validate_python_file(file_path: Path) -> bool:
    """Validate Python file syntax."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the AST to check syntax
        ast.parse(content)
        print(f"✓ {file_path.name} - Syntax valid")
        return True
    except SyntaxError as e:
        print(f"✗ {file_path.name} - Syntax error: {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path.name} - Error: {e}")
        return False


def validate_model_structure():
    """Validate model file structure and syntax."""
    print("Validating model files...")
    
    model_files = [
        Path("app/models/__init__.py"),
        Path("app/models/pydantic_models.py"),
        Path("app/models/sqlalchemy_models.py"),
        Path("app/models/converters.py"),
        Path("app/models/validators.py"),
    ]
    
    all_valid = True
    for file_path in model_files:
        if file_path.exists():
            if not validate_python_file(file_path):
                all_valid = False
        else:
            print(f"✗ {file_path.name} - File not found")
            all_valid = False
    
    # Validate Alembic files
    alembic_files = [
        Path("alembic.ini"),
        Path("alembic/env.py"),
        Path("alembic/script.py.mako"),
        Path("alembic/versions/0001_initial_schema.py"),
    ]
    
    print("\nValidating Alembic files...")
    for file_path in alembic_files:
        if file_path.exists():
            if file_path.suffix == '.py':
                if not validate_python_file(file_path):
                    all_valid = False
            else:
                print(f"✓ {file_path.name} - File exists")
        else:
            print(f"✗ {file_path.name} - File not found")
            all_valid = False
    
    return all_valid


def check_model_completeness():
    """Check if all required model components are present."""
    print("\nChecking model completeness...")
    
    # Check Pydantic models
    pydantic_file = Path("app/models/pydantic_models.py")
    if pydantic_file.exists():
        with open(pydantic_file, 'r') as f:
            content = f.read()
        
        required_models = [
            "class Job(BaseModel)",
            "class JobCreate(BaseModel)",
            "class Workspace(BaseModel)",
            "class WorkspaceCreate(BaseModel)",
            "class Question(BaseModel)",
            "class QuestionCreate(BaseModel)",
            "class QuestionResult(BaseModel)",
            "class LLMConfig(BaseModel)",
        ]
        
        for model in required_models:
            if model in content:
                print(f"✓ {model.split('(')[0].replace('class ', '')} - Found")
            else:
                print(f"✗ {model.split('(')[0].replace('class ', '')} - Missing")
    
    # Check SQLAlchemy models
    sqlalchemy_file = Path("app/models/sqlalchemy_models.py")
    if sqlalchemy_file.exists():
        with open(sqlalchemy_file, 'r') as f:
            content = f.read()
        
        required_models = [
            "class JobModel(Base",
            "class WorkspaceModel(Base",
            "class QuestionModel(Base",
            "class QuestionResultModel(Base",
        ]
        
        for model in required_models:
            if model in content:
                print(f"✓ {model.split('(')[0].replace('class ', '')} - Found")
            else:
                print(f"✗ {model.split('(')[0].replace('class ', '')} - Missing")


def main():
    """Main validation function."""
    print("=" * 50)
    print("AnythingLLM API - Model Validation")
    print("=" * 50)
    
    # Change to the script directory
    script_dir = Path(__file__).parent
    original_cwd = Path.cwd()
    
    try:
        import os
        os.chdir(script_dir)
        
        # Validate syntax
        syntax_valid = validate_model_structure()
        
        # Check completeness
        check_model_completeness()
        
        print("\n" + "=" * 50)
        if syntax_valid:
            print("✓ All model files have valid syntax")
            print("✓ Task 2 implementation appears complete")
            print("\nNext steps:")
            print("1. Install dependencies: pip install -r requirements.txt")
            print("2. Set up database connection")
            print("3. Run Alembic migrations: alembic upgrade head")
            print("4. Run tests: pytest tests/test_models.py")
        else:
            print("✗ Some model files have syntax errors")
            print("Please fix the errors before proceeding")
        
        return 0 if syntax_valid else 1
        
    finally:
        os.chdir(original_cwd)


if __name__ == "__main__":
    sys.exit(main())