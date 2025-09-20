"""Metrics collection middleware."""

import time
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import get_metrics_collector

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP request metrics."""
    
    def __init__(self, app, exclude_paths: list = None):
        """Initialize metrics middleware.
        
        Args:
            app: FastAPI application instance
            exclude_paths: List of paths to exclude from metrics collection
        """
        super().__init__(app)
        self.metrics = get_metrics_collector()
        self.exclude_paths = exclude_paths or ['/metrics', '/health']
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        # Skip metrics collection for excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # Record start time
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Extract endpoint pattern from route
            endpoint = self._get_endpoint_pattern(request)
            
            # Record metrics
            self.metrics.record_http_request(
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration=duration
            )
            
            return response
            
        except Exception as e:
            # Record error metrics
            duration = time.time() - start_time
            endpoint = self._get_endpoint_pattern(request)
            
            self.metrics.record_http_request(
                method=request.method,
                endpoint=endpoint,
                status_code=500,
                duration=duration
            )
            
            raise e
    
    def _get_endpoint_pattern(self, request: Request) -> str:
        """Extract endpoint pattern from request."""
        try:
            # Try to get the route pattern
            if hasattr(request, 'scope') and 'route' in request.scope:
                route = request.scope['route']
                if hasattr(route, 'path'):
                    return route.path
            
            # Fallback to path
            return request.url.path
            
        except Exception:
            # Ultimate fallback
            return request.url.path