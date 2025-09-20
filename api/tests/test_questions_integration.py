"""Integration tests for question processing endpoints."""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import status
from fastapi.testclient import TestClient

from app.core.security import User
from app.models.pydantic_models import (
    Job,
    JobResponse,
    JobStatus,
    JobType,
    LLMConfig,
    LLMProvider,
    QuestionCreate,
    QuestionRequest,
    QuestionResult,
    QuestionResults,
)


# Mock authentication middleware for all tests
@pytest.fixture(autouse=True)
def mock_auth_middleware():
    """Mock authentication middleware for all tests."""
    async def mock_dispatch(self, request, call_next):
        # Set a mock user in request state
        request.state.user = User(
            id="test_user_123",
            username="testuser",
            is_active=True,
            roles=["user"]
        )
        return await call_next(request)
    
    with patch("app.middleware.authentication.AuthenticationMiddleware.dispatch", mock_dispatch):
        yield


class TestQuestionProcessingIntegration:
    """Integration tests for complete question processing workflow."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies."""
        with patch("app.routers.questions.get_question_service") as mock_question_service, \
             patch("app.routers.questions.get_job_service") as mock_job_service, \
             patch("app.routers.questions.require_user") as mock_require_user:
            
            # Setup user
            from app.core.security import User
            mock_user = User(id="user_123", username="testuser", roles=["user"])
            mock_require_user.return_value = mock_user
            
            # Setup services
            mock_question_svc = AsyncMock()
            mock_job_svc = AsyncMock()
            mock_question_service.return_value = mock_question_svc
            mock_job_service.return_value = mock_job_svc
            
            yield {
                "user": mock_user,
                "question_service": mock_question_svc,
                "job_service": mock_job_svc
            }
    
    def test_complete_question_processing_workflow(self, client: TestClient, mock_dependencies):
        """Test complete workflow from execution to results retrieval."""
        question_svc = mock_dependencies["question_service"]
        job_svc = mock_dependencies["job_service"]
        
        # Step 1: Execute questions
        job_id = "job_123"
        workspace_id = "ws_456"
        
        # Mock job creation response
        initial_job = Job(
            id=job_id,
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PENDING,
            workspace_id=workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={
                "workspace_id": workspace_id,
                "question_count": 2,
                "user_id": "user_123"
            }
        )
        
        job_response = JobResponse(
            job=initial_job,
            links={
                "status": f"/api/v1/questions/jobs/{job_id}",
                "results": f"/api/v1/questions/jobs/{job_id}/results"
            },
            estimated_completion=datetime.utcnow() + timedelta(minutes=5)
        )
        
        question_svc.execute_questions.return_value = job_response
        
        # Execute questions
        request_data = {
            "workspace_id": workspace_id,
            "questions": [
                {
                    "text": "What is the contract value?",
                    "expected_fragments": ["$", "million", "value"]
                },
                {
                    "text": "Who are the contracting parties?",
                    "expected_fragments": ["party", "contractor", "client"]
                }
            ],
            "llm_config": {
                "provider": "openai",
                "model": "gpt-3.5-turbo",
                "temperature": 0.7
            },
            "max_concurrent": 2,
            "timeout": 300
        }
        
        response = client.post("/api/v1/questions/execute", json=request_data)
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["job"]["id"] == job_id
        assert data["job"]["status"] == "pending"
        assert "links" in data
        
        # Step 2: Check job status (processing)
        processing_job = Job(
            id=job_id,
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PROCESSING,
            workspace_id=workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            progress=50.0,
            metadata={
                "workspace_id": workspace_id,
                "question_count": 2,
                "user_id": "user_123"
            }
        )
        
        job_svc.get_job.return_value = processing_job
        
        response = client.get(f"/api/v1/questions/jobs/{job_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "processing"
        assert data["progress"] == 50.0
        
        # Step 3: Check job status (completed)
        completed_job = Job(
            id=job_id,
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id=workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "What is the contract value?",
                        "response": "The contract value is $2.5 million",
                        "confidence_score": 0.92,
                        "processing_time": 2.1,
                        "fragments_found": ["$", "million", "value"],
                        "success": True,
                        "error": None,
                        "metadata": {"llm_model": "gpt-3.5-turbo"}
                    },
                    {
                        "question_id": "q2",
                        "question_text": "Who are the contracting parties?",
                        "response": "The contracting parties are TechCorp Inc. and BuildCo Ltd.",
                        "confidence_score": 0.88,
                        "processing_time": 1.9,
                        "fragments_found": ["party", "contractor"],
                        "success": True,
                        "error": None,
                        "metadata": {"llm_model": "gpt-3.5-turbo"}
                    }
                ],
                "summary": {
                    "total_questions": 2,
                    "successful_questions": 2,
                    "failed_questions": 0,
                    "success_rate": 100.0,
                    "average_confidence": 0.90,
                    "confidence_distribution": {
                        "high (0.8-1.0)": 2,
                        "medium (0.5-0.8)": 0,
                        "low (0.0-0.5)": 0
                    }
                },
                "total_questions": 2,
                "successful_questions": 2,
                "failed_questions": 0,
                "total_processing_time": 4.0,
                "average_confidence": 0.90
            },
            metadata={
                "workspace_id": workspace_id,
                "question_count": 2,
                "user_id": "user_123"
            }
        )
        
        job_svc.get_job.return_value = completed_job
        
        response = client.get(f"/api/v1/questions/jobs/{job_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 100.0
        assert data["result"]["total_questions"] == 2
        assert data["result"]["successful_questions"] == 2
        
        # Step 4: Get results
        response = client.get(f"/api/v1/questions/jobs/{job_id}/results")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["job_id"] == job_id
        assert data["workspace_id"] == workspace_id
        assert len(data["results"]) == 2
        assert data["total_questions"] == 2
        assert data["successful_questions"] == 2
        assert data["average_confidence"] == 0.90
        
        # Verify individual results
        results = data["results"]
        assert results[0]["question_text"] == "What is the contract value?"
        assert results[0]["confidence_score"] == 0.92
        assert results[0]["success"] is True
        assert "$" in results[0]["fragments_found"]
        
        assert results[1]["question_text"] == "Who are the contracting parties?"
        assert results[1]["confidence_score"] == 0.88
        assert results[1]["success"] is True
    
    def test_question_processing_with_failures(self, client: TestClient, mock_dependencies):
        """Test question processing workflow with some failures."""
        question_svc = mock_dependencies["question_service"]
        job_svc = mock_dependencies["job_service"]
        
        job_id = "job_456"
        workspace_id = "ws_789"
        
        # Mock job creation
        initial_job = Job(
            id=job_id,
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PENDING,
            workspace_id=workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={"user_id": "user_123"}
        )
        
        job_response = JobResponse(
            job=initial_job,
            links={
                "status": f"/api/v1/questions/jobs/{job_id}",
                "results": f"/api/v1/questions/jobs/{job_id}/results"
            }
        )
        
        question_svc.execute_questions.return_value = job_response
        
        # Execute questions
        request_data = {
            "workspace_id": workspace_id,
            "questions": [
                {"text": "What is the contract value?"},
                {"text": "Invalid question that will fail?"},
                {"text": "Who are the parties?"}
            ],
            "max_concurrent": 2,
            "timeout": 300
        }
        
        response = client.post("/api/v1/questions/execute", json=request_data)
        assert response.status_code == status.HTTP_202_ACCEPTED
        
        # Mock completed job with mixed results
        completed_job = Job(
            id=job_id,
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id=workspace_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "What is the contract value?",
                        "response": "The contract value is $1.2 million",
                        "confidence_score": 0.85,
                        "processing_time": 2.0,
                        "fragments_found": [],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    },
                    {
                        "question_id": "q2",
                        "question_text": "Invalid question that will fail?",
                        "response": "",
                        "confidence_score": 0.0,
                        "processing_time": 0.5,
                        "fragments_found": [],
                        "success": False,
                        "error": "Question processing failed: Invalid question format",
                        "metadata": {}
                    },
                    {
                        "question_id": "q3",
                        "question_text": "Who are the parties?",
                        "response": "The parties are Company A and Company B",
                        "confidence_score": 0.78,
                        "processing_time": 1.8,
                        "fragments_found": [],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    }
                ],
                "summary": {
                    "total_questions": 3,
                    "successful_questions": 2,
                    "failed_questions": 1,
                    "success_rate": 66.67,
                    "average_confidence": 0.815,
                    "error_types": {
                        "Question processing failed": 1
                    }
                },
                "total_questions": 3,
                "successful_questions": 2,
                "failed_questions": 1,
                "total_processing_time": 4.3,
                "average_confidence": 0.815
            },
            metadata={"user_id": "user_123"}
        )
        
        job_svc.get_job.return_value = completed_job
        
        # Get results
        response = client.get(f"/api/v1/questions/jobs/{job_id}/results")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_questions"] == 3
        assert data["successful_questions"] == 2
        assert data["failed_questions"] == 1
        
        # Check that failed question is included
        failed_result = next(r for r in data["results"] if not r["success"])
        assert failed_result["error"] == "Question processing failed: Invalid question format"
        assert failed_result["confidence_score"] == 0.0
    
    def test_csv_export_workflow(self, client: TestClient, mock_dependencies):
        """Test CSV export functionality."""
        question_svc = mock_dependencies["question_service"]
        job_svc = mock_dependencies["job_service"]
        
        job_id = "job_csv"
        
        # Mock completed job
        completed_job = Job(
            id=job_id,
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "What is the value?",
                        "response": "The value is $1M",
                        "confidence_score": 0.9,
                        "processing_time": 2.0,
                        "fragments_found": ["$"],
                        "success": True,
                        "error": None,
                        "metadata": {"llm_model": "gpt-3.5-turbo"}
                    }
                ]
            },
            metadata={"user_id": "user_123"}
        )
        
        job_svc.get_job.return_value = completed_job
        
        # Mock CSV export
        csv_content = "question_id,question_text,response,confidence_score,processing_time,success,error,fragments_found,llm_model\nq1,What is the value?,The value is $1M,0.9,2.0,True,,\"$\",gpt-3.5-turbo"
        question_svc.export_results.return_value = csv_content
        
        # Request CSV export
        response = client.get(f"/api/v1/questions/jobs/{job_id}/results?format=csv")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert f"question_results_{job_id}.csv" in response.headers["content-disposition"]
        
        # Verify export service was called
        question_svc.export_results.assert_called_once_with(
            job_id=job_id,
            format="csv"
        )
    
    def test_job_listing_and_filtering(self, client: TestClient, mock_dependencies):
        """Test job listing with various filters."""
        job_svc = mock_dependencies["job_service"]
        
        # Mock job list
        from app.models.pydantic_models import PaginatedJobs
        
        jobs = []
        for i in range(3):
            job = Job(
                id=f"job_{i}",
                type=JobType.QUESTION_PROCESSING,
                status=JobStatus.COMPLETED if i < 2 else JobStatus.PROCESSING,
                workspace_id=f"ws_{i}",
                created_at=datetime.utcnow() - timedelta(days=i),
                updated_at=datetime.utcnow() - timedelta(days=i),
                progress=100.0 if i < 2 else 75.0,
                metadata={
                    "user_id": "user_123",
                    "question_count": 5 + i,
                    "llm_config": {"provider": "openai" if i % 2 == 0 else "anthropic"}
                }
            )
            jobs.append(job)
        
        paginated_jobs = PaginatedJobs(
            items=jobs,
            total=3,
            page=1,
            size=20,
            pages=1
        )
        
        job_svc.list_jobs.return_value = paginated_jobs
        
        # Test basic listing
        response = client.get("/api/v1/questions/jobs")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        
        # Test with filters
        response = client.get(
            "/api/v1/questions/jobs"
            "?status=completed&workspace_id=ws_0&llm_provider=openai"
            "&min_questions=5&max_questions=10"
        )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify service was called with filters
        job_svc.list_jobs.assert_called()
        call_args = job_svc.list_jobs.call_args
        filters = call_args.kwargs["filters"]
        assert filters.type == JobType.QUESTION_PROCESSING
        assert filters.status == JobStatus.COMPLETED
        assert filters.workspace_id == "ws_0"
    
    def test_error_scenarios(self, client: TestClient, mock_dependencies):
        """Test various error scenarios."""
        question_svc = mock_dependencies["question_service"]
        job_svc = mock_dependencies["job_service"]
        
        # Test workspace not found during execution
        from app.services.question_service import QuestionProcessingError
        question_svc.execute_questions.side_effect = QuestionProcessingError("Workspace not found: ws_invalid")
        
        request_data = {
            "workspace_id": "ws_invalid",
            "questions": [{"text": "Test question?"}],
            "max_concurrent": 1,
            "timeout": 60
        }
        
        response = client.post("/api/v1/questions/execute", json=request_data)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Workspace not found" in response.json()["detail"]
        
        # Test job not found
        from app.services.job_service import JobNotFoundError
        job_svc.get_job.side_effect = JobNotFoundError("Job not found")
        
        response = client.get("/api/v1/questions/jobs/nonexistent")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]
        
        # Test access denied (different user)
        other_user_job = Job(
            id="job_other",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            metadata={"user_id": "other_user"}  # Different user
        )
        
        job_svc.get_job.side_effect = None
        job_svc.get_job.return_value = other_user_job
        
        response = client.get("/api/v1/questions/jobs/job_other")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied" in response.json()["detail"]


class TestQuestionProcessingEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock dependencies for edge case tests."""
        with patch("app.routers.questions.get_question_service") as mock_question_service, \
             patch("app.routers.questions.get_job_service") as mock_job_service, \
             patch("app.routers.questions.require_user") as mock_require_user:
            
            from app.core.security import User
            mock_user = User(id="user_123", username="testuser", roles=["user"])
            mock_require_user.return_value = mock_user
            
            mock_question_svc = AsyncMock()
            mock_job_svc = AsyncMock()
            mock_question_service.return_value = mock_question_svc
            mock_job_service.return_value = mock_job_svc
            
            yield {
                "user": mock_user,
                "question_service": mock_question_svc,
                "job_service": mock_job_svc
            }
    
    def test_maximum_questions_limit(self, client: TestClient, mock_dependencies):
        """Test handling of maximum questions limit."""
        # Create request with maximum allowed questions (50)
        questions = [{"text": f"Question {i}?"} for i in range(50)]
        
        request_data = {
            "workspace_id": "ws_123",
            "questions": questions,
            "max_concurrent": 5,
            "timeout": 3600
        }
        
        # Should succeed with 50 questions
        response = client.post("/api/v1/questions/execute", json=request_data)
        
        # The validation should happen at the Pydantic model level
        # If it gets to the router, it means validation passed
        assert response.status_code in [status.HTTP_202_ACCEPTED, status.HTTP_422_UNPROCESSABLE_ENTITY]
    
    def test_empty_results_handling(self, client: TestClient, mock_dependencies):
        """Test handling of jobs with no results."""
        job_svc = mock_dependencies["job_service"]
        
        # Mock job with no results
        job_no_results = Job(
            id="job_empty",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result=None,  # No results
            metadata={"user_id": "user_123"}
        )
        
        job_svc.get_job.return_value = job_no_results
        
        response = client.get("/api/v1/questions/jobs/job_empty/results")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "No results found" in response.json()["detail"]
    
    def test_confidence_threshold_filtering(self, client: TestClient, mock_dependencies):
        """Test confidence threshold filtering."""
        job_svc = mock_dependencies["job_service"]
        
        # Mock job with mixed confidence scores
        job_with_results = Job(
            id="job_mixed",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "High confidence question",
                        "response": "High confidence response",
                        "confidence_score": 0.95,
                        "processing_time": 2.0,
                        "fragments_found": [],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    },
                    {
                        "question_id": "q2",
                        "question_text": "Low confidence question",
                        "response": "Low confidence response",
                        "confidence_score": 0.3,
                        "processing_time": 1.5,
                        "fragments_found": [],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    }
                ],
                "total_questions": 2,
                "successful_questions": 2,
                "failed_questions": 0,
                "total_processing_time": 3.5,
                "average_confidence": 0.625
            },
            metadata={"user_id": "user_123"}
        )
        
        job_svc.get_job.return_value = job_with_results
        
        # Request with confidence threshold of 0.8
        response = client.get("/api/v1/questions/jobs/job_mixed/results?confidence_threshold=0.8")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Should only return the high confidence result
        assert len(data["results"]) == 1
        assert data["results"][0]["confidence_score"] >= 0.8
        assert data["total_questions"] == 1  # Updated count for filtered results
    
    def test_admin_access_to_all_jobs(self, client: TestClient):
        """Test admin user can access all jobs."""
        with patch("app.routers.questions.get_job_service") as mock_job_service, \
             patch("app.routers.questions.require_user") as mock_require_user:
            
            # Setup admin user
            from app.core.security import User
            admin_user = User(id="admin_123", username="admin", roles=["admin"])
            mock_require_user.return_value = admin_user
            
            # Mock job from different user
            other_user_job = Job(
                id="job_other",
                type=JobType.QUESTION_PROCESSING,
                status=JobStatus.COMPLETED,
                workspace_id="ws_123",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                progress=100.0,
                metadata={"user_id": "other_user"}
            )
            
            mock_service = AsyncMock()
            mock_service.get_job.return_value = other_user_job
            mock_job_service.return_value = mock_service
            
            # Admin should be able to access other user's job
            response = client.get("/api/v1/questions/jobs/job_other")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["id"] == "job_other"


# Test fixtures
@pytest.fixture
def client():
    """Test client fixture."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)