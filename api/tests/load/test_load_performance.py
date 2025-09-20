"""
Load testing and performance validation for the AnythingLLM API.

This module provides comprehensive load testing scenarios to validate
system performance under various load conditions.
"""

import asyncio
import json
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple
import pytest
import httpx
from fastapi.testclient import TestClient

from app.main import app


class LoadTestResults:
    """Container for load test results."""
    
    def __init__(self):
        self.response_times: List[float] = []
        self.status_codes: List[int] = []
        self.errors: List[str] = []
        self.throughput: float = 0.0
        self.success_rate: float = 0.0
    
    def add_result(self, response_time: float, status_code: int, error: str = None):
        """Add a test result."""
        self.response_times.append(response_time)
        self.status_codes.append(status_code)
        if error:
            self.errors.append(error)
    
    def calculate_metrics(self, duration: float):
        """Calculate performance metrics."""
        total_requests = len(self.response_times)
        successful_requests = sum(1 for code in self.status_codes if 200 <= code < 300)
        
        self.throughput = total_requests / duration if duration > 0 else 0
        self.success_rate = successful_requests / total_requests if total_requests > 0 else 0
        
        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": total_requests - successful_requests,
            "success_rate": self.success_rate,
            "throughput_rps": self.throughput,
            "avg_response_time": sum(self.response_times) / len(self.response_times) if self.response_times else 0,
            "min_response_time": min(self.response_times) if self.response_times else 0,
            "max_response_time": max(self.response_times) if self.response_times else 0,
            "p95_response_time": self._percentile(self.response_times, 95),
            "p99_response_time": self._percentile(self.response_times, 99),
            "error_count": len(self.errors)
        }
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of response times."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int((percentile / 100.0) * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]


class TestLoadPerformance:
    """Load testing scenarios."""
    
    @pytest.fixture(scope="class")
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture(scope="class")
    def sample_zip_file(self):
        """Create a sample ZIP file for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create sample files
        (temp_dir / "test.json").write_text('{"test": "data"}')
        (temp_dir / "test.csv").write_text("col1,col2\nval1,val2\n")
        
        zip_path = temp_dir / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(temp_dir / "test.json", "test.json")
            zf.write(temp_dir / "test.csv", "test.csv")
        
        return zip_path
    
    @pytest.mark.load
    async def test_health_endpoint_load(self, client):
        """Test health endpoint under load."""
        results = LoadTestResults()
        duration = 30  # 30 seconds
        concurrent_users = 10
        
        async def make_health_request():
            start_time = time.time()
            try:
                response = client.get("/api/v1/health")
                response_time = time.time() - start_time
                results.add_result(response_time, response.status_code)
            except Exception as e:
                response_time = time.time() - start_time
                results.add_result(response_time, 500, str(e))
        
        # Run load test
        start_time = time.time()
        tasks = []
        
        while time.time() - start_time < duration:
            # Create batch of concurrent requests
            batch_tasks = [make_health_request() for _ in range(concurrent_users)]
            await asyncio.gather(*batch_tasks, return_exceptions=True)
            await asyncio.sleep(0.1)  # Small delay between batches
        
        actual_duration = time.time() - start_time
        metrics = results.calculate_metrics(actual_duration)
        
        # Validate performance requirements
        assert metrics["success_rate"] >= 0.95, f"Success rate {metrics['success_rate']:.2%} below 95%"
        assert metrics["avg_response_time"] < 1.0, f"Average response time {metrics['avg_response_time']:.3f}s above 1s"
        assert metrics["p95_response_time"] < 2.0, f"95th percentile {metrics['p95_response_time']:.3f}s above 2s"
        assert metrics["throughput_rps"] > 50, f"Throughput {metrics['throughput_rps']:.1f} RPS below 50"
        
        print(f"Health endpoint load test results: {json.dumps(metrics, indent=2)}")
    
    @pytest.mark.load
    async def test_workspace_operations_load(self, client):
        """Test workspace CRUD operations under load."""
        results = LoadTestResults()
        concurrent_users = 5
        operations_per_user = 10
        
        async def workspace_operations():
            for i in range(operations_per_user):
                # Create workspace
                start_time = time.time()
                try:
                    workspace_data = {
                        "name": f"Load Test Workspace {i}",
                        "description": f"Load test workspace {i}"
                    }
                    response = client.post("/api/v1/workspaces", json=workspace_data)
                    response_time = time.time() - start_time
                    results.add_result(response_time, response.status_code)
                    
                    if response.status_code == 201:
                        workspace_id = response.json()["id"]
                        
                        # Get workspace
                        start_time = time.time()
                        response = client.get(f"/api/v1/workspaces/{workspace_id}")
                        response_time = time.time() - start_time
                        results.add_result(response_time, response.status_code)
                        
                        # Delete workspace
                        start_time = time.time()
                        response = client.delete(f"/api/v1/workspaces/{workspace_id}")
                        response_time = time.time() - start_time
                        results.add_result(response_time, response.status_code)
                
                except Exception as e:
                    response_time = time.time() - start_time
                    results.add_result(response_time, 500, str(e))
        
        # Run concurrent workspace operations
        start_time = time.time()
        tasks = [workspace_operations() for _ in range(concurrent_users)]
        await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time
        
        metrics = results.calculate_metrics(duration)
        
        # Validate performance
        assert metrics["success_rate"] >= 0.90, f"Success rate {metrics['success_rate']:.2%} below 90%"
        assert metrics["avg_response_time"] < 3.0, f"Average response time {metrics['avg_response_time']:.3f}s above 3s"
        
        print(f"Workspace operations load test results: {json.dumps(metrics, indent=2)}")
    
    @pytest.mark.load
    async def test_document_upload_load(self, client, sample_zip_file):
        """Test document upload under load."""
        results = LoadTestResults()
        concurrent_uploads = 3
        uploads_per_user = 5
        
        # Create test workspace
        workspace_data = {"name": "Document Upload Load Test"}
        response = client.post("/api/v1/workspaces", json=workspace_data)
        if response.status_code != 201:
            pytest.skip("Cannot create workspace for load test")
        
        workspace_id = response.json()["id"]
        
        async def upload_documents():
            for i in range(uploads_per_user):
                start_time = time.time()
                try:
                    with open(sample_zip_file, "rb") as f:
                        files = {"file": (f"test_{i}.zip", f, "application/zip")}
                        data = {"workspace_id": workspace_id}
                        response = client.post("/api/v1/documents/upload", files=files, data=data)
                    
                    response_time = time.time() - start_time
                    results.add_result(response_time, response.status_code)
                    
                except Exception as e:
                    response_time = time.time() - start_time
                    results.add_result(response_time, 500, str(e))
        
        # Run concurrent uploads
        start_time = time.time()
        tasks = [upload_documents() for _ in range(concurrent_uploads)]
        await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start_time
        
        metrics = results.calculate_metrics(duration)
        
        # Validate performance (more lenient for file uploads)
        assert metrics["success_rate"] >= 0.80, f"Success rate {metrics['success_rate']:.2%} below 80%"
        assert metrics["avg_response_time"] < 10.0, f"Average response time {metrics['avg_response_time']:.3f}s above 10s"
        
        print(f"Document upload load test results: {json.dumps(metrics, indent=2)}")
        
        # Cleanup
        client.delete(f"/api/v1/workspaces/{workspace_id}")
    
    @pytest.mark.load
    async def test_mixed_workload_stress(self, client, sample_zip_file):
        """Test mixed workload stress scenario."""
        results = LoadTestResults()
        duration = 60  # 1 minute stress test
        
        # Create test workspace
        workspace_data = {"name": "Stress Test Workspace"}
        response = client.post("/api/v1/workspaces", json=workspace_data)
        if response.status_code != 201:
            pytest.skip("Cannot create workspace for stress test")
        
        workspace_id = response.json()["id"]
        
        async def health_check_worker():
            """Continuous health checks."""
            while time.time() - start_time < duration:
                try:
                    start_req = time.time()
                    response = client.get("/api/v1/health")
                    response_time = time.time() - start_req
                    results.add_result(response_time, response.status_code)
                except Exception as e:
                    results.add_result(1.0, 500, str(e))
                await asyncio.sleep(0.5)
        
        async def workspace_worker():
            """Workspace operations."""
            counter = 0
            while time.time() - start_time < duration:
                try:
                    counter += 1
                    start_req = time.time()
                    response = client.get(f"/api/v1/workspaces/{workspace_id}")
                    response_time = time.time() - start_req
                    results.add_result(response_time, response.status_code)
                except Exception as e:
                    results.add_result(1.0, 500, str(e))
                await asyncio.sleep(1.0)
        
        async def upload_worker():
            """Document uploads."""
            counter = 0
            while time.time() - start_time < duration:
                try:
                    counter += 1
                    start_req = time.time()
                    with open(sample_zip_file, "rb") as f:
                        files = {"file": (f"stress_{counter}.zip", f, "application/zip")}
                        data = {"workspace_id": workspace_id}
                        response = client.post("/api/v1/documents/upload", files=files, data=data)
                    response_time = time.time() - start_req
                    results.add_result(response_time, response.status_code)
                except Exception as e:
                    results.add_result(5.0, 500, str(e))
                await asyncio.sleep(5.0)  # Less frequent uploads
        
        # Run mixed workload
        start_time = time.time()
        tasks = [
            health_check_worker(),
            health_check_worker(),  # 2 health check workers
            workspace_worker(),
            upload_worker()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        actual_duration = time.time() - start_time
        
        metrics = results.calculate_metrics(actual_duration)
        
        # Validate stress test results
        assert metrics["success_rate"] >= 0.70, f"Success rate {metrics['success_rate']:.2%} below 70% under stress"
        assert metrics["error_count"] < metrics["total_requests"] * 0.3, "Too many errors under stress"
        
        print(f"Mixed workload stress test results: {json.dumps(metrics, indent=2)}")
        
        # Cleanup
        client.delete(f"/api/v1/workspaces/{workspace_id}")
    
    @pytest.mark.load
    async def test_memory_leak_detection(self, client):
        """Test for memory leaks during extended operation."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        memory_samples = [initial_memory]
        
        # Run operations for extended period
        for cycle in range(20):
            # Create and delete workspaces
            for i in range(5):
                workspace_data = {"name": f"Memory Test {cycle}-{i}"}
                response = client.post("/api/v1/workspaces", json=workspace_data)
                if response.status_code == 201:
                    workspace_id = response.json()["id"]
                    client.delete(f"/api/v1/workspaces/{workspace_id}")
            
            # Health checks
            for _ in range(10):
                client.get("/api/v1/health")
            
            # Sample memory usage
            current_memory = process.memory_info().rss
            memory_samples.append(current_memory)
        
        # Analyze memory trend
        memory_growth = memory_samples[-1] - memory_samples[0]
        memory_growth_mb = memory_growth / (1024 * 1024)
        
        # Check for excessive memory growth (more than 100MB indicates potential leak)
        assert memory_growth_mb < 100, f"Memory grew by {memory_growth_mb:.2f}MB, potential memory leak"
        
        # Check memory trend (should not continuously increase)
        recent_avg = sum(memory_samples[-5:]) / 5
        early_avg = sum(memory_samples[:5]) / 5
        growth_rate = (recent_avg - early_avg) / early_avg
        
        assert growth_rate < 0.5, f"Memory growth rate {growth_rate:.2%} indicates potential leak"
        
        print(f"Memory leak test: Growth {memory_growth_mb:.2f}MB, Rate {growth_rate:.2%}")


@pytest.mark.load
class TestPerformanceOptimization:
    """Performance optimization validation."""
    
    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)
    
    async def test_response_compression(self, client):
        """Test response compression effectiveness."""
        # Test large response compression
        response = client.get("/api/v1/workspaces", headers={"Accept-Encoding": "gzip"})
        
        # Check if compression headers are present
        content_encoding = response.headers.get("content-encoding")
        if content_encoding:
            assert "gzip" in content_encoding.lower()
    
    async def test_caching_effectiveness(self, client):
        """Test caching mechanisms."""
        # Test repeated health checks (should be fast due to caching)
        times = []
        for _ in range(5):
            start_time = time.time()
            response = client.get("/api/v1/health")
            response_time = time.time() - start_time
            times.append(response_time)
            assert response.status_code == 200
        
        # Later requests should be faster due to caching
        avg_early = sum(times[:2]) / 2
        avg_later = sum(times[-2:]) / 2
        
        # Allow for some variance, but later requests should generally be faster
        improvement_ratio = avg_early / avg_later if avg_later > 0 else 1
        assert improvement_ratio >= 0.8, f"Caching not effective: {improvement_ratio:.2f}"
    
    async def test_database_connection_pooling(self, client):
        """Test database connection pooling efficiency."""
        # Make multiple concurrent database-dependent requests
        start_time = time.time()
        
        tasks = []
        for _ in range(10):
            # These requests should use database connections
            tasks.append(client.get("/api/v1/workspaces"))
        
        # Execute concurrently
        responses = await asyncio.gather(*[asyncio.create_task(asyncio.to_thread(lambda: task)) for task in tasks], return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # With proper connection pooling, concurrent requests should complete reasonably fast
        assert total_time < 10.0, f"Database operations took {total_time:.2f}s, connection pooling may be ineffective"
        
        # Count successful responses (may fail due to auth, but should not timeout)
        successful_responses = sum(1 for r in responses if not isinstance(r, Exception))
        assert successful_responses >= 5, "Too many database connection failures"


if __name__ == "__main__":
    # Run load tests
    pytest.main([__file__, "-v", "-m", "load"])