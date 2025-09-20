"""Core application components."""

from app.core.circuit_breaker import CircuitBreaker, get_circuit_breaker
from app.core.error_tracking import get_error_tracker, get_error_aggregator
from app.core.exceptions import (
    APIException,
    ValidationError,
    NotFoundError,
    UnauthorizedError,
    ForbiddenError,
    ExternalServiceError,
    ServiceUnavailableError,
    CircuitBreakerOpenError,
    ResourceLimitExceededError,
    DataCorruptionError,
    ProcessingError,
)
from app.core.graceful_degradation import get_degradation_manager, check_service_availability
from app.core.retry import retry_async, retry_sync, RetryConfig
from app.core.validation import InputValidator, validate_and_raise, create_validation_error

__all__ = [
    "CircuitBreaker",
    "get_circuit_breaker",
    "get_error_tracker",
    "get_error_aggregator",
    "APIException",
    "ValidationError",
    "NotFoundError",
    "UnauthorizedError",
    "ForbiddenError",
    "ExternalServiceError",
    "ServiceUnavailableError",
    "CircuitBreakerOpenError",
    "ResourceLimitExceededError",
    "DataCorruptionError",
    "ProcessingError",
    "get_degradation_manager",
    "check_service_availability",
    "retry_async",
    "retry_sync",
    "RetryConfig",
    "InputValidator",
    "validate_and_raise",
    "create_validation_error",
]