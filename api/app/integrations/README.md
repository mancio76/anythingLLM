# Integration Layer

This module provides comprehensive integration capabilities for the AnythingLLM API service, including file storage abstraction, AnythingLLM client integration, and file validation utilities.

## Components Overview

- **Storage Abstraction**: Local filesystem and AWS S3 storage backends
- **AnythingLLM Client**: Complete integration client with resilience patterns
- **File Validation**: Comprehensive file validation utilities

## AnythingLLM Integration Client

The `AnythingLLMClient` provides a complete integration with AnythingLLM instances, featuring workspace management, document upload, thread creation, message sending, and robust error handling with circuit breaker and retry patterns.

### Key Features

- **Workspace Management**: Create, read, update, delete workspaces
- **Document Upload**: Upload files with proper error handling
- **Thread Management**: Create threads and send messages
- **Resilience Patterns**: Circuit breaker and exponential backoff retry
- **Health Monitoring**: Service health checks and status monitoring
- **Async Support**: Full async/await support with proper session management

### Usage Example

```python
from app.core.config import get_settings
from app.integrations.anythingllm_client import create_anythingllm_client

# Create client
settings = get_settings()
client = create_anythingllm_client(settings)

# Use with context manager for proper cleanup
async with client:
    # Health check
    health = await client.health_check()
    
    # Create workspace
    workspace = await client.create_workspace("My Workspace")
    
    # Upload documents
    files = [Path("document1.pdf"), Path("document2.json")]
    upload_result = await client.upload_documents(workspace.workspace.id, files)
    
    # Create thread and send message
    thread = await client.create_thread(workspace.workspace.id, "Analysis Thread")
    response = await client.send_message(
        workspace.workspace.id,
        thread.thread.id,
        "What are the key points in these documents?"
    )
```

### Configuration

The client is configured through application settings:

```python
# Required settings
anythingllm_url = "http://localhost:3001"
anythingllm_api_key = "your-api-key"
anythingllm_timeout = 30  # seconds
```

### Error Handling

The client includes comprehensive error handling:

- **Custom Exceptions**: Specific exceptions for different error types
- **Circuit Breaker**: Protects against cascading failures
- **Retry Logic**: Exponential backoff for transient failures
- **Detailed Logging**: Structured logging with correlation IDs

### Resilience Features

#### Circuit Breaker
Protects against service failures by opening the circuit after a threshold of failures:

```python
# Circuit breaker configuration
failure_threshold = 5  # Open after 5 failures
timeout = 60  # Stay open for 60 seconds
```

#### Retry Handler
Implements exponential backoff for transient failures:

```python
# Retry configuration
max_retries = 3
base_delay = 1.0  # seconds
max_delay = 60.0  # seconds
```

## Storage Abstraction Layer

This module provides a comprehensive file storage abstraction layer for the AnythingLLM API service, supporting both local filesystem and AWS S3 storage backends with file validation utilities.

## Components

### Storage Clients

#### `StorageClient` (Abstract Base Class)
The base interface that defines the contract for all storage implementations:

- `upload_file(file_path, key)` - Upload a file to storage
- `download_file(key, destination)` - Download a file from storage  
- `delete_file(key)` - Delete a file from storage
- `list_files(prefix)` - List files with optional prefix filter
- `file_exists(key)` - Check if a file exists
- `get_file_url(key, expires_in)` - Get a URL for file access

#### `LocalStorageClient`
Local filesystem storage implementation:

- Stores files in a configurable base directory
- Provides path traversal protection
- Uses async file operations with `aiofiles`
- Supports hierarchical directory structures
- Returns `file://` URLs for local file access

#### `S3StorageClient`
AWS S3 storage implementation:

- Supports S3-compatible storage backends
- Uses `aioboto3` for async S3 operations
- Supports IAM roles or explicit credentials
- Generates presigned URLs for secure file access
- Handles S3-specific error conditions

### File Validation

#### `FileValidator`
Comprehensive file validation utilities:

- **Size validation**: Configurable maximum file size limits
- **Type validation**: Extension and MIME type checking
- **Batch validation**: Process multiple files efficiently
- **File organization**: Group files by type categories
- **Supported types**: PDF, JSON, CSV (configurable)

Key methods:
- `validate_file_size(file_path)` - Check file size limits
- `validate_file_type(file_path)` - Validate file type
- `validate_file(file_path)` - Complete validation
- `validate_multiple_files(file_paths)` - Batch validation
- `organize_files_by_type(file_paths)` - Group by file type

### Storage Factory

#### `StorageFactory`
Factory pattern for creating storage clients:

- `create_storage_client(settings)` - Create client from app settings
- `create_local_storage_client(base_path)` - Create local client
- `create_s3_storage_client(bucket, region, ...)` - Create S3 client

Supports configuration-driven client creation based on application settings.

## Configuration

Storage configuration is handled through the application settings:

```python
# Local storage
storage_type = StorageType.LOCAL
storage_path = "/path/to/storage"

# S3 storage  
storage_type = StorageType.S3
s3_bucket = "my-bucket"
s3_region = "us-east-1"
aws_access_key_id = "optional"
aws_secret_access_key = "optional"

# File validation
max_file_size = 100 * 1024 * 1024  # 100MB
allowed_file_types = ["pdf", "json", "csv"]
```

## Usage Examples

### Basic Local Storage

```python
from app.integrations.storage_client import LocalStorageClient

# Create client
client = LocalStorageClient("/tmp/storage")

# Upload file
result = await client.upload_file(Path("document.pdf"), "docs/contract.pdf")

# Check if file exists
exists = await client.file_exists("docs/contract.pdf")

# Download file
success = await client.download_file("docs/contract.pdf", Path("downloaded.pdf"))

# List files
files = await client.list_files("docs/")

# Delete file
deleted = await client.delete_file("docs/contract.pdf")
```

### File Validation

```python
from app.integrations.file_validator import FileValidator

# Create validator
validator = FileValidator(
    max_file_size=1024 * 1024,  # 1MB
    allowed_file_types=['pdf', 'json', 'csv']
)

# Validate single file
is_valid, error = validator.validate_file(Path("document.pdf"))

# Validate multiple files
valid_files, invalid_files = validator.validate_multiple_files(file_list)

# Organize by type
organized = validator.organize_files_by_type(file_list)
```

### Using Storage Factory

```python
from app.integrations.storage_factory import StorageFactory
from app.core.config import get_settings

# Create client from settings
settings = get_settings()
client = StorageFactory.create_storage_client(settings)

# Use client (same interface regardless of backend)
await client.upload_file(source_path, "uploads/file.pdf")
```

### Complete Workflow

```python
from app.integrations.storage_factory import StorageFactory
from app.integrations.file_validator import FileValidator

# Setup
client = StorageFactory.create_storage_client(settings)
validator = FileValidator.create_from_settings(settings)

# Validate files
valid_files, invalid_files = validator.validate_multiple_files(uploaded_files)

# Organize by type
organized = validator.organize_files_by_type(valid_files)

# Upload valid files
for file_type, files in organized.items():
    for file_path in files:
        storage_key = f"processed/{file_type}/{file_path.name}"
        await client.upload_file(file_path, storage_key)
```

## Error Handling

The storage layer defines specific exception types:

- `StorageError` - Base storage operation error
- `FileNotFoundError` - File not found in storage
- `StorageConfigError` - Storage configuration error
- `FileValidationError` - File validation error

All storage operations should be wrapped in appropriate try-catch blocks:

```python
try:
    result = await client.upload_file(file_path, key)
except FileNotFoundError:
    # Handle missing source file
    pass
except StorageError as e:
    # Handle storage operation error
    logger.error(f"Storage error: {e}")
```

## Testing

Comprehensive test suite covers:

- Unit tests for all storage client methods
- File validation test cases
- Storage factory configuration tests
- Mock-based S3 client testing
- Integration test scenarios

Run tests with:
```bash
python -m pytest tests/test_storage.py -v
```

## Security Considerations

- **Path traversal protection**: Local storage prevents directory traversal attacks
- **File type validation**: Strict validation of allowed file types and extensions
- **Size limits**: Configurable file size limits prevent abuse
- **Presigned URLs**: S3 URLs are time-limited and secure
- **Credential handling**: Supports IAM roles and explicit credentials

## Performance

- **Async operations**: All storage operations are async for better concurrency
- **Streaming**: Large files are processed in chunks to manage memory
- **Connection pooling**: S3 client uses connection pooling for efficiency
- **Batch operations**: Support for processing multiple files efficiently

## Dependencies

- `aiofiles` - Async file operations
- `aioboto3` - Async AWS SDK
- `boto3` - AWS SDK for S3 operations
- `pydantic` - Data validation and settings
- `pathlib` - Path manipulation utilities

## Requirements Satisfied

This integration layer implementation satisfies the following requirements from the specification:

### AnythingLLM Client Requirements
- **Requirement 3.1**: Workspace creation and management with AnythingLLM integration
- **Requirement 3.4**: Document upload functionality with proper error handling
- **Requirement 4.1**: Thread creation and message sending capabilities
- **Requirement 4.2**: Support for multiple LLM models and configurations
- **Requirement 9.2**: Circuit breaker pattern for resilience against service failures
- **Requirement 9.5**: Retry logic with exponential backoff for transient failures

### Storage Layer Requirements
- **Requirement 2.1**: Document upload and processing with file validation
- **Requirement 2.6**: File size validation and error handling  
- **Requirement 5.1**: Configurable storage backends (local/S3)

The integration layer provides a robust, scalable foundation for external service integration and file management in the AnythingLLM API service.