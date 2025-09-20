# Repository Layer

The repository layer provides data access abstraction for the AnythingLLM API service. It implements the repository pattern to separate business logic from data access concerns and provides both database and caching capabilities.

## Architecture

The repository layer consists of:

- **Base Repository**: Generic CRUD operations and common patterns
- **Job Repository**: Specialized operations for job management
- **Cache Repository**: Redis/memory backend abstraction for caching
- **Dependencies**: FastAPI dependency injection setup

## Components

### BaseRepository

Generic repository class providing common CRUD operations:

```python
from app.repositories.base import BaseRepository

class MyRepository(BaseRepository[MyModel, MyCreateSchema, MyUpdateSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(MyModel, session)
```

**Features:**
- Generic CRUD operations (create, read, update, delete)
- Pagination and filtering support
- Bulk operations
- Transaction management
- Error handling with custom exceptions
- Relationship loading support

### JobRepository

Specialized repository for job management:

```python
from app.repositories import JobRepository

# Create job
job = await job_repo.create_job(
    job_type=JobType.DOCUMENT_UPLOAD,
    workspace_id="workspace_123",
    metadata={"project": "test"}
)

# Update job status
await job_repo.update_job_status(
    job_id=job.id,
    status=JobStatus.PROCESSING,
    progress=50.0
)

# List jobs with filters
jobs, total = await job_repo.list_jobs_with_filters(
    filters=JobFilters(status=JobStatus.COMPLETED),
    pagination=PaginationParams(page=1, size=20)
)
```

**Features:**
- Job lifecycle management
- Status tracking with timestamps
- Progress monitoring
- Filtering and pagination
- Queue position tracking
- Statistics and analytics
- Cleanup operations

### CacheRepository

Cache abstraction supporting Redis and in-memory backends:

```python
from app.repositories import CacheRepository

# Basic operations
await cache_repo.set("key", "value", ttl=3600)
value = await cache_repo.get("key")
await cache_repo.delete("key")

# Bulk operations
await cache_repo.set_many({"key1": "value1", "key2": "value2"})
values = await cache_repo.get_many(["key1", "key2"])

# Pattern operations
await cache_repo.invalidate_pattern("user:*")
keys = await cache_repo.get_keys("session:*")

# Utility operations
await cache_repo.increment("counter", 5)
await cache_repo.expire("key", 300)
```

**Features:**
- Redis and memory backend support
- Automatic serialization/deserialization
- TTL support
- Bulk operations
- Pattern matching
- Health checking
- Convenience methods for common patterns

## Usage Patterns

### Dependency Injection

Use FastAPI dependencies to inject repositories:

```python
from fastapi import Depends
from app.repositories import get_job_repository, get_cache_repository

@app.post("/jobs")
async def create_job(
    job_data: JobCreate,
    job_repo: JobRepository = Depends(get_job_repository),
    cache_repo: CacheRepository = Depends(get_cache_repository)
):
    # Create job
    job = await job_repo.create_job(
        job_type=job_data.type,
        workspace_id=job_data.workspace_id
    )
    
    # Cache job data
    await cache_repo.set(f"job:{job.id}", job.dict(), ttl=3600)
    
    return job
```

### Transaction Management

Use database transactions for consistency:

```python
from app.core.database import get_db_transaction

async def complex_operation(
    session: AsyncSession = Depends(get_db_transaction)
):
    job_repo = JobRepository(session)
    
    # All operations in this function will be in a single transaction
    job1 = await job_repo.create_job(JobType.DOCUMENT_UPLOAD)
    job2 = await job_repo.create_job(JobType.QUESTION_PROCESSING)
    
    # Transaction commits automatically on success
    # Rolls back automatically on exception
```

### Caching Patterns

#### Cache-Aside Pattern

```python
async def get_job_with_cache(job_id: str, job_repo, cache_repo):
    # Try cache first
    cached_job = await cache_repo.get(f"job:{job_id}")
    if cached_job:
        return cached_job
    
    # Fall back to database
    job = await job_repo.get_by_id(job_id)
    if job:
        # Cache for future requests
        await cache_repo.set(f"job:{job_id}", job.dict(), ttl=3600)
    
    return job
```

#### Write-Through Pattern

```python
async def update_job_with_cache(job_id: str, updates, job_repo, cache_repo):
    # Update database
    job = await job_repo.update(job_id, updates)
    
    # Update cache
    await cache_repo.set(f"job:{job_id}", job.dict(), ttl=3600)
    
    return job
```

#### Cache Invalidation

```python
async def invalidate_workspace_cache(workspace_id: str, cache_repo):
    # Invalidate all workspace-related cache entries
    pattern = f"workspace:{workspace_id}:*"
    invalidated_count = await cache_repo.invalidate_pattern(pattern)
    return invalidated_count
```

## Configuration

### Database Configuration

Configure PostgreSQL connection in settings:

```python
# .env file
DATABASE_URL=postgresql+asyncpg://user:password@localhost/anythingllm
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

### Redis Configuration

Configure Redis for caching (optional):

```python
# .env file
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
REDIS_POOL_SIZE=10
```

If Redis is not available, the cache repository automatically falls back to in-memory caching.

## Error Handling

The repository layer provides custom exceptions:

```python
from app.repositories.base import RepositoryError, NotFoundError, ConflictError

try:
    job = await job_repo.get_by_id_or_raise("invalid_id")
except NotFoundError:
    # Handle not found
    pass
except ConflictError:
    # Handle constraint violations
    pass
except RepositoryError:
    # Handle general repository errors
    pass
```

## Testing

The repository layer is designed for easy testing:

```python
import pytest
from unittest.mock import AsyncMock
from app.repositories import JobRepository

@pytest.fixture
def mock_session():
    session = AsyncMock()
    # Configure mock behavior
    return session

@pytest.fixture
def job_repository(mock_session):
    return JobRepository(mock_session)

@pytest.mark.asyncio
async def test_create_job(job_repository):
    # Test job creation
    job = await job_repository.create_job(JobType.DOCUMENT_UPLOAD)
    assert job.type == JobType.DOCUMENT_UPLOAD
```

## Performance Considerations

### Connection Pooling

The database manager uses connection pooling for optimal performance:

- Pool size: Configurable (default: 10)
- Max overflow: Configurable (default: 20)
- Pre-ping: Enabled for connection health checks

### Caching Strategy

- Use Redis for distributed caching in production
- Fall back to memory caching for development/testing
- Implement appropriate TTL values based on data volatility
- Use bulk operations for better performance
- Implement cache warming for frequently accessed data

### Query Optimization

- Use relationship loading options to avoid N+1 queries
- Implement proper indexing in database schema
- Use pagination for large result sets
- Consider read replicas for read-heavy workloads

## Best Practices

1. **Always use dependency injection** for repository instances
2. **Use transactions** for operations that modify multiple records
3. **Implement proper error handling** with custom exceptions
4. **Cache frequently accessed data** with appropriate TTL
5. **Use bulk operations** when working with multiple records
6. **Implement proper logging** for debugging and monitoring
7. **Test repository operations** with mocked dependencies
8. **Monitor performance** and optimize queries as needed

## Examples

See `examples.py` for complete usage examples showing:
- Service layer integration
- Caching patterns
- Error handling
- Health monitoring
- Data cleanup operations