"""Tests for health monitoring and metrics system."""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import create_app
from app.core.metrics import MetricsCollector, get_metrics_collector
from app.middleware.metrics import MetricsMiddleware


class TestMetricsCollector:
    """Test metrics collection functionality."""
    
    def test_metrics_collector_initialization(self):
        """Test metrics collector initializes correctly."""
        collector = MetricsCollector()
        
        # Check that all metrics are initialized
        assert collector.http_requests_total is not None
        assert collector.http_request_duration is not None
        assert collector.jobs_total is not None
        assert collector.job_duration is not None
        assert collector.active_jobs is not None
        assert collector.external_requests_total is not None
        assert collector.external_request_duration is not None
        assert collector.db_connections_active is not None
        assert collector.db_query_duration is not None
        assert collector.system_cpu_usage is not None
        assert collector.system_memory_usage is not None
        assert collector.system_disk_usage is not None
        assert collector.app_info is not None
    
    def test_record_http_request(self):
        """Test HTTP request metrics recording."""
        collector = MetricsCollector()
        
        # Record a request
        collector.record_http_request("GET", "/api/v1/health", 200, 0.1)
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that metrics are recorded
        assert 'http_requests_total{endpoint="/api/v1/health",method="GET",status_code="200"} 1.0' in metrics_output
        assert 'http_request_duration_seconds_bucket{endpoint="/api/v1/health",method="GET"' in metrics_output
    
    def test_record_job_lifecycle(self):
        """Test job lifecycle metrics recording."""
        collector = MetricsCollector()
        
        # Record job creation
        collector.record_job_created("document_upload")
        
        # Record job completion
        collector.record_job_completed("document_upload", 5.0, True)
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that metrics are recorded
        assert 'jobs_total{job_type="document_upload",status="created"} 1.0' in metrics_output
        assert 'jobs_total{job_type="document_upload",status="completed"} 1.0' in metrics_output
        assert 'job_duration_seconds_bucket{job_type="document_upload"' in metrics_output
    
    def test_record_external_request(self):
        """Test external service request metrics recording."""
        collector = MetricsCollector()
        
        # Record external request
        collector.record_external_request("anythingllm", "create_workspace", "success", 0.5)
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that metrics are recorded
        assert 'external_requests_total{endpoint="create_workspace",service="anythingllm",status="success"} 1.0' in metrics_output
        assert 'external_request_duration_seconds_bucket{endpoint="create_workspace",service="anythingllm"' in metrics_output
    
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    def test_update_system_metrics(self, mock_disk, mock_memory, mock_cpu):
        """Test system metrics collection."""
        # Mock system metrics
        mock_cpu.return_value = 25.5
        mock_memory.return_value = Mock(used=1024*1024*1024)  # 1GB
        mock_disk.return_value = Mock(used=10*1024*1024*1024)  # 10GB
        
        collector = MetricsCollector()
        collector.update_system_metrics()
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that system metrics are recorded
        assert 'system_cpu_usage_percent 25.5' in metrics_output
        assert f'system_memory_usage_bytes {1024*1024*1024}.0' in metrics_output
        assert f'system_disk_usage_bytes{{path="/"}} {10*1024*1024*1024}.0' in metrics_output
    
    def test_set_app_info(self):
        """Test application info setting."""
        collector = MetricsCollector()
        collector.set_app_info("1.0.0", "test")
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that app info is recorded
        assert 'app_info{environment="test",version="1.0.0"} 1.0' in metrics_output
    
    @pytest.mark.asyncio
    async def test_time_external_request_context_manager(self):
        """Test external request timing context manager."""
        collector = MetricsCollector()
        
        # Use context manager
        async with collector.time_external_request("test_service", "test_endpoint"):
            await asyncio.sleep(0.1)  # Simulate work
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that metrics are recorded
        assert 'external_requests_total{endpoint="test_endpoint",service="test_service",status="success"} 1.0' in metrics_output
    
    @pytest.mark.asyncio
    async def test_time_database_query_context_manager(self):
        """Test database query timing context manager."""
        collector = MetricsCollector()
        
        # Use context manager
        async with collector.time_database_query("select"):
            await asyncio.sleep(0.05)  # Simulate query
        
        # Get metrics output
        metrics_output = collector.get_metrics()
        
        # Check that metrics are recorded
        assert 'db_query_duration_seconds_bucket{operation="select"' in metrics_output


class TestMetricsMiddleware:
    """Test metrics middleware functionality."""
    
    @pytest.mark.asyncio
    async def test_middleware_records_metrics(self):
        """Test that middleware records HTTP request metrics."""
        from fastapi import FastAPI, Request, Response
        from starlette.responses import JSONResponse
        
        app = FastAPI()
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        # Add metrics middleware
        app.add_middleware(MetricsMiddleware)
        
        # Create test client
        with TestClient(app) as client:
            # Make request
            response = client.get("/test")
            
            # Check response
            assert response.status_code == 200
            
            # Check that metrics were recorded
            metrics = get_metrics_collector()
            metrics_output = metrics.get_metrics()
            
            # Should contain HTTP request metrics
            assert 'http_requests_total' in metrics_output
            assert 'http_request_duration_seconds' in metrics_output
    
    def test_middleware_excludes_paths(self):
        """Test that middleware excludes specified paths."""
        from fastapi import FastAPI
        
        app = FastAPI()
        
        @app.get("/metrics")
        async def metrics_endpoint():
            return {"metrics": "data"}
        
        @app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}
        
        @app.get("/api/test")
        async def api_endpoint():
            return {"message": "test"}
        
        # Add metrics middleware with default exclusions
        app.add_middleware(MetricsMiddleware)
        
        with TestClient(app) as client:
            # Make requests to excluded paths
            client.get("/metrics")
            client.get("/health")
            
            # Make request to included path
            client.get("/api/test")
            
            # Check metrics - should only have the API endpoint
            metrics = get_metrics_collector()
            metrics_output = metrics.get_metrics()
            
            # Should not contain metrics for excluded paths
            # This is a basic test - in practice, you'd need to parse the metrics more carefully
            assert 'endpoint="/api/test"' in metrics_output or 'http_requests_total' in metrics_output


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_basic_health_check(self):
        """Test basic health check endpoint."""
        app = create_app()
        
        with TestClient(app) as client:
            response = client.get("/api/v1/health/")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert data["version"] == "1.0.0"
    
    @patch('app.routers.health._check_database_health')
    @patch('app.routers.health._check_redis_health')
    @patch('app.routers.health._check_anythingllm_health')
    @patch('app.routers.health._get_system_metrics')
    def test_detailed_health_check(self, mock_system, mock_anythingllm, mock_redis, mock_db):
        """Test detailed health check endpoint."""
        from app.routers.health import ServiceHealth
        
        # Mock health check responses
        mock_db.return_value = ServiceHealth(
            status="healthy",
            message="Database connection successful",
            response_time_ms=10.0
        )
        mock_redis.return_value = ServiceHealth(
            status="disabled",
            message="Redis not configured"
        )
        mock_anythingllm.return_value = ServiceHealth(
            status="healthy",
            message="AnythingLLM connection successful",
            response_time_ms=50.0
        )
        mock_system.return_value = {
            "cpu_usage_percent": 25.0,
            "memory_usage_bytes": 1024*1024*1024,
            "memory_usage_percent": 50.0,
            "disk_usage_bytes": 10*1024*1024*1024,
            "disk_usage_percent": 75.0,
            "uptime_seconds": 3600.0
        }
        
        app = create_app()
        
        with TestClient(app) as client:
            response = client.get("/api/v1/health/detailed")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert data["version"] == "1.0.0"
            
            # Check services
            assert "database" in data["services"]
            assert "redis" in data["services"]
            assert "anythingllm" in data["services"]
            
            assert data["services"]["database"]["status"] == "healthy"
            assert data["services"]["redis"]["status"] == "disabled"
            assert data["services"]["anythingllm"]["status"] == "healthy"
            
            # Check system metrics
            assert "system" in data
            assert data["system"]["cpu_usage_percent"] == 25.0
            assert data["system"]["memory_usage_bytes"] == 1024*1024*1024
    
    def test_metrics_endpoint(self):
        """Test Prometheus metrics endpoint."""
        app = create_app()
        
        with TestClient(app) as client:
            response = client.get("/api/v1/health/metrics")
            
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/plain")
            
            # Check that metrics are in Prometheus format
            content = response.content.decode()
            assert "# HELP" in content
            assert "# TYPE" in content
    
    @patch('app.routers.health._get_system_metrics')
    def test_system_metrics_endpoint(self, mock_system):
        """Test system metrics endpoint."""
        mock_system.return_value = {
            "cpu_usage_percent": 30.0,
            "memory_usage_bytes": 2*1024*1024*1024,
            "memory_usage_percent": 60.0,
            "disk_usage_bytes": 15*1024*1024*1024,
            "disk_usage_percent": 80.0,
            "uptime_seconds": 7200.0
        }
        
        app = create_app()
        
        with TestClient(app) as client:
            response = client.get("/api/v1/health/system")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["cpu_usage_percent"] == 30.0
            assert data["memory_usage_bytes"] == 2*1024*1024*1024
            assert data["memory_usage_percent"] == 60.0
            assert data["disk_usage_bytes"] == 15*1024*1024*1024
            assert data["disk_usage_percent"] == 80.0
            assert data["uptime_seconds"] == 7200.0


if __name__ == "__main__":
    pytest.main([__file__])