"""Performance tests for concurrent operations."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient

from tests.fixtures.mock_data import mock_data


class TestConcurrentOperations:
    """Test cases for concurrent operations performance."""

    @pytest.fixture
    def auth_headers(self):
        """Authentication headers for requests."""
        return {"Authorization": "Bearer test-token"}

    @pytest.mark.asyncio
    async def test_concurrent_document_uploads(
        self,
        async_client: AsyncClient,
        auth_headers,
        tmp_path,
    ):
        """Test concurrent document upload performance."""
        # Create multiple test ZIP files
        zip_files = []
        for i in range(10):
            zip_path = mock_data.create_test_zip_file(tmp_path, f"concurrent_test_{i}.zip")
            zip_files.append(zip_path)
        
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload:
            mock_upload.return_value = mock_data.create_mock_job()
            
            start_time = time.time()
            
            # Upload files concurrently
            async def upload_file(zip_path):
                with open(zip_path, 'rb') as f:
                    return await async_client.post(
                        "/api/v1/documents/upload",
                        headers=auth_headers,
                        files={"file": (zip_path.name, f, "application/zip")},
                        data={"workspace_id": f"ws_{zip_path.stem}"},
                    )
            
            tasks = [upload_file(zip_path) for zip_path in zip_files]
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == 10
        assert all(r.status_code == 202 for r in responses)
        assert total_time < 5.0  # Should complete within 5 seconds
        
        # Calculate throughput
        throughput = len(responses) / total_time
        assert throughput > 2.0  # At least 2 uploads per second

    @pytest.mark.asyncio
    async def test_concurrent_job_status_queries(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test concurrent job status query performance."""
        job_ids = [f"job_{i}" for i in range(50)]
        
        with patch('app.services.job_service.JobService.get_job') as mock_get_job:
            mock_get_job.return_value = mock_data.create_mock_job()
            
            start_time = time.time()
            
            # Query job statuses concurrently
            async def get_job_status(job_id):
                return await async_client.get(
                    f"/api/v1/documents/jobs/{job_id}",
                    headers=auth_headers,
                )
            
            tasks = [get_job_status(job_id) for job_id in job_ids]
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == 50
        assert all(r.status_code == 200 for r in responses)
        assert total_time < 3.0  # Should complete within 3 seconds
        
        # Calculate throughput
        throughput = len(responses) / total_time
        assert throughput > 15.0  # At least 15 queries per second

    @pytest.mark.asyncio
    async def test_concurrent_workspace_operations(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test concurrent workspace operations performance."""
        workspace_count = 20
        
        with patch('app.services.workspace_service.WorkspaceService.create_workspace') as mock_create:
            mock_create.return_value = mock_data.create_mock_workspace()
            
            start_time = time.time()
            
            # Create workspaces concurrently
            async def create_workspace(i):
                workspace_data = {
                    "name": f"Concurrent Workspace {i}",
                    "description": f"Test workspace {i}",
                    "llm_config": {
                        "provider": "openai",
                        "model": "gpt-3.5-turbo",
                        "temperature": 0.7,
                        "max_tokens": 1000,
                        "timeout": 30,
                    },
                }
                return await async_client.post(
                    "/api/v1/workspaces",
                    headers=auth_headers,
                    json=workspace_data,
                )
            
            tasks = [create_workspace(i) for i in range(workspace_count)]
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == workspace_count
        assert all(r.status_code == 201 for r in responses)
        assert total_time < 10.0  # Should complete within 10 seconds

    @pytest.mark.asyncio
    async def test_concurrent_question_processing(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test concurrent question processing performance."""
        question_sets = []
        for i in range(5):
            questions = mock_data.create_sample_questions()
            question_data = {
                "workspace_id": f"ws_{i}",
                "questions": [q.model_dump() for q in questions],
                "llm_config": {
                    "provider": "openai",
                    "model": "gpt-3.5-turbo",
                    "temperature": 0.7,
                    "max_tokens": 1000,
                    "timeout": 30,
                },
                "export_format": "json",
            }
            question_sets.append(question_data)
        
        with patch('app.services.question_service.QuestionService.execute_questions') as mock_execute:
            mock_execute.return_value = mock_data.create_mock_job()
            
            start_time = time.time()
            
            # Process question sets concurrently
            async def process_questions(question_data):
                return await async_client.post(
                    "/api/v1/questions/execute",
                    headers=auth_headers,
                    json=question_data,
                )
            
            tasks = [process_questions(qs) for qs in question_sets]
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == 5
        assert all(r.status_code == 202 for r in responses)
        assert total_time < 8.0  # Should complete within 8 seconds

    @pytest.mark.asyncio
    async def test_high_load_job_listing(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test job listing performance under high load."""
        concurrent_requests = 100
        
        with patch('app.services.job_service.JobService.list_jobs') as mock_list:
            from app.models.pydantic_models import PaginatedJobs
            mock_list.return_value = PaginatedJobs(
                jobs=[mock_data.create_mock_job() for _ in range(10)],
                total=1000,
                page=1,
                per_page=10,
                total_pages=100,
            )
            
            start_time = time.time()
            
            # Make concurrent job listing requests
            async def list_jobs():
                return await async_client.get(
                    "/api/v1/documents/jobs",
                    headers=auth_headers,
                    params={"page": 1, "per_page": 10},
                )
            
            tasks = [list_jobs() for _ in range(concurrent_requests)]
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == concurrent_requests
        assert all(r.status_code == 200 for r in responses)
        assert total_time < 10.0  # Should complete within 10 seconds
        
        # Calculate throughput
        throughput = len(responses) / total_time
        assert throughput > 10.0  # At least 10 requests per second

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test memory usage under concurrent load."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Simulate high concurrent load
        with patch('app.services.job_service.JobService.get_job') as mock_get_job:
            mock_get_job.return_value = mock_data.create_mock_job()
            
            async def make_request():
                return await async_client.get(
                    "/api/v1/documents/jobs/test_job",
                    headers=auth_headers,
                )
            
            # Make 200 concurrent requests
            tasks = [make_request() for _ in range(200)]
            responses = await asyncio.gather(*tasks)
            
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory
        
        # Memory usage assertions
        assert len(responses) == 200
        assert all(r.status_code == 200 for r in responses)
        assert memory_increase < 100  # Should not increase by more than 100MB

    @pytest.mark.asyncio
    async def test_database_connection_pool_performance(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test database connection pool performance under load."""
        concurrent_db_operations = 50
        
        with patch('app.repositories.job_repository.JobRepository.get_by_id') as mock_get:
            mock_get.return_value = mock_data.create_mock_job()
            
            start_time = time.time()
            
            # Simulate concurrent database operations
            async def db_operation():
                return await async_client.get(
                    f"/api/v1/documents/jobs/job_{time.time()}",
                    headers=auth_headers,
                )
            
            tasks = [db_operation() for _ in range(concurrent_db_operations)]
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == concurrent_db_operations
        assert total_time < 5.0  # Should complete within 5 seconds

    @pytest.mark.asyncio
    async def test_rate_limiting_performance(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test rate limiting performance and behavior."""
        requests_per_second = 20
        duration_seconds = 3
        total_requests = requests_per_second * duration_seconds
        
        start_time = time.time()
        responses = []
        
        # Make requests at a controlled rate
        for i in range(total_requests):
            response = await async_client.get(
                "/api/v1/health",
                headers=auth_headers,
            )
            responses.append(response)
            
            # Control request rate
            if i < total_requests - 1:
                await asyncio.sleep(1.0 / requests_per_second)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == total_requests
        assert abs(total_time - duration_seconds) < 1.0  # Within 1 second of expected
        
        # Check for rate limiting responses
        success_responses = [r for r in responses if r.status_code == 200]
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        
        # Should have mostly successful responses with some rate limiting
        assert len(success_responses) > total_requests * 0.8  # At least 80% success

    @pytest.mark.asyncio
    async def test_error_handling_performance(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test error handling performance under load."""
        error_requests = 50
        
        start_time = time.time()
        
        # Make requests that will cause errors
        async def error_request():
            return await async_client.get(
                "/api/v1/documents/jobs/nonexistent_job",
                headers=auth_headers,
            )
        
        tasks = [error_request() for _ in range(error_requests)]
        responses = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == error_requests
        assert all(r.status_code == 404 for r in responses)
        assert total_time < 3.0  # Error handling should be fast

    @pytest.mark.asyncio
    async def test_mixed_operation_performance(
        self,
        async_client: AsyncClient,
        auth_headers,
        tmp_path,
    ):
        """Test performance with mixed operations (realistic load)."""
        # Create test data
        zip_file = mock_data.create_test_zip_file(tmp_path)
        
        with patch('app.services.document_service.DocumentService.upload_documents') as mock_upload, \
             patch('app.services.job_service.JobService.get_job') as mock_get_job, \
             patch('app.services.workspace_service.WorkspaceService.list_workspaces') as mock_list_ws:
            
            mock_upload.return_value = mock_data.create_mock_job()
            mock_get_job.return_value = mock_data.create_mock_job()
            mock_list_ws.return_value = [mock_data.create_mock_workspace()]
            
            start_time = time.time()
            
            # Mix of different operations
            async def upload_operation():
                with open(zip_file, 'rb') as f:
                    return await async_client.post(
                        "/api/v1/documents/upload",
                        headers=auth_headers,
                        files={"file": (zip_file.name, f, "application/zip")},
                        data={"workspace_id": "ws_mixed_test"},
                    )
            
            async def status_operation():
                return await async_client.get(
                    "/api/v1/documents/jobs/mixed_test_job",
                    headers=auth_headers,
                )
            
            async def list_operation():
                return await async_client.get(
                    "/api/v1/workspaces",
                    headers=auth_headers,
                )
            
            # Create mixed workload
            tasks = []
            for i in range(30):
                if i % 3 == 0:
                    tasks.append(upload_operation())
                elif i % 3 == 1:
                    tasks.append(status_operation())
                else:
                    tasks.append(list_operation())
            
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Performance assertions
        assert len(responses) == 30
        assert total_time < 8.0  # Mixed operations should complete within 8 seconds
        
        # Check response distribution
        upload_responses = [r for r in responses if r.status_code == 202]
        status_responses = [r for r in responses if r.status_code == 200]
        
        assert len(upload_responses) == 10  # Upload operations
        assert len(status_responses) == 20  # Status and list operations

    @pytest.mark.asyncio
    async def test_scalability_limits(
        self,
        async_client: AsyncClient,
        auth_headers,
    ):
        """Test system behavior at scalability limits."""
        # Test with very high concurrent load
        extreme_load = 500
        
        with patch('app.services.job_service.JobService.list_jobs') as mock_list:
            from app.models.pydantic_models import PaginatedJobs
            mock_list.return_value = PaginatedJobs(
                jobs=[],
                total=0,
                page=1,
                per_page=10,
                total_pages=0,
            )
            
            start_time = time.time()
            
            async def light_request():
                return await async_client.get(
                    "/api/v1/documents/jobs",
                    headers=auth_headers,
                    params={"per_page": 1},  # Minimal response
                )
            
            # Use semaphore to control concurrency
            semaphore = asyncio.Semaphore(100)  # Limit to 100 concurrent
            
            async def controlled_request():
                async with semaphore:
                    return await light_request()
            
            tasks = [controlled_request() for _ in range(extreme_load)]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            end_time = time.time()
            total_time = end_time - start_time
        
        # Analyze results
        successful_responses = [r for r in responses if hasattr(r, 'status_code') and r.status_code == 200]
        error_responses = [r for r in responses if isinstance(r, Exception)]
        
        # System should handle load gracefully
        success_rate = len(successful_responses) / len(responses)
        assert success_rate > 0.8  # At least 80% success rate
        assert total_time < 30.0  # Should complete within 30 seconds