# Design Document

## Overview

The AnythingLLM API service is a cloud-native FastAPI application that provides REST endpoints for document processing, workspace management, and automated question-answer testing against AnythingLLM instances. The service is specifically designed for procurement and contract document analysis, handling ZIP files containing PDF, JSON, or CSV documents.

The service is designed as a stateless, horizontally scalable microservice that can be deployed in containerized and serverless environments. It replaces the existing CLI-based AnythingLLM Utilities Toolkit with no backward compatibility requirements, providing a complete REST API interface.

The architecture follows a layered approach with clear separation of concerns: API layer for HTTP handling, service layer for business logic, repository layer for data access, and integration layer for external service communication. The service supports configurable storage backends (local volume or S3), optional Redis cache/queue, and PostgreSQL as the primary database engine.

## Architecture

### High-Level Architecture

```mermaid
graph TB
    Client[API Clients] --> LB[Load Balancer]
    LB --> API1[FastAPI Instance 1]
    LB --> API2[FastAPI Instance 2]
    LB --> API3[FastAPI Instance N]
    
    API1 .-> Redis(Redis Cache/Queue)
    API2 .-> Redis
    API3 .-> Redis
    
    API1 --> DB[(PostgreSQL)]
    API2 --> DB
    API3 --> DB
    
    API1 --> AnythingLLM[AnythingLLM Service]
    API2 --> AnythingLLM
    API3 --> AnythingLLM
    
    API1 --> Storage[File Storage<br/>Local/S3]
    API2 --> Storage
    API3 --> Storage
```

### Service Architecture Layers

```mermaid
graph TB
    subgraph "API Layer"
        Router[FastAPI Routers]
        Middleware[Middleware Stack]
        Validation[Request/Response Validation]
    end
    
    subgraph "Service Layer"
        DocumentService[Document Service]
        WorkspaceService[Workspace Service]
        QuestionService[Question Service]
        JobService[Job Service]
    end
    
    subgraph "Repository Layer"
        JobRepo[Job Repository]
        ConfigRepo[Config Repository]
        CacheRepo[Cache Repository]
    end
    
    subgraph "Integration Layer"
        AnythingLLMClient[AnythingLLM Client]
        FileStorage[File Storage Client]
        QueueClient[Queue Client]
    end
    
    Router --> DocumentService
    Router --> WorkspaceService
    Router --> QuestionService
    Router --> JobService
    
    DocumentService --> JobRepo
    DocumentService --> AnythingLLMClient
    DocumentService --> FileStorage
    
    WorkspaceService --> AnythingLLMClient
    WorkspaceService --> CacheRepo
    
    QuestionService --> AnythingLLMClient
    QuestionService --> QueueClient
    
    JobService --> JobRepo
    JobService --> QueueClient
```

## Components and Interfaces

### API Layer Components

#### FastAPI Application (`app/main.py`)

- **Purpose**: Main application entry point and configuration
- **Responsibilities**:
  - Application initialization and dependency injection
  - Middleware configuration (CORS, logging, authentication)
  - Router registration and OpenAPI documentation setup
- **Key Dependencies**: FastAPI, Uvicorn, Pydantic settings

#### Router Modules

- **Document Router** (`app/routers/documents.py`)
  - `POST /api/v1/documents/upload` - Upload ZIP files (PDF, JSON, CSV only)
  - `GET /api/v1/documents/jobs/{job_id}` - Get upload job status with progress
  - `DELETE /api/v1/documents/jobs/{job_id}` - Cancel upload job
  - `GET /api/v1/documents/jobs` - List document processing jobs with filters

- **Workspace Router** (`app/routers/workspaces.py`)
  - `POST /api/v1/workspaces` - Create workspace
  - `GET /api/v1/workspaces` - List workspaces
  - `GET /api/v1/workspaces/{workspace_id}` - Get workspace details
  - `PUT /api/v1/workspaces/{workspace_id}` - Update workspace
  - `DELETE /api/v1/workspaces/{workspace_id}` - Delete workspace

- **Questions Router** (`app/routers/questions.py`)
  - `POST /api/v1/questions/execute` - Execute question sets
  - `GET /api/v1/questions/jobs/{job_id}` - Get question job status
  - `GET /api/v1/questions/jobs/{job_id}/results` - Get question results

- **Health Router** (`app/routers/health.py`)
  - `GET /api/v1/health` - Basic health check
  - `GET /api/v1/health/detailed` - Detailed health with dependencies (AnythingLLM, DB, Redis)
  - `GET /api/v1/metrics` - Prometheus metrics for monitoring

- **Jobs Router** (`app/routers/jobs.py`)
  - `GET /api/v1/jobs` - List all jobs with pagination and filters
  - `GET /api/v1/jobs/{job_id}` - Get specific job details
  - `DELETE /api/v1/jobs/{job_id}` - Delete completed job
  - `POST /api/v1/jobs/cleanup` - Cleanup old completed jobs

#### Middleware Stack

- **Logging Middleware**: Structured request/response logging with correlation IDs and sensitive data sanitization
- **Authentication Middleware**: JWT/API key validation with role-based access control
- **Rate Limiting Middleware**: Request throttling per user/IP with configurable limits
- **Error Handling Middleware**: Consistent error response formatting with detailed validation messages
- **CORS Middleware**: Cross-origin resource sharing configuration for web clients
- **Security Headers Middleware**: Standard security headers (HSTS, CSP, etc.)

### Service Layer Components

#### Document Service (`app/services/document_service.py`)

```python
class DocumentService:
    async def upload_documents(self, zip_file: UploadFile, workspace_id: str) -> JobResponse
    async def process_zip_file(self, file_path: Path, job_id: str) -> ProcessingResult
    async def validate_file_types(self, extracted_files: List[Path]) -> ValidationResult
    async def validate_file_size(self, file: UploadFile, max_size: int) -> bool
    async def extract_zip_safely(self, zip_path: Path, extract_to: Path) -> List[Path]
    async def upload_to_anythingllm(self, files: List[Path], workspace_id: str) -> UploadResult
    async def organize_documents_by_type(self, files: List[Path]) -> Dict[str, List[Path]]
```

#### Workspace Service (`app/services/workspace_service.py`)

```python
class WorkspaceService:
    async def create_workspace(self, config: WorkspaceConfig) -> Workspace
    async def create_or_reuse_workspace(self, name: str, config: WorkspaceConfig) -> Workspace
    async def list_workspaces(self, filters: WorkspaceFilters) -> List[Workspace]
    async def get_workspace(self, workspace_id: str) -> Workspace
    async def update_workspace(self, workspace_id: str, updates: WorkspaceUpdate) -> Workspace
    async def delete_workspace(self, workspace_id: str) -> bool
    async def configure_llm_settings(self, workspace_id: str, llm_config: LLMConfig) -> bool
    async def configure_procurement_prompts(self, workspace_id: str) -> bool
    async def trigger_document_embedding(self, workspace_id: str) -> JobResponse
    async def organize_workspace_folders(self, workspace_id: str, document_types: List[str]) -> bool
```

#### Question Service (`app/services/question_service.py`)

```python
class QuestionService:
    async def execute_questions(self, request: QuestionRequest) -> JobResponse
    async def process_question_set(self, questions: List[Question], workspace_id: str) -> QuestionResults
    async def create_thread(self, workspace_id: str, name: str) -> ThreadInfo
    async def run_single_question(self, question: Question, thread_id: str) -> QuestionResult
    async def route_question_by_document_type(self, question: Question, doc_types: List[str]) -> str
    async def calculate_confidence_score(self, response: str, expected_fragments: List[str]) -> float
    async def manage_concurrent_processing(self, questions: List[Question], max_concurrent: int) -> List[QuestionResult]
    async def cleanup_threads(self, workspace_id: str, thread_ids: List[str]) -> bool
    async def export_results(self, job_id: str, format: ExportFormat) -> ExportData
```

#### Job Service (`app/services/job_service.py`)

```python
class JobService:
    async def create_job(self, job_type: JobType, metadata: Dict) -> Job
    async def update_job_status(self, job_id: str, status: JobStatus, result: Optional[Dict]) -> Job
    async def get_job(self, job_id: str) -> Job
    async def list_jobs(self, filters: JobFilters) -> PaginatedJobs
    async def cleanup_completed_jobs(self, older_than: datetime) -> int
```

### Repository Layer Components

#### Job Repository (`app/repositories/job_repository.py`)

```python
class JobRepository:
    async def create(self, job: JobCreate) -> Job
    async def get_by_id(self, job_id: str) -> Optional[Job]
    async def update_status(self, job_id: str, status: JobStatus, result: Optional[Dict]) -> Job
    async def list_with_filters(self, filters: JobFilters, pagination: Pagination) -> PaginatedJobs
    async def delete_old_jobs(self, cutoff_date: datetime) -> int
```

#### Cache Repository (`app/repositories/cache_repository.py`)

```python
class CacheRepository:
    async def get(self, key: str) -> Optional[Any]
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool
    async def delete(self, key: str) -> bool
    async def exists(self, key: str) -> bool
    async def get_many(self, keys: List[str]) -> Dict[str, Any]
```

### Integration Layer Components

#### AnythingLLM Client (`app/integrations/anythingllm_client.py`)

```python
class AnythingLLMClient:
    async def create_workspace(self, name: str, config: Dict) -> WorkspaceResponse
    async def upload_documents(self, workspace_id: str, files: List[Path]) -> UploadResponse
    async def create_thread(self, workspace_id: str, name: str) -> ThreadResponse
    async def send_message(self, workspace_id: str, thread_id: str, message: str) -> MessageResponse
    async def get_workspaces(self) -> List[WorkspaceInfo]
    async def delete_workspace(self, workspace_id: str) -> bool
    async def health_check(self) -> HealthStatus
```

#### File Storage Client (`app/integrations/storage_client.py`)

```python
class StorageClient:
    async def upload_file(self, file_path: Path, key: str) -> str
    async def download_file(self, key: str, destination: Path) -> bool
    async def delete_file(self, key: str) -> bool
    async def list_files(self, prefix: str) -> List[str]
    async def get_file_url(self, key: str, expires_in: int = 3600) -> str

class LocalStorageClient(StorageClient):
    """Local filesystem storage implementation"""
    def __init__(self, base_path: Path): ...

class S3StorageClient(StorageClient):
    """AWS S3 storage implementation"""
    def __init__(self, bucket: str, region: str, credentials: AWSCredentials): ...
```

**Design Decision**: The storage client uses a factory pattern to support both local filesystem and S3 storage backends. This allows deployment flexibility - local storage for development/testing and S3 for production cloud deployments. The interface remains consistent regardless of the backend.

## Data Models

### Core Domain Models

#### Job Model

```python
class Job(BaseModel):
    id: str = Field(..., description="Unique job identifier")
    type: JobType = Field(..., description="Type of job (upload, questions, etc.)")
    status: JobStatus = Field(..., description="Current job status")
    workspace_id: Optional[str] = Field(None, description="Associated workspace ID")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    progress: float = Field(0.0, ge=0.0, le=100.0, description="Job progress percentage")
    result: Optional[Dict[str, Any]] = Field(None, description="Job result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional job metadata")
```

#### Workspace Model

```python
class Workspace(BaseModel):
    id: str = Field(..., description="Unique workspace identifier")
    name: str = Field(..., min_length=1, max_length=255, description="Workspace name")
    slug: str = Field(..., description="URL-safe workspace identifier")
    description: Optional[str] = Field(None, description="Workspace description")
    llm_config: LLMConfig = Field(..., description="LLM configuration")
    document_count: int = Field(0, ge=0, description="Number of documents in workspace")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    status: WorkspaceStatus = Field(..., description="Workspace status")
```

#### Question Models

```python
class Question(BaseModel):
    id: Optional[str] = Field(None, description="Question identifier")
    text: str = Field(..., min_length=1, description="Question text")
    expected_fragments: List[str] = Field(default_factory=list, description="Expected response fragments")
    llm_config: Optional[LLMConfig] = Field(None, description="Override LLM configuration")

class QuestionResult(BaseModel):
    question_id: str = Field(..., description="Question identifier")
    question_text: str = Field(..., description="Original question text")
    response: str = Field(..., description="LLM response")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Response confidence")
    processing_time: float = Field(..., ge=0.0, description="Processing time in seconds")
    fragments_found: List[str] = Field(default_factory=list, description="Found expected fragments")
    success: bool = Field(..., description="Whether question was answered successfully")
```

### Configuration Models

#### LLM Configuration

```python
class LLMConfig(BaseModel):
    provider: LLMProvider = Field(..., description="LLM provider (openai, ollama, anthropic)")
    model: str = Field(..., description="Model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Response randomness")
    max_tokens: Optional[int] = Field(None, ge=1, description="Maximum response tokens")
    timeout: int = Field(30, ge=1, le=300, description="Request timeout in seconds")
```

#### Application Settings

```python
class Settings(BaseSettings):
    # API Configuration
    api_title: str = "AnythingLLM API"
    api_version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    
    # Database Configuration (PostgreSQL required)
    database_url: str = Field(..., env="DATABASE_URL", description="PostgreSQL connection string")
    
    # Redis Configuration (optional)
    redis_enabled: bool = Field(False, env="REDIS_ENABLED")
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    
    # AnythingLLM Configuration
    anythingllm_url: str = Field(..., env="ANYTHINGLLM_URL")
    anythingllm_api_key: str = Field(..., env="ANYTHINGLLM_API_KEY")
    anythingllm_timeout: int = Field(30, env="ANYTHINGLLM_TIMEOUT")
    
    # File Storage Configuration
    storage_type: StorageType = Field(StorageType.LOCAL, env="STORAGE_TYPE")
    storage_path: str = Field("/tmp/anythingllm-api", env="STORAGE_PATH")
    
    # S3 Configuration (when storage_type=S3)
    s3_bucket: Optional[str] = Field(None, env="S3_BUCKET")
    s3_region: Optional[str] = Field(None, env="S3_REGION")
    aws_access_key_id: Optional[str] = Field(None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(None, env="AWS_SECRET_ACCESS_KEY")
    
    # File Processing Configuration
    max_file_size: int = Field(100 * 1024 * 1024, env="MAX_FILE_SIZE")  # 100MB
    allowed_file_types: List[str] = Field(["pdf", "json", "csv"], env="ALLOWED_FILE_TYPES")
    
    # Security Configuration
    secret_key: str = Field(..., env="SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(60, env="JWT_EXPIRE_MINUTES")
    api_key_header: str = Field("X-API-Key", env="API_KEY_HEADER")
    
    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(True, env="RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(3600, env="RATE_LIMIT_WINDOW")  # 1 hour
    
    # Logging Configuration
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_format: str = Field("json", env="LOG_FORMAT")
    log_sanitize_sensitive: bool = Field(True, env="LOG_SANITIZE_SENSITIVE")
    
    # Job Management Configuration
    job_cleanup_days: int = Field(7, env="JOB_CLEANUP_DAYS")
    max_concurrent_jobs: int = Field(5, env="MAX_CONCURRENT_JOBS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        
    @validator("database_url")
    def validate_postgresql_url(cls, v):
        if not v.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v
    
    @validator("storage_type")
    def validate_storage_config(cls, v, values):
        if v == StorageType.S3:
            required_s3_fields = ["s3_bucket", "s3_region"]
            for field in required_s3_fields:
                if not values.get(field):
                    raise ValueError(f"{field} is required when storage_type is S3")
        return v
```

**Design Decision**: Configuration validation is performed at startup to fail fast if required settings are missing or invalid. The settings support both local and cloud deployments with optional Redis for enhanced performance and S3 for scalable file storage.

## Error Handling

### Error Response Format

```python
class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    correlation_id: str = Field(..., description="Request correlation ID for tracing")
    timestamp: datetime = Field(..., description="Error occurrence timestamp")
```

### Exception Hierarchy

```python
class APIException(Exception):
    def __init__(self, message: str, status_code: int = 500, details: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class ValidationError(APIException):
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, 400, details)

class NotFoundError(APIException):
    def __init__(self, resource: str, identifier: str):
        super().__init__(f"{resource} not found: {identifier}", 404)

class ExternalServiceError(APIException):
    def __init__(self, service: str, message: str):
        super().__init__(f"{service} error: {message}", 502)
```

### Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def call(self, func: Callable, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerOpenError()
        
        try:
            result = await func(*args, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
            
            raise e
```

### Retry Logic with Exponential Backoff

```python
class RetryHandler:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def retry_with_backoff(self, func: Callable, *args, **kwargs):
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt == self.max_retries:
                    break
                
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                await asyncio.sleep(delay)
        
        raise last_exception
```

**Design Decision**: The retry mechanism implements exponential backoff to handle transient failures gracefully, particularly important for external service calls to AnythingLLM. Combined with circuit breakers, this provides robust resilience against service outages.

## API Documentation and Standards

### OpenAPI/Swagger Documentation

The API follows OpenAPI 3.0 specification with comprehensive documentation including:

- **Interactive Documentation**: Swagger UI available at `/docs` endpoint
- **ReDoc Documentation**: Alternative documentation at `/redoc` endpoint
- **OpenAPI Schema**: Machine-readable schema at `/openapi.json`

### API Versioning Strategy

```python
class APIVersioning:
    """
    API versioning follows semantic versioning principles:
    - Major version (v1, v2): Breaking changes
    - Minor version: New features, backward compatible
    - Patch version: Bug fixes, backward compatible
    """
    
    def __init__(self):
        self.current_version = "1.0.0"
        self.supported_versions = ["v1"]
        self.deprecated_versions = []
    
    def get_version_from_header(self, request: Request) -> str:
        return request.headers.get("API-Version", "v1")
    
    def validate_version(self, version: str) -> bool:
        return version in self.supported_versions
```

### REST API Standards

- **HTTP Methods**: Proper use of GET, POST, PUT, DELETE, PATCH
- **Status Codes**: Consistent HTTP status code usage
- **Resource Naming**: Plural nouns for collections, clear hierarchies
- **Query Parameters**: Standardized filtering, pagination, sorting
- **Response Format**: Consistent JSON structure with metadata

### Request/Response Examples

```python
# Document Upload Request
POST /api/v1/documents/upload
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>

{
  "file": <zip_file_binary>,
  "workspace_id": "ws_123456",
  "metadata": {
    "project_name": "Procurement Analysis Q1",
    "document_type": "contracts"
  }
}

# Document Upload Response
{
  "job_id": "job_789012",
  "status": "processing",
  "message": "Document upload initiated",
  "progress": 0.0,
  "estimated_completion": "2024-01-15T10:30:00Z",
  "links": {
    "status": "/api/v1/documents/jobs/job_789012",
    "cancel": "/api/v1/documents/jobs/job_789012"
  }
}
```

**Design Decision**: The API follows RESTful principles with clear resource hierarchies and consistent response formats. Versioning through URL path ensures backward compatibility while allowing evolution of the API.

## Security Architecture

### Authentication and Authorization

```python
class SecurityManager:
    def __init__(self, settings: Settings):
        self.jwt_handler = JWTHandler(settings.secret_key, settings.jwt_algorithm)
        self.api_key_handler = APIKeyHandler()
        self.rate_limiter = RateLimiter(settings)
    
    async def authenticate_request(self, request: Request) -> User:
        # Support both JWT and API key authentication
        auth_header = request.headers.get("Authorization")
        api_key = request.headers.get(settings.api_key_header)
        
        if auth_header and auth_header.startswith("Bearer "):
            return await self.jwt_handler.validate_token(auth_header[7:])
        elif api_key:
            return await self.api_key_handler.validate_key(api_key)
        else:
            raise UnauthorizedError("Authentication required")
    
    async def authorize_action(self, user: User, resource: str, action: str) -> bool:
        return await self.check_permissions(user.role, resource, action)
```

### Data Sanitization and Logging

```python
class LogSanitizer:
    SENSITIVE_FIELDS = ["password", "api_key", "secret", "token", "authorization"]
    
    def sanitize_log_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_log_data(value)
            else:
                sanitized[key] = value
        return sanitized
```

### Rate Limiting and Abuse Prevention

```python
class RateLimiter:
    def __init__(self, settings: Settings):
        self.redis_client = redis.Redis.from_url(settings.redis_url) if settings.redis_enabled else None
        self.memory_store = {} if not self.redis_client else None
        self.requests_per_window = settings.rate_limit_requests
        self.window_seconds = settings.rate_limit_window
    
    async def check_rate_limit(self, identifier: str) -> bool:
        current_time = int(time.time())
        window_start = current_time - self.window_seconds
        
        if self.redis_client:
            # Use Redis for distributed rate limiting
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(identifier, 0, window_start)
            pipe.zcard(identifier)
            pipe.zadd(identifier, {str(current_time): current_time})
            pipe.expire(identifier, self.window_seconds)
            results = pipe.execute()
            
            return results[1] < self.requests_per_window
        else:
            # Use in-memory store for single instance
            requests = self.memory_store.get(identifier, [])
            requests = [req_time for req_time in requests if req_time > window_start]
            requests.append(current_time)
            self.memory_store[identifier] = requests
            
            return len(requests) <= self.requests_per_window
```

**Design Decision**: The security architecture implements defense in depth with multiple authentication methods, comprehensive logging with sensitive data sanitization, and configurable rate limiting. This ensures the API can be securely deployed in various environments while maintaining audit trails.

## Testing Strategy

### Unit Testing

- **Service Layer Tests**: Mock external dependencies, test business logic
- **Repository Layer Tests**: Use in-memory databases for data access testing
- **Integration Layer Tests**: Mock external APIs, test client implementations
- **Model Tests**: Validate Pydantic models and serialization

### Integration Testing

- **API Endpoint Tests**: Test complete request/response cycles
- **Database Integration Tests**: Test with real database instances
- **External Service Integration**: Test with AnythingLLM test instances
- **File Processing Tests**: Test ZIP extraction and file handling

### Performance Testing

- **Load Testing**: Simulate concurrent document uploads and processing
- **Stress Testing**: Test system behavior under resource constraints
- **Endurance Testing**: Long-running tests for memory leaks and stability

### Test Structure

```text
tests/
├── unit/
│   ├── services/
│   │   ├── test_document_service.py
│   │   ├── test_workspace_service.py
│   │   ├── test_question_service.py
│   │   └── test_job_service.py
│   ├── repositories/
│   │   ├── test_job_repository.py
│   │   └── test_cache_repository.py
│   ├── integrations/
│   │   ├── test_anythingllm_client.py
│   │   └── test_storage_client.py
│   ├── models/
│   │   └── test_data_models.py
│   └── security/
│       ├── test_authentication.py
│       ├── test_rate_limiting.py
│       └── test_sanitization.py
├── integration/
│   ├── api/
│   │   ├── test_document_endpoints.py
│   │   ├── test_workspace_endpoints.py
│   │   ├── test_question_endpoints.py
│   │   └── test_health_endpoints.py
│   ├── database/
│   │   └── test_postgresql_integration.py
│   ├── external/
│   │   └── test_anythingllm_integration.py
│   └── storage/
│       ├── test_local_storage.py
│       └── test_s3_storage.py
├── performance/
│   ├── load/
│   │   ├── test_concurrent_uploads.py
│   │   └── test_question_processing.py
│   └── stress/
│       └── test_resource_limits.py
├── security/
│   ├── test_authentication_flows.py
│   ├── test_authorization.py
│   └── test_input_validation.py
└── fixtures/
    ├── sample_documents/
    │   ├── procurement_contracts.zip
    │   ├── financial_reports.zip
    │   └── invalid_files.zip
    ├── test_data/
    │   ├── sample_questions.json
    │   └── expected_responses.json
    └── mock_responses/
        └── anythingllm_responses.json
```

### Test Configuration

```python
class TestSettings(Settings):
    # Test Database Configuration
    database_url: str = "postgresql://test:test@localhost:5432/anythingllm_test"
    
    # Test Redis Configuration
    redis_enabled: bool = True
    redis_url: str = "redis://localhost:6379/1"
    
    # Test AnythingLLM Configuration
    anythingllm_url: str = "http://localhost:3001"
    anythingllm_api_key: str = "test-api-key"
    anythingllm_timeout: int = 10
    
    # Test Storage Configuration
    storage_type: StorageType = StorageType.LOCAL
    storage_path: str = "/tmp/test-storage"
    
    # Test File Processing Configuration
    max_file_size: int = 10 * 1024 * 1024  # 10MB for tests
    allowed_file_types: List[str] = ["pdf", "json", "csv"]
    
    # Test Security Configuration
    secret_key: str = "test-secret-key-for-testing-only"
    jwt_expire_minutes: int = 5  # Short expiry for tests
    
    # Test Rate Limiting Configuration
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 10
    rate_limit_window: int = 60
    
    # Test Logging Configuration
    log_level: str = "DEBUG"
    log_format: str = "json"
    log_sanitize_sensitive: bool = True
    
    # Test Job Configuration
    job_cleanup_days: int = 1
    max_concurrent_jobs: int = 2

@pytest.fixture
async def test_client():
    """Create test client with test database"""
    app = create_app(TestSettings())
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
async def test_db():
    """Create and cleanup test database"""
    # Setup test database
    engine = create_async_engine(TestSettings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup test database
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

**Design Decision**: The test configuration uses separate test databases and reduced timeouts to ensure fast, isolated test execution. Test fixtures provide clean database states for each test, and mock external services to ensure tests are deterministic and don't depend on external availability.

## Deployment and Monitoring

### Container Configuration

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes Deployment

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anythingllm-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: anythingllm-api
  template:
    metadata:
      labels:
        app: anythingllm-api
    spec:
      containers:
      - name: api
        image: anythingllm-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: anythingllm-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: anythingllm-secrets
              key: redis-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health/detailed
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Monitoring and Observability

```python
# Prometheus metrics configuration
from prometheus_client import Counter, Histogram, Gauge

# API Metrics
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status_code']
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint']
)

# Job Metrics
active_jobs = Gauge(
    'active_jobs_total',
    'Number of active jobs',
    ['job_type']
)

job_processing_time = Histogram(
    'job_processing_duration_seconds',
    'Job processing duration',
    ['job_type', 'status']
)

# External Service Metrics
anythingllm_requests = Counter(
    'anythingllm_requests_total',
    'Total requests to AnythingLLM',
    ['operation', 'status']
)

anythingllm_response_time = Histogram(
    'anythingllm_response_duration_seconds',
    'AnythingLLM response time',
    ['operation']
)
```

### Environment-Specific Configurations

```python
# Production Configuration
class ProductionSettings(Settings):
    # Enhanced security for production
    jwt_expire_minutes: int = 15
    rate_limit_requests: int = 1000
    rate_limit_window: int = 3600
    
    # Production storage
    storage_type: StorageType = StorageType.S3
    
    # Production logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Production database with connection pooling
    database_pool_size: int = 20
    database_max_overflow: int = 30
    
    # Production Redis for caching and queuing
    redis_enabled: bool = True
    
    # Production job management
    max_concurrent_jobs: int = 50
    job_cleanup_days: int = 30

# Development Configuration
class DevelopmentSettings(Settings):
    # Relaxed security for development
    jwt_expire_minutes: int = 480  # 8 hours
    rate_limit_enabled: bool = False
    
    # Local storage for development
    storage_type: StorageType = StorageType.LOCAL
    
    # Verbose logging for development
    log_level: str = "DEBUG"
    log_format: str = "text"
    
    # Optional Redis for development
    redis_enabled: bool = False
```

**Design Decision**: The deployment strategy supports both containerized and serverless deployments with comprehensive monitoring. Environment-specific configurations ensure optimal performance in production while maintaining developer productivity in development environments.

This design provides a comprehensive foundation for building a scalable, maintainable FastAPI service that meets all the specified requirements while following modern cloud-native development practices. The architecture emphasizes security, observability, and operational excellence while maintaining flexibility for different deployment scenarios.
