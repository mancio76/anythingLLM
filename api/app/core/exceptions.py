"""Custom exception classes for the AnythingLLM API."""

from typing import Any, Dict, Optional
from uuid import uuid4


class APIException(Exception):
    """Base exception class for API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        self.correlation_id = correlation_id or str(uuid4())
        super().__init__(self.message)


class ValidationError(APIException):
    """Exception for input validation errors."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ):
        error_details = details or {}
        if field:
            error_details["field"] = field
        
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=error_details,
            correlation_id=correlation_id,
        )


class NotFoundError(APIException):
    """Exception for resource not found errors."""
    
    def __init__(
        self,
        resource: str,
        identifier: str,
        correlation_id: Optional[str] = None,
    ):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            status_code=404,
            error_code="NOT_FOUND",
            details={"resource": resource, "identifier": identifier},
            correlation_id=correlation_id,
        )


class ConflictError(APIException):
    """Exception for resource conflict errors."""
    
    def __init__(
        self,
        message: str,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ):
        error_details = details or {}
        if resource:
            error_details["resource"] = resource
        
        super().__init__(
            message=message,
            status_code=409,
            error_code="CONFLICT",
            details=error_details,
            correlation_id=correlation_id,
        )


class UnauthorizedError(APIException):
    """Exception for authentication errors."""
    
    def __init__(
        self,
        message: str = "Authentication required",
        correlation_id: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            status_code=401,
            error_code="UNAUTHORIZED",
            correlation_id=correlation_id,
        )


class ForbiddenError(APIException):
    """Exception for authorization errors."""
    
    def __init__(
        self,
        message: str = "Insufficient permissions",
        required_permission: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        
        super().__init__(
            message=message,
            status_code=403,
            error_code="FORBIDDEN",
            details=details,
            correlation_id=correlation_id,
        )


class RateLimitExceededError(APIException):
    """Exception for rate limit exceeded errors."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
            correlation_id=correlation_id,
        )


class ExternalServiceError(APIException):
    """Exception for external service errors."""
    
    def __init__(
        self,
        service: str,
        message: str,
        upstream_status: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {"service": service}
        if upstream_status:
            details["upstream_status"] = upstream_status
        
        super().__init__(
            message=f"{service} error: {message}",
            status_code=502,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=details,
            correlation_id=correlation_id,
        )


class ServiceUnavailableError(APIException):
    """Exception for service unavailable errors."""
    
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        retry_after: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        
        super().__init__(
            message=message,
            status_code=503,
            error_code="SERVICE_UNAVAILABLE",
            details=details,
            correlation_id=correlation_id,
        )


class CircuitBreakerOpenError(APIException):
    """Exception for circuit breaker open state."""
    
    def __init__(
        self,
        service: str,
        retry_after: Optional[int] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {"service": service}
        if retry_after:
            details["retry_after"] = retry_after
        
        super().__init__(
            message=f"Circuit breaker open for {service}",
            status_code=503,
            error_code="CIRCUIT_BREAKER_OPEN",
            details=details,
            correlation_id=correlation_id,
        )


class ResourceLimitExceededError(APIException):
    """Exception for resource limit exceeded errors."""
    
    def __init__(
        self,
        resource: str,
        limit: Any,
        current: Any,
        correlation_id: Optional[str] = None,
    ):
        super().__init__(
            message=f"{resource} limit exceeded: {current} > {limit}",
            status_code=413,
            error_code="RESOURCE_LIMIT_EXCEEDED",
            details={
                "resource": resource,
                "limit": limit,
                "current": current,
            },
            correlation_id=correlation_id,
        )


class DataCorruptionError(APIException):
    """Exception for data corruption errors."""
    
    def __init__(
        self,
        message: str,
        data_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {}
        if data_type:
            details["data_type"] = data_type
        
        super().__init__(
            message=message,
            status_code=500,
            error_code="DATA_CORRUPTION",
            details=details,
            correlation_id=correlation_id,
        )


class ProcessingError(APIException):
    """Exception for document/job processing errors."""
    
    def __init__(
        self,
        message: str,
        job_id: Optional[str] = None,
        stage: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        details = {}
        if job_id:
            details["job_id"] = job_id
        if stage:
            details["stage"] = stage
        
        super().__init__(
            message=message,
            status_code=422,
            error_code="PROCESSING_ERROR",
            details=details,
            correlation_id=correlation_id,
        )