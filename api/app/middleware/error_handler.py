"""Global exception handler middleware."""

import logging
import traceback
from datetime import datetime
from typing import Any, Dict

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import (
    APIException,
    ValidationError,
    NotFoundError,
    UnauthorizedError,
    ForbiddenError,
    RateLimitExceededError,
    ExternalServiceError,
    ServiceUnavailableError,
    CircuitBreakerOpenError,
    ResourceLimitExceededError,
    DataCorruptionError,
    ProcessingError,
)
from app.core.error_tracking import get_error_tracker, get_error_aggregator


logger = logging.getLogger(__name__)


class ErrorResponse:
    """Standard error response format."""
    
    @staticmethod
    def create_error_response(
        error_code: str,
        message: str,
        status_code: int,
        details: Dict[str, Any] = None,
        correlation_id: str = None,
    ) -> Dict[str, Any]:
        """Create standardized error response."""
        return {
            "error": error_code,
            "message": message,
            "details": details or {},
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
        }


class GlobalExceptionHandler(BaseHTTPMiddleware):
    """Global exception handler middleware."""
    
    async def dispatch(self, request: Request, call_next):
        """Handle all exceptions globally."""
        error_tracker = get_error_tracker()
        error_aggregator = get_error_aggregator()
        
        try:
            response = await call_next(request)
            return response
            
        except APIException as e:
            # Handle custom API exceptions
            error_tracker.log_error(e, {
                "request_path": str(request.url),
                "request_method": request.method,
                "user_agent": request.headers.get("user-agent"),
            })
            error_aggregator.record_error(e, {
                "path": str(request.url),
                "method": request.method,
            })
            
            return JSONResponse(
                status_code=e.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=e.error_code,
                    message=e.message,
                    status_code=e.status_code,
                    details=e.details,
                    correlation_id=e.correlation_id or error_tracker.get_correlation_id(),
                ),
                headers=self._get_error_headers(e),
            )
        
        except PydanticValidationError as e:
            # Handle Pydantic validation errors
            validation_error = ValidationError(
                message="Request validation failed",
                details={"validation_errors": e.errors()},
                correlation_id=error_tracker.get_correlation_id(),
            )
            
            error_tracker.log_error(validation_error, {
                "request_path": str(request.url),
                "request_method": request.method,
                "validation_errors": e.errors(),
            })
            error_aggregator.record_error(validation_error)
            
            return JSONResponse(
                status_code=validation_error.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=validation_error.error_code,
                    message=validation_error.message,
                    status_code=validation_error.status_code,
                    details=validation_error.details,
                    correlation_id=validation_error.correlation_id,
                ),
            )
        
        except ValueError as e:
            # Handle value errors as validation errors
            validation_error = ValidationError(
                message=str(e),
                correlation_id=error_tracker.get_correlation_id(),
            )
            
            error_tracker.log_error(validation_error, {
                "request_path": str(request.url),
                "request_method": request.method,
            })
            error_aggregator.record_error(validation_error)
            
            return JSONResponse(
                status_code=validation_error.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=validation_error.error_code,
                    message=validation_error.message,
                    status_code=validation_error.status_code,
                    details=validation_error.details,
                    correlation_id=validation_error.correlation_id,
                ),
            )
        
        except PermissionError as e:
            # Handle permission errors as forbidden
            forbidden_error = ForbiddenError(
                message=str(e),
                correlation_id=error_tracker.get_correlation_id(),
            )
            
            error_tracker.log_error(forbidden_error, {
                "request_path": str(request.url),
                "request_method": request.method,
            })
            error_aggregator.record_error(forbidden_error)
            
            return JSONResponse(
                status_code=forbidden_error.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=forbidden_error.error_code,
                    message=forbidden_error.message,
                    status_code=forbidden_error.status_code,
                    details=forbidden_error.details,
                    correlation_id=forbidden_error.correlation_id,
                ),
            )
        
        except FileNotFoundError as e:
            # Handle file not found errors
            not_found_error = NotFoundError(
                resource="file",
                identifier=str(e),
                correlation_id=error_tracker.get_correlation_id(),
            )
            
            error_tracker.log_error(not_found_error, {
                "request_path": str(request.url),
                "request_method": request.method,
            })
            error_aggregator.record_error(not_found_error)
            
            return JSONResponse(
                status_code=not_found_error.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=not_found_error.error_code,
                    message=not_found_error.message,
                    status_code=not_found_error.status_code,
                    details=not_found_error.details,
                    correlation_id=not_found_error.correlation_id,
                ),
            )
        
        except ConnectionError as e:
            # Handle connection errors as external service errors
            service_error = ExternalServiceError(
                service="external_service",
                message=str(e),
                correlation_id=error_tracker.get_correlation_id(),
            )
            
            error_tracker.log_error(service_error, {
                "request_path": str(request.url),
                "request_method": request.method,
            })
            error_aggregator.record_error(service_error)
            
            return JSONResponse(
                status_code=service_error.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=service_error.error_code,
                    message=service_error.message,
                    status_code=service_error.status_code,
                    details=service_error.details,
                    correlation_id=service_error.correlation_id,
                ),
            )
        
        except TimeoutError as e:
            # Handle timeout errors as service unavailable
            timeout_error = ServiceUnavailableError(
                message=f"Request timeout: {str(e)}",
                retry_after=30,
                correlation_id=error_tracker.get_correlation_id(),
            )
            
            error_tracker.log_error(timeout_error, {
                "request_path": str(request.url),
                "request_method": request.method,
            })
            error_aggregator.record_error(timeout_error)
            
            return JSONResponse(
                status_code=timeout_error.status_code,
                content=ErrorResponse.create_error_response(
                    error_code=timeout_error.error_code,
                    message=timeout_error.message,
                    status_code=timeout_error.status_code,
                    details=timeout_error.details,
                    correlation_id=timeout_error.correlation_id,
                ),
                headers={"Retry-After": "30"},
            )
        
        except Exception as e:
            # Handle all other exceptions as internal server errors
            correlation_id = error_tracker.get_correlation_id()
            
            # Log the full traceback for debugging
            logger.error(
                f"Unhandled exception: {str(e)}",
                extra={
                    "correlation_id": correlation_id,
                    "request_path": str(request.url),
                    "request_method": request.method,
                    "exception_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                }
            )
            
            error_aggregator.record_error(e, {
                "path": str(request.url),
                "method": request.method,
            })
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse.create_error_response(
                    error_code="INTERNAL_ERROR",
                    message="An internal server error occurred",
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    details={"error_type": type(e).__name__},
                    correlation_id=correlation_id,
                ),
            )
    
    def _get_error_headers(self, error: APIException) -> Dict[str, str]:
        """Get appropriate headers for error response."""
        headers = {}
        
        if isinstance(error, RateLimitExceededError):
            retry_after = error.details.get("retry_after")
            if retry_after:
                headers["Retry-After"] = str(retry_after)
        
        elif isinstance(error, ServiceUnavailableError):
            retry_after = error.details.get("retry_after")
            if retry_after:
                headers["Retry-After"] = str(retry_after)
        
        elif isinstance(error, CircuitBreakerOpenError):
            retry_after = error.details.get("retry_after")
            if retry_after:
                headers["Retry-After"] = str(retry_after)
        
        return headers