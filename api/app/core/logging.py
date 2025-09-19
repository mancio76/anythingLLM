"""Structured logging configuration with sensitive data sanitization."""

import json
import logging
import logging.config
import sys
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.core.config import Settings, LogFormat


class SensitiveDataSanitizer:
    """Sanitizes sensitive data from log records."""
    
    SENSITIVE_FIELDS = {
        "password", "api_key", "secret", "token", "authorization", 
        "jwt", "bearer", "key", "credential", "auth", "session"
    }
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize dictionary data."""
        if not isinstance(data, dict):
            return data
            
        sanitized = {}
        for key, value in data.items():
            if self._is_sensitive_field(key):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized
    
    def _is_sensitive_field(self, field_name: str) -> bool:
        """Check if field name contains sensitive information."""
        field_lower = field_name.lower()
        return any(sensitive in field_lower for sensitive in self.SENSITIVE_FIELDS)


class JSONFormatter(logging.Formatter):
    """JSON log formatter with structured output."""
    
    def __init__(self, sanitize_sensitive: bool = True):
        super().__init__()
        self.sanitizer = SensitiveDataSanitizer() if sanitize_sensitive else None
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception information if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        extra_fields = {
            key: value for key, value in record.__dict__.items()
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "lineno", "funcName", "created",
                "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "getMessage", "exc_info",
                "exc_text", "stack_info"
            }
        }
        
        if extra_fields:
            log_data["extra"] = extra_fields
        
        # Sanitize sensitive data if enabled
        if self.sanitizer:
            log_data = self.sanitizer.sanitize_dict(log_data)
        
        return json.dumps(log_data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Text log formatter with sensitive data sanitization."""
    
    def __init__(self, sanitize_sensitive: bool = True):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        self.sanitizer = SensitiveDataSanitizer() if sanitize_sensitive else None
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as text with sanitization."""
        if self.sanitizer and hasattr(record, '__dict__'):
            # Create a copy of the record to avoid modifying the original
            record_dict = record.__dict__.copy()
            sanitized_dict = self.sanitizer.sanitize_dict(record_dict)
            
            # Update the record with sanitized data
            for key, value in sanitized_dict.items():
                setattr(record, key, value)
        
        return super().format(record)


def setup_logging(settings: Settings) -> None:
    """Setup application logging configuration."""
    
    # Determine formatter based on settings
    if settings.log_format == LogFormat.JSON:
        formatter = JSONFormatter(sanitize_sensitive=settings.log_sanitize_sensitive)
    else:
        formatter = TextFormatter(sanitize_sensitive=settings.log_sanitize_sensitive)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    configure_logger_levels(settings)


def configure_logger_levels(settings: Settings) -> None:
    """Configure specific logger levels."""
    
    # Set application logger level
    app_logger = logging.getLogger("app")
    app_logger.setLevel(getattr(logging, settings.log_level.upper()))
    
    # Configure third-party library loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    
    # Reduce noise from HTTP libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the specified name."""
    return logging.getLogger(name)