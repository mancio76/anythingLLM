"""Tests for document processing REST API endpoints."""

import io
import json
import zipfile
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.core.security import User
from app.models.pydantic_models import (
    Job,
    JobResponse,
    JobStatus,
    JobType,
    PaginatedJobs,
    PaginationParams,
)
from app.services.document_service import DocumentProcessingError
from app.services.job_service import JobNotFoundError, JobCancellationError


class TestDocumentUpload:
    """Test document upload endpoint."""
    
    def test_upload_valid_zip_file(self, client: TestClient, mock_auth_user: User):
        """Test uploading a valid ZIP file."""
        # Create a test ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("test.pdf", b"fake pdf content")
            zip_file.writestr("data.json", json.dumps({"test": "data"}))
        zip_buffer.seek(0)
        
        # Mock services
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PENDING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={}
        )
        
        mock_job_response = JobResponse(
            job=mock_job,
            links={
                "status": "/api/v1/documents/jobs/job_123",
                "cancel": "/api/v1/documents/jobs/job_123"
            }
        )
        
        with patch("app.routers.documents.get_document_service") as mock_doc_service:
            mock_service = AsyncMock()
            mock_service.upload_documents.return_value = mock_job_response
            mock_doc_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.zip", zip_buffer, "application/zip")},
                data={
                    "workspace_id": "ws_456",
                    "project_name": "Test Project",
                    "document_type": "contracts"
                }
            )
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["job"]["id"] == "job_123"
        assert data["job"]["type"] == "document_upload"
        assert data["job"]["status"] == "pending"
        assert data["links"]["status"] == "/api/v1/documents/jobs/job_123"
        
        # Verify service was called correctly
        mock_service.upload_documents.assert_called_once()
        call_args = mock_service.upload_documents.call_args
        assert call_args[1]["workspace_id"] == "ws_456"
        assert call_args[1]["metadata"]["project_name"] == "Test Project"
        assert call_args[1]["metadata"]["document_type"] == "contracts"
    
    def test_upload_non_zip_file(self, client: TestClient, mock_auth_user: User):
        """Test uploading a non-ZIP file."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", b"not a zip file", "text/plain")},
            data={"workspace_id": "ws_456"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Only ZIP files are allowed" in response.json()["detail"]
    
    def test_upload_no_file(self, client: TestClient, mock_auth_user: User):
        """Test upload request without file."""
        response = client.post(
            "/api/v1/documents/upload",
            data={"workspace_id": "ws_456"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_upload_file_too_large(self, client: TestClient, mock_auth_user: User):
        """Test uploading a file that's too large."""
        # Create a large ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("large.pdf", b"x" * (101 * 1024 * 1024))  # 101MB
        zip_buffer.seek(0)
        
        with patch("app.core.config.get_settings") as mock_settings:
            mock_settings.return_value.max_file_size = 100 * 1024 * 1024  # 100MB
            
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("large.zip", zip_buffer, "application/zip")},
                data={"workspace_id": "ws_456"}
            )
        
        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert "exceeds maximum allowed size" in response.json()["detail"]
    
    def test_upload_document_processing_error(self, client: TestClient, mock_auth_user: User):
        """Test handling of document processing errors."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("test.pdf", b"fake pdf content")
        zip_buffer.seek(0)
        
        with patch("app.routers.documents.get_document_service") as mock_doc_service:
            mock_service = AsyncMock()
            mock_service.upload_documents.side_effect = DocumentProcessingError(
                "Invalid ZIP file structure"
            )
            mock_doc_service.return_value = mock_service
            
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.zip", zip_buffer, "application/zip")},
                data={"workspace_id": "ws_456"}
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid ZIP file structure" in response.json()["detail"]
    
    def test_upload_missing_workspace_id(self, client: TestClient, mock_auth_user: User):
        """Test upload without workspace ID."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("test.pdf", b"fake pdf content")
        zip_buffer.seek(0)
        
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.zip", zip_buffer, "application/zip")}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_upload_unauthorized(self, client: TestClient):
        """Test upload without authentication."""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("test.pdf", b"fake pdf content")
        zip_buffer.seek(0)
        
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.zip", zip_buffer, "application/zip")},
            data={"workspace_id": "ws_456"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestJobStatus:
    """Test job status endpoint."""
    
    def test_get_job_status_success(self, client: TestClient, mock_auth_user: User):
        """Test getting job status successfully."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": mock_auth_user.id}
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "job_123"
        assert data["status"] == "processing"
        assert data["progress"] == 45.0
        
        mock_service.get_job.assert_called_once_with("job_123", include_results=False)
    
    def test_get_job_status_with_results(self, client: TestClient, mock_auth_user: User):
        """Test getting job status with results included."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.COMPLETED,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            result={"processed_files": 5, "failed_files": 0},
            metadata={"user_id": mock_auth_user.id}
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs/job_123?include_results=true")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["result"]["processed_files"] == 5
        
        mock_service.get_job.assert_called_once_with("job_123", include_results=True)
    
    def test_get_job_status_not_found(self, client: TestClient, mock_auth_user: User):
        """Test getting status for non-existent job."""
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.side_effect = JobNotFoundError("Job not found")
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs/nonexistent")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]
    
    def test_get_job_status_wrong_type(self, client: TestClient, mock_auth_user: User):
        """Test getting status for non-document job."""
        mock_job = Job(
            id="job_123",
            type=JobType.QUESTION_PROCESSING,  # Wrong type
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": mock_auth_user.id}
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Document processing job not found" in response.json()["detail"]
    
    def test_get_job_status_access_denied(self, client: TestClient, mock_auth_user: User):
        """Test access denied to another user's job."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "other_user"}  # Different user
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied" in response.json()["detail"]
    
    def test_get_job_status_admin_access(self, client: TestClient):
        """Test admin can access any job."""
        admin_user = User(id="admin", username="admin", is_active=True, roles=["admin"])
        
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "other_user"}
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service, \
             patch("app.core.dependencies.get_current_active_user", return_value=admin_user):
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_200_OK


class TestJobCancellation:
    """Test job cancellation endpoint."""
    
    def test_cancel_job_success(self, client: TestClient, mock_auth_user: User):
        """Test successful job cancellation."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=30.0,
            metadata={"user_id": mock_auth_user.id}
        )
        
        cancelled_job = mock_job.model_copy()
        cancelled_job.status = JobStatus.CANCELLED
        cancelled_job.error = f"Cancelled by user {mock_auth_user.username}"
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_service.cancel_job.return_value = cancelled_job
            mock_job_service.return_value = mock_service
            
            response = client.delete("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "cancelled"
        
        mock_service.cancel_job.assert_called_once()
        call_args = mock_service.cancel_job.call_args
        assert call_args[0][0] == "job_123"
        assert mock_auth_user.username in call_args[0][1]
    
    def test_cancel_job_with_reason(self, client: TestClient, mock_auth_user: User):
        """Test job cancellation with custom reason."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=30.0,
            metadata={"user_id": mock_auth_user.id}
        )
        
        cancelled_job = mock_job.model_copy()
        cancelled_job.status = JobStatus.CANCELLED
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_service.cancel_job.return_value = cancelled_job
            mock_job_service.return_value = mock_service
            
            response = client.delete(
                "/api/v1/documents/jobs/job_123?reason=User%20requested%20cancellation"
            )
        
        assert response.status_code == status.HTTP_200_OK
        
        mock_service.cancel_job.assert_called_once_with(
            "job_123", "User requested cancellation"
        )
    
    def test_cancel_completed_job(self, client: TestClient, mock_auth_user: User):
        """Test cancelling a completed job (should fail)."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.COMPLETED,  # Already completed
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            metadata={"user_id": mock_auth_user.id}
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.delete("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "cannot be cancelled" in response.json()["detail"]
        
        # Should not call cancel_job
        mock_service.cancel_job.assert_not_called()
    
    def test_cancel_job_not_found(self, client: TestClient, mock_auth_user: User):
        """Test cancelling non-existent job."""
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.side_effect = JobNotFoundError("Job not found")
            mock_job_service.return_value = mock_service
            
            response = client.delete("/api/v1/documents/jobs/nonexistent")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_cancel_job_access_denied(self, client: TestClient, mock_auth_user: User):
        """Test cancelling another user's job."""
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=30.0,
            metadata={"user_id": "other_user"}
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.get_job.return_value = mock_job
            mock_job_service.return_value = mock_service
            
            response = client.delete("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # Should not call cancel_job
        mock_service.cancel_job.assert_not_called()


class TestJobListing:
    """Test job listing endpoint."""
    
    def test_list_jobs_default(self, client: TestClient, mock_auth_user: User):
        """Test listing jobs with default parameters."""
        mock_jobs = [
            Job(
                id=f"job_{i}",
                type=JobType.DOCUMENT_UPLOAD,
                status=JobStatus.COMPLETED,
                workspace_id="ws_456",
                created_at=datetime.utcnow() - timedelta(hours=i),
                updated_at=datetime.utcnow() - timedelta(hours=i),
                progress=100.0,
                metadata={"user_id": mock_auth_user.id}
            )
            for i in range(5)
        ]
        
        mock_result = PaginatedJobs(
            items=mock_jobs,
            total=5,
            page=1,
            size=20,
            pages=1
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.list_jobs.return_value = mock_result
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 20
        
        # Verify service was called with correct filters
        mock_service.list_jobs.assert_called_once()
        call_args = mock_service.list_jobs.call_args
        filters = call_args[1]["filters"]
        assert filters.type == JobType.DOCUMENT_UPLOAD
    
    def test_list_jobs_with_pagination(self, client: TestClient, mock_auth_user: User):
        """Test listing jobs with pagination parameters."""
        mock_jobs = [
            Job(
                id=f"job_{i}",
                type=JobType.DOCUMENT_UPLOAD,
                status=JobStatus.COMPLETED,
                workspace_id="ws_456",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                progress=100.0,
                metadata={"user_id": mock_auth_user.id}
            )
            for i in range(10)
        ]
        
        mock_result = PaginatedJobs(
            items=mock_jobs,
            total=50,
            page=2,
            size=10,
            pages=5
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.list_jobs.return_value = mock_result
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs?page=2&size=10")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 2
        assert data["size"] == 10
        
        # Verify pagination was passed correctly
        call_args = mock_service.list_jobs.call_args
        pagination = call_args[1]["pagination"]
        assert pagination.page == 2
        assert pagination.size == 10
    
    def test_list_jobs_with_filters(self, client: TestClient, mock_auth_user: User):
        """Test listing jobs with various filters."""
        mock_result = PaginatedJobs(
            items=[],
            total=0,
            page=1,
            size=20,
            pages=0
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.list_jobs.return_value = mock_result
            mock_job_service.return_value = mock_service
            
            response = client.get(
                "/api/v1/documents/jobs"
                "?status=processing"
                "&workspace_id=ws_456"
                "&project_name=Test%20Project"
                "&document_type=contracts"
                "&created_after=2024-01-01T00:00:00"
                "&created_before=2024-12-31T23:59:59"
            )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify filters were applied
        call_args = mock_service.list_jobs.call_args
        filters = call_args[1]["filters"]
        assert filters.status == JobStatus.PROCESSING
        assert filters.workspace_id == "ws_456"
        assert filters.created_after is not None
        assert filters.created_before is not None
    
    def test_list_jobs_invalid_date_format(self, client: TestClient, mock_auth_user: User):
        """Test listing jobs with invalid date format."""
        response = client.get(
            "/api/v1/documents/jobs?created_after=invalid-date"
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Invalid created_after date format" in response.json()["detail"]
    
    def test_list_jobs_invalid_pagination(self, client: TestClient, mock_auth_user: User):
        """Test listing jobs with invalid pagination parameters."""
        response = client.get("/api/v1/documents/jobs?page=0")
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_list_jobs_large_page_size(self, client: TestClient, mock_auth_user: User):
        """Test listing jobs with page size exceeding limit."""
        response = client.get("/api/v1/documents/jobs?size=200")
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_list_jobs_access_filtering(self, client: TestClient, mock_auth_user: User):
        """Test that users only see their own jobs."""
        # Mix of user's jobs and other users' jobs
        all_jobs = [
            Job(
                id="job_user_1",
                type=JobType.DOCUMENT_UPLOAD,
                status=JobStatus.COMPLETED,
                workspace_id="ws_456",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                progress=100.0,
                metadata={"user_id": mock_auth_user.id}  # User's job
            ),
            Job(
                id="job_other_1",
                type=JobType.DOCUMENT_UPLOAD,
                status=JobStatus.COMPLETED,
                workspace_id="ws_456",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                progress=100.0,
                metadata={"user_id": "other_user"}  # Other user's job
            ),
            Job(
                id="job_user_2",
                type=JobType.DOCUMENT_UPLOAD,
                status=JobStatus.PROCESSING,
                workspace_id="ws_789",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                progress=50.0,
                metadata={"user_id": mock_auth_user.id}  # User's job
            )
        ]
        
        mock_result = PaginatedJobs(
            items=all_jobs,
            total=3,
            page=1,
            size=20,
            pages=1
        )
        
        with patch("app.routers.documents.get_job_service") as mock_job_service:
            mock_service = AsyncMock()
            mock_service.list_jobs.return_value = mock_result
            mock_job_service.return_value = mock_service
            
            response = client.get("/api/v1/documents/jobs")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Should only return user's jobs (2 out of 3)
        assert len(data["items"]) == 2
        job_ids = [job["id"] for job in data["items"]]
        assert "job_user_1" in job_ids
        assert "job_user_2" in job_ids
        assert "job_other_1" not in job_ids


# Fixtures and test configuration

@pytest.fixture
def mock_auth_user():
    """Mock authenticated user."""
    return User(
        id="user_123",
        username="testuser",
        is_active=True,
        roles=["user"]
    )


@pytest.fixture
def client(mock_auth_user):
    """Test client with mocked authentication."""
    from app.main import app
    
    with patch("app.core.dependencies.get_current_active_user", return_value=mock_auth_user):
        with TestClient(app) as test_client:
            yield test_client


# Integration test helpers

def create_test_zip_file(files: Dict[str, bytes]) -> io.BytesIO:
    """Create a test ZIP file with specified files."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for filename, content in files.items():
            zip_file.writestr(filename, content)
    zip_buffer.seek(0)
    return zip_buffer


def create_mock_job(
    job_id: str = None,
    status: JobStatus = JobStatus.PENDING,
    user_id: str = "user_123",
    **kwargs
) -> Job:
    """Create a mock job for testing."""
    return Job(
        id=job_id or str(uuid4()),
        type=JobType.DOCUMENT_UPLOAD,
        status=status,
        workspace_id=kwargs.get("workspace_id", "ws_456"),
        created_at=kwargs.get("created_at", datetime.utcnow()),
        updated_at=kwargs.get("updated_at", datetime.utcnow()),
        progress=kwargs.get("progress", 0.0),
        result=kwargs.get("result"),
        error=kwargs.get("error"),
        metadata={"user_id": user_id, **kwargs.get("metadata", {})}
    )