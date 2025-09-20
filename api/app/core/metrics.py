"""Prometheus metrics collection and monitoring."""

import time
import psutil
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from prometheus_client import (
    Counter, Histogram, Gauge, Info, CollectorRegistry, 
    generate_latest, CONTENT_TYPE_LATEST
)

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Centralized metrics collection for the application."""
    
    def __init__(self):
        """Initialize metrics collectors."""
        self.registry = CollectorRegistry()
        
        # API Request Metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )
        
        self.http_request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint'],
            registry=self.registry
        )
        
        # Job Metrics
        self.jobs_total = Counter(
            'jobs_total',
            'Total jobs created',
            ['job_type', 'status'],
            registry=self.registry
        )
        
        self.job_duration = Histogram(
            'job_duration_seconds',
            'Job processing duration in seconds',
            ['job_type'],
            registry=self.registry
        )
        
        self.active_jobs = Gauge(
            'active_jobs',
            'Number of currently active jobs',
            ['job_type'],
            registry=self.registry
        ) 
       
        # External Service Metrics
        self.external_requests_total = Counter(
            'external_requests_total',
            'Total external service requests',
            ['service', 'endpoint', 'status'],
            registry=self.registry
        )
        
        self.external_request_duration = Histogram(
            'external_request_duration_seconds',
            'External service request duration in seconds',
            ['service', 'endpoint'],
            registry=self.registry
        )
        
        # Database Metrics
        self.db_connections_active = Gauge(
            'db_connections_active',
            'Active database connections',
            registry=self.registry
        )
        
        self.db_query_duration = Histogram(
            'db_query_duration_seconds',
            'Database query duration in seconds',
            ['operation'],
            registry=self.registry
        )
        
        # System Resource Metrics
        self.system_cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'System CPU usage percentage',
            registry=self.registry
        )
        
        self.system_memory_usage = Gauge(
            'system_memory_usage_bytes',
            'System memory usage in bytes',
            registry=self.registry
        )
        
        self.system_disk_usage = Gauge(
            'system_disk_usage_bytes',
            'System disk usage in bytes',
            ['path'],
            registry=self.registry
        )
        
        # Application Info
        self.app_info = Info(
            'app_info',
            'Application information',
            registry=self.registry
        )
        
        logger.info("Metrics collector initialized")
    
    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics."""
        self.http_requests_total.labels(
            method=method, 
            endpoint=endpoint, 
            status_code=status_code
        ).inc()
        
        self.http_request_duration.labels(
            method=method, 
            endpoint=endpoint
        ).observe(duration)
    
    def record_job_created(self, job_type: str):
        """Record job creation."""
        self.jobs_total.labels(job_type=job_type, status='created').inc()
        self.active_jobs.labels(job_type=job_type).inc()
    
    def record_job_completed(self, job_type: str, duration: float, success: bool):
        """Record job completion."""
        status = 'completed' if success else 'failed'
        self.jobs_total.labels(job_type=job_type, status=status).inc()
        self.job_duration.labels(job_type=job_type).observe(duration)
        self.active_jobs.labels(job_type=job_type).dec()
    
    def record_external_request(self, service: str, endpoint: str, status: str, duration: float):
        """Record external service request."""
        self.external_requests_total.labels(
            service=service, 
            endpoint=endpoint, 
            status=status
        ).inc()
        
        self.external_request_duration.labels(
            service=service, 
            endpoint=endpoint
        ).observe(duration)
    
    def update_system_metrics(self):
        """Update system resource metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=None)
            self.system_cpu_usage.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_memory_usage.set(memory.used)
            
            # Disk usage for root path
            disk = psutil.disk_usage('/')
            self.system_disk_usage.labels(path='/').set(disk.used)
            
        except Exception as e:
            logger.warning(f"Failed to update system metrics: {e}")
    
    def set_app_info(self, version: str, environment: str = "production"):
        """Set application information."""
        self.app_info.info({
            'version': version,
            'environment': environment
        })
    
    def get_metrics(self) -> str:
        """Get Prometheus metrics in text format."""
        self.update_system_metrics()
        return generate_latest(self.registry).decode('utf-8')
    
    def get_content_type(self) -> str:
        """Get Prometheus metrics content type."""
        return CONTENT_TYPE_LATEST
    
    @asynccontextmanager
    async def time_external_request(self, service: str, endpoint: str):
        """Context manager to time external requests."""
        start_time = time.time()
        status = "success"
        
        try:
            yield
        except Exception as e:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            self.record_external_request(service, endpoint, status, duration)
    
    @asynccontextmanager
    async def time_database_query(self, operation: str):
        """Context manager to time database queries."""
        start_time = time.time()
        
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.db_query_duration.labels(operation=operation).observe(duration)


# Global metrics collector instance
metrics = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    return metrics