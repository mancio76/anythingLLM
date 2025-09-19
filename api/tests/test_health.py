"""Test health check endpoints."""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_basic_health_check(self, client: TestClient):
        """Test basic health check endpoint."""
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_basic_health_check_async(self, async_client: AsyncClient):
        """Test basic health check endpoint with async client."""
        response = await async_client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["version"] == "1.0.0"
    
    def test_detailed_health_check(self, client: TestClient):
        """Test detailed health check endpoint."""
        response = client.get("/api/v1/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["healthy", "degraded"]
        assert "timestamp" in data
        assert data["version"] == "1.0.0"
        assert "services" in data
        
        # Check service statuses
        services = data["services"]
        assert "redis" in services
        assert "database" in services
        assert "anythingllm" in services
        
        # Each service should have status and message
        for service_name, service_data in services.items():
            assert "status" in service_data
            assert "message" in service_data
            assert service_data["status"] in ["healthy", "unhealthy", "disabled", "pending"]
    
    @pytest.mark.asyncio
    async def test_detailed_health_check_async(self, async_client: AsyncClient):
        """Test detailed health check endpoint with async client."""
        response = await async_client.get("/api/v1/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["healthy", "degraded"]
        assert "services" in data