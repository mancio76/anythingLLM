"""Tests for question processing REST API endpoints."""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
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
    PaginatedJobs,
    QuestionCreate,
    QuestionRequest,
    QuestionResult,
    QuestionResults,
)
from app.services.question_service import QuestionProcessingError
from app.services.job_service import JobNotFoundError


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


class TestQuestionExecution:
    """Test question execution endpoint."""
    
    @pytest.fixture
    def sample_question_request(self):
        """Sample question request."""
        return QuestionRequest(
            workspace_id="ws_123",
            questions=[
                QuestionCreate(
                    text="What is the contract value?",
                    expected_fragments=["$", "million", "value"]
                ),
                QuestionCreate(
                    text="Who are the parties involved?",
                    expected_fragments=["party", "contractor", "client"]
                )
            ],
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=0.7
            ),
            max_concurrent=2,
            timeout=300
        )
    
    @pytest.fixture
    def sample_job_response(self):
        """Sample job response."""
        job = Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PENDING,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={
                "workspace_id": "ws_123",
                "question_count": 2,
                "max_concurrent": 2,
                "timeout": 300
            }
        )
        
        return JobResponse(
            job=job,
            links={
                "status": "/api/v1/questions/jobs/job_456",
                "results": "/api/v1/questions/jobs/job_456/results"
            },
            estimated_completion=datetime.utcnow() + timedelta(seconds=300)
        )
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.require_user")
    def test_execute_questions_success(
        self,
        mock_require_user,
        mock_get_question_service,
        client: TestClient,
        sample_question_request,
        sample_job_response
    ):
        """Test successful question execution."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.execute_questions.return_value = sample_job_response
        mock_get_question_service.return_value = mock_service
        
        # Make request
        response = client.post(
            "/api/v1/questions/execute",
            json=sample_question_request.model_dump()
        )
        
        # Assertions
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["job"]["id"] == "job_456"
        assert data["job"]["type"] == "question_processing"
        assert data["job"]["status"] == "pending"
        assert "links" in data
        assert "estimated_completion" in data
        
        # Verify service was called correctly
        mock_service.execute_questions.assert_called_once()
        call_args = mock_service.execute_questions.call_args[0][0]
        assert call_args.workspace_id == "ws_123"
        assert len(call_args.questions) == 2
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.require_user")
    def test_execute_questions_empty_workspace_id(
        self,
        mock_require_user,
        mock_get_question_service,
        client: TestClient,
        sample_question_request
    ):
        """Test question execution with empty workspace ID."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        # Modify request to have empty workspace ID
        sample_question_request.workspace_id = ""
        
        # Make request
        response = client.post(
            "/api/v1/questions/execute",
            json=sample_question_request.model_dump()
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Workspace ID cannot be empty" in response.json()["detail"]
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.require_user")
    def test_execute_questions_service_error(
        self,
        mock_require_user,
        mock_get_question_service,
        client: TestClient,
        sample_question_request
    ):
        """Test question execution with service error."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.execute_questions.side_effect = QuestionProcessingError("Workspace not found")
        mock_get_question_service.return_value = mock_service
        
        # Make request
        response = client.post(
            "/api/v1/questions/execute",
            json=sample_question_request.model_dump()
        )
        
        # Assertions
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Workspace not found" in response.json()["detail"]
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.require_user")
    def test_execute_questions_validation_error(
        self,
        mock_require_user,
        mock_get_question_service,
        client: TestClient
    ):
        """Test question execution with validation error."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        # Make request with invalid data (no questions)
        invalid_request = {
            "workspace_id": "ws_123",
            "questions": [],  # Empty questions list
            "max_concurrent": 2,
            "timeout": 300
        }
        
        response = client.post(
            "/api/v1/questions/execute",
            json=invalid_request
        )
        
        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestQuestionJobStatus:
    """Test question job status endpoint."""
    
    @pytest.fixture
    def sample_processing_job(self):
        """Sample processing job."""
        return Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PROCESSING,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            progress=45.0,
            metadata={
                "workspace_id": "ws_123",
                "question_count": 10,
                "user_id": "user_123"
            }
        )
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_job_status_success(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient,
        sample_processing_job
    ):
        """Test successful job status retrieval."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = sample_processing_job
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/job_456")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == "job_456"
        assert data["type"] == "question_processing"
        assert data["status"] == "processing"
        assert data["progress"] == 45.0
        
        # Verify service was called correctly
        mock_service.get_job.assert_called_once_with("job_456", include_results=False)
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_job_status_with_results(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient,
        sample_processing_job
    ):
        """Test job status retrieval with results."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = sample_processing_job
        mock_get_job_service.return_value = mock_service
        
        # Make request with include_results=True
        response = client.get("/api/v1/questions/jobs/job_456?include_results=true")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        
        # Verify service was called with include_results=True
        mock_service.get_job.assert_called_once_with("job_456", include_results=True)
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_job_status_not_found(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient
    ):
        """Test job status retrieval for non-existent job."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.get_job.side_effect = JobNotFoundError("Job not found")
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/nonexistent")
        
        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"]
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_job_status_wrong_type(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient
    ):
        """Test job status retrieval for wrong job type."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        # Create job with wrong type
        wrong_type_job = Job(
            id="job_456",
            type=JobType.DOCUMENT_UPLOAD,  # Wrong type
            status=JobStatus.PROCESSING,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=45.0,
            metadata={"user_id": "user_123"}
        )
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = wrong_type_job
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/job_456")
        
        # Assertions
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Question processing job not found" in response.json()["detail"]
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_job_status_access_denied(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient,
        sample_processing_job
    ):
        """Test job status retrieval with access denied."""
        # Setup mocks - different user
        mock_user = User(id="other_user", username="otheruser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = sample_processing_job
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/job_456")
        
        # Assertions
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Access denied" in response.json()["detail"]


class TestQuestionResults:
    """Test question results endpoint."""
    
    @pytest.fixture
    def sample_completed_job(self):
        """Sample completed job with results."""
        return Job(
            id="job_456",
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
                        "question_text": "What is the contract value?",
                        "response": "The contract value is $1.5 million",
                        "confidence_score": 0.85,
                        "processing_time": 2.3,
                        "fragments_found": ["$", "million"],
                        "success": True,
                        "error": None,
                        "metadata": {"llm_model": "gpt-3.5-turbo"}
                    },
                    {
                        "question_id": "q2",
                        "question_text": "Who are the parties?",
                        "response": "The parties are ABC Corp and XYZ Ltd",
                        "confidence_score": 0.92,
                        "processing_time": 1.8,
                        "fragments_found": ["party"],
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
                    "average_confidence": 0.885
                },
                "total_questions": 2,
                "successful_questions": 2,
                "failed_questions": 0,
                "total_processing_time": 4.1,
                "average_confidence": 0.885
            },
            metadata={"user_id": "user_123"}
        )
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_results_success(
        self,
        mock_require_user,
        mock_get_job_service,
        mock_get_question_service,
        client: TestClient,
        sample_completed_job
    ):
        """Test successful results retrieval."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_job_service = AsyncMock()
        mock_job_service.get_job.return_value = sample_completed_job
        mock_get_job_service.return_value = mock_job_service
        
        mock_question_service = AsyncMock()
        mock_get_question_service.return_value = mock_question_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/job_456/results")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["job_id"] == "job_456"
        assert data["workspace_id"] == "ws_123"
        assert len(data["results"]) == 2
        assert data["total_questions"] == 2
        assert data["successful_questions"] == 2
        assert data["average_confidence"] == 0.885
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_results_job_still_processing(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient
    ):
        """Test results retrieval for job still processing."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        processing_job = Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PROCESSING,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=50.0,
            metadata={"user_id": "user_123"}
        )
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = processing_job
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/job_456/results")
        
        # Assertions
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert "still processing" in response.json()["detail"]
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_results_job_failed(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient
    ):
        """Test results retrieval for failed job."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        failed_job = Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.FAILED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            error="Processing failed",
            metadata={"user_id": "user_123"}
        )
        
        mock_service = AsyncMock()
        mock_service.get_job.return_value = failed_job
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs/job_456/results")
        
        # Assertions
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "Job failed" in response.json()["detail"]
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_results_csv_export(
        self,
        mock_require_user,
        mock_get_job_service,
        mock_get_question_service,
        client: TestClient,
        sample_completed_job
    ):
        """Test CSV export of results."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_job_service = AsyncMock()
        mock_job_service.get_job.return_value = sample_completed_job
        mock_get_job_service.return_value = mock_job_service
        
        mock_question_service = AsyncMock()
        mock_question_service.export_results.return_value = "question_id,question_text,response\nq1,What is the value?,The value is $1M"
        mock_get_question_service.return_value = mock_question_service
        
        # Make request for CSV format
        response = client.get("/api/v1/questions/jobs/job_456/results?format=csv")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        
        # Verify export service was called
        mock_question_service.export_results.assert_called_once_with(
            job_id="job_456",
            format="csv"
        )
    
    @patch("app.routers.questions.get_question_service")
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_get_results_with_filters(
        self,
        mock_require_user,
        mock_get_job_service,
        mock_get_question_service,
        client: TestClient,
        sample_completed_job
    ):
        """Test results retrieval with filters."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_job_service = AsyncMock()
        mock_job_service.get_job.return_value = sample_completed_job
        mock_get_job_service.return_value = mock_job_service
        
        mock_question_service = AsyncMock()
        mock_get_question_service.return_value = mock_question_service
        
        # Make request with filters
        response = client.get(
            "/api/v1/questions/jobs/job_456/results"
            "?confidence_threshold=0.9&success_only=true&include_metadata=false"
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Should only include results with confidence >= 0.9
        for result in data["results"]:
            assert result["confidence_score"] >= 0.9
            assert result["success"] is True
            # Metadata should be empty due to include_metadata=false
            assert result["metadata"] == {}


class TestQuestionJobListing:
    """Test question job listing endpoint."""
    
    @pytest.fixture
    def sample_jobs_list(self):
        """Sample jobs list."""
        jobs = []
        for i in range(5):
            job = Job(
                id=f"job_{i}",
                type=JobType.QUESTION_PROCESSING,
                status=JobStatus.COMPLETED if i < 3 else JobStatus.PROCESSING,
                workspace_id=f"ws_{i % 2}",
                created_at=datetime.utcnow() - timedelta(days=i),
                updated_at=datetime.utcnow() - timedelta(days=i),
                progress=100.0 if i < 3 else 50.0,
                metadata={
                    "user_id": "user_123",
                    "question_count": 10 + i,
                    "llm_config": {"provider": "openai"}
                }
            )
            jobs.append(job)
        
        return PaginatedJobs(
            items=jobs,
            total=5,
            page=1,
            size=20,
            pages=1
        )
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_list_jobs_success(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient,
        sample_jobs_list
    ):
        """Test successful job listing."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.list_jobs.return_value = sample_jobs_list
        mock_get_job_service.return_value = mock_service
        
        # Make request
        response = client.get("/api/v1/questions/jobs")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["size"] == 20
        
        # Verify all jobs are question processing type
        for job in data["items"]:
            assert job["type"] == "question_processing"
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_list_jobs_with_filters(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient,
        sample_jobs_list
    ):
        """Test job listing with filters."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.list_jobs.return_value = sample_jobs_list
        mock_get_job_service.return_value = mock_service
        
        # Make request with filters
        response = client.get(
            "/api/v1/questions/jobs"
            "?status=completed&workspace_id=ws_1&llm_provider=openai"
            "&min_questions=10&max_questions=15&min_confidence=0.8"
        )
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        
        # Verify service was called with correct filters
        mock_service.list_jobs.assert_called_once()
        call_args = mock_service.list_jobs.call_args
        filters = call_args.kwargs["filters"]
        assert filters.type == JobType.QUESTION_PROCESSING
        assert filters.status == JobStatus.COMPLETED
        assert filters.workspace_id == "ws_1"
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_list_jobs_pagination(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient,
        sample_jobs_list
    ):
        """Test job listing with pagination."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        mock_service = AsyncMock()
        mock_service.list_jobs.return_value = sample_jobs_list
        mock_get_job_service.return_value = mock_service
        
        # Make request with pagination
        response = client.get("/api/v1/questions/jobs?page=2&size=10")
        
        # Assertions
        assert response.status_code == status.HTTP_200_OK
        
        # Verify pagination was passed correctly
        mock_service.list_jobs.assert_called_once()
        call_args = mock_service.list_jobs.call_args
        pagination = call_args.kwargs["pagination"]
        assert pagination.page == 2
        assert pagination.size == 10
    
    @patch("app.routers.questions.get_job_service")
    @patch("app.routers.questions.require_user")
    def test_list_jobs_invalid_date_format(
        self,
        mock_require_user,
        mock_get_job_service,
        client: TestClient
    ):
        """Test job listing with invalid date format."""
        # Setup mocks
        mock_user = User(id="user_123", username="testuser", roles=["user"])
        mock_require_user.return_value = mock_user
        
        # Make request with invalid date
        response = client.get("/api/v1/questions/jobs?created_after=invalid-date")
        
        # Assertions
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "Invalid created_after date format" in response.json()["detail"]


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_can_access_job_own_job(self):
        """Test user can access their own job."""
        from app.routers.questions import _can_access_job
        
        user = User(id="user_123", username="testuser", roles=["user"])
        job = Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            metadata={"user_id": "user_123"}
        )
        
        assert _can_access_job(job, user) is True
    
    def test_can_access_job_other_user(self):
        """Test user cannot access other user's job."""
        from app.routers.questions import _can_access_job
        
        user = User(id="user_123", username="testuser", roles=["user"])
        job = Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            metadata={"user_id": "other_user"}
        )
        
        assert _can_access_job(job, user) is False
    
    def test_can_access_job_admin_user(self):
        """Test admin user can access any job."""
        from app.routers.questions import _can_access_job
        
        admin_user = User(id="admin_123", username="admin", roles=["admin"])
        job = Job(
            id="job_456",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="ws_123",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=100.0,
            metadata={"user_id": "other_user"}
        )
        
        assert _can_access_job(job, admin_user) is True
    
    def test_is_admin_user(self):
        """Test admin user detection."""
        from app.routers.questions import _is_admin_user
        
        admin_user = User(id="admin_123", username="admin", roles=["admin"])
        regular_user = User(id="user_123", username="user", roles=["user"])
        
        assert _is_admin_user(admin_user) is True
        assert _is_admin_user(regular_user) is False


# Integration test fixtures
@pytest.fixture
def client():
    """Test client fixture."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)