# Testing Guide

## Overview

The AnythingLLM API uses pytest for testing with comprehensive test coverage across unit, integration, and end-to-end tests.

## Test Structure

```
tests/
├── __init__.py              # Test package initialization
├── conftest.py              # Shared fixtures and configuration
├── test_requirements.py     # Dependency import tests
├── test_health.py           # Health endpoint tests
├── test_config.py           # Configuration tests
├── test_logging.py          # Logging functionality tests
├── unit/                    # Unit tests (future)
├── integration/             # Integration tests (future)
└── fixtures/                # Test data and fixtures (future)
```

## Running Tests

### Prerequisites

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

### Basic Test Commands

**Run all tests:**
```bash
pytest
```

**Run specific test file:**
```bash
pytest tests/test_health.py
```

**Run specific test method:**
```bash
pytest tests/test_health.py::TestHealthEndpoints::test_basic_health_check
```

**Run tests with verbose output:**
```bash
pytest -v
```

### Test Categories

**Run by markers:**
```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Async tests only
pytest -m asyncio

# Exclude slow tests
pytest -m "not slow"
```

### Coverage Testing

**Run with coverage:**
```bash
pytest --cov=app
```

**Generate HTML coverage report:**
```bash
pytest --cov=app --cov-report=html
```

**Coverage with missing lines:**
```bash
pytest --cov=app --cov-report=term-missing
```

**Fail if coverage below threshold:**
```bash
pytest --cov=app --cov-fail-under=80
```

## Test Configuration

### Pytest Configuration

The `pytest.ini` file contains:
- Test discovery patterns
- Default options
- Markers definition
- Async support configuration

### Environment Variables

Tests use mock environment variables defined in `conftest.py`:
```python
test_env = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test_db",
    "ANYTHINGLLM_URL": "http://localhost:3001",
    "ANYTHINGLLM_API_KEY": "test-api-key",
    "SECRET_KEY": "test-secret-key-for-testing-only",
    "REDIS_ENABLED": "false",
    "LOG_LEVEL": "DEBUG",
}
```

## Test Fixtures

### Available Fixtures

**Application Fixtures:**
- `app`: FastAPI application instance
- `client`: Synchronous test client (TestClient)
- `async_client`: Asynchronous test client (AsyncClient)

**Configuration Fixtures:**
- `settings`: Application settings
- `mock_env_vars`: Mock environment variables

**Example Usage:**
```python
def test_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_async_endpoint(async_client):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
```

## Writing Tests

### Test File Structure

```python
"""Test module docstring."""

import pytest
from fastapi.testclient import TestClient


class TestFeatureName:
    """Test class for specific feature."""
    
    def test_basic_functionality(self, client: TestClient):
        """Test basic functionality."""
        response = client.get("/api/v1/endpoint")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_async_functionality(self, async_client):
        """Test async functionality."""
        response = await async_client.post("/api/v1/endpoint", json={})
        assert response.status_code == 201
    
    @pytest.mark.integration
    def test_integration_scenario(self, client):
        """Test integration scenario."""
        # Integration test code
        pass
```

### Test Naming Conventions

- **Files**: `test_*.py` or `*_test.py`
- **Classes**: `Test*` (e.g., `TestUserService`)
- **Methods**: `test_*` (e.g., `test_create_user_success`)

### Test Categories and Markers

**Unit Tests:**
```python
@pytest.mark.unit
def test_function_logic():
    """Test individual function logic."""
    pass
```

**Integration Tests:**
```python
@pytest.mark.integration
def test_api_endpoint():
    """Test API endpoint integration."""
    pass
```

**Async Tests:**
```python
@pytest.mark.asyncio
async def test_async_operation():
    """Test async operation."""
    pass
```

**Slow Tests:**
```python
@pytest.mark.slow
def test_performance_scenario():
    """Test that takes significant time."""
    pass
```

## Mocking and Patching

### External Dependencies

```python
import pytest
from unittest.mock import patch, AsyncMock

@patch('app.services.external_service.make_request')
def test_with_mocked_service(mock_request, client):
    """Test with mocked external service."""
    mock_request.return_value = {"status": "success"}
    
    response = client.post("/api/v1/process")
    assert response.status_code == 200

@pytest.mark.asyncio
@patch('app.services.async_service.async_operation')
async def test_async_with_mock(mock_async_op, async_client):
    """Test async operation with mock."""
    mock_async_op.return_value = AsyncMock(return_value="result")
    
    response = await async_client.get("/api/v1/async-endpoint")
    assert response.status_code == 200
```

### Database Mocking

```python
@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch('app.core.database.get_db_session') as mock:
        yield mock

def test_database_operation(mock_db_session, client):
    """Test database operation with mocked session."""
    # Configure mock behavior
    mock_db_session.return_value.__aenter__.return_value.execute.return_value = mock_result
    
    response = client.get("/api/v1/data")
    assert response.status_code == 200
```

## Test Data and Fixtures

### Static Test Data

```python
# tests/fixtures/sample_data.py
SAMPLE_DOCUMENT = {
    "title": "Test Document",
    "content": "This is test content",
    "type": "pdf"
}

SAMPLE_WORKSPACE = {
    "name": "Test Workspace",
    "description": "Test workspace description"
}
```

### Dynamic Fixtures

```python
@pytest.fixture
def sample_user():
    """Create sample user data."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "role": "user"
    }

@pytest.fixture
async def created_workspace(async_client):
    """Create a workspace for testing."""
    response = await async_client.post("/api/v1/workspaces", json={
        "name": "Test Workspace",
        "description": "Created for testing"
    })
    return response.json()
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: |
        pytest --cov=app --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Best Practices

### Test Organization

1. **One test class per feature/module**
2. **Group related tests together**
3. **Use descriptive test names**
4. **Keep tests focused and small**

### Test Quality

1. **Test both success and failure cases**
2. **Use appropriate assertions**
3. **Mock external dependencies**
4. **Clean up after tests**

### Performance

1. **Use fixtures for expensive setup**
2. **Mark slow tests appropriately**
3. **Parallelize when possible**
4. **Profile test execution**

### Maintenance

1. **Keep tests up to date with code changes**
2. **Remove obsolete tests**
3. **Refactor test code like production code**
4. **Document complex test scenarios**

## Troubleshooting

### Common Issues

**Import Errors:**
```bash
# Ensure PYTHONPATH includes the project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest
```

**Async Test Issues:**
```bash
# Install pytest-asyncio
pip install pytest-asyncio

# Use asyncio marker
@pytest.mark.asyncio
async def test_async_function():
    pass
```

**Database Connection Issues:**
```bash
# Use test database URL
export DATABASE_URL="postgresql+asyncpg://test:test@localhost:5432/test_db"
pytest
```

### Debug Mode

**Run with debugging:**
```bash
pytest --pdb  # Drop into debugger on failure
pytest -s     # Don't capture output
pytest --lf   # Run last failed tests only
```

**Verbose output:**
```bash
pytest -vv    # Extra verbose
pytest --tb=long  # Long traceback format
```