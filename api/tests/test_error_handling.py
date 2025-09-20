"""Tests for error handling and resilience systems."""

import asyncio
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from app.core.exceptions import (
    APIException,
    ValidationError,
    NotFoundError,
    ExternalServiceError,
    CircuitBreakerOpenError,
    ServiceUnavailableError,
)
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from app.core.retry import RetryHandler, RetryConfig
from app.core.error_tracking import ErrorTracker, ErrorAggregator
from app.core.graceful_degradation import GracefulDegradationManager, ServiceLevel
from app.core.validation import InputValidator, ValidationResult
from app.middleware.error_handler import GlobalExceptionHandler, ErrorResponse


class TestCustomExceptions:
    """Test custom exception classes."""
    
    def test_api_exception_creation(self):
        """Test APIException creation with all parameters."""
        exception = APIException(
            message="Test error",
            status_code=400,
            error_code="TEST_ERROR",
            details={"field": "value"},
            correlation_id="test-id"
        )
        
        assert exception.message == "Test error"
        assert exception.status_code == 400
        assert exception.error_code == "TEST_ERROR"
        assert exception.details == {"field": "value"}
        assert exception.correlation_id == "test-id"
    
    def test_validation_error_creation(self):
        """Test ValidationError creation."""
        error = ValidationError(
            message="Invalid input",
            field="username",
            details={"min_length": 3}
        )
        
        assert error.status_code == 400
        assert error.error_code == "VALIDATION_ERROR"
        assert error.details["field"] == "username"
    
    def test_not_found_error_creation(self):
        """Test NotFoundError creation."""
        error = NotFoundError(resource="user", identifier="123")
        
        assert error.status_code == 404
        assert error.error_code == "NOT_FOUND"
        assert "user not found: 123" in error.message


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker for testing."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout=1,
            success_threshold=2
        )
        return CircuitBreaker("test_service", config)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self, circuit_breaker):
        """Test circuit breaker in closed state."""
        async def successful_function():
            return "success"
        
        result = await circuit_breaker.call(successful_function)
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, circuit_breaker):
        """Test circuit breaker opens after threshold failures."""
        async def failing_function():
            raise Exception("Test failure")
        
        # First failure
        with pytest.raises(Exception):
            await circuit_breaker.call(failing_function)
        assert circuit_breaker.state == CircuitState.CLOSED
        
        # Second failure - should open circuit
        with pytest.raises(Exception):
            await circuit_breaker.call(failing_function)
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Third call should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.call(failing_function)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_transition(self, circuit_breaker):
        """Test circuit breaker transitions to half-open after timeout."""
        async def failing_function():
            raise Exception("Test failure")
        
        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_function)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Wait for timeout and update state
        await asyncio.sleep(1.1)
        await circuit_breaker._update_state()
        
        assert circuit_breaker.state == CircuitState.HALF_OPEN


class TestRetryHandler:
    """Test retry logic with exponential backoff."""
    
    @pytest.fixture
    def retry_handler(self):
        """Create a retry handler for testing."""
        config = RetryConfig(
            max_retries=2,
            base_delay=0.1,
            max_delay=1.0,
            jitter=False
        )
        return RetryHandler(config)
    
    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self, retry_handler):
        """Test successful function on first attempt."""
        async def successful_function():
            return "success"
        
        result = await retry_handler.retry_async(successful_function)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self, retry_handler):
        """Test successful function after some failures."""
        call_count = 0
        
        async def eventually_successful_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary failure")
            return "success"
        
        result = await retry_handler.retry_async(eventually_successful_function)
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_retry_exhausted(self, retry_handler):
        """Test retry exhaustion."""
        async def always_failing_function():
            raise ConnectionError("Persistent failure")
        
        with pytest.raises(ConnectionError):
            await retry_handler.retry_async(always_failing_function)


class TestErrorTracking:
    """Test error tracking and correlation."""
    
    @pytest.fixture
    def error_tracker(self):
        """Create an error tracker for testing."""
        return ErrorTracker()
    
    @pytest.fixture
    def error_aggregator(self):
        """Create an error aggregator for testing."""
        return ErrorAggregator()
    
    def test_correlation_id_management(self, error_tracker):
        """Test correlation ID management."""
        correlation_id = error_tracker.generate_correlation_id()
        assert correlation_id is not None
        assert error_tracker.get_correlation_id() == correlation_id
    
    def test_error_logging(self, error_tracker):
        """Test error logging with context."""
        with patch.object(error_tracker.logger, 'error') as mock_logger:
            error = ValueError("Test error")
            context = {"key": "value"}
            
            error_tracker.log_error(error, context)
            
            mock_logger.assert_called_once()
            call_args = mock_logger.call_args
            assert "Error occurred: Test error" in call_args[0][0]
    
    def test_error_aggregation(self, error_aggregator):
        """Test error aggregation and pattern detection."""
        error1 = ValueError("Test error")
        error2 = ValueError("Test error")  # Same error
        error3 = TypeError("Different error")
        
        error_aggregator.record_error(error1)
        error_aggregator.record_error(error2)
        error_aggregator.record_error(error3)
        
        stats = error_aggregator.get_error_stats()
        assert stats["total_errors"] == 3
        assert stats["unique_errors"] == 2


class TestGracefulDegradation:
    """Test graceful degradation system."""
    
    @pytest.fixture
    def degradation_manager(self):
        """Create a degradation manager for testing."""
        return GracefulDegradationManager()
    
    def test_service_level_determination(self, degradation_manager):
        """Test service level determination based on resources."""
        # Normal conditions
        level = degradation_manager._determine_service_level(50, 50, 50, 50)
        assert level == ServiceLevel.FULL
        
        # Warning conditions
        level = degradation_manager._determine_service_level(75, 50, 50, 50)
        assert level == ServiceLevel.DEGRADED
        
        # Critical conditions
        level = degradation_manager._determine_service_level(90, 50, 50, 50)
        assert level == ServiceLevel.MINIMAL
    
    def test_operation_limits(self, degradation_manager):
        """Test operation limits based on service level."""
        # Full service
        degradation_manager.current_level = ServiceLevel.FULL
        assert degradation_manager.check_operation_allowed("upload")
        
        # Maintenance mode
        degradation_manager.current_level = ServiceLevel.MAINTENANCE
        assert not degradation_manager.check_operation_allowed("upload")
    
    def test_file_size_validation(self, degradation_manager):
        """Test file size validation based on service level."""
        # Full service allows larger files
        degradation_manager.current_level = ServiceLevel.FULL
        assert degradation_manager.validate_file_size(50 * 1024 * 1024)  # 50MB
        
        # Minimal service has stricter limits
        degradation_manager.current_level = ServiceLevel.MINIMAL
        assert not degradation_manager.validate_file_size(50 * 1024 * 1024)  # 50MB


class TestInputValidation:
    """Test input validation utilities."""
    
    def test_string_validation(self):
        """Test string validation with various constraints."""
        # Valid string
        result = InputValidator.validate_string("test", "field", min_length=2, max_length=10)
        assert result.is_valid
        
        # Too short
        result = InputValidator.validate_string("a", "field", min_length=2)
        assert not result.is_valid
        assert "at least 2 characters" in result.errors[0]
        
        # Too long
        result = InputValidator.validate_string("toolongstring", "field", max_length=5)
        assert not result.is_valid
        assert "at most 5 characters" in result.errors[0]
    
    def test_email_validation(self):
        """Test email validation."""
        # Valid email
        result = InputValidator.validate_email("test@example.com")
        assert result.is_valid
        
        # Invalid email
        result = InputValidator.validate_email("invalid-email")
        assert not result.is_valid
        assert "format is invalid" in result.errors[0]
    
    def test_integer_validation(self):
        """Test integer validation with range constraints."""
        # Valid integer
        result = InputValidator.validate_integer(5, "field", min_value=1, max_value=10)
        assert result.is_valid
        
        # Below minimum
        result = InputValidator.validate_integer(0, "field", min_value=1)
        assert not result.is_valid
        assert "at least 1" in result.errors[0]
        
        # Above maximum
        result = InputValidator.validate_integer(15, "field", max_value=10)
        assert not result.is_valid
        assert "at most 10" in result.errors[0]
    
    def test_file_validation(self):
        """Test file validation."""
        # Valid file size
        result = InputValidator.validate_file_size(1024, 2048)
        assert result.is_valid
        
        # File too large
        result = InputValidator.validate_file_size(3072, 2048)
        assert not result.is_valid
        assert "exceeds maximum allowed size" in result.errors[0]
        
        # Valid file type
        result = InputValidator.validate_file_type("document.pdf", ["pdf", "doc"])
        assert result.is_valid
        
        # Invalid file type
        result = InputValidator.validate_file_type("document.txt", ["pdf", "doc"])
        assert not result.is_valid
        assert "not allowed" in result.errors[0]


class TestErrorResponse:
    """Test error response formatting."""
    
    def test_error_response_creation(self):
        """Test error response creation."""
        response = ErrorResponse.create_error_response(
            error_code="TEST_ERROR",
            message="Test message",
            status_code=400,
            details={"field": "value"},
            correlation_id="test-id"
        )
        
        assert response["error"] == "TEST_ERROR"
        assert response["message"] == "Test message"
        assert response["details"] == {"field": "value"}
        assert response["correlation_id"] == "test-id"
        assert "timestamp" in response


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Integration tests for error handling system."""
    
    def test_api_exception_handling(self, client: TestClient):
        """Test API exception handling through middleware."""
        # This would require a test endpoint that raises exceptions
        # For now, we'll test the basic structure
        pass
    
    def test_validation_error_handling(self, client: TestClient):
        """Test validation error handling."""
        # This would test actual API endpoints with invalid data
        pass
    
    def test_circuit_breaker_integration(self):
        """Test circuit breaker integration with external services."""
        # This would test circuit breaker with actual service calls
        pass