"""Examples demonstrating storage client usage."""

import asyncio
import tempfile
from pathlib import Path
from typing import List

from app.core.config import Settings, StorageType
from app.integrations.file_validator import FileValidator
from app.integrations.storage_factory import StorageFactory


async def example_local_storage():
    """Example of using local storage client."""
    print("=== Local Storage Example ===")
    
    # Create a temporary directory for this example
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create storage client
        from app.integrations.storage_client import LocalStorageClient
        client = LocalStorageClient(temp_dir)
        
        # Create some test files
        test_files_dir = Path(temp_dir) / "test_files"
        test_files_dir.mkdir()
        
        pdf_file = test_files_dir / "document.pdf"
        json_file = test_files_dir / "data.json"
        csv_file = test_files_dir / "report.csv"
        
        pdf_file.write_text("%PDF-1.4 Sample PDF content")
        json_file.write_text('{"key": "value", "number": 42}')
        csv_file.write_text("name,age,city\nJohn,30,NYC\nJane,25,LA")
        
        print(f"Created test files in: {test_files_dir}")
        
        # Upload files
        uploaded_files = []
        for file_path in [pdf_file, json_file, csv_file]:
            storage_key = f"uploads/{file_path.name}"
            result = await client.upload_file(file_path, storage_key)
            uploaded_files.append(storage_key)
            print(f"Uploaded {file_path.name} -> {storage_key}")
        
        # List files
        files = await client.list_files("uploads/")
        print(f"Found {len(files)} files in storage:")
        for file_info in files:
            print(f"  - {file_info.key} ({file_info.size} bytes)")
        
        # Check file existence
        for key in uploaded_files:
            exists = await client.file_exists(key)
            print(f"File {key} exists: {exists}")
        
        # Get file URLs
        for key in uploaded_files:
            url = await client.get_file_url(key)
            print(f"URL for {key}: {url}")
        
        # Download a file
        download_path = Path(temp_dir) / "downloaded_document.pdf"
        success = await client.download_file("uploads/document.pdf", download_path)
        if success:
            print(f"Downloaded file to: {download_path}")
            print(f"Content: {download_path.read_text()[:50]}...")
        
        # Clean up - delete files
        for key in uploaded_files:
            deleted = await client.delete_file(key)
            print(f"Deleted {key}: {deleted}")


async def example_file_validation():
    """Example of using file validator."""
    print("\n=== File Validation Example ===")
    
    # Create validator with 1MB limit and specific file types
    validator = FileValidator(
        max_file_size=1024 * 1024,  # 1MB
        allowed_file_types=['pdf', 'json', 'csv']
    )
    
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        
        # Create test files
        valid_pdf = test_dir / "valid.pdf"
        valid_json = test_dir / "valid.json"
        valid_csv = test_dir / "valid.csv"
        invalid_txt = test_dir / "invalid.txt"
        large_file = test_dir / "large.pdf"
        
        valid_pdf.write_text("%PDF-1.4 Valid PDF")
        valid_json.write_text('{"valid": true}')
        valid_csv.write_text("col1,col2\nval1,val2")
        invalid_txt.write_text("This is a text file")
        large_file.write_bytes(b"x" * (1024 * 1024 + 1))  # > 1MB
        
        test_files = [valid_pdf, valid_json, valid_csv, invalid_txt, large_file]
        
        print("Validating individual files:")
        for file_path in test_files:
            is_valid, error = validator.validate_file(file_path)
            status = "✓ VALID" if is_valid else f"✗ INVALID: {error}"
            print(f"  {file_path.name}: {status}")
        
        print("\nValidating multiple files:")
        valid_files, invalid_files = validator.validate_multiple_files(test_files)
        print(f"Valid files: {[f.name for f in valid_files]}")
        print(f"Invalid files: {[(f.name, err) for f, err in invalid_files]}")
        
        print("\nOrganizing files by type:")
        organized = validator.organize_files_by_type(valid_files)
        for file_type, files in organized.items():
            print(f"  {file_type}: {[f.name for f in files]}")


async def example_storage_factory():
    """Example of using storage factory."""
    print("\n=== Storage Factory Example ===")
    
    # Create mock settings for local storage
    class MockSettings:
        storage_type = StorageType.LOCAL
        storage_path = tempfile.mkdtemp()
        s3_bucket = None
        s3_region = None
        aws_access_key_id = None
        aws_secret_access_key = None
    
    settings = MockSettings()
    
    # Create storage client using factory
    client = StorageFactory.create_storage_client(settings)
    print(f"Created storage client: {type(client).__name__}")
    print(f"Storage path: {client.base_path}")
    
    # Test basic operations
    test_file = Path(settings.storage_path) / "test_input.txt"
    test_file.write_text("Factory test content")
    
    # Upload using factory-created client
    result = await client.upload_file(test_file, "factory_test/uploaded.txt")
    print(f"Upload result: {result}")
    
    # Verify file exists
    exists = await client.file_exists("factory_test/uploaded.txt")
    print(f"File exists: {exists}")
    
    # Clean up
    import shutil
    shutil.rmtree(settings.storage_path, ignore_errors=True)


async def example_complete_workflow():
    """Example of complete file processing workflow."""
    print("\n=== Complete Workflow Example ===")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup
        storage_client = StorageFactory.create_local_storage_client(temp_dir)
        validator = FileValidator(
            max_file_size=1024 * 1024,
            allowed_file_types=['pdf', 'json', 'csv']
        )
        
        # Create mixed test files
        test_dir = Path(temp_dir) / "input"
        test_dir.mkdir()
        
        files_to_create = [
            ("contract.pdf", "%PDF-1.4 Contract content"),
            ("data.json", '{"contract_id": "C001", "value": 50000}'),
            ("report.csv", "item,quantity,price\nWidget,10,25.50"),
            ("readme.txt", "This should be rejected"),
            ("large.pdf", "x" * (1024 * 1024 + 1))  # Too large
        ]
        
        created_files = []
        for filename, content in files_to_create:
            file_path = test_dir / filename
            if filename == "large.pdf":
                file_path.write_bytes(content.encode())
            else:
                file_path.write_text(content)
            created_files.append(file_path)
        
        print(f"Created {len(created_files)} test files")
        
        # Step 1: Validate files
        print("\nStep 1: Validating files...")
        valid_files, invalid_files = validator.validate_multiple_files(created_files)
        
        print(f"Valid files ({len(valid_files)}):")
        for file_path in valid_files:
            print(f"  ✓ {file_path.name}")
        
        print(f"Invalid files ({len(invalid_files)}):")
        for file_path, error in invalid_files:
            print(f"  ✗ {file_path.name}: {error}")
        
        # Step 2: Organize valid files by type
        print("\nStep 2: Organizing files by type...")
        organized = validator.organize_files_by_type(valid_files)
        for file_type, files in organized.items():
            print(f"  {file_type}: {len(files)} files")
        
        # Step 3: Upload valid files to storage
        print("\nStep 3: Uploading valid files...")
        uploaded_files = []
        for file_path in valid_files:
            file_type = validator.get_file_type(file_path)
            storage_key = f"processed/{file_type}/{file_path.name}"
            
            try:
                result = await storage_client.upload_file(file_path, storage_key)
                uploaded_files.append(storage_key)
                print(f"  ✓ Uploaded {file_path.name} -> {storage_key}")
            except Exception as e:
                print(f"  ✗ Failed to upload {file_path.name}: {e}")
        
        # Step 4: Verify uploads
        print("\nStep 4: Verifying uploads...")
        for key in uploaded_files:
            exists = await storage_client.file_exists(key)
            print(f"  {key}: {'✓' if exists else '✗'}")
        
        # Step 5: List all uploaded files
        print("\nStep 5: Listing all uploaded files...")
        all_files = await storage_client.list_files("processed/")
        print(f"Total files in storage: {len(all_files)}")
        for file_info in all_files:
            print(f"  - {file_info.key} ({file_info.size} bytes)")
        
        print("\nWorkflow completed successfully!")


async def main():
    """Run all examples."""
    print("Storage Implementation Examples")
    print("=" * 50)
    
    try:
        await example_local_storage()
        await example_file_validation()
        await example_storage_factory()
        await example_complete_workflow()
        
        print("\n" + "=" * 50)
        print("All examples completed successfully!")
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())