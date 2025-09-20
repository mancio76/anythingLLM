"""FastAPI application entry point with dependency injection and lifecycle management."""

from app.core.factory import create_app

# Create the FastAPI application using the factory
app = create_app()