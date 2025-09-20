"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.core.logging import setup_logging
from app.core.metrics import get_metrics_collector
from app.middleware import (
    AuthenticationMiddleware,
    GlobalExceptionHandler,
    LoggingMiddleware,
    MetricsMiddleware,
    RateLimitingMiddleware,
    SecurityHeadersMiddleware,
)
from app.routers import auth, documents, health, questions, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    
    # Setup logging
    setup_logging(settings)
    
    # Initialize database
    await init_db(settings)
    
    # Initialize metrics
    metrics = get_metrics_collector()
    metrics.set_app_info(
        version=settings.api_version,
        environment="production"  # Could be made configurable
    )
    
    yield
    
    # Cleanup
    await close_db()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="AnythingLLM API service for document processing and workspace management",
        lifespan=lifespan,
    )
    
    # Add middleware (order matters - last added is executed first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GlobalExceptionHandler)  # Error handling should be early in the stack
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        RateLimitingMiddleware,
        requests_per_window=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window,
    )
    app.add_middleware(AuthenticationMiddleware)
    
    # Include routers
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(documents.router, prefix=settings.api_prefix)
    app.include_router(questions.router, prefix=settings.api_prefix)
    app.include_router(workspaces.router, prefix=settings.api_prefix)
    app.include_router(health.router, prefix=settings.api_prefix)
    
    return app


app = create_app()