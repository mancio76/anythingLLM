"""Tests for API documentation functionality."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from app.main import create_app
from app.core.documentation import (
    custom_openapi,
    get_custom_schemas,
    get_api_examples,
    get_authentication_examples,
    get_error_code_documentation
)
from app.core.versioning import APIVersion, APIVersionManager, get_version_manager
from app.examples.api_examples import (
    get_curl_examples,
    get_python_examples,
    get_javascript_examples,
    get_postman_collection
)


class TestOpenAPIDocumentation:
    """Test OpenAPI/Swagger documentation generation."""
    
    def test_custom_openapi_schema_generation(self):
        """Test custom OpenAPI schema generation."""
        app = create_app()
        schema = custom_openapi(app)
        
        # Test basic schema structure
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema
        assert "components" in schema
        
        # Test custom security schemes
        security_schemes = schema["components"]["securitySchemes"]
        assert "BearerAuth" in security_schemes
        assert "ApiKeyAuth" in security_schemes
        
        # Test Bearer auth configuration
        bearer_auth = security_schemes["BearerAuth"]
        assert bearer_auth["type"] == "http"
        assert bearer_auth["scheme"] == "bearer"
        assert bearer_auth["bearerFormat"] == "JWT"
        
        # Test API key auth configuration
        api_key_auth = security_schemes["ApiKeyAuth"]
        assert api_key_auth["type"] == "apiKey"
        assert api_key_auth["in"] == "header"
        assert api_key_auth["name"] == "X-API-Key"
        
        # Test global security requirement
        assert "security" in schema
        security = schema["security"]
        assert {"BearerAuth": []} in security
        assert {"ApiKeyAuth": []} in security
    
    def test_custom_schemas_addition(self):
        """Test addition of custom schemas."""
        custom_schemas = get_custom_schemas()
        
        assert "RateLimitHeaders" in custom_schemas
        assert "CorrelationHeaders" in custom_schemas
        
        # Test rate limit headers schema
        rate_limit_schema = custom_schemas["RateLimitHeaders"]
        assert "properties" in rate_limit_schema
        assert "X-RateLimit-Limit" in rate_limit_schema["properties"]
        assert "X-RateLimit-Remaining" in rate_limit_schema["properties"]
        assert "X-RateLimit-Reset" in rate_limit_schema["properties"]
        assert "Retry-After" in rate_limit_schema["properties"]
    
    def test_interactive_documentation_endpoints(self):
        """Test that interactive documentation endpoints are accessible."""
        app = create_app()
        client = TestClient(app)
        
        # Test Swagger UI endpoint
        response = client.get("/api/v1/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Test ReDoc endpoint
        response = client.get("/api/v1/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Test OpenAPI JSON endpoint
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        openapi_data = response.json()
        assert "openapi" in openapi_data
        assert "info" in openapi_data
        assert "paths" in openapi_data


class TestAPIVersioning:
    """Test API versioning functionality."""
    
    def test_version_manager_initialization(self):
        """Test version manager initialization."""
        version_manager = APIVersionManager()
        
        assert version_manager.default_version == APIVersion.V1
        assert APIVersion.V1 in version_manager.supported_versions
        assert len(version_manager.deprecated_versions) == 0
        
        # Test version info
        v1_info = version_manager.get_version_info(APIVersion.V1)
        assert v1_info.version == "1.0.0"
        assert v1_info.status == "stable"
        assert v1_info.release_date == "2024-01-15"
    
    def test_version_extraction_from_url_path(self):
        """Test version extraction from URL path."""
        version_manager = APIVersionManager()
        
        # Mock request with v1 in path
        mock_request = Mock()
        mock_request.url.path = "/api/v1/workspaces"
        mock_request.headers = {}
        mock_request.query_params = {}
        
        version = version_manager.get_version_from_request(mock_request)
        assert version == APIVersion.V1
    
    def test_version_extraction_from_header(self):
        """Test version extraction from API-Version header."""
        version_manager = APIVersionManager()
        
        # Mock request with version header
        mock_request = Mock()
        mock_request.url.path = "/api/workspaces"
        mock_request.headers = {"API-Version": "v1"}
        mock_request.query_params = {}
        
        version = version_manager.get_version_from_request(mock_request)
        assert version == APIVersion.V1
    
    def test_version_validation(self):
        """Test version validation."""
        version_manager = APIVersionManager()
        
        # Valid version should not raise exception
        version_manager.validate_version(APIVersion.V1)
        
        # Invalid version should raise HTTPException
        with pytest.raises(Exception):  # HTTPException
            # Create a mock unsupported version
            unsupported_version = Mock()
            unsupported_version.value = "v99"
            version_manager.validate_version(unsupported_version)
    
    def test_backward_compatibility_info(self):
        """Test backward compatibility information."""
        from app.core.versioning import get_backward_compatibility_info
        
        compat_info = get_backward_compatibility_info()
        
        assert "versioning_strategy" in compat_info
        assert "version_lifecycle" in compat_info
        assert "breaking_change_policy" in compat_info
        assert "deprecation_process" in compat_info
        assert "compatibility_guarantees" in compat_info
        
        # Test versioning strategy details
        strategy = compat_info["versioning_strategy"]
        assert strategy["type"] == "URL path versioning"
        assert strategy["format"] == "/api/{version}/..."


class TestDocumentationEndpoints:
    """Test documentation-specific API endpoints."""
    
    def test_versions_endpoint(self):
        """Test API versions information endpoint."""
        app = create_app()
        client = TestClient(app)
        
        response = client.get("/api/v1/docs/versions")
        assert response.status_code == 200
        
        data = response.json()
        assert "versions" in data
        assert "default_version" in data
        assert "supported_versions" in data
        assert "deprecated_versions" in data
        assert "backward_compatibility" in data
    
    def test_examples_endpoint(self):
        """Test API examples endpoint."""
        app = create_app()
        client = TestClient(app)
        
        response = client.get("/api/v1/docs/examples")
        assert response.status_code == 200
        
        data = response.json()
        assert "api_examples" in data
        assert "authentication" in data
        assert "error_codes" in data
    
    def test_authentication_endpoint(self):
        """Test authentication documentation endpoint."""
        app = create_app()
        client = TestClient(app)
        
        response = client.get("/api/v1/docs/authentication")
        assert response.status_code == 200
        
        data = response.json()
        assert "methods" in data
        assert "examples" in data
        assert "security_considerations" in data
        
        # Test authentication methods
        methods = data["methods"]
        assert "jwt_bearer" in methods
        assert "api_key" in methods
    
    def test_errors_endpoint(self):
        """Test error documentation endpoint."""
        app = create_app()
        client = TestClient(app)
        
        response = client.get("/api/v1/docs/errors")
        assert response.status_code == 200
        
        data = response.json()
        assert "error_format" in data
        assert "status_codes" in data
        assert "error_handling_best_practices" in data
        
        # Test error format schema
        error_format = data["error_format"]
        assert "schema" in error_format
        schema = error_format["schema"]
        assert "error" in schema
        assert "message" in schema
        assert "correlation_id" in schema
    
    def test_rate_limits_endpoint(self):
        """Test rate limits documentation endpoint."""
        app = create_app()
        client = TestClient(app)
        
        response = client.get("/api/v1/docs/rate-limits")
        assert response.status_code == 200
        
        data = response.json()
        assert "default_limits" in data
        assert "headers" in data
        assert "response_codes" in data
        assert "best_practices" in data
        assert "exemptions" in data


class TestAPIExamples:
    """Test API examples and code samples."""
    
    def test_api_examples_structure(self):
        """Test API examples structure."""
        examples = get_api_examples()
        
        assert "document_upload" in examples
        assert "workspace_creation" in examples
        assert "question_execution" in examples
        assert "error_responses" in examples
        
        # Test document upload example
        doc_upload = examples["document_upload"]
        assert "summary" in doc_upload
        assert "description" in doc_upload
        assert "request" in doc_upload
        assert "response" in doc_upload
    
    def test_authentication_examples(self):
        """Test authentication examples."""
        auth_examples = get_authentication_examples()
        
        assert "jwt_bearer" in auth_examples
        assert "api_key" in auth_examples
        
        # Test JWT bearer example
        jwt_example = auth_examples["jwt_bearer"]
        assert "description" in jwt_example
        assert "example" in jwt_example
        
        example = jwt_example["example"]
        assert "header" in example
        assert "curl" in example
        assert "javascript" in example
        assert "python" in example
    
    def test_error_code_documentation(self):
        """Test error code documentation."""
        error_docs = get_error_code_documentation()
        
        # Test common HTTP status codes
        assert "400" in error_docs
        assert "401" in error_docs
        assert "403" in error_docs
        assert "404" in error_docs
        assert "422" in error_docs
        assert "429" in error_docs
        assert "500" in error_docs
        
        # Test error structure
        error_400 = error_docs["400"]
        assert "name" in error_400
        assert "description" in error_400
        assert "common_causes" in error_400
        assert "example" in error_400
    
    def test_curl_examples(self):
        """Test cURL examples."""
        curl_examples = get_curl_examples()
        
        assert "authentication" in curl_examples
        assert "document_upload" in curl_examples
        assert "workspace_creation" in curl_examples
        assert "question_execution" in curl_examples
        
        # Test authentication examples
        auth = curl_examples["authentication"]
        assert "jwt_bearer" in auth
        assert "api_key" in auth
        
        # Verify cURL commands contain proper syntax
        assert "curl -X GET" in auth["jwt_bearer"]
        assert "Authorization: Bearer" in auth["jwt_bearer"]
    
    def test_python_examples(self):
        """Test Python code examples."""
        python_examples = get_python_examples()
        
        assert "setup" in python_examples
        assert "document_upload" in python_examples
        assert "workspace_management" in python_examples
        assert "question_processing" in python_examples
        assert "error_handling" in python_examples
        
        # Test setup example contains class definition
        setup = python_examples["setup"]
        assert "class AnythingLLMClient" in setup
        assert "def __init__" in setup
        assert "requests.Session" in setup
    
    def test_javascript_examples(self):
        """Test JavaScript code examples."""
        js_examples = get_javascript_examples()
        
        assert "setup" in js_examples
        assert "document_upload" in js_examples
        assert "workspace_management" in js_examples
        assert "question_processing" in js_examples
        assert "error_handling" in js_examples
        
        # Test setup example contains class definition
        setup = js_examples["setup"]
        assert "class AnythingLLMClient" in setup
        assert "constructor" in setup
        assert "fetch" in setup
    
    def test_postman_collection(self):
        """Test Postman collection structure."""
        collection = get_postman_collection()
        
        assert "info" in collection
        assert "auth" in collection
        assert "variable" in collection
        assert "item" in collection
        
        # Test collection info
        info = collection["info"]
        assert info["name"] == "AnythingLLM API"
        assert "version" in info
        assert "schema" in info
        
        # Test variables
        variables = collection["variable"]
        var_keys = [var["key"] for var in variables]
        assert "base_url" in var_keys
        assert "api_token" in var_keys
        assert "workspace_id" in var_keys
        
        # Test request items
        items = collection["item"]
        item_names = [item["name"] for item in items]
        assert "Authentication" in item_names
        assert "Documents" in item_names
        assert "Workspaces" in item_names
        assert "Questions" in item_names


class TestSchemaExamples:
    """Test schema examples in OpenAPI documentation."""
    
    def test_model_examples_in_schema(self):
        """Test that Pydantic models have examples in OpenAPI schema."""
        app = create_app()
        schema = custom_openapi(app)
        
        schemas = schema.get("components", {}).get("schemas", {})
        
        # Test that key models have examples
        if "Job" in schemas:
            job_schema = schemas["Job"]
            assert "example" in job_schema
            
            example = job_schema["example"]
            assert "id" in example
            assert "type" in example
            assert "status" in example
        
        if "Workspace" in schemas:
            workspace_schema = schemas["Workspace"]
            assert "example" in workspace_schema
            
            example = workspace_schema["example"]
            assert "id" in example
            assert "name" in example
            assert "config" in example
    
    def test_response_headers_in_schema(self):
        """Test that response headers are documented in schema."""
        app = create_app()
        schema = custom_openapi(app)
        
        paths = schema.get("paths", {})
        
        # Check that at least one endpoint has response headers
        found_headers = False
        for path_data in paths.values():
            for method_data in path_data.values():
                if isinstance(method_data, dict) and "responses" in method_data:
                    for status_code, response_data in method_data["responses"].items():
                        if status_code.startswith("2") and "headers" in response_data:
                            headers = response_data["headers"]
                            if "X-Correlation-ID" in headers:
                                found_headers = True
                                break
        
        assert found_headers, "Response headers should be documented in OpenAPI schema"


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.api_title = "AnythingLLM API"
    settings.api_version = "1.0.0"
    settings.api_prefix = "/api/v1"
    return settings


class TestDocumentationIntegration:
    """Test integration of documentation components."""
    
    def test_documentation_endpoints_require_no_auth(self):
        """Test that documentation endpoints don't require authentication."""
        app = create_app()
        client = TestClient(app)
        
        # These endpoints should be accessible without authentication
        public_endpoints = [
            "/api/v1/docs/versions",
            "/api/v1/docs/examples",
            "/api/v1/docs/authentication",
            "/api/v1/docs/errors",
            "/api/v1/docs/rate-limits",
            "/api/v1/docs/status"
        ]
        
        for endpoint in public_endpoints:
            response = client.get(endpoint)
            # Should not return 401 Unauthorized
            assert response.status_code != 401
    
    def test_openapi_schema_validation(self):
        """Test that generated OpenAPI schema is valid."""
        app = create_app()
        schema = custom_openapi(app)
        
        # Basic OpenAPI 3.0 structure validation
        required_fields = ["openapi", "info", "paths"]
        for field in required_fields:
            assert field in schema, f"Required field '{field}' missing from OpenAPI schema"
        
        # Test info section
        info = schema["info"]
        required_info_fields = ["title", "version"]
        for field in required_info_fields:
            assert field in info, f"Required info field '{field}' missing"
        
        # Test that paths exist
        paths = schema["paths"]
        assert len(paths) > 0, "No API paths found in schema"
        
        # Test that components exist
        components = schema.get("components", {})
        assert "schemas" in components, "No schemas found in components"
        assert "securitySchemes" in components, "No security schemes found in components"
    
    def test_version_consistency(self):
        """Test that version information is consistent across documentation."""
        app = create_app()
        client = TestClient(app)
        
        # Get version from OpenAPI schema
        openapi_response = client.get("/api/v1/openapi.json")
        openapi_data = openapi_response.json()
        openapi_version = openapi_data["info"]["version"]
        
        # Get version from versions endpoint
        versions_response = client.get("/api/v1/docs/versions")
        versions_data = versions_response.json()
        default_version = versions_data["default_version"]
        
        # Get version from status endpoint
        status_response = client.get("/api/v1/docs/status")
        status_data = status_response.json()
        current_version = status_data["current_version"]
        
        # All versions should be consistent
        assert openapi_version == "1.0.0"
        assert default_version == "v1"
        assert current_version == "v1"


if __name__ == "__main__":
    pytest.main([__file__])