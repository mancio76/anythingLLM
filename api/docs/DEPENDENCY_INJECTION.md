# Dependency Injection Architecture

This document describes the dependency injection system implemented for the AnythingLLM API service.

## Overview

The application uses a comprehensive dependency injection system that provides:

- **Centralized Configuration**: All services are configured through a single container
- **Singleton Management**: Expensive resources like database connections and HTTP clients are managed as singletons
- **Lifecycle Management**: Proper startup and shutdown handling for all components
- **Testability**: Easy mocking and testing through dependency injection
- **Separation of Concerns**: Clear boundaries between layers

## Architecture Components

### 1. Container (`app/core/container.py`)

The `Container` class is the heart of the dependency injection system:

```python
from app.core.container import Container, get_container

# Create container with settings
container = Container(settings)

# Access singleton services
anythingllm_client = container.anythingllm_client
storage_client = container.storage_client

# Create service instances with dependencies
document_service = container.get_document_service(job_repository)
```

**Key Features:**
- Singleton management for expensive resources
- Lazy initialization of services
- Settings-based configuration
- Factory methods for service creation

### 2. Application Factory (`app/core/factory.py`)

The `ApplicationFactory` creates and configures the FastAPI application:

```python
from app.core.factory import create_app

# Create application with default settings
app = create_app()

# Create application with custom settings
app = create_app(custom_settings)
```

**Key Features:**
- Lifecycle management with startup/shutdown hooks
- Database migration execution on startup
- Middleware configuration in proper order
- External service validation
- Comprehensive error handling

### 3. Dependencies (`app/core/dependencies.py`)

FastAPI dependency functions that integrate with the container:

```python
from app.core.dependencies import (
    get_document_service,
    get_job_service,
    get_workspace_service,
    get_question_service
)

@router.post("/upload")
async def upload_documents(
    document_service: DocumentService = Depends(get_document_service)
):
    # Use the injected service
    return await document_service.upload_documents(...)
```

### 4. Migration Manager (`app/core/migrations.py`)

Handles database migrations during application startup:

```python
from app.core.migrations import get_migration_manager

migration_manager = get_migration_manager(settings)
await migration_manager.run_migrations(engine)
```

## Service Layer Architecture

### Repository Layer
- `JobRepository`: Database operations for job management
- `CacheRepository`: Redis/memory caching operations

### Service Layer
- `DocumentService`: Document processing and file handling
- `JobService`: Job management and progress tracking
- `WorkspaceService`: AnythingLLM workspace management
- `QuestionService`: Question processing and execution

### Integration Layer
- `AnythingLLMClient`: External API integration
- `StorageClient`: File storage abstraction (Local/S3)
- `FileValidator`: File validation and security

## Startup Sequence

1. **Configuration Loading**: Environment variables and settings validation
2. **Container Initialization**: Dependency injection container setup
3. **Database Connection**: PostgreSQL connection pool creation
4. **Redis Connection**: Optional Redis connection (if enabled)
5. **Migration Execution**: Database schema updates via Alembic
6. **Service Validation**: External service health checks
7. **Middleware Configuration**: Security, logging, metrics middleware
8. **Router Registration**: API endpoint registration

## Configuration Management

The system uses Pydantic settings for configuration:

```python
from app.core.config import Settings, get_settings

# Get cached settings
settings = get_settings()

# Access configuration
database_url = settings.database_url
anythingllm_url = settings.anythingllm_url
```

**Environment Variables:**
- `DATABASE_URL`: PostgreSQL connection string (required)
- `ANYTHINGLLM_URL`: AnythingLLM service URL (required)
- `ANYTHINGLLM_API_KEY`: AnythingLLM API key (required)
- `SECRET_KEY`: JWT signing key (required)
- `REDIS_ENABLED`: Enable Redis caching (optional)
- `REDIS_URL`: Redis connection string (optional)
- `STORAGE_TYPE`: Storage backend (local/s3)

## Middleware Stack

The middleware is configured in the correct order (last added = first executed):

1. **CORSMiddleware**: Cross-origin resource sharing
2. **SecurityHeadersMiddleware**: Security headers
3. **GlobalExceptionHandler**: Error handling
4. **LoggingMiddleware**: Request/response logging
5. **MetricsMiddleware**: Performance metrics
6. **RateLimitingMiddleware**: Request throttling
7. **AuthenticationMiddleware**: JWT/API key validation
8. **VersioningMiddleware**: API versioning

## Testing

The dependency injection system makes testing easier:

```python
from app.core.container import Container, set_container

# Create test container with mocked dependencies
test_container = Container(test_settings)
test_container._anythingllm_client = mock_client
set_container(test_container)

# Now all dependencies will use the mocked services
```

## Production Deployment

The application is designed for cloud-native deployment:

```python
# main.py - Production ready
from app.core.factory import create_app

app = create_app()

# Run with: uvicorn main:app --host 0.0.0.0 --port 8000
```

**Key Features:**
- Graceful startup and shutdown
- Health checks for all dependencies
- Automatic database migrations
- Comprehensive error handling
- Metrics and monitoring integration
- Security middleware stack

## Benefits

1. **Maintainability**: Clear separation of concerns and dependencies
2. **Testability**: Easy mocking and unit testing
3. **Scalability**: Singleton management and connection pooling
4. **Reliability**: Comprehensive error handling and validation
5. **Observability**: Built-in logging, metrics, and health checks
6. **Security**: Layered security with authentication and rate limiting

## Migration from Previous Architecture

The new system replaces manual service instantiation with automatic dependency injection:

**Before:**
```python
# Manual service creation in each router
anythingllm_client = AnythingLLMClient(url, key)
document_service = DocumentService(client, settings)
```

**After:**
```python
# Automatic dependency injection
async def upload_documents(
    service: DocumentService = Depends(get_document_service)
):
    # Service is automatically created with all dependencies
```

This provides better resource management, easier testing, and cleaner code organization.