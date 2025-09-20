"""Integration tests for document endpoints."""

import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient

from tests.fixtures.mock_data import mock_data, mock_files


class TestDocumentEndpointsIntegration:
    """Integration tests for document endpoints."""

    @pytest.fixture
    def auth_headers(self):
        """Authentication headers for requests."""
        return {"Authorization": "Bearer test-token"}

    @pytest.fixture
    def sample_zip_file(self, tmp_path):
        """Create a sample ZIP file for testing."""
        return mock_data.create_test_zip_file(tmp_path)

    @pytest.mark.asyncio
    async def test_upload_documents_success(
        self,
        async_client: AsyncClient,
        auth_headers,
        sample_zip_file,
    ):
        """Test successful document upload."""
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.return_value = mock_data.create_mock_job()
            
            with open(sample_zip_file, 'rb') as f:
                response = await async_client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={"file": ("test.zip", f, "application/zip")},
                    data={"workspace_id": "ws_123"},
                )
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_upload_documents_no_file(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test document upload without file."""
        response = await async_client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            data={"workspace_id": "ws_123"},
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_upload_documents_invalid_file_type(
        self,
        async_client: AsyncClient,
        auth_headers,
        tmp_path,
    ):
        """Test document upload with invalid file type."""
        # Create a text file instead of ZIP
        text_file = tmp_path / "invalid.txt"
        text_file.write_text("This is not a ZIP file")
        
        with open(text_file, 'rb') as f:
            response = await async_client.post(
                "/api/v1/documents/upload",
                headers=auth_headers,
                files={"file": ("invalid.txt", f, "text/plain")},
                data={"workspace_id": "ws_123"},
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_upload_documents_missing_workspace_id(
        self,
        async_client: AsyncClient,
        auth_headers,
        sample_zip_file,
    ):
        """Test document upload without workspace ID."""
        with open(sample_zip_file, 'rb') as f:
            response = await async_client.post(
                "/api/v1/documents/upload",
                headers=auth_headers,
                files={"file": ("test.zip", f, "application/zip")},
            )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_upload_documents_unauthorized(
        self,
        async_client: AsyncClient,
        sample_zip_file,
    ):
        """Test document upload without authentication."""
        with open(sample_zip_file, 'rb') as f:
            response = await async_client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.zip", f, "application/zip")},
                data={"workspace_id": "ws_123"},
            )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_job_status_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test successful job status retrieval."""
        job_id = "job_123"
        
        with patch('app.services.job_service.JobService.get_job') as mock_get_job:
            mock_get_job.return_value = mock_data.create_mock_job(
                job_id=job_id,
                progress=75.0,
            )
            
            response = await async_client.get(
                f"/api/v1/documents/jobs/{job_id}",
                headers=auth_headers,
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == job_id
        assert data["progress"] == 75.0

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test job status retrieval for non-existent job."""
        with patch('app.services.job_service.JobService.get_job') as mock_get_job:
            from app.services.job_service import JobNotFoundError
            mock_get_job.side_effect = JobNotFoundError("Job not found")
            
            response = await async_client.get(
                "/api/v1/documents/jobs/nonexistent",
                headers=auth_headers,
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_cancel_job_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test successful job cancellation."""
        job_id = "job_123"
        
        with patch('app.services.job_service.JobService.cancel_job') as mock_cancel:
            mock_cancel.return_value = True
            
            response = await async_client.delete(
                f"/api/v1/documents/jobs/{job_id}",
                headers=auth_headers,
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "Job cancelled successfully"

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test job cancellation for non-existent job."""
        with patch('app.services.job_service.JobService.cancel_job') as mock_cancel:
            from app.services.job_service import JobNotFoundError
            mock_cancel.side_effect = JobNotFoundError("Job not found")
            
            response = await async_client.delete(
                "/api/v1/documents/jobs/nonexistent",
                headers=auth_headers,
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_list_jobs_success(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test successful job listing."""
        with patch('app.services.job_service.JobService.list_jobs') as mock_list:
            from app.models.pydantic_models import PaginatedJobs
            mock_list.return_value = PaginatedJobs(
                jobs=[mock_data.create_mock_job() for _ in range(3)],
                total=3,
                page=1,
                per_page=10,
                total_pages=1,
            )
            
            response = await async_client.get(
                "/api/v1/documents/jobs",
                headers=auth_headers,
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 3
        assert len(data["jobs"]) == 3
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_jobs_with_filters(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test job listing with filters."""
        with patch('app.services.job_service.JobService.list_jobs') as mock_list:
            from app.models.pydantic_models import PaginatedJobs
            mock_list.return_value = PaginatedJobs(
                jobs=[mock_data.create_mock_job()],
                total=1,
                page=1,
                per_page=10,
                total_pages=1,
            )
            
            response = await async_client.get(
                "/api/v1/documents/jobs",
                headers=auth_headers,
                params={
                    "status": "completed",
                    "workspace_id": "ws_123",
                    "page": 1,
                    "per_page": 10,
                },
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test job listing with pagination."""
        with patch('app.services.job_service.JobService.list_jobs') as mock_list:
            from app.models.pydantic_models import PaginatedJobs
            mock_list.return_value = PaginatedJobs(
                jobs=[mock_data.create_mock_job() for _ in range(5)],
                total=25,
                page=2,
                per_page=5,
                total_pages=5,
            )
            
            response = await async_client.get(
                "/api/v1/documents/jobs",
                headers=auth_headers,
                params={"page": 2, "per_page": 5},
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 25
        assert data["page"] == 2
        assert data["total_pages"] == 5
        assert len(data["jobs"]) == 5

    @pytest.mark.asyncio
    async def test_upload_large_file(
        self,
        async_client: AsyncClient,
        auth_headers,
        tmp_path,
    ):
        """Test upload of large file."""
        # Create a large ZIP file
        large_zip = tmp_path / "large.zip"
        with zipfile.ZipFile(large_zip, 'w') as zf:
            # Add multiple files to make it larger
            for i in range(10):
                content = f"Large file content {i}" * 1000
                zf.writestr(f"large_file_{i}.txt", content)
        
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.return_value = mock_data.create_mock_job()
            
            with open(large_zip, 'rb') as f:
                response = await async_client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={"file": ("large.zip", f, "application/zip")},
                    data={"workspace_id": "ws_123"},
                )
        
        assert response.status_code == status.HTTP_202_ACCEPTED

    @pytest.mark.asyncio
    async def test_concurrent_uploads(
        self,
        async_client: AsyncClient,
        auth_headers,
        tmp_path,
    ):
        """Test concurrent document uploads."""
        import asyncio
        
        # Create multiple ZIP files
        zip_files = []
        for i in range(3):
            zip_path = mock_data.create_test_zip_file(tmp_path, f"test_{i}.zip")
            zip_files.append(zip_path)
        
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.return_value = mock_data.create_mock_job()
            
            # Upload files concurrently
            async def upload_file(zip_path):
                with open(zip_path, 'rb') as f:
                    return await async_client.post(
                        "/api/v1/documents/upload",
                        headers=auth_headers,
                        files={"file": (zip_path.name, f, "application/zip")},
                        data={"workspace_id": "ws_123"},
                    )
            
            tasks = [upload_file(zip_path) for zip_path in zip_files]
            responses = await asyncio.gather(*tasks)
        
        # All uploads should succeed
        assert all(r.status_code == status.HTTP_202_ACCEPTED for r in responses)
        assert len(responses) == 3

    @pytest.mark.asyncio
    async def test_upload_with_metadata(
        self,
        async_client: AsyncClient,
        auth_headers,
        sample_zip_file,
    ):
        """Test document upload with additional metadata."""
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.return_value = mock_data.create_mock_job()
            
            with open(sample_zip_file, 'rb') as f:
                response = await async_client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={"file": ("test.zip", f, "application/zip")},
                    data={
                        "workspace_id": "ws_123",
                        "project_name": "Test Project",
                        "document_type": "contracts",
                        "priority": "high",
                    },
                )
        
        assert response.status_code == status.HTTP_202_ACCEPTED

    @pytest.mark.asyncio
    async def test_error_handling_service_unavailable(
        self,
        async_client: AsyncClient,
        auth_headers,
        sample_zip_file,
    ):
        """Test error handling when service is unavailable."""
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.side_effect = Exception("Service unavailable")
            
            with open(sample_zip_file, 'rb') as f:
                response = await async_client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={"file": ("test.zip", f, "application/zip")},
                    data={"workspace_id": "ws_123"},
                )
        
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_request_validation_errors(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test various request validation errors."""
        # Test invalid workspace ID format
        response = await async_client.post(
            "/api/v1/documents/upload",
            headers=auth_headers,
            data={"workspace_id": ""},  # Empty workspace ID
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test invalid job ID format in status endpoint
        response = await async_client.get(
            "/api/v1/documents/jobs/",  # Empty job ID
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_response_format_consistency(
        self,
        async_client: AsyncClient,
        auth_headers,
        sample_zip_file,
    ):
        """Test response format consistency across endpoints."""
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.return_value = mock_data.create_mock_job()
            
            # Test upload response format
            with open(sample_zip_file, 'rb') as f:
                upload_response = await async_client.post(
                    "/api/v1/documents/upload",
                    headers=auth_headers,
                    files={"file": ("test.zip", f, "application/zip")},
                    data={"workspace_id": "ws_123"},
                )
            
            assert upload_response.status_code == status.HTTP_202_ACCEPTED
            upload_data = upload_response.json()
            
            # Verify required fields
            required_fields = ["job_id", "status", "message"]
            assert all(field in upload_data for field in required_fields)
        
        with patch('app.services.job_service.JobService.get_job') as mock_get_job:
            mock_get_job.return_value = mock_data.create_mock_job()
            
            # Test job status response format
            status_response = await async_client.get(
                f"/api/v1/documents/jobs/{upload_data['job_id']}",
                headers=auth_headers,
            )
            
            assert status_response.status_code == status.HTTP_200_OK
            status_data = status_response.json()
            
            # Verify job response format
            job_fields = ["id", "type", "status", "created_at", "progress"]
            assert all(field in status_data for field in job_fields)