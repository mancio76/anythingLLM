#!/usr/bin/env python3
"""
System validation script for AnythingLLM API.

This script performs comprehensive validation of all system components
to ensure the API is ready for production deployment.
"""

import asyncio
import json
import sys
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import httpx

from tests.fixtures.mock_data import mock_files, mock_data


class SystemValidator:
    """Comprehensive system validation."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.auth_headers = {"Authorization": "Bearer test-token"}
        self.validation_results: Dict[str, Dict] = {}
    
    async def validate_all_components(self) -> bool:
        """Validate all system components."""
        print("🔍 Starting Comprehensive System Validation")
        print("=" * 60)
        
        validations = [
            ("API Health", self.validate_api_health),
            ("Authentication", self.validate_authentication),
            ("Document Processing", self.validate_document_processing),
            ("Workspace Management", self.validate_workspace_management),
            ("Question Processing", self.validate_question_processing),
            ("Security Measures", self.validate_security_measures),
            ("Error Handling", self.validate_error_handling),
            ("Performance", self.validate_performance),
            ("Data Persistence", self.validate_data_persistence),
            ("External Integrations", self.validate_external_integrations),
        ]
        
        overall_success = True
        
        for validation_name, validation_func in validations:
            print(f"\n📋 Validating {validation_name}...")
            start_time = time.time()
            
            try:
                success = await validation_func()
                duration = time.time() - start_time
                
                self.validation_results[validation_name] = {
                    "success": success,
                    "duration": duration,
                    "error": None
                }
                
                status = "✅ PASSED" if success else "❌ FAILED"
                print(f"   {status} ({duration:.2f}s)")
                
                if not success:
                    overall_success = False
                    
            except Exception as e:
                duration = time.time() - start_time
                self.validation_results[validation_name] = {
                    "success": False,
                    "duration": duration,
                    "error": str(e)
                }
                print(f"   ❌ FAILED - Error: {e}")
                overall_success = False
        
        self.print_validation_summary()
        return overall_success
    
    async def validate_api_health(self) -> bool:
        """Validate API health endpoints."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Basic health check
            response = await client.get("/api/v1/health")
            if response.status_code != 200:
                print(f"   ❌ Basic health check failed: {response.status_code}")
                return False
            
            health_data = response.json()
            if health_data.get("status") != "healthy":
                print(f"   ❌ Health status not healthy: {health_data.get('status')}")
                return False
            
            # Detailed health check
            response = await client.get(
                "/api/v1/health/detailed",
                headers=self.auth_headers
            )
            if response.status_code != 200:
                print(f"   ❌ Detailed health check failed: {response.status_code}")
                return False
            
            detailed_health = response.json()
            required_services = ["database", "anythingllm"]
            
            for service in required_services:
                if service not in detailed_health.get("services", {}):
                    print(f"   ❌ Missing service in health check: {service}")
                    return False
            
            print("   ✅ Health endpoints working correctly")
            return True
    
    async def validate_authentication(self) -> bool:
        """Validate authentication mechanisms."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Test unauthenticated request
            response = await client.get("/api/v1/workspaces")
            if response.status_code != 401:
                print(f"   ❌ Unauthenticated request should return 401, got {response.status_code}")
                return False
            
            # Test invalid token
            response = await client.get(
                "/api/v1/workspaces",
                headers={"Authorization": "Bearer invalid-token"}
            )
            if response.status_code != 401:
                print(f"   ❌ Invalid token should return 401, got {response.status_code}")
                return False
            
            # Test valid token
            response = await client.get(
                "/api/v1/workspaces",
                headers=self.auth_headers
            )
            if response.status_code not in [200, 404]:
                print(f"   ❌ Valid token should work, got {response.status_code}")
                return False
            
            print("   ✅ Authentication working correctly")
            return True
    
    async def validate_document_processing(self) -> bool:
        """Validate complete document processing workflow."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Create workspace
            workspace_data = {
                "name": "Validation Test Workspace",
                "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
            }
            
            response = await client.post(
                "/api/v1/workspaces",
                json=workspace_data,
                headers=self.auth_headers
            )
            if response.status_code != 201:
                print(f"   ❌ Workspace creation failed: {response.status_code}")
                return False
            
            workspace_id = response.json()["id"]
            
            try:
                # Upload documents
                with tempfile.TemporaryDirectory() as temp_dir:
                    test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=3)
                    zip_path = mock_files.create_zip_from_files(
                        test_files, 
                        Path(temp_dir) / "validation_test.zip"
                    )
                    
                    with open(zip_path, "rb") as zip_file:
                        response = await client.post(
                            "/api/v1/documents/upload",
                            files={"file": ("validation_test.zip", zip_file, "application/zip")},
                            data={"workspace_id": workspace_id},
                            headers=self.auth_headers
                        )
                
                if response.status_code != 202:
                    print(f"   ❌ Document upload failed: {response.status_code}")
                    return False
                
                job_id = response.json()["job_id"]
                
                # Wait for processing to complete
                max_wait = 60  # seconds
                start_wait = time.time()
                
                while time.time() - start_wait < max_wait:
                    response = await client.get(
                        f"/api/v1/jobs/{job_id}",
                        headers=self.auth_headers
                    )
                    
                    if response.status_code == 200:
                        job_data = response.json()
                        if job_data["status"] == "completed":
                            break
                        elif job_data["status"] == "failed":
                            print(f"   ❌ Document processing failed: {job_data.get('error')}")
                            return False
                    
                    await asyncio.sleep(2)
                else:
                    print("   ❌ Document processing timed out")
                    return False
                
                # Verify workspace has documents
                response = await client.get(
                    f"/api/v1/workspaces/{workspace_id}",
                    headers=self.auth_headers
                )
                
                if response.status_code != 200:
                    print(f"   ❌ Failed to get workspace: {response.status_code}")
                    return False
                
                workspace_data = response.json()
                if workspace_data.get("document_count", 0) == 0:
                    print("   ❌ No documents found in workspace after upload")
                    return False
                
                print("   ✅ Document processing working correctly")
                return True
                
            finally:
                # Cleanup workspace
                await client.delete(
                    f"/api/v1/workspaces/{workspace_id}",
                    headers=self.auth_headers
                )
    
    async def validate_workspace_management(self) -> bool:
        """Validate workspace CRUD operations."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Create workspace
            workspace_data = {
                "name": "CRUD Test Workspace",
                "description": "Testing CRUD operations",
                "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
            }
            
            response = await client.post(
                "/api/v1/workspaces",
                json=workspace_data,
                headers=self.auth_headers
            )
            if response.status_code != 201:
                print(f"   ❌ Workspace creation failed: {response.status_code}")
                return False
            
            workspace = response.json()
            workspace_id = workspace["id"]
            
            try:
                # Read workspace
                response = await client.get(
                    f"/api/v1/workspaces/{workspace_id}",
                    headers=self.auth_headers
                )
                if response.status_code != 200:
                    print(f"   ❌ Workspace read failed: {response.status_code}")
                    return False
                
                # Update workspace
                update_data = {
                    "name": "Updated CRUD Test Workspace",
                    "description": "Updated description"
                }
                
                response = await client.put(
                    f"/api/v1/workspaces/{workspace_id}",
                    json=update_data,
                    headers=self.auth_headers
                )
                if response.status_code != 200:
                    print(f"   ❌ Workspace update failed: {response.status_code}")
                    return False
                
                updated_workspace = response.json()
                if updated_workspace["name"] != update_data["name"]:
                    print("   ❌ Workspace update did not persist")
                    return False
                
                # List workspaces
                response = await client.get(
                    "/api/v1/workspaces",
                    headers=self.auth_headers
                )
                if response.status_code != 200:
                    print(f"   ❌ Workspace list failed: {response.status_code}")
                    return False
                
                workspaces = response.json()
                if not any(ws["id"] == workspace_id for ws in workspaces.get("workspaces", [])):
                    print("   ❌ Created workspace not found in list")
                    return False
                
                print("   ✅ Workspace management working correctly")
                return True
                
            finally:
                # Delete workspace
                response = await client.delete(
                    f"/api/v1/workspaces/{workspace_id}",
                    headers=self.auth_headers
                )
                if response.status_code != 204:
                    print(f"   ⚠️  Workspace deletion failed: {response.status_code}")
    
    async def validate_question_processing(self) -> bool:
        """Validate question processing functionality."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Create workspace with documents
            workspace_response = await client.post(
                "/api/v1/workspaces",
                json={
                    "name": "Question Test Workspace",
                    "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
                },
                headers=self.auth_headers
            )
            workspace_id = workspace_response.json()["id"]
            
            try:
                # Upload documents first
                with tempfile.TemporaryDirectory() as temp_dir:
                    test_files = mock_files.create_test_document_set(Path(temp_dir))
                    zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "test.zip")
                    
                    with open(zip_path, "rb") as zip_file:
                        upload_response = await client.post(
                            "/api/v1/documents/upload",
                            files={"file": ("test.zip", zip_file, "application/zip")},
                            data={"workspace_id": workspace_id},
                            headers=self.auth_headers
                        )
                
                # Wait for document processing
                upload_job_id = upload_response.json()["job_id"]
                await self._wait_for_job_completion(client, upload_job_id)
                
                # Execute questions
                questions_data = {
                    "workspace_id": workspace_id,
                    "questions": [
                        {
                            "id": "validation_q1",
                            "text": "What is the contract value?",
                            "expected_fragments": ["value", "contract"]
                        },
                        {
                            "id": "validation_q2",
                            "text": "Who is the vendor?",
                            "expected_fragments": ["vendor", "company"]
                        }
                    ]
                }
                
                response = await client.post(
                    "/api/v1/questions/execute",
                    json=questions_data,
                    headers=self.auth_headers
                )
                
                if response.status_code != 202:
                    print(f"   ❌ Question execution failed: {response.status_code}")
                    return False
                
                questions_job_id = response.json()["job_id"]
                
                # Wait for question processing
                await self._wait_for_job_completion(client, questions_job_id, timeout=120)
                
                # Get results
                response = await client.get(
                    f"/api/v1/questions/jobs/{questions_job_id}/results",
                    headers=self.auth_headers
                )
                
                if response.status_code != 200:
                    print(f"   ❌ Failed to get question results: {response.status_code}")
                    return False
                
                results = response.json()
                if "results" not in results or len(results["results"]) != 2:
                    print("   ❌ Invalid question results structure")
                    return False
                
                # Validate result structure
                for result in results["results"]:
                    required_fields = ["question_id", "question_text", "response", "confidence_score", "success"]
                    if not all(field in result for field in required_fields):
                        print(f"   ❌ Missing required fields in result: {result}")
                        return False
                
                print("   ✅ Question processing working correctly")
                return True
                
            finally:
                await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=self.auth_headers)
    
    async def validate_security_measures(self) -> bool:
        """Validate security measures."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Test rate limiting (make many requests quickly)
            rate_limit_responses = []
            for _ in range(50):
                response = await client.get("/api/v1/health", headers=self.auth_headers)
                rate_limit_responses.append(response.status_code)
            
            # Should have some rate limiting
            if not any(code == 429 for code in rate_limit_responses):
                print("   ⚠️  Rate limiting may not be working (no 429 responses)")
            
            # Test input validation
            malicious_inputs = [
                {"name": "<script>alert('xss')</script>"},
                {"name": "'; DROP TABLE workspaces; --"},
                {"description": "A" * 10000},  # Very long input
            ]
            
            for malicious_data in malicious_inputs:
                response = await client.post(
                    "/api/v1/workspaces",
                    json=malicious_data,
                    headers=self.auth_headers
                )
                if response.status_code not in [400, 422]:
                    print(f"   ❌ Malicious input not rejected: {malicious_data}")
                    return False
            
            # Test file upload security
            with tempfile.TemporaryDirectory() as temp_dir:
                # Create malicious file
                malicious_file = Path(temp_dir) / "malware.exe"
                malicious_file.write_bytes(b"fake executable content")
                
                with open(malicious_file, "rb") as f:
                    response = await client.post(
                        "/api/v1/documents/upload",
                        files={"file": ("malware.exe", f, "application/octet-stream")},
                        data={"workspace_id": "test"},
                        headers=self.auth_headers
                    )
                
                if response.status_code not in [400, 422]:
                    print("   ❌ Malicious file upload not rejected")
                    return False
            
            print("   ✅ Security measures working correctly")
            return True
    
    async def validate_error_handling(self) -> bool:
        """Validate error handling."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Test 404 errors
            response = await client.get(
                "/api/v1/workspaces/nonexistent-id",
                headers=self.auth_headers
            )
            if response.status_code != 404:
                print(f"   ❌ Expected 404 for nonexistent resource, got {response.status_code}")
                return False
            
            # Test validation errors
            response = await client.post(
                "/api/v1/workspaces",
                json={"invalid": "data"},
                headers=self.auth_headers
            )
            if response.status_code not in [400, 422]:
                print(f"   ❌ Expected validation error, got {response.status_code}")
                return False
            
            # Verify error response format
            error_data = response.json()
            if "error" not in error_data and "detail" not in error_data:
                print("   ❌ Error response missing error information")
                return False
            
            print("   ✅ Error handling working correctly")
            return True
    
    async def validate_performance(self) -> bool:
        """Validate basic performance requirements."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Test response times for basic endpoints
            endpoints = [
                "/api/v1/health",
                "/api/v1/workspaces",
                "/api/v1/jobs",
            ]
            
            for endpoint in endpoints:
                start_time = time.time()
                response = await client.get(endpoint, headers=self.auth_headers)
                response_time = time.time() - start_time
                
                if response_time > 2.0:
                    print(f"   ❌ Slow response time for {endpoint}: {response_time:.2f}s")
                    return False
                
                if response.status_code >= 500:
                    print(f"   ❌ Server error for {endpoint}: {response.status_code}")
                    return False
            
            print("   ✅ Performance requirements met")
            return True
    
    async def validate_data_persistence(self) -> bool:
        """Validate data persistence."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Create workspace
            workspace_data = {
                "name": "Persistence Test Workspace",
                "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
            }
            
            response = await client.post(
                "/api/v1/workspaces",
                json=workspace_data,
                headers=self.auth_headers
            )
            workspace_id = response.json()["id"]
            
            try:
                # Verify workspace persists
                await asyncio.sleep(1)  # Small delay
                
                response = await client.get(
                    f"/api/v1/workspaces/{workspace_id}",
                    headers=self.auth_headers
                )
                
                if response.status_code != 200:
                    print("   ❌ Workspace not persisted")
                    return False
                
                workspace = response.json()
                if workspace["name"] != workspace_data["name"]:
                    print("   ❌ Workspace data not persisted correctly")
                    return False
                
                print("   ✅ Data persistence working correctly")
                return True
                
            finally:
                await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=self.auth_headers)
    
    async def validate_external_integrations(self) -> bool:
        """Validate external service integrations."""
        async with httpx.AsyncClient(base_url=self.base_url) as client:
            # Check detailed health to see external service status
            response = await client.get(
                "/api/v1/health/detailed",
                headers=self.auth_headers
            )
            
            if response.status_code != 200:
                print("   ❌ Cannot check external service health")
                return False
            
            health_data = response.json()
            services = health_data.get("services", {})
            
            # Check AnythingLLM integration
            anythingllm_status = services.get("anythingllm", {}).get("status")
            if anythingllm_status not in ["healthy", "degraded"]:
                print(f"   ❌ AnythingLLM integration unhealthy: {anythingllm_status}")
                return False
            
            # Check database integration
            database_status = services.get("database", {}).get("status")
            if database_status != "healthy":
                print(f"   ❌ Database integration unhealthy: {database_status}")
                return False
            
            print("   ✅ External integrations working correctly")
            return True
    
    async def _wait_for_job_completion(
        self, 
        client: httpx.AsyncClient, 
        job_id: str, 
        timeout: int = 60
    ):
        """Wait for a job to complete."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = await client.get(
                f"/api/v1/jobs/{job_id}",
                headers=self.auth_headers
            )
            
            if response.status_code == 200:
                job_data = response.json()
                if job_data["status"] in ["completed", "failed"]:
                    return job_data
            
            await asyncio.sleep(2)
        
        raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
    
    def print_validation_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("📊 System Validation Summary")
        print("=" * 60)
        
        total_validations = len(self.validation_results)
        passed_validations = sum(1 for r in self.validation_results.values() if r["success"])
        failed_validations = total_validations - passed_validations
        total_duration = sum(r["duration"] for r in self.validation_results.values())
        
        print(f"Total Validations: {total_validations}")
        print(f"Passed: {passed_validations}")
        print(f"Failed: {failed_validations}")
        print(f"Total Duration: {total_duration:.2f}s")
        print()
        
        for validation_name, result in self.validation_results.items():
            status = "✅" if result["success"] else "❌"
            print(f"{status} {validation_name}: {result['duration']:.2f}s")
            if result["error"]:
                print(f"   Error: {result['error']}")
        
        if failed_validations == 0:
            print("\n🎉 All system validations passed! System is ready for production.")
        else:
            print(f"\n⚠️  {failed_validations} validation(s) failed. System needs attention.")


async def main():
    """Main validation entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate AnythingLLM API system")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the API service"
    )
    
    args = parser.parse_args()
    
    validator = SystemValidator(base_url=args.base_url)
    success = await validator.validate_all_components()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())