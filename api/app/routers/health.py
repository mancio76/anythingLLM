"""Health check endpoints."""

import logging
import time
import psutil
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_redis, get_db_session, db_manager
from app.core.config import get_settings
from app.core.metrics import get_metrics_collector
from app.core.error_tracking import get_error_aggregator
from app.core.graceful_degradation import get_degradation_manager
from app.core.circuit_breaker import circuit_breaker_registry
from app.integrations.anythingllm_client import AnythingLLMClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"


class ServiceHealth(BaseModel):
    """Individual service health status."""
    status: str
    message: str
    response_time_ms: float = 0.0
    details: Dict[str, Any] = {}


class DetailedHealthResponse(BaseModel):
    """Detailed health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"
    services: Dict[str, ServiceHealth]
    system: Dict[str, Any]
    resilience: Dict[str, Any]


class SystemMetrics(BaseModel):
    """System resource metrics."""
    cpu_usage_percent: float
    memory_usage_bytes: int
    memory_usage_percent: float
    disk_usage_bytes: int
    disk_usage_percent: float
    uptime_seconds: float


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint.
    
    Returns a simple health status without checking dependencies.
    This endpoint should be fast and used for basic liveness checks.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


@router.get("/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check(
    redis_client=Depends(get_redis),
    db_session: AsyncSession = Depends(get_db_session)
):
    """Detailed health check with dependency verification.
    
    Checks all critical dependencies and returns detailed status information.
    This endpoint may take longer and should be used for readiness checks.
    """
    services = {}
    overall_status = "healthy"
    settings = get_settings()
    
    # Check Database
    db_health = await _check_database_health(db_session)
    services["database"] = db_health
    if db_health.status != "healthy":
        overall_status = "degraded"
    
    # Check Redis if enabled
    redis_health = await _check_redis_health(redis_client)
    services["redis"] = redis_health
    if redis_health.status == "unhealthy":
        overall_status = "degraded"
    
    # Check AnythingLLM
    anythingllm_health = await _check_anythingllm_health(settings)
    services["anythingllm"] = anythingllm_health
    if anythingllm_health.status != "healthy":
        overall_status = "degraded"
    
    # Get system metrics
    system_metrics = _get_system_metrics()
    
    # Get resilience status
    resilience_status = _get_resilience_status()
    
    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        services=services,
        system=system_metrics,
        resilience=resilience_status
    )


@router.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format for monitoring and alerting.
    """
    metrics_collector = get_metrics_collector()
    metrics_data = metrics_collector.get_metrics()
    
    return Response(
        content=metrics_data,
        media_type=metrics_collector.get_content_type()
    )


@router.get("/system", response_model=SystemMetrics)
async def get_system_metrics():
    """Get current system resource metrics.
    
    Returns detailed system resource utilization information.
    """
    return SystemMetrics(**_get_system_metrics())


@router.get("/resilience")
async def get_resilience_status():
    """Get error handling and resilience system status.
    
    Returns detailed information about error tracking, circuit breakers,
    and service degradation status.
    """
    return _get_resilience_status()


@router.post("/resilience/reset")
async def reset_resilience_systems():
    """Reset resilience systems (circuit breakers, error stats).
    
    This endpoint allows administrators to reset circuit breakers
    and error statistics for troubleshooting purposes.
    """
    try:
        # Reset error aggregator
        error_aggregator = get_error_aggregator()
        error_aggregator.reset_stats()
        
        # Reset all circuit breakers
        for breaker_name in circuit_breaker_registry._breakers:
            circuit_breaker_registry.reset_breaker(breaker_name)
        
        return {
            "status": "success",
            "message": "Resilience systems reset successfully",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Failed to reset resilience systems: {e}")
        return {
            "status": "error",
            "message": f"Failed to reset resilience systems: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


async def _check_database_health(db_session: AsyncSession) -> ServiceHealth:
    """Check database connectivity and performance."""
    import time
    
    start_time = time.time()
    
    try:
        # Simple query to test connectivity
        result = await db_session.execute("SELECT 1 as health_check")
        row = result.fetchone()
        
        response_time = (time.time() - start_time) * 1000
        
        if row and row[0] == 1:
            # Get connection pool info if available
            pool_info = {}
            if hasattr(db_manager.engine, 'pool'):
                pool = db_manager.engine.pool
                pool_info = {
                    "pool_size": pool.size(),
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                    "invalid": pool.invalid()
                }
            
            return ServiceHealth(
                status="healthy",
                message="Database connection successful",
                response_time_ms=response_time,
                details=pool_info
            )
        else:
            return ServiceHealth(
                status="unhealthy",
                message="Database query returned unexpected result",
                response_time_ms=response_time
            )
            
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return ServiceHealth(
            status="unhealthy",
            message=f"Database connection failed: {str(e)}",
            response_time_ms=response_time
        )


async def _check_redis_health(redis_client) -> ServiceHealth:
    """Check Redis connectivity and performance."""
    import time
    
    if not redis_client:
        return ServiceHealth(
            status="disabled",
            message="Redis not configured"
        )
    
    start_time = time.time()
    
    try:
        # Test basic connectivity
        pong = await redis_client.ping()
        response_time = (time.time() - start_time) * 1000
        
        if pong:
            # Get Redis info
            info = await redis_client.info()
            details = {
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0)
            }
            
            return ServiceHealth(
                status="healthy",
                message="Redis connection successful",
                response_time_ms=response_time,
                details=details
            )
        else:
            return ServiceHealth(
                status="unhealthy",
                message="Redis ping failed",
                response_time_ms=response_time
            )
            
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return ServiceHealth(
            status="unhealthy",
            message=f"Redis connection failed: {str(e)}",
            response_time_ms=response_time
        )


async def _check_anythingllm_health(settings) -> ServiceHealth:
    """Check AnythingLLM service connectivity and performance."""
    import time
    
    start_time = time.time()
    
    try:
        client = AnythingLLMClient(
            base_url=settings.anythingllm_url,
            api_key=settings.anythingllm_api_key,
            timeout=settings.anythingllm_timeout
        )
        
        # Test basic connectivity with health check or workspace list
        health_status = await client.health_check()
        response_time = (time.time() - start_time) * 1000
        
        if health_status.get("status") == "healthy":
            return ServiceHealth(
                status="healthy",
                message="AnythingLLM connection successful",
                response_time_ms=response_time,
                details=health_status
            )
        else:
            return ServiceHealth(
                status="degraded",
                message="AnythingLLM responded but may have issues",
                response_time_ms=response_time,
                details=health_status
            )
            
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return ServiceHealth(
            status="unhealthy",
            message=f"AnythingLLM connection failed: {str(e)}",
            response_time_ms=response_time
        )


def _get_system_metrics() -> Dict[str, Any]:
    """Get current system resource metrics."""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage
        disk = psutil.disk_usage('/')
        
        # System uptime (boot time)
        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
        
        return {
            "cpu_usage_percent": cpu_percent,
            "memory_usage_bytes": memory.used,
            "memory_usage_percent": memory.percent,
            "disk_usage_bytes": disk.used,
            "disk_usage_percent": (disk.used / disk.total) * 100,
            "uptime_seconds": uptime
        }
        
    except Exception as e:
        logger.warning(f"Failed to get system metrics: {e}")
        return {
            "cpu_usage_percent": 0.0,
            "memory_usage_bytes": 0,
            "memory_usage_percent": 0.0,
            "disk_usage_bytes": 0,
            "disk_usage_percent": 0.0,
            "uptime_seconds": 0.0
        }


def _get_resilience_status() -> Dict[str, Any]:
    """Get error handling and resilience system status."""
    try:
        # Get error aggregator stats
        error_aggregator = get_error_aggregator()
        error_stats = error_aggregator.get_error_stats()
        
        # Get degradation manager status
        degradation_manager = get_degradation_manager()
        degradation_status = degradation_manager.get_status()
        
        # Get circuit breaker stats
        circuit_breaker_stats = circuit_breaker_registry.get_all_stats()
        
        return {
            "error_tracking": {
                "total_errors": error_stats.get("total_errors", 0),
                "unique_errors": error_stats.get("unique_errors", 0),
                "top_errors": error_stats.get("top_errors", [])[:5],  # Top 5 errors
            },
            "service_degradation": {
                "current_level": degradation_status.get("service_level", "unknown"),
                "active_connections": degradation_status.get("active_connections", 0),
                "resource_usage": degradation_status.get("resource_usage", {}),
                "current_limits": degradation_status.get("current_limits", {}),
            },
            "circuit_breakers": circuit_breaker_stats,
        }
        
    except Exception as e:
        logger.warning(f"Failed to get resilience status: {e}")
        return {
            "error_tracking": {"status": "unavailable", "error": str(e)},
            "service_degradation": {"status": "unavailable", "error": str(e)},
            "circuit_breakers": {"status": "unavailable", "error": str(e)},
        }