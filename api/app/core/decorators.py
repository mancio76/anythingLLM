"""Decorators for metrics collection and monitoring."""

import asyncio
import functools
import time
import logging
from typing import Callable, Any

from app.core.metrics import get_metrics_collector

logger = logging.getLogger(__name__)


def track_external_request(service: str, endpoint: str = None):
    """Decorator to track external service requests.
    
    Args:
        service: Name of the external service (e.g., 'anythingllm', 's3')
        endpoint: Specific endpoint being called (optional)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            metrics = get_metrics_collector()
            endpoint_name = endpoint or func.__name__
            
            async with metrics.time_external_request(service, endpoint_name):
                return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            metrics = get_metrics_collector()
            endpoint_name = endpoint or func.__name__
            start_time = time.time()
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                metrics.record_external_request(service, endpoint_name, status, duration)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def track_database_query(operation: str = None):
    """Decorator to track database query performance.
    
    Args:
        operation: Type of database operation (e.g., 'select', 'insert', 'update')
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            metrics = get_metrics_collector()
            operation_name = operation or func.__name__
            
            async with metrics.time_database_query(operation_name):
                return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            metrics = get_metrics_collector()
            operation_name = operation or func.__name__
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                metrics.db_query_duration.labels(operation=operation_name).observe(duration)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def track_job_lifecycle(job_type: str):
    """Decorator to track job creation and completion.
    
    Args:
        job_type: Type of job being tracked
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            metrics = get_metrics_collector()
            start_time = time.time()
            
            # Record job creation
            metrics.record_job_created(job_type)
            
            try:
                result = await func(*args, **kwargs)
                # Record successful completion
                duration = time.time() - start_time
                metrics.record_job_completed(job_type, duration, success=True)
                return result
            except Exception as e:
                # Record failed completion
                duration = time.time() - start_time
                metrics.record_job_completed(job_type, duration, success=False)
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            metrics = get_metrics_collector()
            start_time = time.time()
            
            # Record job creation
            metrics.record_job_created(job_type)
            
            try:
                result = func(*args, **kwargs)
                # Record successful completion
                duration = time.time() - start_time
                metrics.record_job_completed(job_type, duration, success=True)
                return result
            except Exception as e:
                # Record failed completion
                duration = time.time() - start_time
                metrics.record_job_completed(job_type, duration, success=False)
                raise
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator