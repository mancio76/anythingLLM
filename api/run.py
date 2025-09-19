"""Application startup script."""

import uvicorn
from app.core.config import get_settings


def main():
    """Run the FastAPI application."""
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=False,  # Set to True for development
        log_config=None,  # Use our custom logging configuration
    )


if __name__ == "__main__":
    main()