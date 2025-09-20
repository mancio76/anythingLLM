#!/usr/bin/env python3
"""Validation script for storage implementation."""

import ast
import sys
from pathlib import Path


def validate_python_syntax(file_path: Path) -> bool:
    """Validate Python file syntax."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        ast.parse(content)
        print(f"✓ {file_path.name}: Syntax valid")
        return True
    except SyntaxError as e:
        print(f"✗ {file_path.name}: Syntax error - {e}")
        return False
    except Exception as e:
        print(f"✗ {file_path.name}: Error - {e}")
        return False


def validate_class_structure(file_path: Path, expected_classes: list) -> bool:
    """Validate that expected classes are defined."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Find all class definitions
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        
        missing_classes = set(expected_classes) - set(classes)
        if missing_classes:
            print(f"✗ {file_path.name}: Missing classes - {missing_classes}")
            return False
        
        print(f"✓ {file_path.name}: All expected classes found - {expected_classes}")
        return True
    except Exception as e:
        print(f"✗ {file_path.name}: Error validating classes - {e}")
        return False


def validate_method_structure(file_path: Path, class_name: str, expected_methods: list) -> bool:
    """Validate that expected methods are defined in a class."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        # Find the specific class
        target_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                target_class = node
                break
        
        if not target_class:
            print(f"✗ {file_path.name}: Class {class_name} not found")
            return False
        
        # Find all method definitions in the class (including async methods)
        methods = [node.name for node in target_class.body 
                  if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        
        missing_methods = set(expected_methods) - set(methods)
        if missing_methods:
            print(f"✗ {file_path.name}: Class {class_name} missing methods - {missing_methods}")
            return False
        
        print(f"✓ {file_path.name}: Class {class_name} has all expected methods - {expected_methods}")
        return True
    except Exception as e:
        print(f"✗ {file_path.name}: Error validating methods - {e}")
        return False


def main():
    """Main validation function."""
    print("Validating storage implementation...")
    print("=" * 50)
    
    all_valid = True
    
    # Validate storage_client.py
    storage_client_path = Path("app/integrations/storage_client.py")
    if storage_client_path.exists():
        all_valid &= validate_python_syntax(storage_client_path)
        all_valid &= validate_class_structure(storage_client_path, [
            'StorageClient', 'LocalStorageClient', 'S3StorageClient', 'FileInfo'
        ])
        all_valid &= validate_method_structure(storage_client_path, 'StorageClient', [
            'upload_file', 'download_file', 'delete_file', 'list_files', 'file_exists', 'get_file_url'
        ])
        all_valid &= validate_method_structure(storage_client_path, 'LocalStorageClient', [
            '__init__', 'upload_file', 'download_file', 'delete_file', 'list_files', 'file_exists', 'get_file_url'
        ])
        all_valid &= validate_method_structure(storage_client_path, 'S3StorageClient', [
            '__init__', 'upload_file', 'download_file', 'delete_file', 'list_files', 'file_exists', 'get_file_url'
        ])
    else:
        print(f"✗ {storage_client_path}: File not found")
        all_valid = False
    
    # Validate file_validator.py
    file_validator_path = Path("app/integrations/file_validator.py")
    if file_validator_path.exists():
        all_valid &= validate_python_syntax(file_validator_path)
        all_valid &= validate_class_structure(file_validator_path, ['FileValidator'])
        all_valid &= validate_method_structure(file_validator_path, 'FileValidator', [
            '__init__', 'validate_file_size', 'validate_file_type', 'validate_file',
            'validate_multiple_files', 'get_file_type', 'organize_files_by_type', 'create_from_settings'
        ])
    else:
        print(f"✗ {file_validator_path}: File not found")
        all_valid = False
    
    # Validate storage_factory.py
    storage_factory_path = Path("app/integrations/storage_factory.py")
    if storage_factory_path.exists():
        all_valid &= validate_python_syntax(storage_factory_path)
        all_valid &= validate_class_structure(storage_factory_path, ['StorageFactory'])
        all_valid &= validate_method_structure(storage_factory_path, 'StorageFactory', [
            'create_storage_client', 'create_local_storage_client', 'create_s3_storage_client'
        ])
    else:
        print(f"✗ {storage_factory_path}: File not found")
        all_valid = False
    
    # Validate test file
    test_storage_path = Path("tests/test_storage.py")
    if test_storage_path.exists():
        all_valid &= validate_python_syntax(test_storage_path)
        all_valid &= validate_class_structure(test_storage_path, [
            'TestFileValidator', 'TestLocalStorageClient', 'TestS3StorageClient', 'TestStorageFactory'
        ])
    else:
        print(f"✗ {test_storage_path}: File not found")
        all_valid = False
    
    print("=" * 50)
    if all_valid:
        print("✓ All storage implementation files are valid!")
        return 0
    else:
        print("✗ Some validation errors found")
        return 1


if __name__ == "__main__":
    sys.exit(main())