"""Tests for job service."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.config import Settings
from app.models.pydantic_models import (
    Job,
    JobCreate,
    JobFilters,
    JobResponse,
    JobStatus,
    JobType,
    PaginatedJobs,
    PaginationParams,
)
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository
from app.services.job_service import (
    JobService,
    JobServiceError,
    JobNotFoundError,
    JobCancellationError,
    ResourceAllocationError,
    create_job_service,
)


class TestJobService:
    """Test cases for JobService."""
    
    @pytest.fixture
    def mock_job_repository(self):
        """Mock job repository."""
        return AsyncMock(spec=JobRepository)
    
    @pytest.fixture
    def mock_cache_repository(self):
        """Mock cache repository."""
        return AsyncMock(spec=CacheRepository)
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        settings = MagicMock(spec=Settings)
        settings.max_concurrent_jobs = 5
        settings.job_cleanup_days = 7
        settings.default_job_timeout = 3600
        return settings
    
    @pytest.fixture
    def job_service(self, mock_job_repository, mock_cache_repository, mock_settings):
        """Job service instance."""
        return JobService(
            job_repository=mock_job_repository,
            cache_repository=mock_cache_repository,
            settings=mock_settings
        )
    
    @pytest.fixture
    def sample_job_model(self):
        """Sample job model."""
        job_id = str(uuid4())
        workspace_id = str(uuid4())
        created_at = datetime.utcnow()
        updated_at = datetime.utcnow()
        
        # Create a simple object with the required attributes
        class MockJobModel:
            def __init__(self):
                self.id = job_id
                self.type = JobType.DOCUMENT_UPLOAD
                self.status = JobStatus.PENDING
                self.workspace_id = workspace_id
                self.created_at = created_at
                self.updated_at = updated_at
                self.started_at = None
                self.completed_at = None
                self.progress = 0.0
                self.result = None
                self.error = None
                self.metadata = {}
                self.__dict__ = {
                    "id": self.id,
                    "type": self.type,
                    "status": self.status,
                    "workspace_id": self.workspace_id,
                    "created_at": self.created_at,
                    "updated_at": self.updated_at,
                    "started_at": self.started_at,
                    "completed_at": self.completed_at,
                    "progress": self.progress,
                    "result": self.result,
                    "error": self.error,
                    "metadata": self.metadata,
                }
        
        return MockJobModel()
    
    @pytest.mark.asyncio
    async def test_create_job_success(self, job_service, mock_job_repository, sample_job_model):
        """Test successful job creation."""
        # Setup
        mock_job_repository.create_job.return_value = sample_job_model
        mock_job_repository.get_active_jobs.return_value = []  # No active jobs
        
        # Execute
        result = await job_service.create_job(
            job_type=JobType.DOCUMENT_UPLOAD,
            workspace_id=sample_job_model.workspace_id,
            metadata={"test": "data"},
            estimated_duration=300
        )
        
        # Verify
        assert isinstance(result, JobResponse)
        assert result.job.id == sample_job_model.id
        assert result.job.type == JobType.DOCUMENT_UPLOAD
        assert result.job.status == JobStatus.PENDING
        assert "self" in result.links
        assert "status" in result.links
        assert "cancel" in result.links
        assert "workspace" in result.links
        
        # Verify repository calls
        mock_job_repository.get_active_jobs.assert_called_once()
        mock_job_repository.create_job.assert_called_once()
        
        # Check metadata was enhanced
        call_args = mock_job_repository.create_job.call_args
        metadata = call_args.kwargs["metadata"]
        assert metadata["test"] == "data"
        assert metadata["estimated_duration"] == 300
        assert "service_version" in metadata
    
    @pytest.mark.asyncio
    async def test_create_job_resource_limit_exceeded(self, job_service, mock_job_repository):
        """Test job creation when resource limit is exceeded."""
        # Setup - simulate max concurrent jobs reached
        active_jobs = [MagicMock() for _ in range(5)]  # Max is 5
        mock_job_repository.get_active_jobs.return_value = active_jobs
        
        # Execute & Verify
        with pytest.raises(ResourceAllocationError) as exc_info:
            await job_service.create_job(JobType.DOCUMENT_UPLOAD)
        
        assert "Maximum concurrent jobs limit reached" in str(exc_info.value)
        mock_job_repository.create_job.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_update_job_status_success(self, job_service, mock_job_repository, sample_job_model):
        """Test successful job status update."""
        # Setup
        updated_model = sample_job_model
        updated_model.status = JobStatus.PROCESSING
        updated_model.progress = 50.0
        updated_model.__dict__["status"] = JobStatus.PROCESSING
        updated_model.__dict__["progress"] = 50.0
        mock_job_repository.update_job_status.return_value = updated_model
        
        # Execute
        result = await job_service.update_job_status(
            job_id=sample_job_model.id,
            status=JobStatus.PROCESSING,
            progress=50.0,
            metadata={"step": "processing"}
        )
        
        # Verify
        assert isinstance(result, Job)
        assert result.id == sample_job_model.id
        assert result.status == JobStatus.PROCESSING
        assert result.progress == 50.0
        
        # Verify repository call
        mock_job_repository.update_job_status.assert_called_once_with(
            job_id=sample_job_model.id,
            status=JobStatus.PROCESSING,
            progress=50.0,
            result=None,
            error=None,
            metadata={"step": "processing"}
        )
    
    @pytest.mark.asyncio
    async def test_update_job_status_not_found(self, job_service, mock_job_repository):
        """Test job status update when job not found."""
        # Setup
        mock_job_repository.update_job_status.side_effect = Exception("Job not found")
        
        # Execute & Verify
        with pytest.raises(JobNotFoundError):
            await job_service.update_job_status(
                job_id="nonexistent",
                status=JobStatus.FAILED
            )
    
    @pytest.mark.asyncio
    async def test_get_job_success(self, job_service, mock_job_repository, mock_cache_repository, sample_job_model):
        """Test successful job retrieval."""
        # Setup
        mock_cache_repository.get.return_value = None  # No cache hit
        mock_job_repository.get_by_id.return_value = sample_job_model
        
        # Execute
        result = await job_service.get_job(sample_job_model.id)
        
        # Verify
        assert isinstance(result, Job)
        assert result.id == sample_job_model.id
        assert result.type == JobType.DOCUMENT_UPLOAD
        
        mock_job_repository.get_by_id.assert_called_once_with(sample_job_model.id)
    
    @pytest.mark.asyncio
    async def test_get_job_with_results(self, job_service, mock_job_repository, mock_cache_repository, sample_job_model):
        """Test job retrieval with results."""
        # Setup
        mock_job_repository.get_job_with_results.return_value = sample_job_model
        
        # Execute
        result = await job_service.get_job(sample_job_model.id, include_results=True)
        
        # Verify
        assert isinstance(result, Job)
        assert result.id == sample_job_model.id
        
        mock_job_repository.get_job_with_results.assert_called_once_with(sample_job_model.id)
        mock_job_repository.get_by_id.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_job_not_found(self, job_service, mock_job_repository, mock_cache_repository):
        """Test job retrieval when job not found."""
        # Setup
        mock_cache_repository.get.return_value = None  # No cache hit
        mock_job_repository.get_by_id.return_value = None
        
        # Execute & Verify
        with pytest.raises(JobNotFoundError):
            await job_service.get_job("nonexistent")
    
    @pytest.mark.asyncio
    async def test_get_job_from_cache(self, job_service, mock_cache_repository, sample_job_model):
        """Test job retrieval from cache."""
        # Setup
        cached_job_data = {
            "id": sample_job_model.id,
            "type": JobType.DOCUMENT_UPLOAD.value,
            "status": JobStatus.PENDING.value,
            "workspace_id": sample_job_model.workspace_id,
            "created_at": sample_job_model.created_at.isoformat(),
            "updated_at": sample_job_model.updated_at.isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": 0.0,
            "result": None,
            "error": None,
            "metadata": {},
        }
        mock_cache_repository.get.return_value = cached_job_data
        
        # Execute
        result = await job_service.get_job(sample_job_model.id)
        
        # Verify
        assert isinstance(result, Job)
        assert result.id == sample_job_model.id
        
        # Verify cache was checked
        mock_cache_repository.get.assert_called_once_with(f"job:{sample_job_model.id}")
    
    @pytest.mark.asyncio
    async def test_list_jobs_success(self, job_service, mock_job_repository, sample_job_model):
        """Test successful job listing."""
        # Setup
        jobs = [sample_job_model]
        total_count = 1
        mock_job_repository.list_jobs_with_filters.return_value = (jobs, total_count)
        
        filters = JobFilters(status=JobStatus.PENDING)
        pagination = PaginationParams(page=1, size=20)
        
        # Execute
        result = await job_service.list_jobs(filters=filters, pagination=pagination)
        
        # Verify
        assert isinstance(result, PaginatedJobs)
        assert len(result.items) == 1
        assert result.total == 1
        assert result.page == 1
        assert result.size == 20
        assert result.pages == 1
        
        mock_job_repository.list_jobs_with_filters.assert_called_once_with(
            filters=filters,
            pagination=pagination,
            load_relationships=False
        )
    
    @pytest.mark.asyncio
    async def test_list_jobs_with_defaults(self, job_service, mock_job_repository):
        """Test job listing with default parameters."""
        # Setup
        mock_job_repository.list_jobs_with_filters.return_value = ([], 0)
        
        # Execute
        result = await job_service.list_jobs()
        
        # Verify
        assert isinstance(result, PaginatedJobs)
        assert len(result.items) == 0
        assert result.total == 0
        
        # Verify default parameters were used
        call_args = mock_job_repository.list_jobs_with_filters.call_args
        assert isinstance(call_args.kwargs["filters"], JobFilters)
        assert isinstance(call_args.kwargs["pagination"], PaginationParams)
    
    @pytest.mark.asyncio
    async def test_cancel_job_success(self, job_service, mock_job_repository, sample_job_model):
        """Test successful job cancellation."""
        # Setup
        cancelled_model = sample_job_model
        cancelled_model.status = JobStatus.CANCELLED
        cancelled_model.error = "Job cancelled: User request"
        cancelled_model.__dict__["status"] = JobStatus.CANCELLED
        cancelled_model.__dict__["error"] = "Job cancelled: User request"
        mock_job_repository.cancel_job.return_value = cancelled_model
        
        # Execute
        result = await job_service.cancel_job(sample_job_model.id, "User request")
        
        # Verify
        assert isinstance(result, Job)
        assert result.id == sample_job_model.id
        assert result.status == JobStatus.CANCELLED
        
        mock_job_repository.cancel_job.assert_called_once_with(
            sample_job_model.id, "User request"
        )
    
    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_service, mock_job_repository):
        """Test job cancellation when job not found."""
        # Setup
        mock_job_repository.cancel_job.side_effect = Exception("Job not found")
        
        # Execute & Verify
        with pytest.raises(JobNotFoundError):
            await job_service.cancel_job("nonexistent")
    
    @pytest.mark.asyncio
    async def test_cancel_job_cannot_cancel(self, job_service, mock_job_repository):
        """Test job cancellation when job cannot be cancelled."""
        # Setup
        mock_job_repository.cancel_job.side_effect = Exception("Job cannot be cancelled")
        
        # Execute & Verify
        with pytest.raises(JobCancellationError):
            await job_service.cancel_job("completed_job")
    
    @pytest.mark.asyncio
    async def test_get_job_queue_position(self, job_service, mock_job_repository):
        """Test getting job queue position."""
        # Setup
        job_id = str(uuid4())
        mock_job_repository.get_job_queue_position.return_value = 3
        
        # Execute
        result = await job_service.get_job_queue_position(job_id)
        
        # Verify
        assert result == 3
        mock_job_repository.get_job_queue_position.assert_called_once_with(job_id)
    
    @pytest.mark.asyncio
    async def test_get_job_statistics(self, job_service, mock_job_repository):
        """Test getting job statistics."""
        # Setup
        workspace_id = str(uuid4())
        mock_stats = {
            "total_jobs": 100,
            "status_counts": {JobStatus.COMPLETED: 80, JobStatus.FAILED: 20},
            "average_processing_time_seconds": 300.0,
            "success_rate": 80.0
        }
        mock_job_repository.get_job_statistics.return_value = mock_stats
        mock_job_repository.get_active_jobs.return_value = [MagicMock(), MagicMock()]  # 2 active
        
        # Execute
        result = await job_service.get_job_statistics(workspace_id=workspace_id, days=30)
        
        # Verify
        assert result["total_jobs"] == 100
        assert result["current_active_jobs"] == 2
        assert result["max_concurrent_jobs"] == 5
        assert result["resource_utilization"] == 40.0  # 2/5 * 100
        assert result["pending_jobs"] == 0  # No pending jobs in active list
        
        mock_job_repository.get_job_statistics.assert_called_once_with(
            workspace_id=workspace_id, days=30
        )
        mock_job_repository.get_active_jobs.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_old_jobs(self, job_service, mock_job_repository):
        """Test cleaning up old jobs."""
        # Setup
        mock_job_repository.cleanup_old_jobs.return_value = 15
        
        # Execute
        result = await job_service.cleanup_old_jobs(older_than_days=30)
        
        # Verify
        assert result == 15
        mock_job_repository.cleanup_old_jobs.assert_called_once_with(30)
    
    @pytest.mark.asyncio
    async def test_cleanup_old_jobs_default_days(self, job_service, mock_job_repository):
        """Test cleaning up old jobs with default days."""
        # Setup
        mock_job_repository.cleanup_old_jobs.return_value = 5
        
        # Execute
        result = await job_service.cleanup_old_jobs()
        
        # Verify
        assert result == 5
        mock_job_repository.cleanup_old_jobs.assert_called_once_with(7)  # Default from settings
    
    @pytest.mark.asyncio
    async def test_get_estimated_completion_time_completed_job(self, job_service, mock_job_repository, mock_cache_repository, sample_job_model):
        """Test estimated completion time for completed job."""
        # Setup
        completed_time = datetime.utcnow()
        sample_job_model.status = JobStatus.COMPLETED
        sample_job_model.completed_at = completed_time
        sample_job_model.__dict__["status"] = JobStatus.COMPLETED
        sample_job_model.__dict__["completed_at"] = completed_time
        mock_cache_repository.get.return_value = None  # No cache hit
        mock_job_repository.get_by_id.return_value = sample_job_model
        
        # Execute
        result = await job_service.get_estimated_completion_time(sample_job_model.id)
        
        # Verify
        assert result == completed_time
    
    @pytest.mark.asyncio
    async def test_get_estimated_completion_time_pending_job(self, job_service, mock_job_repository, mock_cache_repository, sample_job_model):
        """Test estimated completion time for pending job."""
        # Setup
        mock_cache_repository.get.return_value = None  # No cache hit
        mock_job_repository.get_by_id.return_value = sample_job_model
        mock_job_repository.get_job_queue_position.return_value = 2
        mock_stats = {"average_processing_time_seconds": 300.0}
        mock_job_repository.get_job_statistics.return_value = mock_stats
        
        # Execute
        result = await job_service.get_estimated_completion_time(sample_job_model.id)
        
        # Verify
        assert result is not None
        assert isinstance(result, datetime)
        # Should be approximately 600 seconds from now (2 * 300)
        expected_time = datetime.utcnow() + timedelta(seconds=600)
        assert abs((result - expected_time).total_seconds()) < 60  # Within 1 minute
    
    @pytest.mark.asyncio
    async def test_get_estimated_completion_time_processing_job(self, job_service, mock_job_repository, mock_cache_repository, sample_job_model):
        """Test estimated completion time for processing job with progress."""
        # Setup
        started_time = datetime.utcnow() - timedelta(minutes=5)  # Started 5 minutes ago
        sample_job_model.status = JobStatus.PROCESSING
        sample_job_model.started_at = started_time
        sample_job_model.progress = 25.0  # 25% complete
        sample_job_model.__dict__["status"] = JobStatus.PROCESSING
        sample_job_model.__dict__["started_at"] = started_time
        sample_job_model.__dict__["progress"] = 25.0
        mock_cache_repository.get.return_value = None  # No cache hit
        mock_job_repository.get_by_id.return_value = sample_job_model
        
        # Execute
        result = await job_service.get_estimated_completion_time(sample_job_model.id)
        
        # Verify
        assert result is not None
        assert isinstance(result, datetime)
        # Should be approximately 15 minutes from now (if 25% took 5 min, 100% takes 20 min total)
        expected_time = datetime.utcnow() + timedelta(minutes=15)
        assert abs((result - expected_time).total_seconds()) < 120  # Within 2 minutes
    
    @pytest.mark.asyncio
    async def test_resource_allocation_check_type_specific_limit(self, job_service, mock_job_repository, mock_settings):
        """Test resource allocation with job type specific limits."""
        # Setup type-specific limit
        mock_settings.max_concurrent_document_upload_jobs = 2
        
        # Create active jobs of the same type
        active_jobs = []
        for _ in range(2):
            job = MagicMock()
            job.type = JobType.DOCUMENT_UPLOAD
            active_jobs.append(job)
        
        mock_job_repository.get_active_jobs.return_value = active_jobs
        
        # Execute & Verify
        with pytest.raises(ResourceAllocationError) as exc_info:
            await job_service.create_job(JobType.DOCUMENT_UPLOAD)
        
        assert "Maximum concurrent document_upload jobs limit reached" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_cache_operations(self, job_service, mock_cache_repository, mock_job_repository, sample_job_model):
        """Test cache operations during job updates."""
        # Setup
        mock_job_repository.update_job_status.return_value = sample_job_model
        
        # Execute
        await job_service.update_job_status(
            job_id=sample_job_model.id,
            status=JobStatus.PROCESSING,
            progress=50.0
        )
        
        # Verify cache operations
        cache_key = f"job_status:{sample_job_model.id}"
        mock_cache_repository.set.assert_called_once()
        call_args = mock_cache_repository.set.call_args
        assert call_args[0][0] == cache_key
        assert call_args[0][1]["status"] == JobStatus.PROCESSING.value
        assert call_args[0][1]["progress"] == 50.0
        assert call_args[1]["ttl"] == 300
    
    def test_create_job_service_factory(self, mock_job_repository, mock_cache_repository, mock_settings):
        """Test job service factory function."""
        # Execute
        service = create_job_service(
            job_repository=mock_job_repository,
            cache_repository=mock_cache_repository,
            settings=mock_settings
        )
        
        # Verify
        assert isinstance(service, JobService)
        assert service.job_repository == mock_job_repository
        assert service.cache_repository == mock_cache_repository
        assert service.settings == mock_settings
    
    def test_create_job_service_factory_minimal(self, mock_job_repository):
        """Test job service factory with minimal parameters."""
        # Execute
        service = create_job_service(job_repository=mock_job_repository)
        
        # Verify
        assert isinstance(service, JobService)
        assert service.job_repository == mock_job_repository
        assert service.cache_repository is None
        assert service.settings is not None  # Should create default settings


class TestJobServiceIntegration:
    """Integration tests for JobService with real-like scenarios."""
    
    @pytest.fixture
    def job_service_with_mocks(self):
        """Job service with comprehensive mocks."""
        job_repo = AsyncMock(spec=JobRepository)
        cache_repo = AsyncMock(spec=CacheRepository)
        settings = MagicMock(spec=Settings)
        settings.max_concurrent_jobs = 3
        settings.job_cleanup_days = 7
        
        return JobService(
            job_repository=job_repo,
            cache_repository=cache_repo,
            settings=settings
        ), job_repo, cache_repo
    
    @pytest.mark.asyncio
    async def test_job_lifecycle_complete_workflow(self, job_service_with_mocks):
        """Test complete job lifecycle from creation to completion."""
        service, job_repo, cache_repo = job_service_with_mocks
        
        # Setup job model
        job_id = str(uuid4())
        workspace_id = str(uuid4())
        
        # Mock job creation
        class MockCreatedJob:
            def __init__(self):
                self.id = job_id
                self.type = JobType.DOCUMENT_UPLOAD
                self.status = JobStatus.PENDING
                self.workspace_id = workspace_id
                self.created_at = datetime.utcnow()
                self.updated_at = datetime.utcnow()
                self.started_at = None
                self.completed_at = None
                self.progress = 0.0
                self.result = None
                self.error = None
                self.metadata = {}
                self.__dict__ = {
                    "id": job_id,
                    "type": JobType.DOCUMENT_UPLOAD,
                    "status": JobStatus.PENDING,
                    "workspace_id": workspace_id,
                    "created_at": self.created_at,
                    "updated_at": self.updated_at,
                    "started_at": None,
                    "completed_at": None,
                    "progress": 0.0,
                    "result": None,
                    "error": None,
                    "metadata": {},
                }
        
        created_job = MockCreatedJob()
        
        job_repo.get_active_jobs.return_value = []
        job_repo.create_job.return_value = created_job
        
        # Step 1: Create job
        create_response = await service.create_job(
            job_type=JobType.DOCUMENT_UPLOAD,
            workspace_id=workspace_id,
            metadata={"file_count": 5}
        )
        
        assert create_response.job.id == job_id
        assert create_response.job.status == JobStatus.PENDING
        
        # Step 2: Start processing
        processing_job = created_job
        processing_job.status = JobStatus.PROCESSING
        processing_job.started_at = datetime.utcnow()
        processing_job.progress = 0.0
        processing_job.__dict__["status"] = JobStatus.PROCESSING
        processing_job.__dict__["started_at"] = processing_job.started_at
        
        job_repo.update_job_status.return_value = processing_job
        
        start_result = await service.update_job_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress=0.0
        )
        
        assert start_result.status == JobStatus.PROCESSING
        
        # Step 3: Update progress
        progress_job = processing_job
        progress_job.progress = 50.0
        progress_job.__dict__["progress"] = 50.0
        
        progress_result = await service.update_job_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            progress=50.0,
            metadata={"files_processed": 2}
        )
        
        assert progress_result.progress == 50.0
        
        # Step 4: Complete job
        completed_job = progress_job
        completed_job.status = JobStatus.COMPLETED
        completed_job.completed_at = datetime.utcnow()
        completed_job.progress = 100.0
        completed_job.result = {"files_uploaded": 5, "success": True}
        completed_job.__dict__.update({
            "status": JobStatus.COMPLETED,
            "completed_at": completed_job.completed_at,
            "progress": 100.0,
            "result": {"files_uploaded": 5, "success": True}
        })
        
        complete_result = await service.update_job_status(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            progress=100.0,
            result={"files_uploaded": 5, "success": True}
        )
        
        assert complete_result.status == JobStatus.COMPLETED
        assert complete_result.progress == 100.0
        assert complete_result.result["success"] is True
        
        # Verify all repository calls were made
        assert job_repo.create_job.call_count == 1
        assert job_repo.update_job_status.call_count == 3
        
        # Verify cache operations
        assert cache_repo.set.call_count >= 3  # Status updates cached
    
    @pytest.mark.asyncio
    async def test_concurrent_job_management(self, job_service_with_mocks):
        """Test concurrent job creation and resource management."""
        service, job_repo, cache_repo = job_service_with_mocks
        
        # Setup: 2 active jobs, limit is 3
        active_jobs = [MagicMock(), MagicMock()]
        job_repo.get_active_jobs.return_value = active_jobs
        
        # Mock successful job creation
        class MockNewJob:
            def __init__(self):
                self.id = str(uuid4())
                self.type = JobType.QUESTION_PROCESSING
                self.status = JobStatus.PENDING
                self.__dict__ = {
                    "id": self.id,
                    "type": JobType.QUESTION_PROCESSING,
                    "status": JobStatus.PENDING,
                    "workspace_id": None,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "started_at": None,
                    "completed_at": None,
                    "progress": 0.0,
                    "result": None,
                    "error": None,
                    "metadata": {},
                }
        
        new_job = MockNewJob()
        job_repo.create_job.return_value = new_job
        
        # Should succeed (2 active + 1 new = 3, which is the limit)
        result = await service.create_job(JobType.QUESTION_PROCESSING)
        assert result.job.id == new_job.id
        
        # Now simulate limit reached
        job_repo.get_active_jobs.return_value = [MagicMock(), MagicMock(), MagicMock()]  # 3 active
        
        # Should fail
        with pytest.raises(ResourceAllocationError):
            await service.create_job(JobType.DOCUMENT_UPLOAD)
    
    @pytest.mark.asyncio
    async def test_job_statistics_and_monitoring(self, job_service_with_mocks):
        """Test job statistics and monitoring functionality."""
        service, job_repo, cache_repo = job_service_with_mocks
        
        # Setup statistics data
        workspace_id = str(uuid4())
        mock_stats = {
            "period_days": 30,
            "workspace_id": workspace_id,
            "total_jobs": 150,
            "status_counts": {
                JobStatus.COMPLETED: 120,
                JobStatus.FAILED: 20,
                JobStatus.CANCELLED: 10
            },
            "type_counts": {
                JobType.DOCUMENT_UPLOAD: 80,
                JobType.QUESTION_PROCESSING: 70
            },
            "average_processing_time_seconds": 450.0,
            "success_rate": 80.0
        }
        
        # Mock active jobs
        active_jobs = [
            MagicMock(status=JobStatus.PROCESSING),
            MagicMock(status=JobStatus.PENDING),
            MagicMock(status=JobStatus.PROCESSING)
        ]
        
        job_repo.get_job_statistics.return_value = mock_stats
        job_repo.get_active_jobs.return_value = active_jobs
        
        # Execute
        stats = await service.get_job_statistics(workspace_id=workspace_id, days=30)
        
        # Verify enhanced statistics
        assert stats["total_jobs"] == 150
        assert stats["current_active_jobs"] == 3
        assert stats["max_concurrent_jobs"] == 3
        assert stats["resource_utilization"] == 100.0  # 3/3 * 100
        assert stats["pending_jobs"] == 1  # One pending job
        assert stats["success_rate"] == 80.0
        
        # Verify repository calls
        job_repo.get_job_statistics.assert_called_once_with(
            workspace_id=workspace_id, days=30
        )
        job_repo.get_active_jobs.assert_called_once()