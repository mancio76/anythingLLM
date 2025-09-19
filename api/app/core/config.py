"""Application configuration with Pydantic settings."""

import os
from functools import lru_cache
from typing import List, Optional
from enum import Enum

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class StorageType(str, Enum):
    """Storage backend types."""
    LOCAL = "local"
    S3 = "s3"


class LogFormat(str, Enum):
    """Log format types."""
    JSON = "json"
    TEXT = "text"


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Configuration
    api_title: str = Field("AnythingLLM API", env="API_TITLE")
    api_version: str = Field("1.0.0", env="API_VERSION")
    api_prefix: str = Field("/api/v1", env="API_PREFIX")
    
    # Server Configuration
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")
    workers: int = Field(1, env="WORKERS")
    
    # CORS Configuration
    cors_origins: List[str] = Field(["*"], env="CORS_ORIGINS")
    
    # Database Configuration (PostgreSQL required)
    database_url: str = Field(..., env="DATABASE_URL", description="PostgreSQL connection string")
    database_pool_size: int = Field(10, env="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(20, env="DATABASE_MAX_OVERFLOW")
    
    # Redis Configuration (optional)
    redis_enabled: bool = Field(False, env="REDIS_ENABLED")
    redis_url: Optional[str] = Field(None, env="REDIS_URL")
    redis_pool_size: int = Field(10, env="REDIS_POOL_SIZE")
    
    # AnythingLLM Configuration
    anythingllm_url: str = Field(..., env="ANYTHINGLLM_URL")
    anythingllm_api_key: str = Field(..., env="ANYTHINGLLM_API_KEY")
    anythingllm_timeout: int = Field(30, env="ANYTHINGLLM_TIMEOUT")
    
    # File Storage Configuration
    storage_type: StorageType = Field(StorageType.LOCAL, env="STORAGE_TYPE")
    storage_path: str = Field("/tmp/anythingllm-api", env="STORAGE_PATH")
    
    # S3 Configuration (when storage_type=S3)
    s3_bucket: Optional[str] = Field(None, env="S3_BUCKET")
    s3_region: Optional[str] = Field(None, env="S3_REGION")
    aws_access_key_id: Optional[str] = Field(None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(None, env="AWS_SECRET_ACCESS_KEY")
    
    # File Processing Configuration
    max_file_size: int = Field(100 * 1024 * 1024, env="MAX_FILE_SIZE")  # 100MB
    allowed_file_types: List[str] = Field(["pdf", "json", "csv"], env="ALLOWED_FILE_TYPES")
    
    # Security Configuration
    secret_key: str = Field(..., env="SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(60, env="JWT_EXPIRE_MINUTES")
    api_key_header: str = Field("X-API-Key", env="API_KEY_HEADER")
    
    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(True, env="RATE_LIMIT_ENABLED")
    rate_limit_requests: int = Field(100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(3600, env="RATE_LIMIT_WINDOW")  # 1 hour
    
    # Logging Configuration
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_format: LogFormat = Field(LogFormat.JSON, env="LOG_FORMAT")
    log_sanitize_sensitive: bool = Field(True, env="LOG_SANITIZE_SENSITIVE")
    
    # Job Management Configuration
    job_cleanup_days: int = Field(7, env="JOB_CLEANUP_DAYS")
    max_concurrent_jobs: int = Field(5, env="MAX_CONCURRENT_JOBS")
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        case_sensitive = False
        
    @field_validator("database_url")
    @classmethod
    def validate_postgresql_url(cls, v):
        """Validate PostgreSQL connection string."""
        if not v.startswith(("postgresql://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        return v
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def parse_allowed_file_types(cls, v):
        """Parse allowed file types from string or list."""
        if isinstance(v, str):
            return [file_type.strip().lower() for file_type in v.split(",")]
        return [file_type.lower() for file_type in v]
    
    @model_validator(mode="after")
    def validate_interdependent_fields(self):
        """Validate fields that depend on other fields."""
        # Validate S3 configuration
        if self.storage_type == StorageType.S3:
            if not self.s3_bucket:
                raise ValueError("s3_bucket is required when storage_type is S3")
            if not self.s3_region:
                raise ValueError("s3_region is required when storage_type is S3")
        
        # Validate Redis configuration
        if self.redis_enabled and not self.redis_url:
            raise ValueError("redis_url is required when redis_enabled is True")
        
        return self


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()