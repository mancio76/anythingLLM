# Error Handling and Resilience Systems

This document describes the comprehensive error handling and resilience systems implemented in the AnythingLLM API service.

## Overview

The error handling system provides:

- **Consistent Error Responses**: Standardized error format across all endpoints
- **Custom Exception Classes**: Specific exceptions for different error types
- **Circuit Breaker Pattern**: Protection against cascading failures
- **Retry Logic**: Exponential backoff for transient failures
- **Error Correlation**: Request tracking and correlation IDs
- **Graceful Degradation**: Service level adjustment under load
- **Input Validation**: Detailed validation with clear error messages

## Components

### 1. Custom Exception Classes

Located in `app/core/exceptions.py`, these provide specific error types:

#### Base Exception

```python
APIException(
    message="Error description",
    status_code=500,
    error_code="ERROR_CODE",
    details={"key": "value"},
    correlation_id="optional-id"
)
```

#### Specific Exceptions

- `ValidationError` (400) - Input validation failures
- `NotFoundError` (404) - Resource not found
- `UnauthorizedError` (401) - Authentication required
- `ForbiddenError` (403) - Insufficient permissions
- `ExternalServiceError` (502) - External service failures
- `ServiceUnavailableError` (503) - Service temporarily unavailable
- `CircuitBreakerOpenError` (503) - Circuit breaker protection
- `ResourceLimitExceededError` (413) - Resource limits exceeded
- `DataCorruptionError` (500) - Data integrity issues
- `ProcessingError` (422) - Processing failures

### 2. Circuit Breaker

Located in `app/core/circuit_breaker.py`, provides protection against cascading failures:

```python
from app.core.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig

# Configure circuit breaker
breaker = get_circuit_breaker(
    "external_service",
    CircuitBreakerConfig(
        failure_threshold=5,    # Open after 5 failures
        timeout=60,            # Stay open for 60 seconds
        success_threshold=3    # Close after 3 successes in half-open
    )
)

# Use circuit breaker
result = await breaker.call(external_function, *args, **kwargs)
```

#### States

- **CLOSED**: Normal operation, calls pass through
- **OPEN**: Failures exceeded threshold, calls fail fast
- **HALF_OPEN**: Testing if service recovered

### 3. Retry Logic

Located in `app/core/retry.py`, provides exponential backoff:

```python
from app.core.retry import retry_async, RetryConfig

# Configure retry policy
config = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True
)

# Use retry logic
result = await retry_async(
    function_to_retry,
    *args,
    config=config,
    correlation_id="request-id",
    **kwargs
)
```

### 4. Error Tracking and Correlation

Located in `app/core/error_tracking.py`, provides request correlation:

```python
from app.core.error_tracking import get_error_tracker

tracker = get_error_tracker()

# Set correlation context
tracker.set_correlation_id("request-123")
tracker.set_user_id("user-456")

# Log with correlation
tracker.log_error(exception, context={"key": "value"})
tracker.log_info("Operation completed", context={"result": "success"})
```

#### Context Variables

- `correlation_id`: Unique request identifier
- `request_id`: HTTP request identifier
- `user_id`: Authenticated user identifier

### 5. Graceful Degradation

Located in `app/core/graceful_degradation.py`, adjusts service levels under load:

```python
from app.core.graceful_degradation import check_service_availability

# Check if operation is allowed
await check_service_availability("upload")  # Raises ServiceUnavailableError if not
```

#### Service Levels

- **FULL**: All features available
- **DEGRADED**: Reduced limits and features
- **MINIMAL**: Essential operations only
- **MAINTENANCE**: Service unavailable

#### Resource Thresholds

- CPU usage: 70% warning, 85% critical
- Memory usage: 70% warning, 85% critical
- Disk usage: 80% warning, 90% critical
- Active connections: 100 warning, 200 critical

### 6. Input Validation

Located in `app/core/validation.py`, provides detailed validation:

```python
from app.core.validation import InputValidator, validate_and_raise

# Validate string
result = InputValidator.validate_string(
    value="test",
    field_name="username",
    min_length=3,
    max_length=50,
    pattern=r"^[a-zA-Z0-9_]+$"
)
validate_and_raise(result, "username")  # Raises ValidationError if invalid

# Validate email
result = InputValidator.validate_email("user@example.com", "email")
validate_and_raise(result, "email")

# Validate file
result = InputValidator.validate_file_type("document.pdf", ["pdf", "doc"])
validate_and_raise(result, "file")
```

### 7. Global Exception Handler

Located in `app/middleware/error_handler.py`, handles all exceptions:

- Catches all exceptions in the application
- Converts to standardized error responses
- Logs errors with correlation IDs
- Adds appropriate HTTP headers (Retry-After, etc.)

## Error Response Format

All errors return a consistent JSON format:

```json
{
  "error": "ERROR_CODE",
  "message": "Human-readable error message",
  "details": {
    "field": "validation_field",
    "additional": "context"
  },
  "correlation_id": "request-correlation-id",
  "timestamp": "2024-01-01T00:00:00.000Z"
}
```

## Usage Patterns

### 1. Service Implementation

```python
class MyService:
    def __init__(self):
        self.error_tracker = get_error_tracker()
        self.circuit_breaker = get_circuit_breaker("external_api")
    
    async def process_data(self, data: dict):
        try:
            # Check service availability
            await check_service_availability("processing")
            
            # Validate input
            result = InputValidator.validate_string(data.get("name"), "name")
            validate_and_raise(result, "name")
            
            # Call external service with circuit breaker
            external_result = await self.circuit_breaker.call(
                self._call_external_service,
                data
            )
            
            return {"status": "success", "result": external_result}
            
        except ValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            self.error_tracker.log_error(e, {"operation": "process_data"})
            raise ProcessingError("Data processing failed")
```

### 2. API Endpoint Implementation

```python
@router.post("/process")
async def process_endpoint(data: ProcessRequest):
    try:
        service = MyService()
        result = await service.process_data(data.dict())
        return result
    except APIException:
        raise  # Let global handler manage API exceptions
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error: {e}")
        raise APIException("Internal server error")
```

## Monitoring and Health Checks

### Health Endpoints

- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/detailed` - Detailed health with dependencies
- `GET /api/v1/health/resilience` - Error handling system status
- `POST /api/v1/health/resilience/reset` - Reset circuit breakers and error stats

### Metrics

The system exposes Prometheus metrics for:

- Error rates by type and endpoint
- Circuit breaker states and transitions
- Retry attempt counts and success rates
- Service degradation level changes
- Response times and resource usage

### Logging

All errors are logged with structured data including:

- Correlation IDs for request tracing
- Error context and stack traces
- User and request information
- Performance metrics

## Configuration

Error handling behavior can be configured through environment variables:

```env
# Circuit Breaker Settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60
CIRCUIT_BREAKER_SUCCESS_THRESHOLD=3

# Retry Settings
RETRY_MAX_ATTEMPTS=3
RETRY_BASE_DELAY=1.0
RETRY_MAX_DELAY=60.0

# Degradation Thresholds
DEGRADATION_CPU_WARNING=70.0
DEGRADATION_CPU_CRITICAL=85.0
DEGRADATION_MEMORY_WARNING=70.0
DEGRADATION_MEMORY_CRITICAL=85.0

# Logging
LOG_LEVEL=INFO
LOG_SANITIZE_SENSITIVE=true
```

## Best Practices

1. **Use Specific Exceptions**: Choose the most appropriate exception type
2. **Provide Context**: Include relevant details in error messages
3. **Log Appropriately**: Use correlation IDs and structured logging
4. **Validate Early**: Check inputs at service boundaries
5. **Fail Fast**: Use circuit breakers for external dependencies
6. **Retry Wisely**: Only retry transient failures
7. **Monitor Actively**: Track error rates and patterns
8. **Test Thoroughly**: Include error scenarios in tests

## Testing

The error handling system includes comprehensive tests:

```bash
# Run error handling tests
python -m pytest tests/test_error_handling.py -v

# Run integration tests
python -m pytest tests/integration/test_error_scenarios.py -v
```

## Examples

See `app/examples/error_handling_usage.py` for complete usage examples demonstrating all error handling patterns.
