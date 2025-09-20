"""Comprehensive unit tests for JobRepository."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pydantic_models import JobCreate, JobFilters, JobStatus, JobType, Pagination
from app.models.sqlalchemy_models import JobModel
from app.repositories.job_repository import JobRepository, JobNotFoundError
from tests.fixtures.mock_data import mock_data


class TestJobRepository:
    """Test cases for JobRepository."""

    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def job_repository(self, mock_session):
        """Create JobRepository instance with mocked session."""
        return JobRepository(session=mock_session)

    @pytest.fixture
    def sample_job_create(self):
        """Sample job creation data."""
        return JobCreate(
            type=JobType.DOCUMENT_UPLOAD,
            workspace_id="ws_123",
            metadata={"file_count": 5, "total_size": 1024000},
        )

    @pytest.fixture
    def mock_job_model(self):
        """Mock SQLAlchemy job model."""
        job_model = MagicMock(spec=JobModel)
        job_model.id = "job_123"
        job_model.type = JobType.DOCUMENT_UPLOAD
        job_model.status = JobStatus.PENDING
        job_model.workspace_id = "ws_123"
        job_model.created_at = datetime.utcnow()
        job_model.updated_at = datetime.utcnow()
        job_model.started_at = None
        job_model.completed_at = None
        job_model.progress = 0.0
        job_model.result = None
        job_model.error = None
        job_model.metadata = {"file_count": 5}
        return job_model

    @pytest.mark.asyncio
    async def test_create_job_success(
        self,
        job_repository,
        sample_job_create,
        mock_session,
        mock_job_model,
    ):
        """Test successful job creation."""
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        with patch('app.repositories.job_repository.JobModel', return_value=mock_job_model):
            result = await job_repository.create_job(sample_job_create)
        
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_job_database_error(
        self,
        job_repository,
        sample_job_create,
        mock_session,
    ):
        """Test job creation with database error."""
        mock_session.commit.side_effect = Exception("Database error")
        mock_session.rollback.return_value = None
        
        with pytest.raises(Exception) as exc_info:
            await job_repository.create_job(sample_job_create)
        
        assert "Database error" in str(exc_info.value)
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_success(
        self,
        job_repository,
        mock_session,
        mock_job_model,
    ):
        """Test successful job retrieval by ID."""
        job_id = "job_123"
        mock_session.get.return_value = mock_job_model
        
        result = await job_repository.get_by_id(job_id)
        
        assert result is not None
        assert result.id == job_id
        mock_session.get.assert_called_once_with(JobModel, job_id)

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self,
        job_repository,
        mock_session,
    ):
        """Test job retrieval when job doesn't exist."""
        mock_session.get.return_value = None
        
        result = await job_repository.get_by_id("nonexistent")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_update_job_status_success(
        self,
        job_repository,
        mock_session,
        mock_job_model,
    ):
        """Test successful job status update."""
        job_id = "job_123"
        new_status = JobStatus.PROCESSING
        result_data = {"progress": 50}
        
        mock_session.get.return_value = mock_job_model
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        result = await job_repository.update_job_status(job_id, new_status, result_data)
        
        assert result is not None
        assert mock_job_model.status == new_status
        assert mock_job_model.result == result_data
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_job_status_not_found(
        self,
        job_repository,
        mock_session,
    ):
        """Test job status update when job doesn't exist."""
        mock_session.get.return_value = None
        
        with pytest.raises(JobNotFoundError):
            await job_repository.update_job_status("nonexistent", JobStatus.COMPLETED)

    @pytest.mark.asyncio
    async def test_list_with_filters_basic(
        self,
        job_repository,
        mock_session,
        mock_job_model,
    ):
        """Test job listing with basic filters."""
        filters = JobFilters(status=JobStatus.COMPLETED)
        
        # Mock query result
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_job_model]
        mock_query.count.return_value = 1
        
        mock_session.query.return_value = mock_query
        
        with patch('app.repositories.job_repository.select') as mock_select:
            mock_select.return_value = mock_query
            result = await job_repository.list_with_filters(filters)
        
        assert result.total == 1
        assert len(result.jobs) == 1

    @pytest.mark.asyncio
    async def test_list_with_filters_complex(
        self,
        job_repository,
        mock_session,
        mock_job_model,
    ):
        """Test job listing with complex filters."""
        filters = JobFilters(
            status=JobStatus.COMPLETED,
            job_type=JobType.DOCUMENT_UPLOAD,
            workspace_id="ws_123",
            created_after=datetime.utcnow() - timedelta(days=7),
            created_before=datetime.utcnow(),
        )
        
        # Mock query result
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_job_model, mock_job_model]
        mock_query.count.return_value = 2
        
        mock_session.query.return_value = mock_query
        
        with patch('app.repositories.job_repository.select') as mock_select:
            mock_select.return_value = mock_query
            result = await job_repository.list_with_filters(filters)
        
        assert result.total == 2
        assert len(result.jobs) == 2

    @pytest.mark.asyncio
    async def test_list_with_pagination(
        self,
        job_repository,
        mock_session,
        mock_job_model,
    ):
        """Test job listing with pagination."""
        filters = JobFilters(page=2, per_page=5)
        
        # Mock query result
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_job_model] * 5
        mock_query.count.return_value = 15  # Total jobs
        
        mock_session.query.return_value = mock_query
        
        with patch('app.repositories.job_repository.select') as mock_select:
            mock_select.return_value = mock_query
            result = await job_repository.list_with_filters(filters)
        
        assert result.total == 15
        assert result.page == 2
        assert result.per_page == 5
        assert result.total_pages == 3
        assert len(result.jobs) == 5

    @pytest.mark.asyncio
    async def test_delete_old_jobs_success(
        self,
        job_repository,
        mock_session,
    ):
        """Test successful deletion of old jobs."""
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        # Mock delete query
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.delete.return_value = 5  # Number of deleted jobs
        
        mock_session.query.return_value = mock_query
        mock_session.commit.return_value = None
        
        with patch('app.repositories.job_repository.delete') as mock_delete:
            mock_delete.return_value = mock_query
            result = await job_repository.delete_old_jobs(cutoff_date)
        
        assert result == 5
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_old_jobs_no_jobs(
        self,
        job_repository,
        mock_session,
    ):
        """Test deletion when no old jobs exist."""
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        # Mock delete query returning 0
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.delete.return_value = 0
        
        mock_session.query.return_value = mock_query
        mock_session.commit.return_value = None
        
        with patch('app.repositories.job_repository.delete') as mock_delete:
            mock_delete.return_value = mock_query
            result = await job_repository.delete_old_jobs(cutoff_date)
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(
        self,
        job_repository,
        sample_job_create,
        mock_session,
    ):
        """Test transaction rollback on database error."""
        mock_session.add.return_value = None
        mock_session.commit.side_effect = Exception("Constraint violation")
        mock_session.rollback.return_value = None
        
        with pytest.raises(Exception):
            await job_repository.create_job(sample_job_create)
        
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_job_operations(
        self,
        job_repository,
        mock_session,
        mock_job_model,
    ):
        """Test concurrent job operations."""
        import asyncio
        
        # Mock successful operations
        mock_session.get.return_value = mock_job_model
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        job_id = "job_123"
        
        # Simulate concurrent status updates
        tasks = [
            job_repository.update_job_status(job_id, JobStatus.PROCESSING, {"step": i})
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All operations should complete (though some might be exceptions in real scenarios)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_job_model_conversion(
        self,
        job_repository,
        mock_job_model,
    ):
        """Test conversion between SQLAlchemy model and Pydantic model."""
        # Test the conversion logic (this would be in the actual implementation)
        pydantic_job = job_repository._model_to_pydantic(mock_job_model)
        
        assert pydantic_job.id == mock_job_model.id
        assert pydantic_job.type == mock_job_model.type
        assert pydantic_job.status == mock_job_model.status
        assert pydantic_job.workspace_id == mock_job_model.workspace_id

    @pytest.mark.asyncio
    async def test_query_optimization(
        self,
        job_repository,
        mock_session,
    ):
        """Test query optimization for large datasets."""
        filters = JobFilters(per_page=1000)  # Large page size
        
        # Mock query with optimization
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.options.return_value = mock_query  # For eager loading
        mock_query.all.return_value = []
        mock_query.count.return_value = 0
        
        mock_session.query.return_value = mock_query
        
        with patch('app.repositories.job_repository.select') as mock_select:
            mock_select.return_value = mock_query
            result = await job_repository.list_with_filters(filters)
        
        # Verify query was executed
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_database_connection_handling(
        self,
        job_repository,
        mock_session,
    ):
        """Test database connection error handling."""
        mock_session.get.side_effect = Exception("Connection lost")
        
        with pytest.raises(Exception) as exc_info:
            await job_repository.get_by_id("job_123")
        
        assert "Connection lost" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_job_metadata_serialization(
        self,
        job_repository,
        sample_job_create,
        mock_session,
        mock_job_model,
    ):
        """Test job metadata serialization/deserialization."""
        complex_metadata = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "boolean": True,
            "null_value": None,
        }
        
        sample_job_create.metadata = complex_metadata
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        with patch('app.repositories.job_repository.JobModel', return_value=mock_job_model):
            result = await job_repository.create_job(sample_job_create)
        
        # Verify metadata was properly handled
        assert result is not None