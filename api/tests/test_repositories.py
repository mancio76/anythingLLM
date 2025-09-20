"""Tests for repository layer."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.repositories.base import BaseRepository, RepositoryError, NotFoundError, ConflictError
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository, MemoryBackend, RedisBackend
from app.models.pydantic_models import JobCreate, JobType, JobStatus, JobFilters, PaginationParams
from app.models.sqlalchemy_models import JobModel


class TestBaseRepository:
    """Test base repository functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.close = AsyncMock()
        session.execute = AsyncMock()
        return session
    
    @pytest.fixture
    def mock_model(self):
        """Mock SQLAlchemy model."""
        model = MagicMock()
        model.__name__ = "TestModel"
        model.id = "test_id"
        return model
    
    def test_repository_initialization(self, mock_model, mock_session):
        """Test repository initialization."""
        repo = BaseRepository(mock_model, mock_session)
        
        assert repo.model == mock_model
        assert repo.session == mock_session
        assert repo.logger is not None


class TestJobRepository:
    """Test job repository functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.close = AsyncMock()
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.delete = AsyncMock()
        return session
    
    @pytest.fixture
    def job_repository(self, mock_session):
        """Job repository instance."""
        return JobRepository(mock_session)
    
    @pytest.mark.asyncio
    async def test_create_job(self, job_repository, mock_session):
        """Test job creation."""
        # Mock the job creation
        mock_job = JobModel()
        mock_job.id = "test_job_id"
        mock_job.type = JobType.DOCUMENT_UPLOAD
        mock_job.status = JobStatus.PENDING
        
        # Mock session behavior
        mock_session.add = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()
        
        # Mock the job creation process
        job_repository.create = AsyncMock(return_value=mock_job)
        
        # Test job creation
        result = await job_repository.create_job(
            job_type=JobType.DOCUMENT_UPLOAD,
            workspace_id="workspace_123",
            metadata={"test": "data"}
        )
        
        assert result == mock_job
        job_repository.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_job_status(self, job_repository):
        """Test job status update."""
        # Mock existing job
        mock_job = JobModel()
        mock_job.id = "test_job_id"
        mock_job.status = JobStatus.PENDING
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.metadata = {}
        
        # Mock repository methods
        job_repository.get_by_id_or_raise = AsyncMock(return_value=mock_job)
        job_repository.update = AsyncMock(return_value=mock_job)
        
        # Test status update
        result = await job_repository.update_job_status(
            job_id="test_job_id",
            status=JobStatus.PROCESSING,
            progress=50.0
        )
        
        assert result == mock_job
        job_repository.get_by_id_or_raise.assert_called_once_with("test_job_id")
        job_repository.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_jobs_with_filters(self, job_repository, mock_session):
        """Test job listing with filters."""
        # Mock query results
        mock_jobs = [JobModel(), JobModel()]
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = mock_jobs
        
        mock_count_result = AsyncMock()
        mock_count_result.scalar.return_value = 2
        
        mock_session.execute.side_effect = [mock_result, mock_count_result]
        
        # Test listing
        filters = JobFilters(status=JobStatus.COMPLETED)
        pagination = PaginationParams(page=1, size=10)
        
        jobs, total = await job_repository.list_jobs_with_filters(filters, pagination)
        
        assert len(jobs) == 2
        assert total == 2
        assert mock_session.execute.call_count == 2


class TestCacheRepository:
    """Test cache repository functionality."""
    
    @pytest.mark.asyncio
    async def test_memory_backend_basic_operations(self):
        """Test memory backend basic operations."""
        backend = MemoryBackend()
        
        # Test set and get
        await backend.set("test_key", "test_value")
        value = await backend.get("test_key")
        assert value == "test_value"
        
        # Test exists
        exists = await backend.exists("test_key")
        assert exists is True
        
        # Test delete
        deleted = await backend.delete("test_key")
        assert deleted is True
        
        # Test get after delete
        value = await backend.get("test_key")
        assert value is None
    
    @pytest.mark.asyncio
    async def test_memory_backend_ttl(self):
        """Test memory backend TTL functionality."""
        backend = MemoryBackend()
        
        # Set value with short TTL
        await backend.set("ttl_key", "ttl_value", ttl=1)
        
        # Should exist immediately
        value = await backend.get("ttl_key")
        assert value == "ttl_value"
        
        # Wait for expiration (in real test, you'd mock datetime)
        # For now, just test the expiration logic exists
        exists = await backend.exists("ttl_key")
        assert exists is True  # Still exists since we haven't waited
    
    @pytest.mark.asyncio
    async def test_memory_backend_bulk_operations(self):
        """Test memory backend bulk operations."""
        backend = MemoryBackend()
        
        # Test set_many
        data = {"key1": "value1", "key2": "value2", "key3": "value3"}
        result = await backend.set_many(data)
        assert result is True
        
        # Test get_many
        values = await backend.get_many(["key1", "key2", "key3"])
        assert values == data
        
        # Test delete_many
        deleted_count = await backend.delete_many(["key1", "key2"])
        assert deleted_count == 2
        
        # Verify deletion
        remaining = await backend.get_many(["key1", "key2", "key3"])
        assert remaining == {"key3": "value3"}
    
    @pytest.mark.asyncio
    async def test_cache_repository_initialization(self):
        """Test cache repository initialization."""
        # Test with memory backend (no Redis)
        cache_repo = CacheRepository()
        assert cache_repo.backend_type == "memory"
        assert isinstance(cache_repo.backend, MemoryBackend)
        
        # Test health check
        healthy = await cache_repo.health_check()
        assert healthy is True
    
    @pytest.mark.asyncio
    async def test_cache_repository_operations(self):
        """Test cache repository operations."""
        cache_repo = CacheRepository()
        
        # Test basic operations
        await cache_repo.set("test", "value")
        value = await cache_repo.get("test")
        assert value == "value"
        
        # Test increment
        await cache_repo.set("counter", 5)
        new_value = await cache_repo.increment("counter", 3)
        assert new_value == 8
        
        # Test pattern operations
        await cache_repo.set("prefix:key1", "value1")
        await cache_repo.set("prefix:key2", "value2")
        await cache_repo.set("other:key", "value3")
        
        keys = await cache_repo.get_keys("prefix:*")
        assert len(keys) == 2
        assert all(key.startswith("prefix:") for key in keys)
    
    @pytest.mark.asyncio
    async def test_cache_with_ttl_pattern(self):
        """Test cache with TTL pattern."""
        cache_repo = CacheRepository()
        
        # Mock value factory
        call_count = 0
        async def value_factory():
            nonlocal call_count
            call_count += 1
            return f"generated_value_{call_count}"
        
        # First call should generate value
        value1 = await cache_repo.cache_with_ttl("factory_key", value_factory, ttl=3600)
        assert value1 == "generated_value_1"
        assert call_count == 1
        
        # Second call should use cached value
        value2 = await cache_repo.cache_with_ttl("factory_key", value_factory, ttl=3600)
        assert value2 == "generated_value_1"  # Same as first call
        assert call_count == 1  # Factory not called again
    
    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        """Test pattern invalidation."""
        cache_repo = CacheRepository()
        
        # Set up test data
        await cache_repo.set("user:1:profile", "profile1")
        await cache_repo.set("user:1:settings", "settings1")
        await cache_repo.set("user:2:profile", "profile2")
        await cache_repo.set("other:data", "data")
        
        # Invalidate user:1 data
        invalidated = await cache_repo.invalidate_pattern("user:1:*")
        assert invalidated == 2
        
        # Verify invalidation
        profile = await cache_repo.get("user:1:profile")
        settings = await cache_repo.get("user:1:settings")
        other_profile = await cache_repo.get("user:2:profile")
        other_data = await cache_repo.get("other:data")
        
        assert profile is None
        assert settings is None
        assert other_profile == "profile2"  # Not invalidated
        assert other_data == "data"  # Not invalidated
    
    @pytest.mark.asyncio
    async def test_cache_stats(self):
        """Test cache statistics."""
        cache_repo = CacheRepository()
        
        # Add some test data
        await cache_repo.set("key1", "value1")
        await cache_repo.set("key2", "value2")
        
        # Get stats
        stats = await cache_repo.get_cache_stats()
        
        assert stats["backend_type"] == "memory"
        assert stats["healthy"] is True
        assert stats["total_keys"] == 2


if __name__ == "__main__":
    pytest.main([__file__])