"""Test configuration management."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, StorageType, LogFormat


class TestSettings:
    """Test application settings."""
    
    def test_default_settings(self, mock_env_vars):
        """Test settings with default values."""
        settings = Settings()
        
        assert settings.api_title == "AnythingLLM API"
        assert settings.api_version == "1.0.0"
        assert settings.api_prefix == "/api/v1"
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.storage_type == StorageType.LOCAL
        assert settings.log_format == LogFormat.JSON
    
    def test_required_fields_validation(self):
        """Test that required fields raise validation errors."""
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        
        errors = exc_info.value.errors()
        required_fields = {"database_url", "anythingllm_url", "anythingllm_api_key", "secret_key"}
        
        error_fields = {error["loc"][0] for error in errors if error["type"] == "missing"}
        assert required_fields.issubset(error_fields)
    
    def test_database_url_validation(self, mock_env_vars):
        """Test database URL validation."""
        # Valid PostgreSQL URL
        settings = Settings(database_url="postgresql+asyncpg://user:pass@host:5432/db")
        assert settings.database_url == "postgresql+asyncpg://user:pass@host:5432/db"
        
        # Invalid URL should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                database_url="mysql://user:pass@host:3306/db",
                anythingllm_url="http://localhost:3001",
                anythingllm_api_key="test-key",
                secret_key="test-secret"
            )
        
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("database_url",) for error in errors)
    
    def test_cors_origins_parsing(self, mock_env_vars):
        """Test CORS origins parsing from string."""
        # Test string parsing
        settings = Settings(cors_origins="http://localhost:3000,https://example.com")
        assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]
        
        # Test list input
        settings = Settings(cors_origins=["http://localhost:3000", "https://example.com"])
        assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]
    
    def test_allowed_file_types_parsing(self, mock_env_vars):
        """Test allowed file types parsing from string."""
        # Test string parsing
        settings = Settings(allowed_file_types="PDF,JSON,CSV")
        assert settings.allowed_file_types == ["pdf", "json", "csv"]
        
        # Test list input
        settings = Settings(allowed_file_types=["PDF", "JSON", "CSV"])
        assert settings.allowed_file_types == ["pdf", "json", "csv"]
    
    def test_s3_storage_validation(self, mock_env_vars):
        """Test S3 storage configuration validation."""
        # S3 storage without required fields should fail
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                storage_type=StorageType.S3,
                # Missing s3_bucket and s3_region
            )
        
        errors = exc_info.value.errors()
        error_messages = [error["msg"] for error in errors]
        assert any("s3_bucket is required when storage_type is S3" in msg for msg in error_messages)
        assert any("s3_region is required when storage_type is S3" in msg for msg in error_messages)
        
        # Valid S3 configuration should work
        settings = Settings(
            storage_type=StorageType.S3,
            s3_bucket="test-bucket",
            s3_region="us-east-1"
        )
        assert settings.storage_type == StorageType.S3
        assert settings.s3_bucket == "test-bucket"
        assert settings.s3_region == "us-east-1"
    
    def test_redis_validation(self, mock_env_vars):
        """Test Redis configuration validation."""
        # Redis enabled without URL should fail
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                redis_enabled=True,
                # Missing redis_url
            )
        
        errors = exc_info.value.errors()
        error_messages = [error["msg"] for error in errors]
        assert any("redis_url is required when redis_enabled is True" in msg for msg in error_messages)
        
        # Valid Redis configuration should work
        settings = Settings(
            redis_enabled=True,
            redis_url="redis://localhost:6379/0"
        )
        assert settings.redis_enabled is True
        assert settings.redis_url == "redis://localhost:6379/0"
    
    def test_environment_variable_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        monkeypatch.setenv("API_TITLE", "Custom API Title")
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
        monkeypatch.setenv("ANYTHINGLLM_URL", "http://localhost:3001")
        monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        
        settings = Settings()
        
        assert settings.api_title == "Custom API Title"
        assert settings.port == 9000
        assert settings.log_level == "DEBUG"