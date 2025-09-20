# AnythingLLM API Test Suite

This directory contains a comprehensive test suite for the AnythingLLM API service, organized by test type and component.

## Test Structure

```
tests/
├── unit/                    # Unit tests for individual components
│   ├── services/           # Service layer tests
│   ├── repositories/       # Repository layer tests
│   ├── integrations/       # Integration layer tests
│   └── models/            # Data model tests
├── integration/            # Integration tests
│   ├── api/               # API endpoint tests
│   ├── database/          # Database integration tests
│   └── external/          # External service integration tests
├── security/              # Security and authentication tests
├── performance/           # Performance and load tests
├── fixtures/              # Test fixtures and mock data
└── README.md             # This file
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual components in isolation with mocked dependencies:

- **Service Tests**: Business logic validation
- **Repository Tests**: Data access layer testing
- **Integration Tests**: External service client testing
- **Model Tests**: Data validation and serialization

**Markers**: `@pytest.mark.unit`

### Integration Tests (`tests/integration/`)

Test complete workflows and API endpoints:

- **API Endpoint Tests**: Full request/response cycle testing
- **Database Integration**: Real database operations
- **External Service Integration**: Testing with actual external services

**Markers**: `@pytest.mark.integration`

### Security Tests (`tests/security/`)

Test authentication, authorization, and security measures:

- **Authentication Tests**: JWT, API key validation
- **Authorization Tests**: Role-based access control
- **Security Headers**: CORS, security headers validation
- **Input Validation**: SQL injection, XSS prevention

**Markers**: `@pytest.mark.security`

### Performance Tests (`tests/performance/`)

Test system performance under load:

- **Concurrent Operations**: Multiple simultaneous requests
- **Load Testing**: High-volume request handling
- **Memory Usage**: Resource consumption monitoring
- **Database Performance**: Connection pooling, query optimization

**Markers**: `@pytest.mark.performance`, `@pytest.mark.slow`

## Running Tests

### Quick Start

```bash
# Run all tests
python run_tests.py

# Run specific test type
python run_tests.py --type unit
python run_tests.py --type integration
python run_tests.py --type security
python run_tests.py --type performance

# Run with coverage
python run_tests.py --coverage

# Run tests in parallel
python run_tests.py --parallel

# Skip slow tests
python run_tests.py --fast
```

### Using pytest directly

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/ -m unit

# Run integration tests only
pytest tests/integration/ -m integration

# Run security tests only
pytest tests/security/ -m security

# Run performance tests only
pytest tests/performance/ -m performance

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/unit/services/test_document_service.py

# Run specific test method
pytest tests/unit/services/test_document_service.py::TestDocumentService::test_upload_documents_success

# Run tests matching pattern
pytest -k "test_upload"

# Run tests with verbose output
pytest -vv

# Skip slow tests
pytest -m "not slow"
```

## Test Configuration

### Environment Variables

Tests use the following environment variables (set in `conftest.py`):

```bash
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db
ANYTHINGLLM_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=test-api-key
SECRET_KEY=test-secret-key-for-testing-only
REDIS_ENABLED=false
LOG_LEVEL=DEBUG
```

### Test Database Setup

For integration tests requiring a database:

```bash
# Create test database
createdb test_db

# Run migrations
alembic upgrade head
```

### External Service Dependencies

Some tests require external services:

- **AnythingLLM**: For integration tests (can be mocked)
- **Redis**: For cache tests (optional, falls back to memory)
- **PostgreSQL**: For database integration tests

## Test Fixtures and Mock Data

### Mock Data Generator (`tests/fixtures/mock_data.py`)

Provides factory methods for creating test data:

```python
from tests.fixtures.mock_data import mock_data

# Create mock job
job = mock_data.create_mock_job()

# Create mock workspace
workspace = mock_data.create_mock_workspace()

# Create test ZIP file
zip_file = mock_data.create_test_zip_file(tmp_path)

# Create sample questions
questions = mock_data.create_sample_questions()
```

### File Generator (`tests/fixtures/mock_data.py`)

Creates temporary files for testing:

```python
from tests.fixtures.mock_data import mock_files

# Create temporary directory
temp_dir = mock_files.create_temp_directory()

# Create test files
pdf_file = mock_files.create_pdf_file(temp_dir)
json_file = mock_files.create_json_file(temp_dir)
csv_file = mock_files.create_csv_file(temp_dir)
```

## Writing New Tests

### Unit Test Example

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.document_service import DocumentService
from tests.fixtures.mock_data import mock_data

class TestDocumentService:
    @pytest.fixture
    def document_service(self):
        # Create service with mocked dependencies
        return DocumentService(
            job_repository=AsyncMock(),
            storage_client=AsyncMock(),
            anythingllm_client=AsyncMock(),
        )
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_upload_documents_success(self, document_service):
        # Test implementation
        pass
```

### Integration Test Example

```python
import pytest
from httpx import AsyncClient

class TestDocumentEndpoints:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_upload_endpoint(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": "Bearer test-token"},
            files={"file": ("test.zip", file_content, "application/zip")},
            data={"workspace_id": "ws_123"},
        )
        assert response.status_code == 202
```

### Performance Test Example

```python
import pytest
import asyncio
import time

class TestPerformance:
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_concurrent_uploads(self, async_client):
        start_time = time.time()
        
        tasks = [upload_file() for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        assert total_time < 5.0  # Performance requirement
```

## Test Markers

Use pytest markers to categorize tests:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.security` - Security tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.slow` - Tests taking >5 seconds
- `@pytest.mark.asyncio` - Async tests
- `@pytest.mark.database` - Tests requiring database
- `@pytest.mark.redis` - Tests requiring Redis
- `@pytest.mark.external` - Tests requiring external services

## Coverage Requirements

- **Minimum Coverage**: 80%
- **Service Layer**: 90%+ coverage required
- **Repository Layer**: 85%+ coverage required
- **API Endpoints**: 85%+ coverage required

## Continuous Integration

Tests are designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Unit Tests
  run: python run_tests.py --type unit --coverage

- name: Run Integration Tests
  run: python run_tests.py --type integration
  
- name: Run Security Tests
  run: python run_tests.py --type security
```

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Mock External Dependencies**: Use mocks for external services
3. **Clear Test Names**: Descriptive test method names
4. **Arrange-Act-Assert**: Follow AAA pattern
5. **Performance Assertions**: Include timing assertions for performance tests
6. **Error Testing**: Test both success and failure scenarios
7. **Edge Cases**: Test boundary conditions and edge cases

## Troubleshooting

### Common Issues

1. **Database Connection Errors**: Ensure test database is running
2. **Import Errors**: Check PYTHONPATH includes project root
3. **Async Test Issues**: Use `@pytest.mark.asyncio` decorator
4. **Mock Issues**: Verify mock paths match actual import paths

### Debug Mode

Run tests with debugging:

```bash
pytest --pdb  # Drop into debugger on failure
pytest -s    # Don't capture output
pytest -vv   # Very verbose output
```

## Contributing

When adding new tests:

1. Follow the existing directory structure
2. Use appropriate test markers
3. Include both positive and negative test cases
4. Add performance tests for new endpoints
5. Update this README if adding new test categories