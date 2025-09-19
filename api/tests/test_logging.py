"""Test logging configuration and functionality."""

import json
import logging
from io import StringIO

import pytest

from app.core.logging import (
    SensitiveDataSanitizer,
    JSONFormatter,
    TextFormatter,
    setup_logging,
    get_logger
)
from app.core.config import Settings, LogFormat


class TestSensitiveDataSanitizer:
    """Test sensitive data sanitization."""
    
    def test_sanitize_sensitive_fields(self):
        """Test that sensitive fields are sanitized."""
        sanitizer = SensitiveDataSanitizer()
        
        data = {
            "username": "testuser",
            "password": "secret123",
            "api_key": "abc123",
            "token": "xyz789",
            "normal_field": "normal_value"
        }
        
        sanitized = sanitizer.sanitize_dict(data)
        
        assert sanitized["username"] == "testuser"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["api_key"] == "[REDACTED]"
        assert sanitized["token"] == "[REDACTED]"
        assert sanitized["normal_field"] == "normal_value"
    
    def test_sanitize_nested_dict(self):
        """Test sanitization of nested dictionaries."""
        sanitizer = SensitiveDataSanitizer()
        
        data = {
            "user": {
                "name": "testuser",
                "credentials": {
                    "password": "secret123",
                    "api_key": "abc123"
                }
            },
            "config": {
                "database_url": "postgresql://user:pass@host/db",
                "timeout": 30
            }
        }
        
        sanitized = sanitizer.sanitize_dict(data)
        
        assert sanitized["user"]["name"] == "testuser"
        assert sanitized["user"]["credentials"]["password"] == "[REDACTED]"
        assert sanitized["user"]["credentials"]["api_key"] == "[REDACTED]"
        assert sanitized["config"]["timeout"] == 30
    
    def test_sanitize_list_with_dicts(self):
        """Test sanitization of lists containing dictionaries."""
        sanitizer = SensitiveDataSanitizer()
        
        data = {
            "users": [
                {"name": "user1", "password": "secret1"},
                {"name": "user2", "api_key": "key2"}
            ]
        }
        
        sanitized = sanitizer.sanitize_dict(data)
        
        assert sanitized["users"][0]["name"] == "user1"
        assert sanitized["users"][0]["password"] == "[REDACTED]"
        assert sanitized["users"][1]["name"] == "user2"
        assert sanitized["users"][1]["api_key"] == "[REDACTED]"


class TestJSONFormatter:
    """Test JSON log formatter."""
    
    def test_json_format_basic(self):
        """Test basic JSON formatting."""
        formatter = JSONFormatter(sanitize_sensitive=False)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        data = json.loads(formatted)
        
        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert data["module"] == "file"
        assert data["line"] == 42
        assert "timestamp" in data
    
    def test_json_format_with_sanitization(self):
        """Test JSON formatting with sensitive data sanitization."""
        formatter = JSONFormatter(sanitize_sensitive=True)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        # Add sensitive data to record
        record.password = "secret123"
        record.normal_field = "normal_value"
        
        formatted = formatter.format(record)
        data = json.loads(formatted)
        
        assert data["extra"]["password"] == "[REDACTED]"
        assert data["extra"]["normal_field"] == "normal_value"


class TestTextFormatter:
    """Test text log formatter."""
    
    def test_text_format_basic(self):
        """Test basic text formatting."""
        formatter = TextFormatter(sanitize_sensitive=False)
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        
        assert "INFO" in formatted
        assert "test.logger" in formatted
        assert "Test message" in formatted


class TestLoggingSetup:
    """Test logging setup and configuration."""
    
    def test_setup_logging_json_format(self, mock_env_vars):
        """Test logging setup with JSON format."""
        settings = Settings(log_format=LogFormat.JSON, log_level="DEBUG")
        
        # Capture the root logger before setup
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        
        try:
            setup_logging(settings)
            
            # Check that logger level is set correctly
            assert root_logger.level == logging.DEBUG
            
            # Check that handlers were added
            assert len(root_logger.handlers) > 0
            
            # Check that the formatter is JSONFormatter
            handler = root_logger.handlers[0]
            assert isinstance(handler.formatter, JSONFormatter)
            
        finally:
            # Restore original handlers
            root_logger.handlers = original_handlers
    
    def test_setup_logging_text_format(self, mock_env_vars):
        """Test logging setup with text format."""
        settings = Settings(log_format=LogFormat.TEXT, log_level="INFO")
        
        # Capture the root logger before setup
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        
        try:
            setup_logging(settings)
            
            # Check that logger level is set correctly
            assert root_logger.level == logging.INFO
            
            # Check that the formatter is TextFormatter
            handler = root_logger.handlers[0]
            assert isinstance(handler.formatter, TextFormatter)
            
        finally:
            # Restore original handlers
            root_logger.handlers = original_handlers
    
    def test_get_logger(self):
        """Test logger creation."""
        logger = get_logger("test.module")
        
        assert logger.name == "test.module"
        assert isinstance(logger, logging.Logger)