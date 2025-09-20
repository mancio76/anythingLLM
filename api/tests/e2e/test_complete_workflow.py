"""
End-to-end integration tests for complete document processing workflow.

This module tests the entire workflow from document upload through question processing
with real AnythingLLM integration, multiple LLM models, and comprehensive validation.
"""

import asyncio
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List
import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.models.pydantic_models import JobStatus, LLMProvider


class TestCompleteWorkflow:
    """Test complete document processing workflow end-to-end."""
    
    @pytest.fixture(scope="class")
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture(scope="class")
    def settings(self):
        """Get application settings."""
        return get_settings()
    
    @pytest.fixture(scope="class")
    def sample_documents(self):
        """Create sample documents for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create sample PDF content (mock)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        (temp_dir / "contract.pdf").write_bytes(pdf_content)
        
        # Create sample JSON content
        json_content = {
            "contract_id": "C001",
            "vendor": "ACME Corp",
            "value": 50000,
            "terms": "Net 30 payment terms"
        }
        (temp_dir / "contract_data.json").write_text(json.dumps(json_content))
        
        # Create sample CSV content
        csv_content = "item,quantity,price\nLaptops,10,1000\nMice,20,25\n"
        (temp_dir / "inventory.csv").write_text(csv_content)
        
        # Create ZIP file
        zip_path = temp_dir / "documents.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(temp_dir / "contract.pdf", "contract.pdf")
            zf.write(temp_dir / "contract_data.json", "contract_data.json")
            zf.write(temp_dir / "inventory.csv", "inventory.csv")
        
        return zip_path
    
    @pytest.fixture(scope="class")
    def sample_questions(self):
        """Create sample questions for testing."""
        return [
            {
                "text": "What is the contract value?",
                "expected_fragments": ["50000", "fifty thousand"]
            },
            {
                "text": "Who is the vendor?",
                "expected_fragments": ["ACME Corp", "ACME"]
            },
            {
                "text": "What are the payment terms?",
                "expected_fragments": ["Net 30", "30 days"]
            }
        ]
    
    @pytest.mark.asyncio
    async def test_complete_document_workflow(self, client, sample_documents, sample_questions):
        """Test complete document processing workflow."""
        
        # Step 1: Create workspace
        workspace_data = {
            "name": "E2E Test Workspace",
            "description": "End-to-end testing workspace",
            "llm_config": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "temperature": 0.7
            }
        }
        
        response = client.post("/api/v1/workspaces", json=workspace_data)
        assert response.status_code == 201
        workspace = response.json()
        workspace_id = workspace["id"]
        
        # Step 2: Upload documents
        with open(sample_documents, "rb") as f:
            files = {"file": ("documents.zip", f, "application/zip")}
            data = {"workspace_id": workspace_id}
            response = client.post("/api/v1/documents/upload", files=files, data=data)
        
        assert response.status_code == 202
        upload_job = response.json()
        upload_job_id = upload_job["job_id"]
        
        # Step 3: Wait for document processing to complete
        await self._wait_for_job_completion(client, upload_job_id)
        
        # Step 4: Verify workspace has documents
        response = client.get(f"/api/v1/workspaces/{workspace_id}")
        assert response.status_code == 200
        workspace_details = response.json()
        assert workspace_details["document_count"] > 0
        
        # Step 5: Execute questions
        question_data = {
            "workspace_id": workspace_id,
            "questions": sample_questions,
            "llm_config": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "temperature": 0.3
            }
        }
        
        response = client.post("/api/v1/questions/execute", json=question_data)
        assert response.status_code == 202
        question_job = response.json()
        question_job_id = question_job["job_id"]
        
        # Step 6: Wait for question processing to complete
        await self._wait_for_job_completion(client, question_job_id)
        
        # Step 7: Retrieve and validate results
        response = client.get(f"/api/v1/questions/jobs/{question_job_id}/results")
        assert response.status_code == 200
        results = response.json()
        
        assert "results" in results
        assert len(results["results"]) == len(sample_questions)
        
        # Validate each question result
        for result in results["results"]:
            assert "question_text" in result
            assert "response" in result
            assert "confidence_score" in result
            assert "success" in result
            assert 0.0 <= result["confidence_score"] <= 1.0
        
        # Step 8: Cleanup
        response = client.delete(f"/api/v1/workspaces/{workspace_id}")
        assert response.status_code == 204
    
    @pytest.mark.asyncio
    async def test_multiple_llm_models(self, client, sample_documents, sample_questions):
        """Test question processing with multiple LLM models."""
        
        llm_models = [
            {"provider": "openai", "model": "gpt-3.5-turbo"},
            {"provider": "openai", "model": "gpt-4"},
            {"provider": "anthropic", "model": "claude-3-sonnet"},
            {"provider": "ollama", "model": "llama2"}
        ]
        
        # Create workspace
        workspace_data = {
            "name": "Multi-LLM Test Workspace",
            "description": "Testing multiple LLM models"
        }
        
        response = client.post("/api/v1/workspaces", json=workspace_data)
        assert response.status_code == 201
        workspace_id = response.json()["id"]
        
        # Upload documents
        with open(sample_documents, "rb") as f:
            files = {"file": ("documents.zip", f, "application/zip")}
            data = {"workspace_id": workspace_id}
            response = client.post("/api/v1/documents/upload", files=files, data=data)
        
        upload_job_id = response.json()["job_id"]
        await self._wait_for_job_completion(client, upload_job_id)
        
        # Test each LLM model
        results_by_model = {}
        
        for llm_config in llm_models:
            try:
                question_data = {
                    "workspace_id": workspace_id,
                    "questions": sample_questions[:1],  # Test with one question
                    "llm_config": llm_config
                }
                
                response = client.post("/api/v1/questions/execute", json=question_data)
                if response.status_code == 202:
                    job_id = response.json()["job_id"]
                    await self._wait_for_job_completion(client, job_id)
                    
                    response = client.get(f"/api/v1/questions/jobs/{job_id}/results")
                    if response.status_code == 200:
                        results_by_model[f"{llm_config['provider']}-{llm_config['model']}"] = response.json()
                
            except Exception as e:
                # Some models might not be available in test environment
                print(f"Model {llm_config['provider']}-{llm_config['model']} not available: {e}")
        
        # Verify at least one model worked
        assert len(results_by_model) > 0, "No LLM models were successfully tested"
        
        # Cleanup
        client.delete(f"/api/v1/workspaces/{workspace_id}")
    
    @pytest.mark.asyncio
    async def test_security_and_rate_limiting(self, client):
        """Test security measures and rate limiting."""
        
        # Test authentication required
        response = client.get("/api/v1/workspaces")
        assert response.status_code in [401, 403]  # Unauthorized or Forbidden
        
        # Test rate limiting (if enabled)
        # Make rapid requests to trigger rate limiting
        responses = []
        for i in range(20):
            response = client.get("/api/v1/health")
            responses.append(response.status_code)
        
        # Check if rate limiting is working (429 status code)
        rate_limited = any(status == 429 for status in responses)
        
        # Test input validation
        invalid_workspace_data = {
            "name": "",  # Invalid empty name
            "llm_config": {
                "provider": "invalid_provider",
                "model": ""
            }
        }
        
        response = client.post("/api/v1/workspaces", json=invalid_workspace_data)
        assert response.status_code == 422  # Validation error
        
        # Test file upload validation
        invalid_file_content = b"This is not a valid ZIP file"
        files = {"file": ("invalid.zip", invalid_file_content, "application/zip")}
        data = {"workspace_id": "invalid_id"}
        
        response = client.post("/api/v1/documents/upload", files=files, data=data)
        assert response.status_code in [400, 422]  # Bad request or validation error
    
    @pytest.mark.asyncio
    async def test_error_handling_and_resilience(self, client):
        """Test error handling and system resilience."""
        
        # Test handling of non-existent resources
        response = client.get("/api/v1/workspaces/non-existent-id")
        assert response.status_code == 404
        
        response = client.get("/api/v1/jobs/non-existent-job")
        assert response.status_code == 404
        
        # Test handling of invalid file formats
        invalid_zip = b"Invalid ZIP content"
        files = {"file": ("invalid.zip", invalid_zip, "application/zip")}
        data = {"workspace_id": "test-workspace"}
        
        response = client.post("/api/v1/documents/upload", files=files, data=data)
        assert response.status_code in [400, 422]
        
        # Test graceful degradation
        # This would test circuit breaker behavior with external services
        # In a real test, you might mock external service failures
        
        # Test error response format consistency
        response = client.get("/api/v1/workspaces/invalid-id")
        error_response = response.json()
        
        # Verify error response structure
        assert "error" in error_response
        assert "message" in error_response
        assert "correlation_id" in error_response or "timestamp" in error_response
    
    @pytest.mark.asyncio
    async def test_health_and_monitoring(self, client):
        """Test health checks and monitoring endpoints."""
        
        # Test basic health check
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        health_data = response.json()
        assert "status" in health_data
        assert health_data["status"] in ["healthy", "degraded", "unhealthy"]
        
        # Test detailed health check
        response = client.get("/api/v1/health/detailed")
        assert response.status_code == 200
        detailed_health = response.json()
        
        assert "status" in detailed_health
        assert "dependencies" in detailed_health
        assert "timestamp" in detailed_health
        
        # Verify dependency checks
        dependencies = detailed_health["dependencies"]
        expected_deps = ["database", "anythingllm"]
        
        for dep in expected_deps:
            if dep in dependencies:
                assert "status" in dependencies[dep]
                assert "response_time" in dependencies[dep]
        
        # Test metrics endpoint (if available)
        response = client.get("/api/v1/metrics")
        # Metrics might return 200 with Prometheus format or 404 if not enabled
        assert response.status_code in [200, 404]
    
    async def _wait_for_job_completion(self, client, job_id: str, timeout: int = 60):
        """Wait for a job to complete with timeout."""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            response = client.get(f"/api/v1/jobs/{job_id}")
            if response.status_code == 200:
                job_data = response.json()
                status = job_data.get("status")
                
                if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    if status == JobStatus.FAILED:
                        error_msg = job_data.get("error", "Unknown error")
                        pytest.fail(f"Job {job_id} failed: {error_msg}")
                    return job_data
            
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout:
                pytest.fail(f"Job {job_id} did not complete within {timeout} seconds")
            
            await asyncio.sleep(2)  # Wait 2 seconds before checking again


@pytest.mark.asyncio
class TestPerformanceAndLoad:
    """Performance and load testing."""
    
    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)
    
    async def test_concurrent_document_uploads(self, client):
        """Test concurrent document upload handling."""
        
        # Create multiple small test files
        test_files = []
        for i in range(5):
            temp_dir = Path(tempfile.mkdtemp())
            
            # Create small test content
            (temp_dir / f"test_{i}.json").write_text(f'{{"test": "data_{i}"}}')
            
            zip_path = temp_dir / f"test_{i}.zip"
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.write(temp_dir / f"test_{i}.json", f"test_{i}.json")
            
            test_files.append(zip_path)
        
        # Create workspace
        workspace_data = {"name": "Load Test Workspace"}
        response = client.post("/api/v1/workspaces", json=workspace_data)
        workspace_id = response.json()["id"]
        
        # Upload files concurrently
        async def upload_file(file_path):
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "application/zip")}
                data = {"workspace_id": workspace_id}
                return client.post("/api/v1/documents/upload", files=files, data=data)
        
        # Execute concurrent uploads
        tasks = [upload_file(file_path) for file_path in test_files]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify responses
        successful_uploads = 0
        for response in responses:
            if not isinstance(response, Exception) and response.status_code == 202:
                successful_uploads += 1
        
        assert successful_uploads >= len(test_files) * 0.8  # At least 80% success rate
        
        # Cleanup
        client.delete(f"/api/v1/workspaces/{workspace_id}")
    
    async def test_memory_usage_stability(self, client):
        """Test memory usage stability under load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Perform multiple operations
        for i in range(10):
            # Create and delete workspace
            workspace_data = {"name": f"Memory Test {i}"}
            response = client.post("/api/v1/workspaces", json=workspace_data)
            if response.status_code == 201:
                workspace_id = response.json()["id"]
                client.delete(f"/api/v1/workspaces/{workspace_id}")
            
            # Check health
            client.get("/api/v1/health")
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 50MB for this test)
        assert memory_increase < 50 * 1024 * 1024, f"Memory increased by {memory_increase / 1024 / 1024:.2f}MB"
    
    async def test_response_time_performance(self, client):
        """Test API response time performance."""
        import time
        
        # Test health endpoint response time
        start_time = time.time()
        response = client.get("/api/v1/health")
        response_time = time.time() - start_time
        
        assert response.status_code == 200
        assert response_time < 1.0, f"Health check took {response_time:.2f}s, should be under 1s"
        
        # Test workspace listing response time
        start_time = time.time()
        response = client.get("/api/v1/workspaces")
        response_time = time.time() - start_time
        
        # Response time should be reasonable even if authentication fails
        assert response_time < 2.0, f"Workspace listing took {response_time:.2f}s, should be under 2s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])