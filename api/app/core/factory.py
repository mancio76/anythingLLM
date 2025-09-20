"""FastAPI application factory with dependency injection and lifecycle management."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.container import Container, get_container, set_container
from app.core.database import DatabaseManager
from app.core.logging import setup_logging
from app.core.metrics import get_metrics_collector
from app.core.migrations import get_migration_manager
from app.core.documentation import custom_openapi
from app.core.versioning import VersioningMiddleware, get_version_manager
from app.middleware import (
    AuthenticationMiddleware,
    GlobalExceptionHandler,
    LoggingMiddleware,
    MetricsMiddleware,
    RateLimitingMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import auth, documents, docs, health, questions, workspaces

logger = logging.getLogger(__name__)


class ApplicationFactory:
    """Factory for creating and configuring FastAPI applications."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize application factory.
        
        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self.container: Optional[Container] = None
        self.db_manager: Optional[DatabaseManager] = None
    
    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """Application lifespan manager with startup and shutdown logic."""
        logger.info("Starting application startup sequence...")
        
        try:
            # Setup logging first
            setup_logging(self.settings)
            logger.info("Logging configured")
            
            # Initialize dependency injection container
            self.container = Container(self.settings)
            set_container(self.container)
            logger.info("Dependency injection container initialized")
            
            # Initialize database connections
            self.db_manager = self.container.db_manager
            await self.db_manager.init_db(self.settings)
            logger.info("Database connections established")
            
            # Run database migrations
            await self._run_migrations()
            
            # Initialize metrics
            metrics = get_metrics_collector()
            metrics.set_app_info(
                version=self.settings.api_version,
                environment=getattr(self.settings, 'environment', 'production')
            )
            logger.info("Metrics collector initialized")
            
            # Validate external service connections
            await self._validate_external_services()
            
            logger.info("Application startup completed successfully")
            
            yield
            
        except Exception as e:
            logger.error(f"Application startup failed: {e}")
            raise
        finally:
            # Cleanup during shutdown
            logger.info("Starting application shutdown sequence...")
            
            try:
                if self.db_manager:
                    await self.db_manager.close_db()
                    logger.info("Database connections closed")
                
                logger.info("Application shutdown completed successfully")
                
            except Exception as e:
                logger.error(f"Error during application shutdown: {e}")
    
    async def _run_migrations(self) -> None:
        """Run database migrations on startup."""
        try:
            logger.info("Running database migrations...")
            migration_manager = get_migration_manager(self.settings)
            
            if self.db_manager and self.db_manager.engine:
                success = await migration_manager.run_migrations(self.db_manager.engine)
                if success:
                    logger.info("Database migrations completed successfully")
                else:
                    logger.error("Database migrations failed")
                    raise RuntimeError("Database migrations failed")
            else:
                logger.error("Database engine not available for migrations")
                raise RuntimeError("Database engine not available for migrations")
                
        except Exception as e:
            logger.error(f"Migration execution failed: {e}")
            raise
    
    async def _validate_external_services(self) -> None:
        """Validate connections to external services."""
        try:
            logger.info("Validating external service connections...")
            
            # Validate AnythingLLM connection
            anythingllm_client = self.container.anythingllm_client
            health_status = await anythingllm_client.health_check()
            
            if health_status.is_healthy:
                logger.info("AnythingLLM service connection validated")
            else:
                logger.warning(f"AnythingLLM service health check failed: {health_status.message}")
                # Don't fail startup for external service issues, just log warning
            
            # Validate storage client
            storage_client = self.container.storage_client
            # Storage client validation would depend on implementation
            logger.info("Storage client initialized")
            
        except Exception as e:
            logger.warning(f"External service validation failed: {e}")
            # Don't fail startup for external service issues
    
    def create_app(self) -> FastAPI:
        """Create and configure FastAPI application.
        
        Returns:
            Configured FastAPI application
        """
        logger.info("Creating FastAPI application...")
        
        app = FastAPI(
            title=self.settings.api_title,
            version=self.settings.api_version,
            description=self._get_api_description(),
            lifespan=self.lifespan,
            contact={
                "name": "AnythingLLM API Support",
                "email": "support@example.com",
            },
            license_info={
                "name": "MIT License",
                "url": "https://opensource.org/licenses/MIT",
            },
            servers=self._get_server_config(),
            openapi_tags=self._get_openapi_tags(),
            openapi_url=f"{self.settings.api_prefix}/openapi.json",
            docs_url=f"{self.settings.api_prefix}/docs",
            redoc_url=f"{self.settings.api_prefix}/redoc",
        )
        
        # Configure middleware stack (order matters - last added is executed first)
        self._configure_middleware(app)
        
        # Set custom OpenAPI schema
        app.openapi = lambda: custom_openapi(app)
        
        # Include routers
        self._include_routers(app)
        
        logger.info("FastAPI application created and configured")
        return app
    
    def _configure_middleware(self, app: FastAPI) -> None:
        """Configure middleware stack in proper order.
        
        Args:
            app: FastAPI application
        """
        logger.info("Configuring middleware stack...")
        
        # CORS middleware (outermost)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Security headers middleware
        app.add_middleware(SecurityHeadersMiddleware)
        
        # Global exception handler (should be early in the stack)
        app.add_middleware(GlobalExceptionHandler)
        
        # Logging middleware
        app.add_middleware(LoggingMiddleware)
        
        # Metrics middleware
        app.add_middleware(MetricsMiddleware)
        
        # Rate limiting middleware
        if self.settings.rate_limit_enabled:
            app.add_middleware(
                RateLimitingMiddleware,
                requests_per_window=self.settings.rate_limit_requests,
                window_seconds=self.settings.rate_limit_window,
            )
        
        # Authentication middleware (innermost, closest to route handlers)
        app.add_middleware(AuthenticationMiddleware)
        
        # Versioning middleware
        app.add_middleware(VersioningMiddleware, version_manager=get_version_manager())
        
        logger.info("Middleware stack configured")
    
    def _include_routers(self, app: FastAPI) -> None:
        """Include API routers.
        
        Args:
            app: FastAPI application
        """
        logger.info("Including API routers...")
        
        routers = [
            (auth.router, "Authentication"),
            (health.router, "Health monitoring"),
            (documents.router, "Document processing"),
            (questions.router, "Question processing"),
            (workspaces.router, "Workspace management"),
            (docs.router, "API documentation"),
        ]
        
        for router, description in routers:
            app.include_router(router, prefix=self.settings.api_prefix)
            logger.debug(f"Included {description} router")
        
        logger.info("All API routers included")
    
    def _get_api_description(self) -> str:
        """Get API description."""
        return """
# AnythingLLM API Service

A cloud-native REST API service for document processing, workspace management, and automated question-answer testing against AnythingLLM instances. Specifically designed for procurement and contract document analysis.

## Features

- **Document Processing**: Upload and process ZIP files containing PDF, JSON, or CSV documents
- **Workspace Management**: Create and manage AnythingLLM workspaces with procurement-specific configuration
- **Question Processing**: Execute automated question sets with confidence scoring and multiple LLM model support
- **Job Management**: Track long-running operations with detailed progress and status information
- **Health Monitoring**: Comprehensive health checks and metrics for production deployment

## Authentication

This API supports multiple authentication methods:

- **JWT Bearer Tokens**: Include `Authorization: Bearer <token>` header
- **API Keys**: Include `X-API-Key: <key>` header (configurable)

## Rate Limiting

API requests are rate-limited to prevent abuse:
- Default: 100 requests per hour per user/IP
- Rate limits are configurable via environment variables
- Rate limit headers are included in responses

## Error Handling

All errors follow a consistent format with:
- HTTP status codes following REST standards
- Structured error responses with correlation IDs
- Detailed validation error messages
- Retry-after headers for rate limiting

## Supported File Types

- **PDF**: Portable Document Format files
- **JSON**: JavaScript Object Notation files
- **CSV**: Comma-Separated Values files

## LLM Model Support

- **OpenAI**: GPT-3.5, GPT-4, and other OpenAI models
- **Ollama**: Local deployment models
- **Anthropic**: Claude variants and other Anthropic models
        """
    
    def _get_server_config(self) -> list:
        """Get server configuration."""
        return [
            {
                "url": f"http://{self.settings.host}:{self.settings.port}",
                "description": "Development server"
            },
            {
                "url": "https://api.example.com",
                "description": "Production server"
            }
        ]
    
    def _get_openapi_tags(self) -> list:
        """Get OpenAPI tags."""
        return [
            {
                "name": "documents",
                "description": "Document upload and processing operations. Handle ZIP files containing PDF, JSON, or CSV documents with background processing and job tracking."
            },
            {
                "name": "workspaces",
                "description": "Workspace management operations. Create, configure, and manage AnythingLLM workspaces with procurement-specific settings."
            },
            {
                "name": "questions",
                "description": "Question processing operations. Execute automated question sets against workspaces with multiple LLM models and confidence scoring."
            },
            {
                "name": "health",
                "description": "Health monitoring and metrics endpoints. Check service status, dependencies, and system resources."
            },
            {
                "name": "authentication",
                "description": "Authentication and authorization operations. Manage API access tokens and user sessions."
            }
        ]


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create FastAPI application using the factory.
    
    Args:
        settings: Optional application settings
        
    Returns:
        Configured FastAPI application
    """
    factory = ApplicationFactory(settings)
    return factory.create_app()