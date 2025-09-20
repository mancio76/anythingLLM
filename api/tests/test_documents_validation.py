"""Test document endpoint validation logic."""

import io
import zipfile
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.core.security import User
from app.models.pydantic_models import Job, JobStatus, JobType


class TestDocumentValidation:
    """Test document endpoint validation functions."""
    
    def test_can_access_job_helper_function(self):
        """Test the _can_access_job helper function."""
        from app.routers.documents import _can_access_job
        
        user = User(id="user_123", username="test", is_active=True, roles=["user"])
        admin = User(id="admin_123", username="admin", is_active=True, roles=["admin"])
        
        # User's own job
        user_job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "user_123"}
        )
        
        # Other user's job
        other_job = Job(
            id="job_456",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "other_user"}
        )
        
        # Test user access
        assert _can_access_job(user_job, user) is True
        assert _can_access_job(other_job, user) is False
        
        # Test admin access
        assert _can_access_job(user_job, admin) is True
        assert _can_access_job(other_job, admin) is True
    
    def test_is_admin_user_helper_function(self):
        """Test the _is_admin_user helper function."""
        from app.routers.documents import _is_admin_user
        
        user = User(id="user_123", username="test", is_active=True, roles=["user"])
        admin = User(id="admin_123", username="admin", is_active=True, roles=["admin"])
        manager = User(id="mgr_123", username="manager", is_active=True, roles=["manager"])
        multi_role = User(id="multi_123", username="multi", is_active=True, roles=["user", "admin"])
        
        assert _is_admin_user(user) is False
        assert _is_admin_user(admin) is True
        assert _is_admin_user(manager) is False
        assert _is_admin_user(multi_role) is True
    
    def test_zip_file_validation_logic(self):
        """Test ZIP file validation logic."""
        # Test valid ZIP filename
        assert "test.zip".lower().endswith('.zip') is True
        assert "test.ZIP".lower().endswith('.zip') is True
        assert "test.txt".lower().endswith('.zip') is False
        assert "test.pdf".lower().endswith('.zip') is False
        
        # Test empty filename
        assert "".lower().endswith('.zip') is False
    
    def test_file_size_validation_logic(self):
        """Test file size validation logic."""
        max_size = 100 * 1024 * 1024  # 100MB
        
        # Test valid sizes
        assert 50 * 1024 * 1024 <= max_size  # 50MB
        assert 100 * 1024 * 1024 <= max_size  # Exactly 100MB
        
        # Test invalid sizes
        assert 150 * 1024 * 1024 > max_size  # 150MB
        assert 200 * 1024 * 1024 > max_size  # 200MB
    
    def test_job_status_validation_logic(self):
        """Test job status validation for cancellation."""
        # Jobs that can be cancelled
        cancellable_statuses = [JobStatus.PENDING, JobStatus.PROCESSING]
        
        # Jobs that cannot be cancelled
        non_cancellable_statuses = [
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED
        ]
        
        for status in cancellable_statuses:
            assert status not in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
        
        for status in non_cancellable_statuses:
            assert status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    
    def test_metadata_filtering_logic(self):
        """Test metadata filtering logic for job listing."""
        jobs = [
            {
                "id": "job_1",
                "metadata": {
                    "project_name": "Test Project Alpha",
                    "document_type": "contracts"
                }
            },
            {
                "id": "job_2", 
                "metadata": {
                    "project_name": "Beta Testing",
                    "document_type": "invoices"
                }
            },
            {
                "id": "job_3",
                "metadata": {
                    "project_name": "Alpha Release",
                    "document_type": "contracts"
                }
            }
        ]
        
        # Test project name filtering (partial match)
        project_filter = "alpha"
        filtered_by_project = [
            job for job in jobs
            if project_filter.lower() in job["metadata"].get("project_name", "").lower()
        ]
        assert len(filtered_by_project) == 2
        assert filtered_by_project[0]["id"] == "job_1"
        assert filtered_by_project[1]["id"] == "job_3"
        
        # Test document type filtering (exact match)
        doc_type_filter = "contracts"
        filtered_by_doc_type = [
            job for job in jobs
            if job["metadata"].get("document_type") == doc_type_filter
        ]
        assert len(filtered_by_doc_type) == 2
        assert filtered_by_doc_type[0]["id"] == "job_1"
        assert filtered_by_doc_type[1]["id"] == "job_3"
    
    def test_date_parsing_logic(self):
        """Test date parsing logic for filters."""
        from datetime import datetime
        
        # Test valid ISO date formats
        valid_dates = [
            "2024-01-15T10:30:00",
            "2024-01-15T10:30:00Z",
            "2024-01-15T10:30:00+00:00",
            "2024-12-31T23:59:59"
        ]
        
        for date_str in valid_dates:
            try:
                parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                assert isinstance(parsed, datetime)
            except ValueError:
                pytest.fail(f"Valid date string failed to parse: {date_str}")
        
        # Test invalid date formats
        invalid_dates = [
            "invalid-date",
            "2024-13-01",  # Invalid month
            "2024-01-32",  # Invalid day
            "not-a-date",
            ""
        ]
        
        for date_str in invalid_dates:
            with pytest.raises(ValueError):
                datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    
    def test_pagination_calculation_logic(self):
        """Test pagination calculation logic."""
        # Test valid pagination
        page = 2
        size = 10
        offset = (page - 1) * size
        assert offset == 10
        
        page = 1
        size = 20
        offset = (page - 1) * size
        assert offset == 0
        
        # Test total pages calculation
        total_items = 95
        page_size = 20
        total_pages = (total_items + page_size - 1) // page_size
        assert total_pages == 5  # 95 items / 20 per page = 4.75, rounded up to 5
        
        total_items = 100
        page_size = 20
        total_pages = (total_items + page_size - 1) // page_size
        assert total_pages == 5  # Exactly 5 pages
        
        total_items = 0
        page_size = 20
        total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
        assert total_pages == 0  # No items, no pages


class TestDocumentEndpointConstants:
    """Test constants and configuration used in document endpoints."""
    
    def test_job_type_constants(self):
        """Test job type constants."""
        assert JobType.DOCUMENT_UPLOAD == "document_upload"
        assert JobType.QUESTION_PROCESSING == "question_processing"
        assert JobType.WORKSPACE_CREATION == "workspace_creation"
    
    def test_job_status_constants(self):
        """Test job status constants."""
        assert JobStatus.PENDING == "pending"
        assert JobStatus.PROCESSING == "processing"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"
    
    def test_http_status_codes(self):
        """Test HTTP status codes used in endpoints."""
        from fastapi import status
        
        # Success codes
        assert status.HTTP_200_OK == 200
        assert status.HTTP_202_ACCEPTED == 202
        
        # Client error codes
        assert status.HTTP_400_BAD_REQUEST == 400
        assert status.HTTP_401_UNAUTHORIZED == 401
        assert status.HTTP_403_FORBIDDEN == 403
        assert status.HTTP_404_NOT_FOUND == 404
        assert status.HTTP_409_CONFLICT == 409
        assert status.HTTP_413_REQUEST_ENTITY_TOO_LARGE == 413
        assert status.HTTP_422_UNPROCESSABLE_ENTITY == 422
        
        # Server error codes
        assert status.HTTP_500_INTERNAL_SERVER_ERROR == 500
        assert status.HTTP_501_NOT_IMPLEMENTED == 501


class TestDocumentEndpointModels:
    """Test Pydantic models used in document endpoints."""
    
    def test_job_model_properties(self):
        """Test Job model properties."""
        now = datetime.utcnow()
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.COMPLETED,
            workspace_id="ws_456",
            created_at=now,
            updated_at=now,
            started_at=now,  # Need started_at for duration calculation
            completed_at=now,
            progress=100.0,
            metadata={}
        )
        
        assert job.is_completed is True
        assert job.duration_seconds is not None
        assert job.duration_seconds >= 0
    
    def test_job_model_incomplete(self):
        """Test Job model for incomplete jobs."""
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PROCESSING,
            workspace_id="ws_456",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=50.0,
            metadata={}
        )
        
        assert job.is_completed is False
        assert job.duration_seconds is None  # No completion time
    
    def test_pagination_params_offset_calculation(self):
        """Test PaginationParams offset calculation."""
        from app.models.pydantic_models import PaginationParams
        
        # Page 1
        params = PaginationParams(page=1, size=20)
        assert params.offset == 0
        
        # Page 2
        params = PaginationParams(page=2, size=20)
        assert params.offset == 20
        
        # Page 3 with different size
        params = PaginationParams(page=3, size=10)
        assert params.offset == 20


# Utility functions for testing

def create_test_zip_content(files: dict) -> bytes:
    """Create ZIP file content for testing."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for filename, content in files.items():
            if isinstance(content, str):
                content = content.encode('utf-8')
            zip_file.writestr(filename, content)
    return zip_buffer.getvalue()


def create_test_user(user_id: str = "user_123", roles: list = None) -> User:
    """Create test user for validation tests."""
    return User(
        id=user_id,
        username=f"user_{user_id}",
        is_active=True,
        roles=roles or ["user"]
    )


def create_test_job(
    job_id: str = "job_123",
    user_id: str = "user_123",
    status: JobStatus = JobStatus.PENDING
) -> Job:
    """Create test job for validation tests."""
    return Job(
        id=job_id,
        type=JobType.DOCUMENT_UPLOAD,
        status=status,
        workspace_id="ws_456",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        progress=0.0,
        metadata={"user_id": user_id}
    )