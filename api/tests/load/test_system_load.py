"""
System load testing for AnythingLLM API.

This module contains comprehensive load tests to validate system performance
under various load conditions and stress scenarios.
"""

import asyncio
import time
import statistics
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor
import pytest
from httpx import AsyncClient

from tests.fixtures.mock_data import mock_files, mock_data


class LoadTestMetrics:
    """Collect and analyze load test metrics."""
    
    def __init__(self):
        self.response_times: List[float] = []
        self.status_codes: List[int] = []
        self.errors: List[str] = []
        self.throughput_data: List[Tuple[float, int]] = []  # (timestamp, requests_completed)
        self.start_time: float = 0
        self.end_time: float = 0
    
    def add_response(self, response_time: float, status_code: int, error: str = None):
        """Add a response measurement."""
        self.response_times.append(response_time)
        self.status_codes.append(status_code)
        if error:
            self.errors.append(error)
    
    def add_throughput_point(self, timestamp: float, requests_completed: int):
        """Add a throughput measurement point."""
        self.throughput_data.append((timestamp, requests_completed))
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test summary statistics."""
        if not self.response_times:
            return {"error": "No response data collected"}
        
        total_requests = len(self.response_times)
        successful_requests = sum(1 for code in self.status_codes if 200 <= code < 300)
        error_requests = sum(1 for code in self.status_codes if code >= 400)
        
        duration = self.end_time - self.start_time if self.end_time > self.start_time else 0
        
        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "error_requests": error_requests,
            "success_rate": successful_requests / total_requests if total_requests > 0 else 0,
            "error_rate": error_requests / total_requests if total_requests > 0 else 0,
            "duration_seconds": duration,
            "requests_per_second": total_requests / duration if duration > 0 else 0,
            "response_times": {
                "min": min(self.response_times),
                "max": max(self.response_times),
                "mean": statistics.mean(self.response_times),
                "median": statistics.median(self.response_times),
                "p95": self._percentile(self.response_times, 95),
                "p99": self._percentile(self.response_times, 99),
            },
            "status_code_distribution": self._count_status_codes(),
            "error_count": len(self.errors),
            "unique_errors": len(set(self.errors)),
        }
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of response times."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int((percentile / 100) * len(sorted_data))
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _count_status_codes(self) -> Dict[int, int]:
        """Count occurrences of each status code."""
        counts = {}
        for code in self.status_codes:
            counts[code] = counts.get(code, 0) + 1
        return counts


class LoadTestScenarios:
    """Load testing scenarios for different API operations."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.auth_headers = {"Authorization": "Bearer test-token"}
    
    async def scenario_document_upload_load(
        self, 
        concurrent_users: int = 10,
        requests_per_user: int = 5,
        ramp_up_time: int = 10
    ) -> LoadTestMetrics:
        """Test document upload under load."""
        metrics = LoadTestMetrics()
        metrics.start_time = time.time()
        
        # Create test workspace
        async with AsyncClient(base_url=self.base_url) as client:
            workspace_response = await client.post(
                "/api/v1/workspaces",
                json={
                    "name": "Load Test Workspace",
                    "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
                },
                headers=self.auth_headers
            )
            workspace_id = workspace_response.json()["id"]
        
        async def user_upload_session(user_id: int):
            """Simulate a user uploading multiple documents."""
            async with AsyncClient(base_url=self.base_url) as client:
                for request_num in range(requests_per_user):
                    try:
                        # Create test document
                        with tempfile.TemporaryDirectory() as temp_dir:
                            test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=2)
                            zip_path = mock_files.create_zip_from_files(
                                test_files, 
                                Path(temp_dir) / f"user_{user_id}_req_{request_num}.zip"
                            )
                            
                            with open(zip_path, "rb") as zip_file:
                                start_time = time.time()
                                response = await client.post(
                                    "/api/v1/documents/upload",
                                    files={"file": (f"test_{user_id}_{request_num}.zip", zip_file, "application/zip")},
                                    data={"workspace_id": workspace_id},
                                    headers=self.auth_headers
                                )
                                response_time = time.time() - start_time
                                
                                metrics.add_response(response_time, response.status_code)
                                
                    except Exception as e:
                        metrics.add_response(0, 500, str(e))
        
        # Ramp up users gradually
        tasks = []
        for user_id in range(concurrent_users):
            # Stagger user start times
            await asyncio.sleep(ramp_up_time / concurrent_users)
            task = asyncio.create_task(user_upload_session(user_id))
            tasks.append(task)
        
        # Wait for all users to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        metrics.end_time = time.time()
        
        # Cleanup workspace
        async with AsyncClient(base_url=self.base_url) as client:
            await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=self.auth_headers)
        
        return metrics
    
    async def scenario_question_processing_load(
        self,
        concurrent_users: int = 5,
        questions_per_user: int = 10,
        ramp_up_time: int = 5
    ) -> LoadTestMetrics:
        """Test question processing under load."""
        metrics = LoadTestMetrics()
        metrics.start_time = time.time()
        
        # Setup workspace with documents
        async with AsyncClient(base_url=self.base_url) as client:
            # Create workspace
            workspace_response = await client.post(
                "/api/v1/workspaces",
                json={
                    "name": "Question Load Test Workspace",
                    "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
                },
                headers=self.auth_headers
            )
            workspace_id = workspace_response.json()["id"]
            
            # Upload documents
            with tempfile.TemporaryDirectory() as temp_dir:
                test_files = mock_files.create_test_document_set(Path(temp_dir))
                zip_path = mock_files.create_zip_from_files(test_files, Path(temp_dir) / "setup.zip")
                
                with open(zip_path, "rb") as zip_file:
                    await client.post(
                        "/api/v1/documents/upload",
                        files={"file": ("setup.zip", zip_file, "application/zip")},
                        data={"workspace_id": workspace_id},
                        headers=self.auth_headers
                    )
        
        # Wait for document processing
        await asyncio.sleep(10)
        
        async def user_question_session(user_id: int):
            """Simulate a user asking multiple questions."""
            async with AsyncClient(base_url=self.base_url) as client:
                for question_num in range(questions_per_user):
                    try:
                        questions_data = {
                            "workspace_id": workspace_id,
                            "questions": [
                                {
                                    "id": f"user_{user_id}_q_{question_num}",
                                    "text": f"User {user_id} Question {question_num}: What is the contract value?",
                                    "expected_fragments": ["value", "contract", "amount"]
                                }
                            ]
                        }
                        
                        start_time = time.time()
                        response = await client.post(
                            "/api/v1/questions/execute",
                            json=questions_data,
                            headers=self.auth_headers
                        )
                        response_time = time.time() - start_time
                        
                        metrics.add_response(response_time, response.status_code)
                        
                    except Exception as e:
                        metrics.add_response(0, 500, str(e))
        
        # Ramp up users
        tasks = []
        for user_id in range(concurrent_users):
            await asyncio.sleep(ramp_up_time / concurrent_users)
            task = asyncio.create_task(user_question_session(user_id))
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        metrics.end_time = time.time()
        
        # Cleanup
        async with AsyncClient(base_url=self.base_url) as client:
            await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=self.auth_headers)
        
        return metrics
    
    async def scenario_mixed_workload(
        self,
        duration_seconds: int = 60,
        concurrent_users: int = 20
    ) -> LoadTestMetrics:
        """Test mixed workload scenario."""
        metrics = LoadTestMetrics()
        metrics.start_time = time.time()
        
        # Setup test workspace
        async with AsyncClient(base_url=self.base_url) as client:
            workspace_response = await client.post(
                "/api/v1/workspaces",
                json={
                    "name": "Mixed Load Test Workspace",
                    "llm_config": {"provider": "openai", "model": "gpt-3.5-turbo"}
                },
                headers=self.auth_headers
            )
            workspace_id = workspace_response.json()["id"]
        
        async def mixed_user_session(user_id: int):
            """Simulate mixed user behavior."""
            async with AsyncClient(base_url=self.base_url) as client:
                session_end = time.time() + duration_seconds
                request_count = 0
                
                while time.time() < session_end:
                    try:
                        # Randomly choose operation type
                        import random
                        operation = random.choice([
                            "list_workspaces",
                            "get_workspace", 
                            "list_jobs",
                            "health_check",
                            "upload_document",
                            "execute_question"
                        ])
                        
                        start_time = time.time()
                        
                        if operation == "list_workspaces":
                            response = await client.get("/api/v1/workspaces", headers=self.auth_headers)
                        elif operation == "get_workspace":
                            response = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=self.auth_headers)
                        elif operation == "list_jobs":
                            response = await client.get("/api/v1/jobs", headers=self.auth_headers)
                        elif operation == "health_check":
                            response = await client.get("/api/v1/health", headers=self.auth_headers)
                        elif operation == "upload_document":
                            with tempfile.TemporaryDirectory() as temp_dir:
                                test_files = mock_files.create_test_document_set(Path(temp_dir), file_count=1)
                                zip_path = mock_files.create_zip_from_files(
                                    test_files, 
                                    Path(temp_dir) / f"mixed_{user_id}_{request_count}.zip"
                                )
                                
                                with open(zip_path, "rb") as zip_file:
                                    response = await client.post(
                                        "/api/v1/documents/upload",
                                        files={"file": (f"mixed_{user_id}_{request_count}.zip", zip_file, "application/zip")},
                                        data={"workspace_id": workspace_id},
                                        headers=self.auth_headers
                                    )
                        elif operation == "execute_question":
                            questions_data = {
                                "workspace_id": workspace_id,
                                "questions": [
                                    {
                                        "id": f"mixed_{user_id}_{request_count}",
                                        "text": "What is the main topic of the documents?",
                                        "expected_fragments": ["contract", "agreement"]
                                    }
                                ]
                            }
                            response = await client.post(
                                "/api/v1/questions/execute",
                                json=questions_data,
                                headers=self.auth_headers
                            )
                        
                        response_time = time.time() - start_time
                        metrics.add_response(response_time, response.status_code)
                        request_count += 1
                        
                        # Small delay between requests
                        await asyncio.sleep(random.uniform(0.1, 1.0))
                        
                    except Exception as e:
                        metrics.add_response(0, 500, str(e))
        
        # Start all user sessions
        tasks = [
            asyncio.create_task(mixed_user_session(user_id))
            for user_id in range(concurrent_users)
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        metrics.end_time = time.time()
        
        # Cleanup
        async with AsyncClient(base_url=self.base_url) as client:
            await client.delete(f"/api/v1/workspaces/{workspace_id}", headers=self.auth_headers)
        
        return metrics


class TestSystemLoad:
    """System load testing suite."""
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_document_upload_load(self):
        """Test document upload performance under load."""
        scenarios = LoadTestScenarios()
        
        # Light load test
        metrics = await scenarios.scenario_document_upload_load(
            concurrent_users=5,
            requests_per_user=3,
            ramp_up_time=5
        )
        
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["success_rate"] >= 0.9, f"Success rate too low: {summary['success_rate']}"
        assert summary["response_times"]["p95"] < 10.0, f"95th percentile too high: {summary['response_times']['p95']}"
        assert summary["requests_per_second"] > 0.5, f"Throughput too low: {summary['requests_per_second']}"
        
        print(f"Document Upload Load Test Results:")
        print(f"  Total Requests: {summary['total_requests']}")
        print(f"  Success Rate: {summary['success_rate']:.2%}")
        print(f"  Average Response Time: {summary['response_times']['mean']:.2f}s")
        print(f"  95th Percentile: {summary['response_times']['p95']:.2f}s")
        print(f"  Throughput: {summary['requests_per_second']:.2f} req/s")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_question_processing_load(self):
        """Test question processing performance under load."""
        scenarios = LoadTestScenarios()
        
        metrics = await scenarios.scenario_question_processing_load(
            concurrent_users=3,
            questions_per_user=5,
            ramp_up_time=3
        )
        
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["success_rate"] >= 0.8, f"Success rate too low: {summary['success_rate']}"
        assert summary["response_times"]["p95"] < 15.0, f"95th percentile too high: {summary['response_times']['p95']}"
        
        print(f"Question Processing Load Test Results:")
        print(f"  Total Requests: {summary['total_requests']}")
        print(f"  Success Rate: {summary['success_rate']:.2%}")
        print(f"  Average Response Time: {summary['response_times']['mean']:.2f}s")
        print(f"  95th Percentile: {summary['response_times']['p95']:.2f}s")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_mixed_workload_performance(self):
        """Test mixed workload performance."""
        scenarios = LoadTestScenarios()
        
        metrics = await scenarios.scenario_mixed_workload(
            duration_seconds=30,
            concurrent_users=10
        )
        
        summary = metrics.get_summary()
        
        # Performance assertions
        assert summary["success_rate"] >= 0.85, f"Success rate too low: {summary['success_rate']}"
        assert summary["response_times"]["mean"] < 5.0, f"Average response time too high: {summary['response_times']['mean']}"
        assert summary["requests_per_second"] > 2.0, f"Throughput too low: {summary['requests_per_second']}"
        
        print(f"Mixed Workload Test Results:")
        print(f"  Total Requests: {summary['total_requests']}")
        print(f"  Success Rate: {summary['success_rate']:.2%}")
        print(f"  Average Response Time: {summary['response_times']['mean']:.2f}s")
        print(f"  Throughput: {summary['requests_per_second']:.2f} req/s")
        print(f"  Status Code Distribution: {summary['status_code_distribution']}")
    
    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_stress_limits(self):
        """Test system behavior at stress limits."""
        scenarios = LoadTestScenarios()
        
        # Gradually increase load to find breaking point
        load_levels = [
            (5, 2),   # 5 users, 2 requests each
            (10, 3),  # 10 users, 3 requests each
            (20, 2),  # 20 users, 2 requests each
            (30, 1),  # 30 users, 1 request each
        ]
        
        results = []
        
        for concurrent_users, requests_per_user in load_levels:
            print(f"Testing load level: {concurrent_users} users, {requests_per_user} requests each")
            
            metrics = await scenarios.scenario_document_upload_load(
                concurrent_users=concurrent_users,
                requests_per_user=requests_per_user,
                ramp_up_time=min(concurrent_users, 10)
            )
            
            summary = metrics.get_summary()
            results.append({
                "concurrent_users": concurrent_users,
                "requests_per_user": requests_per_user,
                "total_requests": summary["total_requests"],
                "success_rate": summary["success_rate"],
                "avg_response_time": summary["response_times"]["mean"],
                "p95_response_time": summary["response_times"]["p95"],
                "throughput": summary["requests_per_second"]
            })
            
            # Stop if success rate drops too low
            if summary["success_rate"] < 0.7:
                print(f"Stopping stress test - success rate dropped to {summary['success_rate']:.2%}")
                break
        
        # Analyze results
        print("\nStress Test Results:")
        for result in results:
            print(f"  {result['concurrent_users']} users: "
                  f"Success Rate: {result['success_rate']:.2%}, "
                  f"Avg Response: {result['avg_response_time']:.2f}s, "
                  f"Throughput: {result['throughput']:.2f} req/s")
        
        # At least the first load level should pass
        assert results[0]["success_rate"] >= 0.9, "System should handle basic load"
        
        # Response times should be reasonable at low load
        assert results[0]["avg_response_time"] < 5.0, "Response times should be reasonable at low load"


if __name__ == "__main__":
    # Run load tests directly
    import sys
    
    async def run_load_tests():
        test_instance = TestSystemLoad()
        
        print("🚀 Starting System Load Tests")
        print("=" * 50)
        
        tests = [
            ("Document Upload Load", test_instance.test_document_upload_load),
            ("Question Processing Load", test_instance.test_question_processing_load),
            ("Mixed Workload", test_instance.test_mixed_workload_performance),
            ("Stress Limits", test_instance.test_stress_limits),
        ]
        
        for test_name, test_func in tests:
            print(f"\n📋 Running {test_name}...")
            try:
                await test_func()
                print(f"✅ {test_name} completed successfully")
            except Exception as e:
                print(f"❌ {test_name} failed: {e}")
                return False
        
        print("\n🎉 All load tests completed!")
        return True
    
    success = asyncio.run(run_load_tests())
    sys.exit(0 if success else 1)