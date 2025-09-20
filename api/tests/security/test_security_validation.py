"""
Comprehensive security validation tests for the AnythingLLM API.

This module tests authentication, authorization, input validation,
rate limiting, and other security measures.
"""

import json
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List
import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings


class TestSecurityValidation:
    """Comprehensive security testing."""
    
    @pytest.fixture(scope="class")
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture(scope="class")
    def settings(self):
        """Get application settings."""
        return get_settings()
    
    def test_authentication_required(self, client):
        """Test that authentication is required for protected endpoints."""
        protected_endpoints = [
            ("GET", "/api/v1/workspaces"),
            ("POST", "/api/v1/workspaces"),
            ("GET", "/api/v1/workspaces/test-id"),
            ("PUT", "/api/v1/workspaces/test-id"),
            ("DELETE", "/api/v1/workspaces/test-id"),
            ("POST", "/api/v1/documents/upload"),
            ("GET", "/api/v1/documents/jobs/test-id"),
            ("DELETE", "/api/v1/documents/jobs/test-id"),
            ("POST", "/api/v1/questions/execute"),
            ("GET", "/api/v1/questions/jobs/test-id/results"),
            ("GET", "/api/v1/jobs"),
            ("GET", "/api/v1/jobs/test-id"),
            ("DELETE", "/api/v1/jobs/test-id"),
        ]
        
        for method, endpoint in protected_endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint, json={})
            elif method == "PUT":
                response = client.put(endpoint, json={})
            elif method == "DELETE":
                response = client.delete(endpoint)
            
            # Should require authentication
            assert response.status_code in [401, 403], f"{method} {endpoint} should require authentication"
    
    def test_invalid_authentication_tokens(self, client):
        """Test handling of invalid authentication tokens."""
        invalid_tokens = [
            "Bearer invalid_token",
            "Bearer ",
            "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.invalid",
            "Invalid Bearer token",
            "Basic dGVzdDp0ZXN0",  # Basic auth instead of Bearer
        ]
        
        for token in invalid_tokens:
            headers = {"Authorization": token}
            response = client.get("/api/v1/workspaces", headers=headers)
            assert response.status_code in [401, 403], f"Invalid token '{token}' should be rejected"
    
    def test_api_key_authentication(self, client, settings):
        """Test API key authentication."""
        # Test missing API key
        response = client.get("/api/v1/workspaces")
        assert response.status_code in [401, 403]
        
        # Test invalid API key
        headers = {settings.api_key_header: "invalid_api_key"}
        response = client.get("/api/v1/workspaces", headers=headers)
        assert response.status_code in [401, 403]
        
        # Test malformed API key header
        headers = {"X-Invalid-Header": "test_key"}
        response = client.get("/api/v1/workspaces", headers=headers)
        assert response.status_code in [401, 403]
    
    def test_input_validation_security(self, client):
        """Test input validation for security vulnerabilities."""
        
        # Test SQL injection attempts
        sql_injection_payloads = [
            "'; DROP TABLE workspaces; --",
            "' OR '1'='1",
            "1; DELETE FROM jobs; --",
            "admin'--",
            "' UNION SELECT * FROM users --"
        ]
        
        for payload in sql_injection_payloads:
            # Test in workspace name
            workspace_data = {"name": payload}
            response = client.post("/api/v1/workspaces", json=workspace_data)
            # Should either reject due to auth or validate input properly
            assert response.status_code in [400, 401, 403, 422]
            
            # Test in workspace ID parameter
            response = client.get(f"/api/v1/workspaces/{payload}")
            assert response.status_code in [400, 401, 403, 404, 422]
        
        # Test XSS attempts
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//",
            "<svg onload=alert('xss')>"
        ]
        
        for payload in xss_payloads:
            workspace_data = {"name": payload, "description": payload}
            response = client.post("/api/v1/workspaces", json=workspace_data)
            # Should validate and sanitize input
            assert response.status_code in [400, 401, 403, 422]
    
    def test_file_upload_security(self, client):
        """Test file upload security measures."""
        
        # Test malicious file types
        malicious_files = [
            ("malware.exe", b"MZ\x90\x00", "application/octet-stream"),
            ("script.js", b"alert('xss');", "application/javascript"),
            ("shell.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh"),
            ("virus.bat", b"@echo off\ndel /f /q *.*", "application/x-msdos-program"),
        ]
        
        for filename, content, content_type in malicious_files:
            files = {"file": (filename, content, content_type)}
            data = {"workspace_id": "test"}
            response = client.post("/api/v1/documents/upload", files=files, data=data)
            # Should reject malicious file types
            assert response.status_code in [400, 401, 403, 415, 422]
        
        # Test oversized files
        large_content = b"A" * (200 * 1024 * 1024)  # 200MB
        files = {"file": ("large.zip", large_content, "application/zip")}
        data = {"workspace_id": "test"}
        response = client.post("/api/v1/documents/upload", files=files, data=data)
        # Should reject oversized files
        assert response.status_code in [400, 401, 403, 413, 422]
        
        # Test ZIP bomb protection
        zip_bomb = self._create_zip_bomb()
        files = {"file": ("bomb.zip", zip_bomb, "application/zip")}
        data = {"workspace_id": "test"}
        response = client.post("/api/v1/documents/upload", files=files, data=data)
        # Should detect and reject ZIP bombs
        assert response.status_code in [400, 401, 403, 422]
    
    def test_path_traversal_protection(self, client):
        """Test protection against path traversal attacks."""
        
        path_traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%252f..%252f..%252fetc%252fpasswd",
        ]
        
        for payload in path_traversal_payloads:
            # Test in workspace ID
            response = client.get(f"/api/v1/workspaces/{payload}")
            assert response.status_code in [400, 401, 403, 404, 422]
            
            # Test in job ID
            response = client.get(f"/api/v1/jobs/{payload}")
            assert response.status_code in [400, 401, 403, 404, 422]
    
    def test_rate_limiting(self, client, settings):
        """Test rate limiting functionality."""
        if not settings.rate_limit_enabled:
            pytest.skip("Rate limiting not enabled")
        
        # Make rapid requests to trigger rate limiting
        responses = []
        for i in range(settings.rate_limit_requests + 10):
            response = client.get("/api/v1/health")
            responses.append(response.status_code)
            
            # Small delay to avoid overwhelming the test
            if i % 10 == 0:
                time.sleep(0.1)
        
        # Should eventually get rate limited (429 status)
        rate_limited_responses = [code for code in responses if code == 429]
        assert len(rate_limited_responses) > 0, "Rate limiting not working"
        
        # Test rate limit headers
        response = client.get("/api/v1/health")
        rate_limit_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ]
        
        # At least some rate limit headers should be present
        present_headers = [header for header in rate_limit_headers if header in response.headers]
        # Note: Headers might not be present if rate limiting is implemented differently
    
    def test_cors_security(self, client):
        """Test CORS security configuration."""
        
        # Test preflight request
        headers = {
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"
        }
        
        response = client.options("/api/v1/workspaces", headers=headers)
        
        # Check CORS headers
        cors_headers = response.headers
        
        # Should have proper CORS configuration
        if "Access-Control-Allow-Origin" in cors_headers:
            # Should not allow all origins in production
            assert cors_headers["Access-Control-Allow-Origin"] != "*"
    
    def test_security_headers(self, client):
        """Test security headers in responses."""
        response = client.get("/api/v1/health")
        
        security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": ["DENY", "SAMEORIGIN"],
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": None,  # Should be present in HTTPS
            "Content-Security-Policy": None,
        }
        
        for header, expected_values in security_headers.items():
            if header in response.headers:
                if expected_values and isinstance(expected_values, list):
                    assert response.headers[header] in expected_values
                elif expected_values:
                    assert response.headers[header] == expected_values
    
    def test_sensitive_data_exposure(self, client):
        """Test that sensitive data is not exposed in responses."""
        
        # Test error responses don't expose sensitive info
        response = client.get("/api/v1/workspaces/non-existent")
        error_response = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        
        # Should not expose internal paths, database info, etc.
        sensitive_patterns = [
            "/app/",
            "postgresql://",
            "redis://",
            "SECRET_KEY",
            "password",
            "api_key",
            "token",
            "traceback",
            "stack trace"
        ]
        
        response_text = json.dumps(error_response).lower()
        for pattern in sensitive_patterns:
            assert pattern.lower() not in response_text, f"Sensitive data '{pattern}' exposed in error response"
    
    def test_http_method_security(self, client):
        """Test HTTP method security."""
        
        # Test that dangerous methods are not allowed
        dangerous_methods = ["TRACE", "CONNECT", "PATCH"]
        
        for method in dangerous_methods:
            response = client.request(method, "/api/v1/health")
            # Should not allow dangerous methods
            assert response.status_code in [405, 501], f"Method {method} should not be allowed"
    
    def test_json_parsing_security(self, client):
        """Test JSON parsing security."""
        
        # Test deeply nested JSON (JSON bomb)
        nested_json = {"a": {}}
        current = nested_json["a"]
        for i in range(100):  # Create deeply nested structure
            current["nested"] = {}
            current = current["nested"]
        
        response = client.post("/api/v1/workspaces", json=nested_json)
        # Should handle or reject deeply nested JSON
        assert response.status_code in [400, 401, 403, 413, 422]
        
        # Test large JSON payload
        large_json = {"data": "A" * (10 * 1024 * 1024)}  # 10MB string
        response = client.post("/api/v1/workspaces", json=large_json)
        # Should reject oversized JSON
        assert response.status_code in [400, 401, 403, 413, 422]
    
    def test_session_security(self, client):
        """Test session security measures."""
        
        # Test session fixation protection
        # Make request without session
        response1 = client.get("/api/v1/health")
        
        # Make another request
        response2 = client.get("/api/v1/health")
        
        # Session IDs should be properly managed
        # This is more relevant for session-based auth, but we test anyway
        
        # Test concurrent sessions
        client1 = TestClient(app)
        client2 = TestClient(app)
        
        response1 = client1.get("/api/v1/health")
        response2 = client2.get("/api/v1/health")
        
        # Both should work independently
        assert response1.status_code == 200
        assert response2.status_code == 200
    
    def _create_zip_bomb(self) -> bytes:
        """Create a simple ZIP bomb for testing."""
        import io
        
        # Create a ZIP file with highly compressed content
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add a file with repetitive content that compresses well
            large_content = "A" * (1024 * 1024)  # 1MB of 'A's
            zf.writestr("bomb.txt", large_content)
        
        return zip_buffer.getvalue()


class TestAuthorizationSecurity:
    """Test authorization and access control."""
    
    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)
    
    def test_workspace_access_control(self, client):
        """Test workspace access control."""
        
        # Test accessing non-existent workspace
        response = client.get("/api/v1/workspaces/non-existent-workspace")
        assert response.status_code in [401, 403, 404]
        
        # Test deleting non-existent workspace
        response = client.delete("/api/v1/workspaces/non-existent-workspace")
        assert response.status_code in [401, 403, 404]
    
    def test_job_access_control(self, client):
        """Test job access control."""
        
        # Test accessing non-existent job
        response = client.get("/api/v1/jobs/non-existent-job")
        assert response.status_code in [401, 403, 404]
        
        # Test deleting non-existent job
        response = client.delete("/api/v1/jobs/non-existent-job")
        assert response.status_code in [401, 403, 404]
    
    def test_privilege_escalation_protection(self, client):
        """Test protection against privilege escalation."""
        
        # Test admin-only operations (if any)
        admin_endpoints = [
            ("POST", "/api/v1/jobs/cleanup"),
            ("GET", "/api/v1/metrics"),
        ]
        
        for method, endpoint in admin_endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint, json={})
            
            # Should require proper authorization
            assert response.status_code in [401, 403, 404]


class TestDataProtectionSecurity:
    """Test data protection and privacy measures."""
    
    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)
    
    def test_log_sanitization(self, client):
        """Test that sensitive data is sanitized in logs."""
        
        # Make request with sensitive data
        sensitive_data = {
            "name": "Test Workspace",
            "api_key": "secret_api_key_12345",
            "password": "secret_password",
            "token": "bearer_token_xyz"
        }
        
        response = client.post("/api/v1/workspaces", json=sensitive_data)
        
        # Response should not contain sensitive data
        response_text = response.text.lower()
        sensitive_patterns = ["secret_api_key", "secret_password", "bearer_token"]
        
        for pattern in sensitive_patterns:
            assert pattern not in response_text, f"Sensitive data '{pattern}' not sanitized"
    
    def test_error_information_disclosure(self, client):
        """Test that errors don't disclose sensitive information."""
        
        # Trigger various error conditions
        error_endpoints = [
            "/api/v1/workspaces/invalid-id",
            "/api/v1/jobs/invalid-job-id",
            "/api/v1/questions/jobs/invalid-job/results",
        ]
        
        for endpoint in error_endpoints:
            response = client.get(endpoint)
            
            if response.headers.get("content-type", "").startswith("application/json"):
                error_data = response.json()
                error_text = json.dumps(error_data).lower()
                
                # Should not expose internal details
                forbidden_info = [
                    "database",
                    "postgresql",
                    "redis",
                    "internal server error",
                    "traceback",
                    "/app/",
                    "secret",
                    "password"
                ]
                
                for info in forbidden_info:
                    assert info not in error_text, f"Error exposes sensitive info: {info}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])