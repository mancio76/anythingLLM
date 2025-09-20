"""Tests for storage client implementations and file validation."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings, StorageType
from app.integrations.file_validator import FileValidator, FileValidationError
from app.integrations.storage_client import (
    FileInfo,
    FileNotFoundError,
    LocalStorageClient,
    S3StorageClient,
    StorageError
)
from app.integrations.storage_factory import StorageFactory, StorageConfigError


class TestFileValidator:
    """Test file validation utilities."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = FileValidator(
            max_file_size=1024 * 1024,  # 1MB
            allowed_file_types=['pdf', 'json', 'csv']
        )
    
    def test_init(self):
        """Test FileValidator initialization."""
        assert self.validator.max_file_size == 1024 * 1024
        assert self.validator.allowed_file_types == {'pdf', 'json', 'csv'}
        assert '.pdf' in self.validator.allowed_extensions
        assert '.json' in self.validator.allowed_extensions
        assert '.csv' in self.validator.allowed_extensions
        assert 'application/pdf' in self.validator.allowed_mime_types
    
    def test_validate_file_size_valid(self, tmp_path):
        """Test file size validation with valid file."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("small content")
        
        result = self.validator.validate_file_size(test_file)
        assert result is True
    
    def test_validate_file_size_too_large(self, tmp_path):
        """Test file size validation with oversized file."""
        test_file = tmp_path / "large.pdf"
        # Create a file larger than 1MB
        test_file.write_bytes(b"x" * (1024 * 1024 + 1))
        
        with pytest.raises(FileValidationError, match="exceeds maximum allowed size"):
            self.validator.validate_file_size(test_file)
    
    def test_validate_file_size_nonexistent(self, tmp_path):
        """Test file size validation with non-existent file."""
        test_file = tmp_path / "nonexistent.pdf"
        
        with pytest.raises(FileValidationError, match="File does not exist"):
            self.validator.validate_file_size(test_file)
    
    def test_validate_file_type_valid_pdf(self, tmp_path):
        """Test file type validation with valid PDF."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4")
        
        result = self.validator.validate_file_type(test_file)
        assert result is True
    
    def test_validate_file_type_valid_json(self, tmp_path):
        """Test file type validation with valid JSON."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"key": "value"}')
        
        result = self.validator.validate_file_type(test_file)
        assert result is True
    
    def test_validate_file_type_valid_csv(self, tmp_path):
        """Test file type validation with valid CSV."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("col1,col2\nval1,val2")
        
        result = self.validator.validate_file_type(test_file)
        assert result is True
    
    def test_validate_file_type_invalid_extension(self, tmp_path):
        """Test file type validation with invalid extension."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        with pytest.raises(FileValidationError, match="File extension '.txt' is not allowed"):
            self.validator.validate_file_type(test_file)
    
    def test_validate_file_complete_valid(self, tmp_path):
        """Test complete file validation with valid file."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("small pdf content")
        
        is_valid, error = self.validator.validate_file(test_file)
        assert is_valid is True
        assert error is None
    
    def test_validate_file_complete_invalid(self, tmp_path):
        """Test complete file validation with invalid file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        is_valid, error = self.validator.validate_file(test_file)
        assert is_valid is False
        assert "not allowed" in error
    
    def test_validate_multiple_files(self, tmp_path):
        """Test validation of multiple files."""
        valid_file = tmp_path / "valid.pdf"
        valid_file.write_text("content")
        
        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("content")
        
        valid_files, invalid_files = self.validator.validate_multiple_files([valid_file, invalid_file])
        
        assert len(valid_files) == 1
        assert valid_files[0] == valid_file
        assert len(invalid_files) == 1
        assert invalid_files[0][0] == invalid_file
    
    def test_get_file_type(self, tmp_path):
        """Test file type detection."""
        pdf_file = tmp_path / "test.pdf"
        json_file = tmp_path / "test.json"
        unknown_file = tmp_path / "test.txt"
        
        assert self.validator.get_file_type(pdf_file) == "pdf"
        assert self.validator.get_file_type(json_file) == "json"
        assert self.validator.get_file_type(unknown_file) is None
    
    def test_organize_files_by_type(self, tmp_path):
        """Test file organization by type."""
        pdf_file = tmp_path / "test.pdf"
        json_file = tmp_path / "test.json"
        csv_file = tmp_path / "test.csv"
        unknown_file = tmp_path / "test.txt"
        
        files = [pdf_file, json_file, csv_file, unknown_file]
        organized = self.validator.organize_files_by_type(files)
        
        assert len(organized['pdf']) == 1
        assert len(organized['json']) == 1
        assert len(organized['csv']) == 1
        assert len(organized['unknown']) == 1
    
    def test_create_from_settings(self):
        """Test creating validator from settings."""
        settings = MagicMock()
        settings.max_file_size = 2048
        settings.allowed_file_types = ['pdf', 'json']
        
        validator = FileValidator.create_from_settings(settings)
        
        assert validator.max_file_size == 2048
        assert validator.allowed_file_types == {'pdf', 'json'}


class TestLocalStorageClient:
    """Test local storage client implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.client = LocalStorageClient(self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_upload_file(self, tmp_path):
        """Test file upload to local storage."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        
        result = await self.client.upload_file(source_file, "test/uploaded.txt")
        
        assert "uploaded.txt" in result
        uploaded_path = Path(result)
        assert uploaded_path.exists()
        assert uploaded_path.read_text() == "test content"
    
    @pytest.mark.asyncio
    async def test_upload_file_nonexistent_source(self, tmp_path):
        """Test upload with non-existent source file."""
        source_file = tmp_path / "nonexistent.txt"
        
        with pytest.raises(FileNotFoundError):
            await self.client.upload_file(source_file, "test/uploaded.txt")
    
    @pytest.mark.asyncio
    async def test_download_file(self, tmp_path):
        """Test file download from local storage."""
        # First upload a file
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        await self.client.upload_file(source_file, "test/file.txt")
        
        # Then download it
        download_path = tmp_path / "downloaded.txt"
        result = await self.client.download_file("test/file.txt", download_path)
        
        assert result is True
        assert download_path.exists()
        assert download_path.read_text() == "test content"
    
    @pytest.mark.asyncio
    async def test_download_file_not_found(self, tmp_path):
        """Test download of non-existent file."""
        download_path = tmp_path / "downloaded.txt"
        
        with pytest.raises(FileNotFoundError):
            await self.client.download_file("nonexistent.txt", download_path)
    
    @pytest.mark.asyncio
    async def test_delete_file(self, tmp_path):
        """Test file deletion from local storage."""
        # First upload a file
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        await self.client.upload_file(source_file, "test/file.txt")
        
        # Then delete it
        result = await self.client.delete_file("test/file.txt")
        
        assert result is True
        assert not await self.client.file_exists("test/file.txt")
    
    @pytest.mark.asyncio
    async def test_delete_file_not_found(self):
        """Test deletion of non-existent file."""
        result = await self.client.delete_file("nonexistent.txt")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_list_files(self, tmp_path):
        """Test file listing in local storage."""
        # Upload some files
        for i in range(3):
            source_file = tmp_path / f"source{i}.txt"
            source_file.write_text(f"content {i}")
            await self.client.upload_file(source_file, f"test/file{i}.txt")
        
        files = await self.client.list_files("test/")
        
        assert len(files) == 3
        assert all(isinstance(f, FileInfo) for f in files)
        assert all("file" in f.key for f in files)
    
    @pytest.mark.asyncio
    async def test_file_exists(self, tmp_path):
        """Test file existence check."""
        # Upload a file
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        await self.client.upload_file(source_file, "test/file.txt")
        
        assert await self.client.file_exists("test/file.txt") is True
        assert await self.client.file_exists("nonexistent.txt") is False
    
    @pytest.mark.asyncio
    async def test_get_file_url(self, tmp_path):
        """Test file URL generation."""
        # Upload a file
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        await self.client.upload_file(source_file, "test/file.txt")
        
        url = await self.client.get_file_url("test/file.txt")
        
        assert url.startswith("file://")
        assert "file.txt" in url
    
    @pytest.mark.asyncio
    async def test_get_file_url_not_found(self):
        """Test URL generation for non-existent file."""
        with pytest.raises(FileNotFoundError):
            await self.client.get_file_url("nonexistent.txt")
    
    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        # These should all resolve to safe paths within base_path
        safe_path1 = self.client._get_full_path("../../../etc/passwd")
        safe_path2 = self.client._get_full_path("./test/../../../etc/passwd")
        safe_path3 = self.client._get_full_path("test/../../etc/passwd")
        
        base_path = Path(self.temp_dir).resolve()
        assert safe_path1.is_relative_to(base_path)
        assert safe_path2.is_relative_to(base_path)
        assert safe_path3.is_relative_to(base_path)


class TestS3StorageClient:
    """Test S3 storage client implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.client = S3StorageClient(
            bucket="test-bucket",
            region="us-east-1",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret"
        )
    
    @pytest.mark.asyncio
    @patch('aioboto3.Session')
    async def test_upload_file(self, mock_session, tmp_path):
        """Test file upload to S3."""
        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client
        
        source_file = tmp_path / "source.txt"
        source_file.write_text("test content")
        
        result = await self.client.upload_file(source_file, "test/uploaded.txt")
        
        assert result == "s3://test-bucket/test/uploaded.txt"
        mock_s3_client.upload_file.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('aioboto3.Session')
    async def test_download_file(self, mock_session, tmp_path):
        """Test file download from S3."""
        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client
        
        download_path = tmp_path / "downloaded.txt"
        result = await self.client.download_file("test/file.txt", download_path)
        
        assert result is True
        mock_s3_client.download_file.assert_called_once_with(
            "test-bucket", "test/file.txt", str(download_path)
        )
    
    @pytest.mark.asyncio
    @patch('aioboto3.Session')
    async def test_delete_file(self, mock_session):
        """Test file deletion from S3."""
        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client
        
        result = await self.client.delete_file("test/file.txt")
        
        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/file.txt"
        )
    
    @pytest.mark.asyncio
    @patch('aioboto3.Session')
    async def test_list_files(self, mock_session):
        """Test file listing in S3."""
        # Mock S3 client and paginator
        mock_s3_client = AsyncMock()
        mock_paginator = AsyncMock()
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client
        mock_s3_client.get_paginator.return_value = mock_paginator
        
        # Mock paginator response
        mock_page = {
            'Contents': [
                {
                    'Key': 'test/file1.txt',
                    'Size': 100,
                    'LastModified': '2024-01-01T00:00:00Z'
                },
                {
                    'Key': 'test/file2.txt',
                    'Size': 200,
                    'LastModified': '2024-01-02T00:00:00Z'
                }
            ]
        }
        
        async def mock_paginate(*args, **kwargs):
            yield mock_page
        
        mock_paginator.paginate.return_value = mock_paginate()
        
        files = await self.client.list_files("test/")
        
        assert len(files) == 2
        assert all(isinstance(f, FileInfo) for f in files)
        assert files[0].key == 'test/file1.txt'
        assert files[0].size == 100
    
    @pytest.mark.asyncio
    @patch('aioboto3.Session')
    async def test_file_exists(self, mock_session):
        """Test file existence check in S3."""
        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client
        
        result = await self.client.file_exists("test/file.txt")
        
        assert result is True
        mock_s3_client.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/file.txt"
        )
    
    @pytest.mark.asyncio
    @patch('aioboto3.Session')
    async def test_get_file_url(self, mock_session):
        """Test presigned URL generation for S3."""
        # Mock S3 client
        mock_s3_client = AsyncMock()
        mock_s3_client.head_object.return_value = {}  # File exists
        mock_s3_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/test/file.txt"
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client
        
        url = await self.client.get_file_url("test/file.txt", expires_in=3600)
        
        assert url.startswith("https://s3.amazonaws.com")
        mock_s3_client.generate_presigned_url.assert_called_once()


class TestStorageFactory:
    """Test storage factory implementation."""
    
    def test_create_local_storage_client(self):
        """Test creation of local storage client."""
        settings = MagicMock()
        settings.storage_type = StorageType.LOCAL
        settings.storage_path = "/tmp/test"
        
        client = StorageFactory.create_storage_client(settings)
        
        assert isinstance(client, LocalStorageClient)
        assert str(client.base_path).endswith("test")
    
    def test_create_s3_storage_client(self):
        """Test creation of S3 storage client."""
        settings = MagicMock()
        settings.storage_type = StorageType.S3
        settings.s3_bucket = "test-bucket"
        settings.s3_region = "us-east-1"
        settings.aws_access_key_id = "test-key"
        settings.aws_secret_access_key = "test-secret"
        
        client = StorageFactory.create_storage_client(settings)
        
        assert isinstance(client, S3StorageClient)
        assert client.bucket == "test-bucket"
        assert client.region == "us-east-1"
    
    def test_create_s3_storage_client_missing_bucket(self):
        """Test S3 client creation with missing bucket."""
        settings = MagicMock()
        settings.storage_type = StorageType.S3
        settings.s3_bucket = None
        settings.s3_region = "us-east-1"
        
        with pytest.raises(StorageConfigError, match="S3 bucket name is required"):
            StorageFactory.create_storage_client(settings)
    
    def test_create_s3_storage_client_missing_region(self):
        """Test S3 client creation with missing region."""
        settings = MagicMock()
        settings.storage_type = StorageType.S3
        settings.s3_bucket = "test-bucket"
        settings.s3_region = None
        
        with pytest.raises(StorageConfigError, match="S3 region is required"):
            StorageFactory.create_storage_client(settings)
    
    def test_unsupported_storage_type(self):
        """Test creation with unsupported storage type."""
        settings = MagicMock()
        settings.storage_type = "unsupported"
        
        with pytest.raises(StorageConfigError, match="Unsupported storage type"):
            StorageFactory.create_storage_client(settings)
    
    def test_create_local_storage_client_direct(self):
        """Test direct creation of local storage client."""
        client = StorageFactory.create_local_storage_client("/tmp/test")
        
        assert isinstance(client, LocalStorageClient)
        assert str(client.base_path).endswith("test")
    
    def test_create_s3_storage_client_direct(self):
        """Test direct creation of S3 storage client."""
        client = StorageFactory.create_s3_storage_client(
            bucket="test-bucket",
            region="us-east-1",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret"
        )
        
        assert isinstance(client, S3StorageClient)
        assert client.bucket == "test-bucket"
        assert client.region == "us-east-1"
    
    def test_create_s3_storage_client_direct_missing_bucket(self):
        """Test direct S3 client creation with missing bucket."""
        with pytest.raises(StorageConfigError, match="S3 bucket name is required"):
            StorageFactory.create_s3_storage_client(
                bucket="",
                region="us-east-1"
            )
    
    def test_create_s3_storage_client_direct_missing_region(self):
        """Test direct S3 client creation with missing region."""
        with pytest.raises(StorageConfigError, match="S3 region is required"):
            StorageFactory.create_s3_storage_client(
                bucket="test-bucket",
                region=""
            )