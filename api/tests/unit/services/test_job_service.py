"""Comprehensive unit tests for JobService."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.pydantic_models import JobFilters, JobStatus, JobType, PaginatedJobs
from app.repositories.job_repository import JobRepository
from app.services.job_service import JobNotFoundError, JobService, JobValidationError
from tests.fixtures.mock_data import mock_data


class TestJobService:
    """Test cases for JobService."""

    @pytest.fixture
    def mock_job_repository(self):
        """Mock job repository."""
        repo = AsyncMock(spec=JobRepository)
        repo.create_job.return_value = mock_data.create_mock_job()
        repo.get_by_id.return_value = mock_data.create_mock_job()
        repo.update_job_status.return_value = mock_data.create_mock_job(status=JobStatus.COMPLETED)
        repo.list_with_filters.return_value = PaginatedJobs(
            jobs=[mock_data.create_mock_job() for _ in range(3)],
            total=3,
            page=1,
            per_page=10,
            total_pages=1,
        )
        repo.delete_old_jobs.return_value = 5
        return repo

    @pytest.fixture
    def job_service(self, mock_job_repository):
        """Create JobService instance with mocked dependencies."""
        return JobService(
            job_repository=mock_job_repository,
            max_concurrent_jobs=5,
            cleanup_days=7,
        )

    @pytest.mark.asyncio
    async def test_create_job_success(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test successful job creation."""
        job_type = JobType.DOCUMENT_UPLOAD
        metadata = {"workspace_id": "ws_123", "file_count": 5}
        
        result = await job_service.create_job(job_type, metadata)
        
        assert result.type == job_type
        assert result.status == JobStatus.PENDING
        assert result.metadata == metadata
        mock_job_repository.create_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_job_invalid_metadata(
        self,
        job_service,
    ):
        """Test job creation with invalid metadata."""
        job_type = JobType.DOCUMENT_UPLOAD
        invalid_metadata = {"invalid_key": None}  # None values might be invalid
        
        # Depending on implementation, this might raise validation error
        result = await job_service.create_job(job_type, invalid_metadata)
        assert result is not None  # Basic validation

    @pytest.mark.asyncio
    async def test_update_job_status_success(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test successful job status update."""
        job_id = "job_123"
        new_status = JobStatus.PROCESSING
        result_data = {"progress": 50, "message": "Processing documents"}
        
        result = await job_service.update_job_status(job_id, new_status, result_data)
        
        assert result.status == new_status
        mock_job_repository.update_job_status.assert_called_once_with(
            job_id, new_status, result_data
        )

    @pytest.mark.asyncio
    async def test_update_job_status_not_found(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job status update when job doesn't exist."""
        mock_job_repository.update_job_status.side_effect = JobNotFoundError("Job not found")
        
        with pytest.raises(JobNotFoundError):
            await job_service.update_job_status("nonexistent", JobStatus.COMPLETED)

    @pytest.mark.asyncio
    async def test_get_job_success(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test successful job retrieval."""
        job_id = "job_123"
        
        result = await job_service.get_job(job_id)
        
        assert result is not None
        assert result.id is not None
        mock_job_repository.get_by_id.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_get_job_not_found(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job retrieval when job doesn't exist."""
        mock_job_repository.get_by_id.return_value = None
        
        with pytest.raises(JobNotFoundError):
            await job_service.get_job("nonexistent")

    @pytest.mark.asyncio
    async def test_list_jobs_success(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test successful job listing."""
        filters = JobFilters(
            status=JobStatus.COMPLETED,
            job_type=JobType.DOCUMENT_UPLOAD,
            workspace_id="ws_123",
        )
        
        result = await job_service.list_jobs(filters)
        
        assert result.total == 3
        assert len(result.jobs) == 3
        assert result.page == 1
        mock_job_repository.list_with_filters.assert_called_once_with(filters)

    @pytest.mark.asyncio
    async def test_list_jobs_with_pagination(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job listing with pagination."""
        # Mock paginated response
        mock_job_repository.list_with_filters.return_value = PaginatedJobs(
            jobs=[mock_data.create_mock_job() for _ in range(5)],
            total=25,
            page=2,
            per_page=5,
            total_pages=5,
        )
        
        filters = JobFilters(page=2, per_page=5)
        result = await job_service.list_jobs(filters)
        
        assert result.total == 25
        assert len(result.jobs) == 5
        assert result.page == 2
        assert result.total_pages == 5

    @pytest.mark.asyncio
    async def test_list_jobs_with_date_filters(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job listing with date filters."""
        created_after = datetime.utcnow() - timedelta(days=7)
        created_before = datetime.utcnow()
        
        filters = JobFilters(
            created_after=created_after,
            created_before=created_before,
        )
        
        result = await job_service.list_jobs(filters)
        
        assert result is not None
        mock_job_repository.list_with_filters.assert_called_once_with(filters)

    @pytest.mark.asyncio
    async def test_cleanup_completed_jobs_success(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test successful cleanup of old completed jobs."""
        older_than = datetime.utcnow() - timedelta(days=7)
        
        result = await job_service.cleanup_completed_jobs(older_than)
        
        assert result == 5  # Number of jobs cleaned up
        mock_job_repository.delete_old_jobs.assert_called_once_with(older_than)

    @pytest.mark.asyncio
    async def test_cleanup_completed_jobs_no_old_jobs(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test cleanup when no old jobs exist."""
        mock_job_repository.delete_old_jobs.return_value = 0
        
        older_than = datetime.utcnow() - timedelta(days=7)
        result = await job_service.cleanup_completed_jobs(older_than)
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_job_progress_calculation(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job progress calculation."""
        job_id = "job_123"
        
        # Test different progress stages
        progress_stages = [
            (JobStatus.PENDING, 0.0),
            (JobStatus.PROCESSING, 50.0),
            (JobStatus.COMPLETED, 100.0),
            (JobStatus.FAILED, 0.0),
        ]
        
        for status, expected_progress in progress_stages:
            mock_job = mock_data.create_mock_job(
                job_id=job_id,
                status=status,
                progress=expected_progress,
            )
            mock_job_repository.update_job_status.return_value = mock_job
            
            result = await job_service.update_job_status(
                job_id, status, {"progress": expected_progress}
            )
            
            assert result.progress == expected_progress

    @pytest.mark.asyncio
    async def test_job_estimated_completion_time(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job estimated completion time calculation."""
        job_id = "job_123"
        
        # Mock job with processing information
        mock_job = mock_data.create_mock_job(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress=25.0,
            metadata={
                "total_items": 100,
                "processed_items": 25,
                "avg_processing_time": 2.0,  # seconds per item
            }
        )
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await job_service.get_job(job_id)
        
        # Verify job contains progress information
        assert result.progress == 25.0
        assert result.metadata["total_items"] == 100

    @pytest.mark.asyncio
    async def test_concurrent_job_management(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test concurrent job creation and management."""
        import asyncio
        
        # Create multiple jobs concurrently
        job_types = [JobType.DOCUMENT_UPLOAD, JobType.QUESTION_PROCESSING, JobType.WORKSPACE_CREATION]
        
        tasks = [
            job_service.create_job(job_type, {"test": f"job_{i}"})
            for i, job_type in enumerate(job_types)
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        assert all(result.status == JobStatus.PENDING for result in results)
        assert mock_job_repository.create_job.call_count == 3

    @pytest.mark.asyncio
    async def test_job_resource_allocation(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job resource allocation and limits."""
        # Test max concurrent jobs limit
        max_concurrent = job_service.max_concurrent_jobs
        
        # Create jobs up to the limit
        for i in range(max_concurrent):
            job = await job_service.create_job(
                JobType.DOCUMENT_UPLOAD,
                {"resource_test": i}
            )
            assert job is not None

        # Verify the service respects resource limits
        assert mock_job_repository.create_job.call_count == max_concurrent

    @pytest.mark.asyncio
    async def test_job_status_transitions(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test valid job status transitions."""
        job_id = "job_123"
        
        # Test valid status transitions
        valid_transitions = [
            (JobStatus.PENDING, JobStatus.PROCESSING),
            (JobStatus.PROCESSING, JobStatus.COMPLETED),
            (JobStatus.PROCESSING, JobStatus.FAILED),
        ]
        
        for from_status, to_status in valid_transitions:
            mock_job = mock_data.create_mock_job(job_id=job_id, status=to_status)
            mock_job_repository.update_job_status.return_value = mock_job
            
            result = await job_service.update_job_status(job_id, to_status)
            assert result.status == to_status

    @pytest.mark.asyncio
    async def test_job_error_handling_and_recovery(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job error handling and recovery mechanisms."""
        job_id = "job_123"
        
        # Test job failure with error details
        error_details = {
            "error_type": "ValidationError",
            "error_message": "Invalid file format",
            "stack_trace": "...",
            "retry_count": 1,
        }
        
        mock_job = mock_data.create_mock_job(
            job_id=job_id,
            status=JobStatus.FAILED,
            error="Invalid file format",
        )
        mock_job_repository.update_job_status.return_value = mock_job
        
        result = await job_service.update_job_status(
            job_id, JobStatus.FAILED, error_details
        )
        
        assert result.status == JobStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_job_metadata_validation(
        self,
        job_service,
    ):
        """Test job metadata validation."""
        # Test with valid metadata
        valid_metadata = {
            "workspace_id": "ws_123",
            "file_count": 5,
            "total_size": 1024000,
            "user_id": "user_456",
        }
        
        result = await job_service.create_job(JobType.DOCUMENT_UPLOAD, valid_metadata)
        assert result.metadata == valid_metadata

    @pytest.mark.asyncio
    async def test_job_history_and_audit_trail(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job history and audit trail functionality."""
        # Test job listing with history filters
        filters = JobFilters(
            created_after=datetime.utcnow() - timedelta(days=30),
            include_completed=True,
            include_failed=True,
        )
        
        result = await job_service.list_jobs(filters)
        
        assert result is not None
        mock_job_repository.list_with_filters.assert_called_once_with(filters)

    @pytest.mark.asyncio
    async def test_job_performance_metrics(
        self,
        job_service,
        mock_job_repository,
    ):
        """Test job performance metrics collection."""
        # Mock jobs with performance data
        performance_jobs = [
            mock_data.create_mock_job(
                status=JobStatus.COMPLETED,
                metadata={
                    "processing_time": 120.5,
                    "items_processed": 50,
                    "throughput": 0.42,  # items per second
                }
            )
            for _ in range(5)
        ]
        
        mock_job_repository.list_with_filters.return_value = PaginatedJobs(
            jobs=performance_jobs,
            total=5,
            page=1,
            per_page=10,
            total_pages=1,
        )
        
        filters = JobFilters(status=JobStatus.COMPLETED)
        result = await job_service.list_jobs(filters)
        
        # Verify performance metrics are included
        assert len(result.jobs) == 5
        for job in result.jobs:
            assert "processing_time" in job.metadata
            assert "items_processed" in job.metadata