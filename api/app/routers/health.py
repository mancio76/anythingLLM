"""Health check endpoints."""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.database import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"


class DetailedHealthResponse(BaseModel):
    """Detailed health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"
    services: Dict[str, Any]


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    from datetime import datetime
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


@router.get("/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check(redis_client=Depends(get_redis)):
    """Detailed health check with dependency verification."""
    from datetime import datetime
    
    services = {}
    overall_status = "healthy"
    
    # Check Redis if enabled
    if redis_client:
        try:
            await redis_client.ping()
            services["redis"] = {"status": "healthy", "message": "Connection successful"}
        except Exception as e:
            services["redis"] = {"status": "unhealthy", "message": str(e)}
            overall_status = "degraded"
    else:
        services["redis"] = {"status": "disabled", "message": "Redis not configured"}
    
    # TODO: Add database health check in future tasks
    services["database"] = {"status": "pending", "message": "Health check not implemented yet"}
    
    # TODO: Add AnythingLLM health check in future tasks
    services["anythingllm"] = {"status": "pending", "message": "Health check not implemented yet"}
    
    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        services=services
    )