"""Integration tests for document endpoints registration."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.documents import router


def test_document_router_registration():
    """Test that document router can be registered with FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    
    # Verify routes are registered
    routes = [route.path for route in app.routes]
    
    expected_routes = [
        "/api/v1/documents/upload",
        "/api/v1/documents/jobs/{job_id}",
        "/api/v1/documents/jobs"
    ]
    
    for expected_route in expected_routes:
        # Check if any registered route matches the expected pattern
        found = any(
            expected_route.replace("{job_id}", "{path}") in route or
            expected_route in route
            for route in routes
        )
        assert found, f"Route {expected_route} not found in registered routes: {routes}"


def test_document_endpoints_respond():
    """Test that document endpoints respond (even if with auth errors)."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    
    client = TestClient(app)
    
    # Test upload endpoint
    response = client.post("/api/v1/documents/upload")
    assert response.status_code != 404  # Should not be "Not Found"
    
    # Test job status endpoint
    response = client.get("/api/v1/documents/jobs/test-job")
    assert response.status_code != 404  # Should not be "Not Found"
    
    # Test job list endpoint
    response = client.get("/api/v1/documents/jobs")
    assert response.status_code != 404  # Should not be "Not Found"
    
    # Test job cancel endpoint
    response = client.delete("/api/v1/documents/jobs/test-job")
    assert response.status_code != 404  # Should not be "Not Found"


def test_document_router_tags():
    """Test that document router has correct tags."""
    assert router.tags == ["documents"]


def test_document_router_prefix():
    """Test that document router has correct prefix."""
    assert router.prefix == "/documents"


def test_openapi_schema_generation():
    """Test that OpenAPI schema can be generated with document endpoints."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    
    # This should not raise an exception
    schema = app.openapi()
    
    # Verify some basic structure
    assert "paths" in schema
    assert "/api/v1/documents/upload" in schema["paths"]
    assert "/api/v1/documents/jobs/{job_id}" in schema["paths"]
    assert "/api/v1/documents/jobs" in schema["paths"]
    
    # Verify HTTP methods are present
    upload_path = schema["paths"]["/api/v1/documents/upload"]
    assert "post" in upload_path
    
    job_status_path = schema["paths"]["/api/v1/documents/jobs/{job_id}"]
    assert "get" in job_status_path
    assert "delete" in job_status_path
    
    job_list_path = schema["paths"]["/api/v1/documents/jobs"]
    assert "get" in job_list_path


def test_endpoint_response_models():
    """Test that endpoints have proper response models defined."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    
    schema = app.openapi()
    
    # Check upload endpoint response
    upload_responses = schema["paths"]["/api/v1/documents/upload"]["post"]["responses"]
    assert "202" in upload_responses  # HTTP_202_ACCEPTED
    assert "400" in upload_responses  # HTTP_400_BAD_REQUEST
    assert "413" in upload_responses  # HTTP_413_REQUEST_ENTITY_TOO_LARGE
    
    # Check job status endpoint response
    job_responses = schema["paths"]["/api/v1/documents/jobs/{job_id}"]["get"]["responses"]
    assert "200" in job_responses  # HTTP_200_OK
    assert "404" in job_responses  # HTTP_404_NOT_FOUND
    assert "403" in job_responses  # HTTP_403_FORBIDDEN


def test_endpoint_parameters():
    """Test that endpoints have proper parameters defined."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    
    schema = app.openapi()
    
    # Check upload endpoint parameters
    upload_params = schema["paths"]["/api/v1/documents/upload"]["post"]
    assert "requestBody" in upload_params
    
    # Check job status endpoint parameters
    job_status_params = schema["paths"]["/api/v1/documents/jobs/{job_id}"]["get"]
    assert "parameters" in job_status_params
    
    # Find job_id parameter
    job_id_param = None
    for param in job_status_params["parameters"]:
        if param["name"] == "job_id":
            job_id_param = param
            break
    
    assert job_id_param is not None
    assert job_id_param["in"] == "path"
    assert job_id_param["required"] is True
    
    # Check job list endpoint parameters
    job_list_params = schema["paths"]["/api/v1/documents/jobs"]["get"]
    assert "parameters" in job_list_params
    
    # Should have pagination and filter parameters
    param_names = [param["name"] for param in job_list_params["parameters"]]
    assert "page" in param_names
    assert "size" in param_names
    assert "status" in param_names
    assert "workspace_id" in param_names


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])