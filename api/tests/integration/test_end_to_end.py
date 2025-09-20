"""
End-to-end integration tests for the complete AnythingLLM API workflow.

This module tests the complete document processing workflow from upload to question answering,
verifying all system components work together correctly.
"""

import pytest
import asyncio
import time
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Any, List
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from app.models.pydantic_models import JobStatus, JobType
from tests.fixtures.mock_data import mock_data, mock_files


class TestEndToEndWorkflow:
    """Test complete document processing workflow end-to-end."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_complete_document_processing_workflow(self, async_client: AsyncClient):
        """Test the complete workflow: upload -> workspace -> questions -> results."""
        
        # Step 1: Create a workspace
        workspace_data = {
            "name": "E2E Test Workspace",
            "description": "End-to-end testing workspace",
            "llm_config": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 1000,
                "timeout": 30
            }
        }
        
        workspace_response = await async_client.post(
            "/api/v1/workspaces",
            json=workspace_data,
            headers={"Authorization": "Bearer test-token"}
        )
        assert workspace_response.status_code == 201
        workspace = workspace_response.json()
        workspace_id = workspace["id"]
        
        # Step 2: Upload documents to the workspace
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test documents
            test_files = mock_files.create_test_document_set(Path(temp_dir))
            zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "test_docs.zip")
            
            with open(zip_path, "rb") as zip_file:
                upload_response = await async_client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("test_docs.zip", zip_file, "application/zip")},
                    data={"workspace_id": workspace_id},
                    headers={"Authorization": "Bearer test-token"}
                )
        
        assert upload_response.status_code == 202
        upload_job = upload_response.json()
        upload_job_id = upload_job["job_id"]
        
        # Step 3: Wait for document processing to complete
        await self._wait_for_job_completion(async_client, upload_job_id, timeout=60)
        
        # Step 4: Verify workspace has documents
        workspace_response = await async_client.get(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert workspace_response.status_code == 200
        workspace_data = workspace_response.json()
        assert workspace_data["document_count"] > 0
        
        # Step 5: Execute questions against the workspace
        questions_data = {
            "workspace_id": workspace_id,
            "questions": [
                {
                    "id": "q1",
                    "text": "What is the total contract value?",
                    "expected_fragments": ["total", "value", "amount"]
                },
                {
                    "id": "q2", 
                    "text": "Who are the contracting parties?",
                    "expected_fragments": ["party", "parties", "contractor"]
                },
                {
                    "id": "q3",
                    "text": "What is the contract duration?",
                    "expected_fragments": ["duration", "term", "period"]
                }
            ],
            "llm_config": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "temperature": 0.3
            }
        }
        
        questions_response = await async_client.post(
            "/api/v1/questions/execute",
            json=questions_data,
            headers={"Authorization": "Bearer test-token"}
        )
        assert questions_response.status_code == 202
        questions_job = questions_response.json()
        questions_job_id = questions_job["job_id"]
        
        # Step 6: Wait for question processing to complete
        await self._wait_for_job_completion(async_client, questions_job_id, timeout=120)
        
        # Step 7: Retrieve and validate results
        results_response = await async_client.get(
            f"/api/v1/questions/jobs/{questions_job_id}/results",
            headers={"Authorization": "Bearer test-token"}
        )
        assert results_response.status_code == 200
        results = results_response.json()
        
        # Validate results structure
        assert "results" in results
        assert len(results["results"]) == 3
        
        for result in results["results"]:
            assert "question_id" in result
            assert "question_text" in result
            assert "response" in result
            assert "confidence_score" in result
            assert "processing_time" in result
            assert "success" in result
            assert 0.0 <= result["confidence_score"] <= 1.0
            assert result["processing_time"] > 0
        
        # Step 8: Export results in different formats
        json_export = await async_client.get(
            f"/api/v1/questions/jobs/{questions_job_id}/results?format=json",
            headers={"Authorization": "Bearer test-token"}
        )
        assert json_export.status_code == 200
        
        csv_export = await async_client.get(
            f"/api/v1/questions/jobs/{questions_job_id}/results?format=csv",
            headers={"Authorization": "Bearer test-token"}
        )
        assert csv_export.status_code == 200
        assert "text/csv" in csv_export.headers.get("content-type", "")
        
        # Step 9: Clean up workspace
        delete_response = await async_client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert delete_response.status_code == 204
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_workspace_management_workflow(self, async_client: AsyncClient):
        """Test complete workspace management operations."""
        
        # Create workspace
        workspace_data = {
            "name": "Workspace Management Test",
            "description": "Testing workspace CRUD operations",
            "llm_config": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.5
            }
        }
        
        create_response = await async_client.post(
            "/api/v1/workspaces",
            json=workspace_data,
            headers={"Authorization": "Bearer test-token"}
        )
        assert create_response.status_code == 201
        workspace = create_response.json()
        workspace_id = workspace["id"]
        
        # List workspaces
        list_response = await async_client.get(
            "/api/v1/workspaces",
            headers={"Authorization": "Bearer test-token"}
        )
        assert list_response.status_code == 200
        workspaces = list_response.json()
        assert any(ws["id"] == workspace_id for ws in workspaces["workspaces"])
        
        # Get specific workspace
        get_response = await async_client.get(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert get_response.status_code == 200
        retrieved_workspace = get_response.json()
        assert retrieved_workspace["id"] == workspace_id
        assert retrieved_workspace["name"] == workspace_data["name"]
        
        # Update workspace
        update_data = {
            "name": "Updated Workspace Name",
            "description": "Updated description",
            "llm_config": {
                "provider": "anthropic",
                "model": "claude-3-sonnet",
                "temperature": 0.8
            }
        }
        
        update_response = await async_client.put(
            f"/api/v1/workspaces/{workspace_id}",
            json=update_data,
            headers={"Authorization": "Bearer test-token"}
        )
        assert update_response.status_code == 200
        updated_workspace = update_response.json()
        assert updated_workspace["name"] == update_data["name"]
        assert updated_workspace["llm_config"]["provider"] == "anthropic"
        
        # Delete workspace
        delete_response = await async_client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert delete_response.status_code == 204
        
        # Verify workspace is deleted
        get_deleted_response = await async_client.get(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert get_deleted_response.status_code == 404
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_llm_models(self, async_client: AsyncClient):
        """Test question processing with different LLM models."""
        
        # Create workspace
        workspace_response = await async_client.post(
            "/api/v1/workspaces",
            json={
                "name": "Multi-LLM Test Workspace",
                "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
            },
            headers={"Authorization": "Bearer test-token"}
        )
        workspace_id = workspace_response.json()["id"]
        
        # Upload test documents
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = mock_files.create_test_document_set(Path(temp_dir))
            zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "test.zip")
            
            with open(zip_path, "rb") as zip_file:
                upload_response = await async_client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("test.zip", zip_file, "application/zip")},
                    data={"workspace_id": workspace_id},
                    headers={"Authorization": "Bearer test-token"}
                )
        
        upload_job_id = upload_response.json()["job_id"]
        await self._wait_for_job_completion(async_client, upload_job_id)
        
        # Test different LLM models
        llm_configs = [
            {"provider": "openai", "model": "gpt-3.5-turbo", "temperature": 0.3},
            {"provider": "openai", "model": "gpt-4", "temperature": 0.5},
            {"provider": "anthropic", "model": "claude-3-sonnet", "temperature": 0.7},
            {"provider": "ollama", "model": "llama2", "temperature": 0.4}
        ]
        
        question_text = "What is the main topic of these documents?"
        
        for llm_config in llm_configs:
            questions_data = {
                "workspace_id": workspace_id,
                "questions": [{"id": "test", "text": question_text}],
                "llm_config": llm_config
            }
            
            response = await async_client.post(
                "/api/v1/questions/execute",
                json=questions_data,
                headers={"Authorization": "Bearer test-token"}
            )
            assert response.status_code == 202
            
            job_id = response.json()["job_id"]
            await self._wait_for_job_completion(async_client, job_id)
            
            # Verify results
            results_response = await async_client.get(
                f"/api/v1/questions/jobs/{job_id}/results",
                headers={"Authorization": "Bearer test-token"}
            )
            assert results_response.status_code == 200
            results = results_response.json()
            assert len(results["results"]) == 1
            assert results["results"][0]["success"]
        
        # Cleanup
        await async_client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
    
    async def _wait_for_job_completion(
        self, 
        client: AsyncClient, 
        job_id: str, 
        timeout: int = 60,
        poll_interval: float = 2.0
    ) -> Dict[str, Any]:
        """Wait for a job to complete with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = await client.get(
                f"/api/v1/jobs/{job_id}",
                headers={"Authorization": "Bearer test-token"}
            )
            assert response.status_code == 200
            
            job = response.json()
            status = job["status"]
            
            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                if status == JobStatus.FAILED:
                    pytest.fail(f"Job {job_id} failed: {job.get('error', 'Unknown error')}")
                return job
            
            await asyncio.sleep(poll_interval)
        
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


class TestSecurityValidation:
    """Test security measures and authentication flows."""
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_authentication_required(self, async_client: AsyncClient):
        """Test that all endpoints require authentication."""
        
        endpoints = [
            ("GET", "/api/v1/workspaces"),
            ("POST", "/api/v1/workspaces"),
            ("GET", "/api/v1/workspaces/test-id"),
            ("PUT", "/api/v1/workspaces/test-id"),
            ("DELETE", "/api/v1/workspaces/test-id"),
            ("POST", "/api/v1/documents/upload"),
            ("GET", "/api/v1/documents/jobs/test-id"),
            ("DELETE", "/api/v1/documents/jobs/test-id"),
            ("POST", "/api/v1/questions/execute"),
            ("GET", "/api/v1/questions/jobs/test-id"),
            ("GET", "/api/v1/questions/jobs/test-id/results"),
            ("GET", "/api/v1/jobs"),
            ("GET", "/api/v1/jobs/test-id"),
            ("DELETE", "/api/v1/jobs/test-id"),
        ]
        
        for method, endpoint in endpoints:
            response = await async_client.request(method, endpoint)
            assert response.status_code == 401, f"Endpoint {method} {endpoint} should require authentication"
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_invalid_token_rejection(self, async_client: AsyncClient):
        """Test that invalid tokens are rejected."""
        
        invalid_tokens = [
            "invalid-token",
            "Bearer invalid-token",
            "Bearer ",
            "",
            "Basic dGVzdDp0ZXN0",  # Basic auth instead of Bearer
        ]
        
        for token in invalid_tokens:
            headers = {"Authorization": token} if token else {}
            response = await async_client.get("/api/v1/workspaces", headers=headers)
            assert response.status_code == 401
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_rate_limiting(self, async_client: AsyncClient):
        """Test rate limiting functionality."""
        
        # Make rapid requests to trigger rate limiting
        responses = []
        for _ in range(150):  # Exceed typical rate limit
            response = await async_client.get(
                "/api/v1/health",
                headers={"Authorization": "Bearer test-token"}
            )
            responses.append(response.status_code)
        
        # Should have some 429 (Too Many Requests) responses
        rate_limited_count = sum(1 for status in responses if status == 429)
        assert rate_limited_count > 0, "Rate limiting should be triggered"
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_input_validation(self, async_client: AsyncClient):
        """Test input validation and sanitization."""
        
        # Test malicious inputs
        malicious_inputs = [
            {"name": "<script>alert('xss')</script>"},
            {"name": "'; DROP TABLE workspaces; --"},
            {"name": "../../../etc/passwd"},
            {"description": "A" * 10000},  # Extremely long input
            {"llm_config": {"provider": "invalid_provider"}},
        ]
        
        for malicious_data in malicious_inputs:
            response = await async_client.post(
                "/api/v1/workspaces",
                json=malicious_data,
                headers={"Authorization": "Bearer test-token"}
            )
            assert response.status_code in [400, 422], f"Should reject malicious input: {malicious_data}"
    
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_file_upload_security(self, async_client: AsyncClient):
        """Test file upload security measures."""
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test malicious file types
            malicious_files = [
                ("malware.exe", b"MZ\x90\x00", "application/octet-stream"),
                ("script.js", b"alert('xss')", "application/javascript"),
                ("shell.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh"),
                ("huge_file.zip", b"0" * (200 * 1024 * 1024), "application/zip"),  # 200MB file
            ]
            
            for filename, content, content_type in malicious_files:
                response = await async_client.post(
                    "/api/v1/documents/upload",
                    files={"file": (filename, content, content_type)},
                    data={"workspace_id": "test-workspace"},
                    headers={"Authorization": "Bearer test-token"}
                )
                assert response.status_code in [400, 413, 422], f"Should reject malicious file: {filename}"


class TestPerformanceAndLoad:
    """Test system performance under load."""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_concurrent_document_uploads(self, async_client: AsyncClient):
        """Test concurrent document upload performance."""
        
        # Create workspace
        workspace_response = await async_client.post(
            "/api/v1/workspaces",
            json={"name": "Performance Test", "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}},
            headers={"Authorization": "Bearer test-token"}
        )
        workspace_id = workspace_response.json()["id"]
        
        async def upload_document(client: AsyncClient, workspace_id: str, file_index: int):
            """Upload a single document."""
            with tempfile.TemporaryDirectory() as temp_dir:
                test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=2)
                zip_path = mock_files.create_zip_from_files(
                    test_files, 
                    Path(temp_dir) / f"test_{file_index}.zip"
                )
                
                with open(zip_path, "rb") as zip_file:
                    start_time = time.time()
                    response = await client.post(
                        "/api/v1/documents/upload",
                        files={"file": (f"test_{file_index}.zip", zip_file, "application/zip")},
                        data={"workspace_id": workspace_id},
                        headers={"Authorization": "Bearer test-token"}
                    )
                    upload_time = time.time() - start_time
                    
                    return {
                        "status_code": response.status_code,
                        "upload_time": upload_time,
                        "job_id": response.json().get("job_id") if response.status_code == 202 else None
                    }
        
        # Perform concurrent uploads
        concurrent_uploads = 10
        start_time = time.time()
        
        tasks = [
            upload_document(async_client, workspace_id, i) 
            for i in range(concurrent_uploads)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful_uploads = [r for r in results if isinstance(r, dict) and r["status_code"] == 202]
        failed_uploads = [r for r in results if not isinstance(r, dict) or r["status_code"] != 202]
        
        # Performance assertions
        assert len(successful_uploads) >= concurrent_uploads * 0.8, "At least 80% of uploads should succeed"
        assert total_time < 30.0, "Concurrent uploads should complete within 30 seconds"
        
        avg_upload_time = sum(r["upload_time"] for r in successful_uploads) / len(successful_uploads)
        assert avg_upload_time < 5.0, "Average upload time should be under 5 seconds"
        
        # Cleanup
        await async_client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_concurrent_question_processing(self, async_client: AsyncClient):
        """Test concurrent question processing performance."""
        
        # Setup workspace with documents
        workspace_response = await async_client.post(
            "/api/v1/workspaces",
            json={"name": "Question Performance Test", "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}},
            headers={"Authorization": "Bearer test-token"}
        )
        workspace_id = workspace_response.json()["id"]
        
        # Upload documents
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = mock_files.create_test_document_set(Path(temp_dir))
            zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "test.zip")
            
            with open(zip_path, "rb") as zip_file:
                upload_response = await async_client.post(
                    "/api/v1/documents/upload",
                    files={"file": ("test.zip", zip_file, "application/zip")},
                    data={"workspace_id": workspace_id},
                    headers={"Authorization": "Bearer test-token"}
                )
        
        upload_job_id = upload_response.json()["job_id"]
        await self._wait_for_job_completion(async_client, upload_job_id)
        
        async def execute_questions(client: AsyncClient, workspace_id: str, question_set: int):
            """Execute a set of questions."""
            questions_data = {
                "workspace_id": workspace_id,
                "questions": [
                    {"id": f"q{question_set}_1", "text": f"Question set {question_set}: What is the main topic?"},
                    {"id": f"q{question_set}_2", "text": f"Question set {question_set}: Who are the key parties?"},
                ]
            }
            
            start_time = time.time()
            response = await client.post(
                "/api/v1/questions/execute",
                json=questions_data,
                headers={"Authorization": "Bearer test-token"}
            )
            processing_time = time.time() - start_time
            
            return {
                "status_code": response.status_code,
                "processing_time": processing_time,
                "job_id": response.json().get("job_id") if response.status_code == 202 else None
            }
        
        # Execute concurrent question sets
        concurrent_sets = 5
        start_time = time.time()
        
        tasks = [
            execute_questions(async_client, workspace_id, i) 
            for i in range(concurrent_sets)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # Analyze results
        successful_executions = [r for r in results if isinstance(r, dict) and r["status_code"] == 202]
        
        # Performance assertions
        assert len(successful_executions) == concurrent_sets, "All question executions should succeed"
        assert total_time < 15.0, "Concurrent question execution should complete within 15 seconds"
        
        # Wait for all jobs to complete and verify results
        for result in successful_executions:
            if result["job_id"]:
                await self._wait_for_job_completion(async_client, result["job_id"], timeout=120)
        
        # Cleanup
        await async_client.delete(
            f"/api/v1/workspaces/{workspace_id}",
            headers={"Authorization": "Bearer test-token"}
        )
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_api_response_times(self, async_client: AsyncClient):
        """Test API endpoint response times."""
        
        endpoints_to_test = [
            ("GET", "/api/v1/health", None),
            ("GET", "/api/v1/health/detailed", None),
            ("GET", "/api/v1/workspaces", None),
            ("GET", "/api/v1/jobs", None),
        ]
        
        for method, endpoint, data in endpoints_to_test:
            start_time = time.time()
            
            if method == "GET":
                response = await async_client.get(
                    endpoint,
                    headers={"Authorization": "Bearer test-token"}
                )
            elif method == "POST":
                response = await async_client.post(
                    endpoint,
                    json=data,
                    headers={"Authorization": "Bearer test-token"}
                )
            
            response_time = time.time() - start_time
            
            # Response time assertions
            assert response_time < 2.0, f"Endpoint {method} {endpoint} should respond within 2 seconds"
            assert response.status_code < 500, f"Endpoint {method} {endpoint} should not have server errors"
    
    async def _wait_for_job_completion(
        self, 
        client: AsyncClient, 
        job_id: str, 
        timeout: int = 60
    ) -> Dict[str, Any]:
        """Wait for a job to complete with timeout."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            response = await client.get(
                f"/api/v1/jobs/{job_id}",
                headers={"Authorization": "Bearer test-token"}
            )
            
            if response.status_code == 200:
                job = response.json()
                if job["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    return job
            
            await asyncio.sleep(2.0)
        
        pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")


class TestSystemResilience:
    """Test system resilience and error handling."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_external_service_failure_handling(self, async_client: AsyncClient):
        """Test handling of external service failures."""
        
        # Mock AnythingLLM service failure
        with patch('app.integrations.anythingllm_client.AnythingLLMClient.health_check') as mock_health:
            mock_health.side_effect = Exception("Service unavailable")
            
            response = await async_client.get(
                "/api/v1/health/detailed",
                headers={"Authorization": "Bearer test-token"}
            )
            
            # Should still return 200 but indicate service issues
            assert response.status_code == 200
            health_data = response.json()
            assert health_data["status"] == "degraded"
            assert "anythingllm" in health_data["services"]
            assert health_data["services"]["anythingllm"]["status"] == "unhealthy"
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_database_connection_resilience(self, async_client: AsyncClient):
        """Test database connection resilience."""
        
        # Test with database connection issues
        with patch('app.repositories.base.BaseRepository._get_session') as mock_session:
            mock_session.side_effect = Exception("Database connection failed")
            
            response = await async_client.get(
                "/api/v1/jobs",
                headers={"Authorization": "Bearer test-token"}
            )
            
            # Should return appropriate error response
            assert response.status_code == 503
            error_data = response.json()
            assert "database" in error_data["message"].lower()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_graceful_degradation(self, async_client: AsyncClient):
        """Test graceful degradation under load."""
        
        # Simulate high load scenario
        async def make_request():
            return await async_client.get(
                "/api/v1/workspaces",
                headers={"Authorization": "Bearer test-token"}
            )
        
        # Make many concurrent requests
        tasks = [make_request() for _ in range(100)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze response patterns
        status_codes = []
        for response in responses:
            if isinstance(response, Exception):
                status_codes.append(500)  # Exception occurred
            else:
                status_codes.append(response.status_code)
        
        # Should handle load gracefully
        success_rate = sum(1 for code in status_codes if code == 200) / len(status_codes)
        assert success_rate >= 0.8, "Should maintain at least 80% success rate under load"
        
        # Should not have too many server errors
        server_error_rate = sum(1 for code in status_codes if code >= 500) / len(status_codes)
        assert server_error_rate <= 0.1, "Should have less than 10% server errors"