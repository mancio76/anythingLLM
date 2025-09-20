"""Tests for DocumentService."""

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
    create_document_service,
)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.max_file_size = 10 * 1024 * 1024  # 10MB
    settings.allowed_file_types = ["pdf", "json", "csv"]
    return settings


@pytest.fixture
def mock_job_repository():
    """Mock job repository."""
    repo = AsyncMock(spec=JobRepository)
    
    # Mock job creation
    mock_job = MagicMock()
    mock_job.id = "test-job-123"
    mock_job.type = JobType.DOCUMENT_UPLOAD
    mock_job.status = JobStatus.PENDING
    repo.create_job.return_value = mock_job
    
    return repo


@pytest.fixture
def mock_anythingllm_client():
    """Mock AnythingLLM client."""
    client = AsyncMock(spec=AnythingLLMClient)
    
    # Mock upload response
    mock_response = MagicMock()
    mock_response.success = True
    mock_response.message = "Upload successful"
    mock_response.files = []
    client.upload_documents.return_value = mock_response
    
    return client


@pytest.fixture
def mock_storage_client():
    """Mock storage client."""
    return AsyncMock(spec=StorageClient)


@pytest.fixture
def mock_file_validator():
    """Mock file validator."""
    validator = MagicMock(spec=FileValidator)
    validator.validate_multiple_files.return_value = ([], [])
    validator.organize_files_by_type.return_value = {}
    return validator


@pytest.fixture
def document_service(
    mock_settings,
    mock_job_repository,
    mock_anythingllm_client,
    mock_storage_client,
    mock_file_validator
):
    """Create DocumentService instance for testing."""
    return DocumentService(
        settings=mock_settings,
        job_repository=mock_job_repository,
        anythingllm_client=mock_anythingllm_client,
        storage_client=mock_storage_client,
        file_validator=mock_file_validator
    )


@pytest.fixture
def sample_zip_file():
    """Create a sample ZIP file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
        with zipfile.ZipFile(temp_zip.name, 'w') as zf:
            # Add sample files
            zf.writestr('document1.pdf', b'PDF content')
            zf.writestr('data.json', b'{"key": "value"}')
            zf.writestr('report.csv', b'col1,col2\nval1,val2')
        
        yield Path(temp_zip.name)
        
        # Cleanup
        Path(temp_zip.name).unlink(missing_ok=True)


@pytest.fixture
def malicious_zip_file():
    """Create a malicious ZIP file for testing security."""
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
        with zipfile.ZipFile(temp_zip.name, 'w') as zf:
            # Add path traversal file
            zf.writestr('../../../etc/passwd', b'malicious content')
            # Add normal file
            zf.writestr('normal.pdf', b'PDF content')
        
        yield Path(temp_zip.name)
        
        # Cleanup
        Path(temp_zip.name).unlink(missing_ok=True)


class TestDocumentService:
    """Test cases for DocumentService."""
    
    def test_init(self, document_service, mock_settings):
        """Test DocumentService initialization."""
        assert document_service.settings == mock_settings
        assert document_service.max_zip_size == mock_settings.max_file_size
        assert document_service.max_files_per_zip == 100
        assert document_service.max_extraction_depth == 3
    
    @pytest.mark.asyncio
    async def test_upload_documents_success(self, document_service, mock_job_repository):
        """Test successful document upload initiation."""
        # Create mock upload file
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "test.zip"
        upload_file.size = 1024
        upload_file.content_type = "application/zip"
        
        workspace_id = "test-workspace"
        metadata = {"project": "test"}
        
        # Call method
        result = await document_service.upload_documents(upload_file, workspace_id, metadata)
        
        # Verify job creation
        mock_job_repository.create_job.assert_called_once()
        call_args = mock_job_repository.create_job.call_args
        assert call_args[1]["job_type"] == JobType.DOCUMENT_UPLOAD
        assert call_args[1]["workspace_id"] == workspace_id
        assert "filename" in call_args[1]["metadata"]
        assert call_args[1]["metadata"]["project"] == "test"
        
        # Verify response
        assert result.job.id == "test-job-123"
        assert "status" in result.links
        assert "cancel" in result.links
    
    @pytest.mark.asyncio
    async def test_upload_documents_file_too_large(self, document_service):
        """Test upload rejection for oversized files."""
        # Create mock upload file that's too large
        upload_file = MagicMock(spec=UploadFile)
        upload_file.filename = "large.zip"
        upload_file.size = 20 * 1024 * 1024  # 20MB (larger than 10MB limit)
        upload_file.content_type = "application/zip"
        
        workspace_id = "test-workspace"
        
        # Should raise error
        with pytest.raises(DocumentProcessingError) as exc_info:
            await document_service.upload_documents(upload_file, workspace_id)
        
        assert "exceeds maximum allowed size" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_extract_zip_safely_success(self, document_service, sample_zip_file):
        """Test safe ZIP extraction with valid files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_to = Path(temp_dir)
            
            extracted_files = await document_service.extract_zip_safely(sample_zip_file, extract_to)
            
            # Verify files were extracted
            assert len(extracted_files) == 3
            
            # Check file contents
            file_names = [f.name for f in extracted_files]
            assert "document1.pdf" in file_names
            assert "data.json" in file_names
            assert "report.csv" in file_names
            
            # Verify file contents
            for file_path in extracted_files:
                assert file_path.exists()
                assert file_path.stat().st_size > 0
    
    @pytest.mark.asyncio
    async def test_extract_zip_safely_path_traversal(self, document_service, malicious_zip_file):
        """Test ZIP extraction blocks path traversal attacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            extract_to = Path(temp_dir)
            
            with pytest.raises(ZipExtractionError) as exc_info:
                await document_service.extract_zip_safely(malicious_zip_file, extract_to)
            
            assert "Path traversal detected" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_extract_zip_safely_invalid_zip(self, document_service):
        """Test ZIP extraction with invalid ZIP file."""
        # Create invalid ZIP file
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
            temp_file.write(b'This is not a ZIP file')
            invalid_zip = Path(temp_file.name)
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                extract_to = Path(temp_dir)
                
                with pytest.raises(ZipExtractionError) as exc_info:
                    await document_service.extract_zip_safely(invalid_zip, extract_to)
                
                assert "Invalid ZIP file" in str(exc_info.value)
        finally:
            invalid_zip.unlink(missing_ok=True)
    
    def test_is_path_traversal(self, document_service):
        """Test path traversal detection."""
        # Malicious paths
        assert document_service._is_path_traversal("../../../etc/passwd")
        assert document_service._is_path_traversal("..\\..\\windows\\system32")
        assert document_service._is_path_traversal("/etc/passwd")
        assert document_service._is_path_traversal("C:\\Windows\\System32")
        assert document_service._is_path_traversal("folder/../../../secret")
        
        # Safe paths
        assert not document_service._is_path_traversal("document.pdf")
        assert not document_service._is_path_traversal("folder/document.pdf")
        assert not document_service._is_path_traversal("data/reports/file.csv")
    
    def test_sanitize_filename(self, document_service):
        """Test filename sanitization."""
        # Valid filenames
        assert document_service._sanitize_filename("document.pdf") == "document.pdf"
        assert document_service._sanitize_filename("folder/file.json") == "file.json"
        
        # Filenames with dangerous characters
        assert document_service._sanitize_filename("file<>name.pdf") == "file__name.pdf"
        assert document_service._sanitize_filename('file"name|.csv') == "file_name_.csv"
        
        # Invalid filenames
        assert document_service._sanitize_filename("") is None
        assert document_service._sanitize_filename("   ") is None
        assert document_service._sanitize_filename(".") is None
        assert document_service._sanitize_filename("..") is None
        
        # Long filename
        long_name = "a" * 300 + ".pdf"
        sanitized = document_service._sanitize_filename(long_name)
        assert len(sanitized) <= 255
        assert sanitized.endswith(".pdf")
    
    def test_validate_file_types(self, document_service, mock_file_validator):
        """Test file type validation."""
        files = [Path("test1.pdf"), Path("test2.json")]
        valid_files = [Path("test1.pdf")]
        invalid_files = [(Path("test2.json"), "Invalid type")]
        
        mock_file_validator.validate_multiple_files.return_value = (valid_files, invalid_files)
        
        result_valid, result_invalid = document_service.validate_file_types(files)
        
        assert result_valid == valid_files
        assert result_invalid == invalid_files
        mock_file_validator.validate_multiple_files.assert_called_once_with(files)
    
    def test_validate_file_size(self, document_service, mock_file_validator):
        """Test file size validation."""
        file_path = Path("test.pdf")
        mock_file_validator.validate_file_size.return_value = True
        
        result = document_service.validate_file_size(file_path)
        
        assert result is True
        mock_file_validator.validate_file_size.assert_called_once_with(file_path)
    
    def test_organize_documents_by_type(self, document_service, mock_file_validator):
        """Test document organization by type."""
        files = [Path("doc.pdf"), Path("data.json")]
        organized = {"pdf": [Path("doc.pdf")], "json": [Path("data.json")]}
        
        mock_file_validator.organize_files_by_type.return_value = organized
        
        result = document_service.organize_documents_by_type(files)
        
        assert result == organized
        mock_file_validator.organize_files_by_type.assert_called_once_with(files)
    
    @pytest.mark.asyncio
    async def test_upload_to_anythingllm_success(self, document_service, mock_anythingllm_client):
        """Test successful upload to AnythingLLM."""
        files = [Path("test1.pdf"), Path("test2.json")]
        workspace_id = "test-workspace"
        
        result = await document_service.upload_to_anythingllm(files, workspace_id)
        
        assert result["success"] is True
        assert result["message"] == "Upload successful"
        assert result["uploaded_count"] == 2
        
        mock_anythingllm_client.upload_documents.assert_called_once_with(
            workspace_id=workspace_id,
            files=files
        )
    
    @pytest.mark.asyncio
    async def test_upload_to_anythingllm_empty_files(self, document_service):
        """Test upload with empty file list."""
        files = []
        workspace_id = "test-workspace"
        
        result = await document_service.upload_to_anythingllm(files, workspace_id)
        
        assert result["success"] is True
        assert result["message"] == "No files to upload"
        assert result["files"] == []
    
    @pytest.mark.asyncio
    async def test_upload_to_anythingllm_failure(self, document_service, mock_anythingllm_client):
        """Test upload failure to AnythingLLM."""
        files = [Path("test.pdf")]
        workspace_id = "test-workspace"
        
        mock_anythingllm_client.upload_documents.side_effect = Exception("Upload failed")
        
        with pytest.raises(DocumentUploadError) as exc_info:
            await document_service.upload_to_anythingllm(files, workspace_id)
        
        assert "Upload to AnythingLLM failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_process_zip_file_success(self, document_service, sample_zip_file, mock_file_validator, mock_anythingllm_client):
        """Test complete ZIP file processing."""
        job_id = "test-job-123"
        workspace_id = "test-workspace"
        
        # Mock file validation
        valid_files = [Path("doc1.pdf"), Path("data.json")]
        invalid_files = []
        mock_file_validator.validate_multiple_files.return_value = (valid_files, invalid_files)
        
        # Mock file organization
        organized = {"pdf": [Path("doc1.pdf")], "json": [Path("data.json")]}
        mock_file_validator.organize_files_by_type.return_value = organized
        
        result = await document_service.process_zip_file(sample_zip_file, job_id, workspace_id)
        
        assert result.success is True
        assert len(result.processed_files) == 2
        assert len(result.failed_files) == 0
        assert result.organized_files == organized
        assert result.upload_result["success"] is True
    
    @pytest.mark.asyncio
    async def test_process_zip_file_no_valid_files(self, document_service, sample_zip_file, mock_file_validator):
        """Test ZIP processing with no valid files."""
        job_id = "test-job-123"
        workspace_id = "test-workspace"
        
        # Mock file validation - no valid files
        valid_files = []
        invalid_files = [(Path("invalid.txt"), "Invalid type")]
        mock_file_validator.validate_multiple_files.return_value = (valid_files, invalid_files)
        
        result = await document_service.process_zip_file(sample_zip_file, job_id, workspace_id)
        
        assert result.success is False
        assert "No valid files found" in result.message
        assert len(result.failed_files) == 1
    
    @pytest.mark.asyncio
    async def test_get_processing_status(self, document_service, mock_job_repository):
        """Test getting processing status."""
        job_id = "test-job-123"
        
        # Mock job
        mock_job = MagicMock()
        mock_job.type = JobType.DOCUMENT_UPLOAD
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await document_service.get_processing_status(job_id)
        
        assert result == mock_job
        mock_job_repository.get_by_id.assert_called_once_with(job_id)
    
    @pytest.mark.asyncio
    async def test_get_processing_status_wrong_type(self, document_service, mock_job_repository):
        """Test getting processing status for wrong job type."""
        job_id = "test-job-123"
        
        # Mock job with wrong type
        mock_job = MagicMock()
        mock_job.type = JobType.QUESTION_PROCESSING
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await document_service.get_processing_status(job_id)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_cancel_processing(self, document_service, mock_job_repository):
        """Test cancelling processing job."""
        job_id = "test-job-123"
        reason = "User requested"
        
        # Mock job
        mock_job = MagicMock()
        mock_job.type = JobType.DOCUMENT_UPLOAD
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await document_service.cancel_processing(job_id, reason)
        
        assert result is True
        mock_job_repository.cancel_job.assert_called_once_with(job_id, reason)
    
    @pytest.mark.asyncio
    async def test_cancel_processing_wrong_type(self, document_service, mock_job_repository):
        """Test cancelling job with wrong type."""
        job_id = "test-job-123"
        
        # Mock job with wrong type
        mock_job = MagicMock()
        mock_job.type = JobType.QUESTION_PROCESSING
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await document_service.cancel_processing(job_id)
        
        assert result is False
        mock_job_repository.cancel_job.assert_not_called()


class TestProcessingResult:
    """Test cases for ProcessingResult."""
    
    def test_init_success(self):
        """Test ProcessingResult initialization for success."""
        result = ProcessingResult(
            success=True,
            message="Success",
            processed_files=[Path("file1.pdf")],
            organized_files={"pdf": [Path("file1.pdf")]}
        )
        
        assert result.success is True
        assert result.message == "Success"
        assert len(result.processed_files) == 1
        assert len(result.failed_files) == 0
        assert "pdf" in result.organized_files
    
    def test_init_failure(self):
        """Test ProcessingResult initialization for failure."""
        result = ProcessingResult(
            success=False,
            message="Failed",
            failed_files=[(Path("bad.txt"), "Invalid type")]
        )
        
        assert result.success is False
        assert result.message == "Failed"
        assert len(result.processed_files) == 0
        assert len(result.failed_files) == 1


class TestCreateDocumentService:
    """Test cases for factory function."""
    
    def test_create_document_service(
        self,
        mock_settings,
        mock_job_repository,
        mock_anythingllm_client,
        mock_storage_client
    ):
        """Test DocumentService factory function."""
        service = create_document_service(
            settings=mock_settings,
            job_repository=mock_job_repository,
            anythingllm_client=mock_anythingllm_client,
            storage_client=mock_storage_client
        )
        
        assert isinstance(service, DocumentService)
        assert service.settings == mock_settings
        assert service.job_repository == mock_job_repository
        assert service.anythingllm_client == mock_anythingllm_client
        assert service.storage_client == mock_storage_client


class TestZipBombProtection:
    """Test cases for ZIP bomb protection."""
    
    @pytest.mark.asyncio
    async def test_too_many_files(self, document_service):
        """Test protection against ZIP files with too many files."""
        # Create ZIP with too many files
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip.name, 'w') as zf:
                # Add more files than allowed
                for i in range(150):  # More than max_files_per_zip (100)
                    zf.writestr(f'file_{i}.txt', b'content')
            
            zip_path = Path(temp_zip.name)
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                extract_to = Path(temp_dir)
                
                with pytest.raises(ZipExtractionError) as exc_info:
                    await document_service.extract_zip_safely(zip_path, extract_to)
                
                assert "too many files" in str(exc_info.value)
        finally:
            zip_path.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_excessive_uncompressed_size(self, document_service):
        """Test protection against excessive uncompressed size."""
        # Create ZIP with files that would expand to excessive size
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
            with zipfile.ZipFile(temp_zip.name, 'w') as zf:
                # Create a file info that claims huge uncompressed size
                # This is a bit tricky to test without actually creating huge files
                # For now, we'll test the logic by mocking
                pass
            
            zip_path = Path(temp_zip.name)
        
        try:
            # This test would need more sophisticated mocking to properly test
            # the uncompressed size check without creating huge files
            pass
        finally:
            zip_path.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__])