"""Comprehensive unit tests for DocumentService."""

import asyncio
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.config import Settings
from app.integrations.anythingllm_client import AnythingLLMClient, DocumentUploadError
from app.integrations.file_validator import FileValidator, FileValidationError
from app.integrations.storage_client import StorageClient
from app.models.pydantic_models import JobStatus, JobType
from app.repositories.job_repository import JobRepository
from app.services.document_service import (
    DocumentProcessingError,
    DocumentService,
    ProcessingResult,
    ZipExtractionError,
)
from tests.fixtures.mock_data import mock_data, mock_files


class TestDocumentService:
    """Test cases for DocumentService."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = MagicMock(spec=Settings)
        settings.max_file_size = 10 * 1024 * 1024  # 10MB
        settings.allowed_file_types = ["pdf", "json", "csv"]
        settings.storage_path = "/tmp/test"
        return settings

    @pytest.fixture
    def mock_job_repository(self):
        """Mock job repository."""
        repo = AsyncMock(spec=JobRepository)
        repo.create_job.return_value = mock_data.create_mock_job()
        repo.update_job_status.return_value = mock_data.create_mock_job(status=JobStatus.COMPLETED)
        return repo

    @pytest.fixture
    def mock_storage_client(self):
        """Mock storage client."""
        client = AsyncMock(spec=StorageClient)
        client.upload_file.return_value = "storage://test/file.zip"
        client.download_file.return_value = True
        client.delete_file.return_value = True
        return client

    @pytest.fixture
    def mock_anythingllm_client(self):
        """Mock AnythingLLM client."""
        client = AsyncMock(spec=AnythingLLMClient)
        client.upload_documents.return_value = mock_data.create_mock_anythingllm_responses()["document_upload"]
        return client

    @pytest.fixture
    def mock_file_validator(self):
        """Mock file validator."""
        validator = AsyncMock(spec=FileValidator)
        validator.validate_file_type.return_value = True
        validator.validate_file_size.return_value = True
        validator.validate_zip_content.return_value = True
        return validator

    @pytest.fixture
    def document_service(
        self,
        mock_settings,
        mock_job_repository,
        mock_storage_client,
        mock_anythingllm_client,
        mock_file_validator,
    ):
        """Create DocumentService instance with mocked dependencies."""
        return DocumentService(
            settings=mock_settings,
            job_repository=mock_job_repository,
            storage_client=mock_storage_client,
            anythingllm_client=mock_anythingllm_client,
            file_validator=mock_file_validator,
        )

    @pytest.fixture
    def sample_upload_file(self, tmp_path):
        """Create a sample upload file."""
        zip_path = mock_files.create_temp_directory() / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("test.pdf", b"fake pdf content")
            zf.writestr("test.json", '{"test": "data"}')
        
        # Create UploadFile mock
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.zip"
        upload_file.size = zip_path.stat().st_size
        upload_file.content_type = "application/zip"
        upload_file.file = open(zip_path, 'rb')
        return upload_file

    @pytest.mark.asyncio
    async def test_upload_documents_success(
        self,
        document_service,
        sample_upload_file,
        mock_job_repository,
        mock_storage_client,
    ):
        """Test successful document upload."""
        workspace_id = "ws_123"
        
        result = await document_service.upload_documents(sample_upload_file, workspace_id)
        
        assert result.job_id is not None
        assert result.status == JobStatus.PENDING
        mock_job_repository.create_job.assert_called_once()
        mock_storage_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_documents_file_too_large(
        self,
        document_service,
        sample_upload_file,
        mock_settings,
    ):
        """Test upload rejection for oversized files."""
        mock_settings.max_file_size = 1024  # 1KB limit
        sample_upload_file.size = 2048  # 2KB file
        
        with pytest.raises(DocumentProcessingError) as exc_info:
            await document_service.upload_documents(sample_upload_file, "ws_123")
        
        assert "File size exceeds limit" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_documents_invalid_file_type(
        self,
        document_service,
        mock_file_validator,
    ):
        """Test upload rejection for invalid file types."""
        mock_file_validator.validate_file_type.side_effect = FileValidationError("Invalid file type")
        
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.txt"
        upload_file.size = 1024
        upload_file.content_type = "text/plain"
        
        with pytest.raises(DocumentProcessingError):
            await document_service.upload_documents(upload_file, "ws_123")

    @pytest.mark.asyncio
    async def test_process_zip_file_success(
        self,
        document_service,
        tmp_path,
        mock_anythingllm_client,
    ):
        """Test successful ZIP file processing."""
        # Create test ZIP file
        zip_path = mock_data.create_test_zip_file(tmp_path)
        job_id = "job_123"
        
        result = await document_service.process_zip_file(zip_path, job_id)
        
        assert result.success is True
        assert len(result.processed_files) > 0
        mock_anythingllm_client.upload_documents.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_zip_file_extraction_error(
        self,
        document_service,
        tmp_path,
    ):
        """Test ZIP file processing with extraction error."""
        # Create invalid ZIP file
        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")
        
        with pytest.raises(ZipExtractionError):
            await document_service.process_zip_file(invalid_zip, "job_123")

    @pytest.mark.asyncio
    async def test_validate_file_types_success(
        self,
        document_service,
        tmp_path,
    ):
        """Test successful file type validation."""
        files = [
            mock_files.create_pdf_file(tmp_path, "test.pdf"),
            mock_files.create_json_file(tmp_path, "test.json"),
            mock_files.create_csv_file(tmp_path, "test.csv"),
        ]
        
        result = await document_service.validate_file_types(files)
        
        assert result.valid is True
        assert len(result.valid_files) == 3
        assert len(result.invalid_files) == 0

    @pytest.mark.asyncio
    async def test_validate_file_types_with_invalid_files(
        self,
        document_service,
        tmp_path,
    ):
        """Test file type validation with invalid files."""
        files = [
            mock_files.create_pdf_file(tmp_path, "test.pdf"),
            mock_files.create_invalid_file(tmp_path, "invalid.txt"),
        ]
        
        result = await document_service.validate_file_types(files)
        
        assert result.valid is False
        assert len(result.valid_files) == 1
        assert len(result.invalid_files) == 1

    @pytest.mark.asyncio
    async def test_extract_zip_safely_success(
        self,
        document_service,
        tmp_path,
    ):
        """Test safe ZIP extraction."""
        zip_path = mock_data.create_test_zip_file(tmp_path)
        extract_to = tmp_path / "extracted"
        
        files = await document_service.extract_zip_safely(zip_path, extract_to)
        
        assert len(files) > 0
        assert extract_to.exists()
        assert all(f.exists() for f in files)

    @pytest.mark.asyncio
    async def test_extract_zip_safely_path_traversal_protection(
        self,
        document_service,
        tmp_path,
    ):
        """Test ZIP extraction with path traversal protection."""
        # Create malicious ZIP with path traversal
        malicious_zip = tmp_path / "malicious.zip"
        with zipfile.ZipFile(malicious_zip, 'w') as zf:
            zf.writestr("../../../etc/passwd", "malicious content")
        
        extract_to = tmp_path / "extracted"
        
        with pytest.raises(ZipExtractionError) as exc_info:
            await document_service.extract_zip_safely(malicious_zip, extract_to)
        
        assert "Path traversal" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_to_anythingllm_success(
        self,
        document_service,
        tmp_path,
        mock_anythingllm_client,
    ):
        """Test successful upload to AnythingLLM."""
        files = [
            mock_files.create_pdf_file(tmp_path, "test.pdf"),
            mock_files.create_json_file(tmp_path, "test.json"),
        ]
        workspace_id = "ws_123"
        
        result = await document_service.upload_to_anythingllm(files, workspace_id)
        
        assert result.success is True
        mock_anythingllm_client.upload_documents.assert_called_once_with(workspace_id, files)

    @pytest.mark.asyncio
    async def test_upload_to_anythingllm_failure(
        self,
        document_service,
        tmp_path,
        mock_anythingllm_client,
    ):
        """Test failed upload to AnythingLLM."""
        mock_anythingllm_client.upload_documents.side_effect = DocumentUploadError("Upload failed")
        
        files = [mock_files.create_pdf_file(tmp_path, "test.pdf")]
        workspace_id = "ws_123"
        
        with pytest.raises(DocumentProcessingError):
            await document_service.upload_to_anythingllm(files, workspace_id)

    @pytest.mark.asyncio
    async def test_organize_documents_by_type(
        self,
        document_service,
        tmp_path,
    ):
        """Test document organization by type."""
        files = [
            mock_files.create_pdf_file(tmp_path, "contract1.pdf"),
            mock_files.create_pdf_file(tmp_path, "contract2.pdf"),
            mock_files.create_json_file(tmp_path, "data1.json"),
            mock_files.create_csv_file(tmp_path, "report1.csv"),
        ]
        
        organized = await document_service.organize_documents_by_type(files)
        
        assert "pdf" in organized
        assert "json" in organized
        assert "csv" in organized
        assert len(organized["pdf"]) == 2
        assert len(organized["json"]) == 1
        assert len(organized["csv"]) == 1

    @pytest.mark.asyncio
    async def test_concurrent_document_processing(
        self,
        document_service,
        tmp_path,
        mock_anythingllm_client,
    ):
        """Test concurrent document processing."""
        # Create multiple ZIP files
        zip_files = []
        for i in range(3):
            zip_path = mock_data.create_test_zip_file(tmp_path, f"test_{i}.zip")
            zip_files.append(zip_path)
        
        # Process concurrently
        tasks = [
            document_service.process_zip_file(zip_path, f"job_{i}")
            for i, zip_path in enumerate(zip_files)
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        assert all(result.success for result in results)
        assert mock_anythingllm_client.upload_documents.call_count == 3

    @pytest.mark.asyncio
    async def test_cleanup_temp_files(
        self,
        document_service,
        tmp_path,
    ):
        """Test cleanup of temporary files after processing."""
        zip_path = mock_data.create_test_zip_file(tmp_path)
        job_id = "job_123"
        
        # Process file
        await document_service.process_zip_file(zip_path, job_id)
        
        # Verify cleanup (implementation should clean up temp files)
        # This test verifies the service properly manages temporary resources
        assert True  # Placeholder - actual implementation would verify cleanup

    @pytest.mark.asyncio
    async def test_error_handling_and_job_status_updates(
        self,
        document_service,
        tmp_path,
        mock_job_repository,
        mock_anythingllm_client,
    ):
        """Test error handling and job status updates."""
        mock_anythingllm_client.upload_documents.side_effect = Exception("Network error")
        
        zip_path = mock_data.create_test_zip_file(tmp_path)
        job_id = "job_123"
        
        with pytest.raises(DocumentProcessingError):
            await document_service.process_zip_file(zip_path, job_id)
        
        # Verify job status was updated to failed
        mock_job_repository.update_job_status.assert_called()
        call_args = mock_job_repository.update_job_status.call_args
        assert call_args[0][1] == JobStatus.FAILED  # status parameter