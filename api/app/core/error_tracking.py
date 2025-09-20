"""Error correlation and tracking system."""

import logging
import time
from contextvars import ContextVar
from typing import Any, Dict, Optional
from uuid import uuid4

from app.core.exceptions import APIException


# Context variables for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)


class ErrorTracker:
    """Error tracking and correlation system."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current context."""
        correlation_id_var.set(correlation_id)
    
    def set_request_id(self, request_id: str):
        """Set request ID for current context."""
        request_id_var.set(request_id)
    
    def set_user_id(self, user_id: str):
        """Set user ID for current context."""
        user_id_var.set(user_id)
    
    def get_correlation_id(self) -> Optional[str]:
        """Get correlation ID from current context."""
        return correlation_id_var.get()
    
    def get_request_id(self) -> Optional[str]:
        """Get request ID from current context."""
        return request_id_var.get()
    
    def get_user_id(self) -> Optional[str]:
        """Get user ID from current context."""
        return user_id_var.get()
    
    def generate_correlation_id(self) -> str:
        """Generate a new correlation ID."""
        correlation_id = str(uuid4())
        self.set_correlation_id(correlation_id)
        return correlation_id
    
    def get_context_data(self) -> Dict[str, Any]:
        """Get all context data for logging."""
        return {
            "correlation_id": self.get_correlation_id(),
            "request_id": self.get_request_id(),
            "user_id": self.get_user_id(),
            "timestamp": time.time(),
        }
    
    def log_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        level: int = logging.ERROR,
    ):
        """Log an error with correlation data."""
        error_data = self.get_context_data()
        
        if context:
            error_data.update(context)
        
        # Add error-specific data
        error_data.update({
            "error_type": type(error).__name__,
            "error_message": str(error),
        })
        
        # Add API exception specific data
        if isinstance(error, APIException):
            error_data.update({
                "status_code": error.status_code,
                "error_code": error.error_code,
                "error_details": error.details,
                "error_correlation_id": error.correlation_id,
            })
        
        self.logger.log(level, f"Error occurred: {error}", extra=error_data)
    
    def log_warning(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Log a warning with correlation data."""
        warning_data = self.get_context_data()
        
        if context:
            warning_data.update(context)
        
        self.logger.warning(message, extra=warning_data)
    
    def log_info(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Log info with correlation data."""
        info_data = self.get_context_data()
        
        if context:
            info_data.update(context)
        
        self.logger.info(message, extra=info_data)
    
    def log_debug(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Log debug with correlation data."""
        debug_data = self.get_context_data()
        
        if context:
            debug_data.update(context)
        
        self.logger.debug(message, extra=debug_data)


class ErrorAggregator:
    """Aggregate and analyze error patterns."""
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.error_patterns: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    def record_error(self, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Record an error for pattern analysis."""
        error_key = f"{type(error).__name__}:{str(error)}"
        
        # Increment error count
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Update error pattern data
        if error_key not in self.error_patterns:
            self.error_patterns[error_key] = {
                "first_seen": time.time(),
                "last_seen": time.time(),
                "count": 1,
                "contexts": [],
            }
        else:
            self.error_patterns[error_key]["last_seen"] = time.time()
            self.error_patterns[error_key]["count"] = self.error_counts[error_key]
        
        # Store context data (limit to prevent memory issues)
        if context and len(self.error_patterns[error_key]["contexts"]) < 10:
            self.error_patterns[error_key]["contexts"].append({
                "timestamp": time.time(),
                "context": context,
            })
        
        # Alert on high error rates
        if self.error_counts[error_key] % 10 == 0:  # Every 10 occurrences
            self.logger.warning(
                f"High error rate detected: {error_key} occurred {self.error_counts[error_key]} times",
                extra={
                    "error_key": error_key,
                    "count": self.error_counts[error_key],
                    "pattern": self.error_patterns[error_key],
                }
            )
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics."""
        return {
            "total_errors": sum(self.error_counts.values()),
            "unique_errors": len(self.error_counts),
            "top_errors": sorted(
                self.error_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "error_patterns": self.error_patterns,
        }
    
    def reset_stats(self):
        """Reset error statistics."""
        self.error_counts.clear()
        self.error_patterns.clear()


# Global instances
error_tracker = ErrorTracker()
error_aggregator = ErrorAggregator()


def get_error_tracker() -> ErrorTracker:
    """Get the global error tracker."""
    return error_tracker


def get_error_aggregator() -> ErrorAggregator:
    """Get the global error aggregator."""
    return error_aggregator