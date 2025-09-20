"""Focused tests for document endpoints without full app initialization."""

import io
import json
import zipfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.core.security import User
from app.models.pydantic_models import (
    Job,
    JobResponse,
    JobStatus,
    JobType,
    PaginatedJobs,
)
from app.routers.documents import router
from app.services.document_service import DocumentProcessingError
from app.services.job_service import JobNotFoundError, JobCancellationError


# Create a minimal test app
def create_test_app():
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def test_app():
    """Test app fixture."""
    return create_test_app()


@pytest.fixture
def client(test_app):
    """Test client fixture."""
    return TestClient(test_app)


@pytest.fixture
def mock_user():
    """Mock user fixture."""
    return User(
        id="user_123",
        username="testuser",
        is_active=True,
        roles=["user"]
    )


@pytest.fixture
def mock_admin_user():
    """Mock admin user fixture."""
    return User(
        id="admin_123",
        username="admin",
        is_active=True,
        roles=["admin"]
    )


class TestDocumentEndpoints:
    """Test document processing endpoints."""
    
    def test_upload_endpoint_structure(self, client):
        """Test that upload endpoint exists and has correct structure."""
        # This will fail with authentication error, but confirms endpoint exists
        response = client.post("/api/v1/documents/upload")
        # Should get 401 (unauthorized) or 422 (validation error), not 404
        assert response.status_code in [401, 422, 501]
    
    def test_job_status_endpoint_structure(self, client):
        """Test that job status endpoint exists."""
        response = client.get("/api/v1/documents/jobs/test-job-id")
        # Should get 401 (unauthorized) or 501 (not implemented), not 404
        assert response.status_code in [401, 501]
    
    def test_job_cancel_endpoint_structure(self, client):
        """Test that job cancel endpoint exists."""
        response = client.delete("/api/v1/documents/jobs/test-job-id")
        # Should get 401 (unauthorized) or 501 (not implemented), not 404
        assert response.status_code in [401, 501]
    
    def test_job_list_endpoint_structure(self, client):
        """Test that job list endpoint exists."""
        response = client.get("/api/v1/documents/jobs")
        # Should get 401 (unauthorized) or 501 (not implemented), not 404
        assert response.status_code in [401, 501]
    
    @patch("app.routers.documents.get_document_service")
    @patch("app.routers.documents.require_user")
    @patch("app.routers.documents.get_settings")
    def test_upload_with_mocked_dependencies(
        self, mock_settings, mock_require_user, mock_doc_service, client, mock_user
    ):
        """Test upload endpoint with mocked dependencies."""
        # Setup mocks
        mock_require_user.return_value = mock_user
        mock_settings.return_value.max_file_size = 100 * 1024 * 1024
        
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
            links={"status": "/api/v1/documents/jobs/job_123"}
        )
        
        mock_service = AsyncMock()
        mock_service.upload_documents.return_value = mock_job_response
        mock_doc_service.return_value = mock_service
        
        # Create test ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            zip_file.writestr("test.pdf", b"fake pdf content")
        zip_buffer.seek(0)
        
        # Make request
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.zip", zip_buffer, "application/zip")},
            data={"workspace_id": "ws_456"}
        )
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["job"]["id"] == "job_123"
        assert data["job"]["type"] == "document_upload"
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_job_status_with_mocked_dependencies(
        self, mock_require_user, mock_job_service, client, mock_user
    ):
        """Test job status endpoint with mocked dependencies."""
        # Setup mocks
        mock_require_user.return_value = mock_user
        
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": mock_user.id}
        )
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = mock_job
        mock_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "job_123"
        assert data["status"] == "processing"
        assert data["progress"] == 45.0
    
    def test_upload_validation_non_zip_file(self, client):
        """Test upload validation for non-ZIP files."""
        with patch("app.routers.documents.require_user") as mock_require_user:
            mock_require_user.return_value = User(
                id="user_123", username="test", is_active=True, roles=["user"]
            )
            
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", b"not a zip", "text/plain")},
                data={"workspace_id": "ws_456"}
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "Only ZIP files are allowed" in response.json()["detail"]
    
    def test_upload_validation_missing_workspace(self, client):
        """Test upload validation for missing workspace ID."""
        with patch("app.routers.documents.require_user") as mock_require_user:
            mock_require_user.return_value = User(
                id="user_123", username="test", is_active=True, roles=["user"]
            )
            
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
                zip_file.writestr("test.pdf", b"fake pdf")
            zip_buffer.seek(0)
            
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.zip", zip_buffer, "application/zip")}
                # Missing workspace_id
            )
            
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_job_not_found_error(self, mock_require_user, mock_job_service, client, mock_user):
        """Test job not found error handling."""
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.get_job.side_effect = JobNotFoundError("Job not found")
        mock_job_service.return_value = mock_service
        
        response = client.get("/api/v1/documents/jobs/nonexistent")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_access_denied_to_other_user_job(
        self, mock_require_user, mock_job_service, client, mock_user
    ):
        """Test access denied to another user's job."""
        mock_require_user.return_value = mock_user
        
        # Job belongs to different user
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
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = mock_job
        mock_job_service.return_value = mock_service
        
        response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied" in response.json()["detail"]
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_admin_can_access_any_job(
        self, mock_require_user, mock_job_service, client, mock_admin_user
    ):
        """Test that admin can access any user's job."""
        mock_require_user.return_value = mock_admin_user
        
        # Job belongs to different user
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
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = mock_job
        mock_job_service.return_value = mock_service
        
        response = client.get("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "job_123"
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_cancel_completed_job_fails(
        self, mock_require_user, mock_job_service, client, mock_user
    ):
        """Test that cancelling a completed job fails."""
        mock_require_user.return_value = mock_user
        
        # Job is already completed
        mock_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.COMPLETED,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            metadata={"user_id": mock_user.id}
        )
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = mock_job
        mock_job_service.return_value = mock_service
        
        response = client.delete("/api/v1/documents/jobs/job_123")
        
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "cannot be cancelled" in response.json()["detail"]
        
        # Verify cancel_job was not called
        mock_service.cancel_job.assert_not_called()
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_list_jobs_pagination_validation(
        self, mock_require_user, mock_job_service, client, mock_user
    ):
        """Test job listing pagination validation."""
        mock_require_user.return_value = mock_user
        
        # Test invalid page number
        response = client.get("/api/v1/documents/jobs?page=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test invalid page size
        response = client.get("/api/v1/documents/jobs?size=200")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @patch("app.routers.documents.get_job_service")
    @patch("app.routers.documents.require_user")
    def test_list_jobs_date_filter_validation(
        self, mock_require_user, mock_job_service, client, mock_user
    ):
        """Test job listing date filter validation."""
        mock_require_user.return_value = mock_user
        
        # Test invalid date format
        response = client.get("/api/v1/documents/jobs?created_after=invalid-date")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Invalid created_after date format" in response.json()["detail"]
        
        response = client.get("/api/v1/documents/jobs?created_before=also-invalid")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Invalid created_before date format" in response.json()["detail"]


class TestHelperFunctions:
    """Test helper functions in the documents router."""
    
    def test_can_access_job_own_job(self, mock_user):
        """Test user can access their own job."""
        from app.routers.documents import _can_access_job
        
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": mock_user.id}
        )
        
        assert _can_access_job(job, mock_user) is True
    
    def test_can_access_job_other_user(self, mock_user):
        """Test user cannot access another user's job."""
        from app.routers.documents import _can_access_job
        
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "other_user"}
        )
        
        assert _can_access_job(job, mock_user) is False
    
    def test_can_access_job_admin_user(self, mock_admin_user):
        """Test admin can access any job."""
        from app.routers.documents import _can_access_job
        
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "other_user"}
        )
        
        assert _can_access_job(job, mock_admin_user) is True
    
    def test_is_admin_user(self, mock_user, mock_admin_user):
        """Test admin user detection."""
        from app.routers.documents import _is_admin_user
        
        assert _is_admin_user(mock_user) is False
        assert _is_admin_user(mock_admin_user) is True


# Test utilities

def create_test_zip_buffer(files: dict) -> io.BytesIO:
    """Create a test ZIP file buffer."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for filename, content in files.items():
            if isinstance(content, str):
                content = content.encode('utf-8')
            zip_file.writestr(filename, content)
    zip_buffer.seek(0)
    return zip_buffer


def create_mock_job(
    job_id: str = "job_123",
    status: JobStatus = JobStatus.PENDING,
    user_id: str = "user_123",
    **kwargs
) -> Job:
    """Create a mock job for testing."""
    return Job(
        id=job_id,
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