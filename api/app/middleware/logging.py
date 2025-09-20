"""Request/response logging middleware with correlation IDs and data sanitization."""

import time
import uuid
import logging
from typing import Callable, Dict, Any, Union

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.error_tracking import get_error_tracker

logger = logging.getLogger(__name__)


class DataSanitizer:
    """Utility class for sanitizing sensitive data in logs."""
    
    # Sensitive field patterns (case-insensitive)
    SENSITIVE_PATTERNS = {
        "password", "passwd", "pwd", "secret", "key", "token", "auth", 
        "authorization", "credential", "api_key", "apikey", "access_key",
        "private_key", "session", "cookie", "jwt", "bearer", "signature",
        "hash", "salt", "nonce", "otp", "pin", "ssn", "social_security",
        "credit_card", "card_number", "cvv", "cvc", "expiry"
    }
    
    @classmethod
    def sanitize_data(cls, data: Union[Dict[str, Any], str, Any]) -> Union[Dict[str, Any], str, Any]:
        """Sanitize sensitive data for logging.
        
        Args:
            data: Data to sanitize
            
        Returns:
            Sanitized data with sensitive fields redacted
        """
        settings = get_settings()
        
        # Skip sanitization if disabled
        if not settings.log_sanitize_sensitive:
            return data
        
        if isinstance(data, dict):
            return cls._sanitize_dict(data)
        elif isinstance(data, str):
            return cls._sanitize_string(data)
        elif isinstance(data, (list, tuple)):
            return [cls.sanitize_data(item) for item in data]
        else:
            return data
    
    @classmethod
    def _sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize dictionary data.
        
        Args:
            data: Dictionary to sanitize
            
        Returns:
            Sanitized dictionary
        """
        sanitized = {}
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Check if key contains sensitive patterns
            if any(pattern in key_lower for pattern in cls.SENSITIVE_PATTERNS):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = cls._sanitize_dict(value)
            elif isinstance(value, (list, tuple)):
                sanitized[key] = [cls.sanitize_data(item) for item in value]
            else:
                sanitized[key] = value
        
        return sanitized
    
    @classmethod
    def _sanitize_string(cls, data: str) -> str:
        """Sanitize string data (basic pattern matching).
        
        Args:
            data: String to sanitize
            
        Returns:
            Sanitized string
        """
        # For now, just return the string as-is
        # In a more sophisticated implementation, you could use regex
        # to find and redact sensitive patterns within strings
        return data


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request/response logging with data sanitization."""
    
    def __init__(self, app):
        """Initialize logging middleware.
        
        Args:
            app: FastAPI application
        """
        super().__init__(app)
        self.sanitizer = DataSanitizer()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        
        # Generate correlation ID
        correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        
        # Set correlation ID in error tracker context
        error_tracker = get_error_tracker()
        error_tracker.set_correlation_id(correlation_id)
        error_tracker.set_request_id(str(uuid.uuid4()))
        
        # Start timing
        start_time = time.time()
        
        # Log request
        await self._log_request(request, correlation_id)
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log response
            await self._log_response(request, response, correlation_id, process_time)
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            
            # Log error with error tracker
            error_tracker.log_error(
                e,
                context={
                    "method": request.method,
                    "url": str(request.url),
                    "process_time": process_time,
                }
            )
            
            raise
    
    async def _log_request(self, request: Request, correlation_id: str) -> None:
        """Log incoming request details with data sanitization."""
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Get user agent
        user_agent = request.headers.get("user-agent", "")
        
        # Get user info if available
        user_info = {}
        if hasattr(request.state, "user") and request.state.user:
            user_info = {
                "user_id": request.state.user.id,
                "username": request.state.user.username,
            }
        
        # Sanitize headers
        headers = dict(request.headers)
        sanitized_headers = self.sanitizer.sanitize_data(headers)
        
        # Sanitize query parameters
        query_params = dict(request.query_params)
        sanitized_query_params = self.sanitizer.sanitize_data(query_params)
        
        # Prepare log data
        log_data = {
            "correlation_id": correlation_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": sanitized_query_params,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "content_type": request.headers.get("content-type"),
            "content_length": request.headers.get("content-length"),
            "headers": sanitized_headers,
            **user_info
        }
        
        # Log request
        logger.info("Incoming request", extra=log_data)
    
    async def _log_response(
        self, 
        request: Request, 
        response: Response, 
        correlation_id: str, 
        process_time: float
    ) -> None:
        """Log outgoing response details with data sanitization."""
        
        # Get user info if available
        user_info = {}
        if hasattr(request.state, "user") and request.state.user:
            user_info = {
                "user_id": request.state.user.id,
                "username": request.state.user.username,
            }
        
        # Sanitize response headers
        response_headers = dict(response.headers)
        sanitized_response_headers = self.sanitizer.sanitize_data(response_headers)
        
        # Prepare log data
        log_data = {
            "correlation_id": correlation_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "status_code": response.status_code,
            "process_time": process_time,
            "response_size": response.headers.get("content-length"),
            "response_headers": sanitized_response_headers,
            **user_info
        }
        
        logger.info("Request completed", extra=log_data)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request."""
        
        # Check for forwarded headers (common in load balancers/proxies)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"