"""Tests for QuestionService."""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.core.config import Settings
from app.integrations.anythingllm_client import (
    AnythingLLMClient,
    AnythingLLMError,
    MessageError,
    ThreadError,
    WorkspaceNotFoundError,
    MessageResponse,
    ThreadResponse,
    ThreadInfo,
)
from app.models.pydantic_models import (
    Job,
    JobStatus,
    JobType,
    LLMConfig,
    LLMProvider,
    Question,
    QuestionCreate,
    QuestionRequest,
    QuestionResult,
    QuestionResults,
)
from app.repositories.job_repository import JobRepository
from app.services.question_service import (
    QuestionService,
    QuestionProcessingError,
    ThreadManagementError,
    ExportFormat,
    DocumentTypeRouter,
    ConfidenceCalculator,
    create_question_service,
)


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return Settings(
        database_url="postgresql://test:test@localhost/test",
        anythingllm_url="http://localhost:3001",
        anythingllm_api_key="test-key",
        secret_key="test-secret-key",
    )


@pytest.fixture
def mock_job_repository():
    """Create mock job repository."""
    mock_repo = AsyncMock(spec=JobRepository)
    
    # Mock job creation
    mock_job = Job(
        id=str(uuid4()),
        type=JobType.QUESTION_PROCESSING,
        status=JobStatus.PENDING,
        workspace_id="test-workspace",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        progress=0.0,
        metadata={}
    )
    mock_repo.create_job.return_value = mock_job
    mock_repo.update_job_status.return_value = mock_job
    mock_repo.get_by_id.return_value = mock_job
    mock_repo.get_job_with_results.return_value = mock_job
    
    return mock_repo


@pytest.fixture
def mock_anythingllm_client():
    """Create mock AnythingLLM client."""
    mock_client = AsyncMock(spec=AnythingLLMClient)
    
    # Mock workspace validation
    mock_client.get_workspace.return_value = MagicMock(id="test-workspace")
    
    # Mock thread creation
    mock_thread = ThreadInfo(
        id="test-thread",
        name="Test Thread",
        workspace_id="test-workspace",
        created_at=datetime.utcnow().isoformat()
    )
    mock_client.create_thread.return_value = ThreadResponse(
        thread=mock_thread,
        message="Thread created"
    )
    
    # Mock message sending
    mock_client.send_message.return_value = MessageResponse(
        id="test-message",
        response="This is a test response from the LLM.",
        sources=[],
        chatId="test-thread"
    )
    
    return mock_client


@pytest.fixture
def question_service(mock_settings, mock_job_repository, mock_anythingllm_client):
    """Create QuestionService instance."""
    return QuestionService(
        settings=mock_settings,
        job_repository=mock_job_repository,
        anythingllm_client=mock_anythingllm_client,
    )


@pytest.fixture
def sample_questions():
    """Create sample questions for testing."""
    return [
        Question(
            id="q1",
            text="What is the contract value?",
            expected_fragments=["$", "value", "amount"]
        ),
        Question(
            id="q2",
            text="Who is the vendor?",
            expected_fragments=["vendor", "supplier", "company"]
        ),
        Question(
            id="q3",
            text="What is the delivery date?",
            expected_fragments=["delivery", "date", "deadline"]
        )
    ]


@pytest.fixture
def sample_question_request(sample_questions):
    """Create sample question request."""
    return QuestionRequest(
        workspace_id="test-workspace",
        questions=[QuestionCreate(**q.model_dump()) for q in sample_questions],
        llm_config=LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-3.5-turbo",
            temperature=0.7
        ),
        max_concurrent=2,
        timeout=60
    )


class TestDocumentTypeRouter:
    """Test DocumentTypeRouter functionality."""
    
    def test_route_question_by_document_type_contract(self):
        """Test routing contract-related questions."""
        router = DocumentTypeRouter()
        question = Question(
            id="test",
            text="What are the contract terms and conditions?",
            expected_fragments=[]
        )
        
        doc_types = ["contract", "financial", "technical"]
        result = router.route_question_by_document_type(question, doc_types)
        
        assert result == "contract"
    
    def test_route_question_by_document_type_financial(self):
        """Test routing financial-related questions."""
        router = DocumentTypeRouter()
        question = Question(
            id="test",
            text="What is the total cost and payment schedule?",
            expected_fragments=[]
        )
        
        doc_types = ["contract", "financial", "technical"]
        result = router.route_question_by_document_type(question, doc_types)
        
        assert result == "financial"
    
    def test_route_question_by_document_type_no_match(self):
        """Test routing when no specific match found."""
        router = DocumentTypeRouter()
        question = Question(
            id="test",
            text="What is the weather like today?",
            expected_fragments=[]
        )
        
        doc_types = ["contract", "financial", "technical"]
        result = router.route_question_by_document_type(question, doc_types)
        
        assert result == "general"
    
    def test_route_question_by_document_type_empty_types(self):
        """Test routing with empty document types."""
        router = DocumentTypeRouter()
        question = Question(
            id="test",
            text="What are the contract terms?",
            expected_fragments=[]
        )
        
        doc_types = []
        result = router.route_question_by_document_type(question, doc_types)
        
        assert result == "general"


class TestConfidenceCalculator:
    """Test ConfidenceCalculator functionality."""
    
    def test_calculate_confidence_score_with_fragments(self):
        """Test confidence calculation with expected fragments."""
        calculator = ConfidenceCalculator()
        
        response = "The contract value is $100,000 and the vendor is ABC Corp."
        expected_fragments = ["$", "value", "vendor"]
        
        confidence, found_fragments = calculator.calculate_confidence_score(
            response, expected_fragments
        )
        
        assert 0.0 <= confidence <= 1.0
        assert len(found_fragments) == 3  # All fragments found
        assert "$" in found_fragments
        assert "value" in found_fragments
        assert "vendor" in found_fragments
    
    def test_calculate_confidence_score_partial_fragments(self):
        """Test confidence calculation with partial fragment matches."""
        calculator = ConfidenceCalculator()
        
        response = "The contract value is mentioned in the document."
        expected_fragments = ["value", "amount", "cost"]
        
        confidence, found_fragments = calculator.calculate_confidence_score(
            response, expected_fragments
        )
        
        assert 0.0 <= confidence <= 1.0
        assert len(found_fragments) == 1  # Only "value" found
        assert "value" in found_fragments
        assert confidence < 1.0  # Should be less than perfect
    
    def test_calculate_confidence_score_no_fragments(self):
        """Test confidence calculation without expected fragments."""
        calculator = ConfidenceCalculator()
        
        response = "This is a detailed response with specific information."
        expected_fragments = []
        
        confidence, found_fragments = calculator.calculate_confidence_score(
            response, expected_fragments
        )
        
        assert 0.0 <= confidence <= 1.0
        assert found_fragments == []
        assert confidence > 0.0  # Should have some confidence based on heuristics
    
    def test_calculate_confidence_score_empty_response(self):
        """Test confidence calculation with empty response."""
        calculator = ConfidenceCalculator()
        
        response = ""
        expected_fragments = ["value", "amount"]
        
        confidence, found_fragments = calculator.calculate_confidence_score(
            response, expected_fragments
        )
        
        assert confidence == 0.0
        assert found_fragments == []
    
    def test_calculate_confidence_score_negative_indicators(self):
        """Test confidence calculation with negative indicators."""
        calculator = ConfidenceCalculator()
        
        response = "I don't know the answer to this question."
        expected_fragments = []
        
        confidence, found_fragments = calculator.calculate_confidence_score(
            response, expected_fragments
        )
        
        assert 0.0 <= confidence <= 1.0
        assert confidence < 0.5  # Should be low due to negative indicators


class TestQuestionService:
    """Test QuestionService functionality."""
    
    @pytest.mark.asyncio
    async def test_execute_questions_success(
        self, 
        question_service, 
        sample_question_request,
        mock_job_repository
    ):
        """Test successful question execution initiation."""
        result = await question_service.execute_questions(sample_question_request)
        
        assert result.job.type == JobType.QUESTION_PROCESSING
        assert result.job.workspace_id == "test-workspace"
        assert "status" in result.links
        assert "results" in result.links
        assert result.estimated_completion is not None
        
        # Verify job creation was called
        mock_job_repository.create_job.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_questions_workspace_not_found(
        self, 
        question_service, 
        sample_question_request,
        mock_anythingllm_client
    ):
        """Test question execution with non-existent workspace."""
        mock_anythingllm_client.get_workspace.side_effect = WorkspaceNotFoundError(
            "Workspace not found"
        )
        
        with pytest.raises(QuestionProcessingError, match="Workspace not found"):
            await question_service.execute_questions(sample_question_request)
    
    @pytest.mark.asyncio
    async def test_execute_questions_too_many_questions(
        self, 
        question_service, 
        mock_anythingllm_client
    ):
        """Test question execution with too many questions."""
        # Create request with too many questions
        many_questions = [
            QuestionCreate(text=f"Question {i}", expected_fragments=[])
            for i in range(51)  # Exceeds max of 50
        ]
        
        # This should fail at Pydantic validation level
        with pytest.raises(Exception):  # Pydantic ValidationError
            request = QuestionRequest(
                workspace_id="test-workspace",
                questions=many_questions,
                max_concurrent=2,
                timeout=60
            )
    
    @pytest.mark.asyncio
    async def test_create_thread_success(
        self, 
        question_service, 
        mock_anythingllm_client
    ):
        """Test successful thread creation."""
        result = await question_service.create_thread("test-workspace", "Test Thread")
        
        assert result.id == "test-thread"
        assert result.name == "Test Thread"
        assert result.workspace_id == "test-workspace"
        
        mock_anythingllm_client.create_thread.assert_called_once_with(
            workspace_id="test-workspace",
            name="Test Thread"
        )
    
    @pytest.mark.asyncio
    async def test_create_thread_failure(
        self, 
        question_service, 
        mock_anythingllm_client
    ):
        """Test thread creation failure."""
        mock_anythingllm_client.create_thread.side_effect = ThreadError("Thread creation failed")
        
        with pytest.raises(ThreadManagementError, match="Thread creation failed"):
            await question_service.create_thread("test-workspace", "Test Thread")
    
    @pytest.mark.asyncio
    async def test_run_single_question_success(
        self, 
        question_service, 
        sample_questions,
        mock_anythingllm_client
    ):
        """Test successful single question processing."""
        question = sample_questions[0]
        
        result = await question_service.run_single_question(
            question=question,
            workspace_id="test-workspace",
            thread_id="test-thread"
        )
        
        assert result.success is True
        assert result.question_id == question.id
        assert result.question_text == question.text
        assert result.response == "This is a test response from the LLM."
        assert 0.0 <= result.confidence_score <= 1.0
        assert result.processing_time > 0.0
        
        mock_anythingllm_client.send_message.assert_called_once_with(
            workspace_id="test-workspace",
            thread_id="test-thread",
            message=question.text,
            mode="query"
        )
    
    @pytest.mark.asyncio
    async def test_run_single_question_message_error(
        self, 
        question_service, 
        sample_questions,
        mock_anythingllm_client
    ):
        """Test single question processing with message error."""
        question = sample_questions[0]
        mock_anythingllm_client.send_message.side_effect = MessageError("Message failed")
        
        result = await question_service.run_single_question(
            question=question,
            workspace_id="test-workspace",
            thread_id="test-thread"
        )
        
        assert result.success is False
        assert result.confidence_score == 0.0
        assert "Message error" in result.error
    
    @pytest.mark.asyncio
    async def test_process_question_set_success(
        self, 
        question_service, 
        sample_questions,
        mock_anythingllm_client
    ):
        """Test successful question set processing."""
        # Mock different responses for each question
        responses = [
            MessageResponse(id="msg1", response="Contract value is $50,000", sources=[], chatId="test-thread"),
            MessageResponse(id="msg2", response="Vendor is XYZ Corp", sources=[], chatId="test-thread"),
            MessageResponse(id="msg3", response="Delivery date is 2024-12-31", sources=[], chatId="test-thread"),
        ]
        mock_anythingllm_client.send_message.side_effect = responses
        
        results = await question_service.process_question_set(
            questions=sample_questions,
            workspace_id="test-workspace",
            max_concurrent=2,
            timeout=60
        )
        
        assert isinstance(results, QuestionResults)
        assert results.workspace_id == "test-workspace"
        assert results.total_questions == 3
        assert len(results.results) == 3
        assert results.successful_questions > 0
        assert results.total_processing_time > 0.0
        
        # Verify all questions were processed
        question_ids = {r.question_id for r in results.results}
        expected_ids = {q.id for q in sample_questions}
        assert question_ids == expected_ids
    
    @pytest.mark.asyncio
    async def test_manage_concurrent_processing_timeout(
        self, 
        question_service, 
        sample_questions,
        mock_anythingllm_client
    ):
        """Test concurrent processing with timeout."""
        # Mock slow responses that will timeout
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(2)  # Longer than timeout
            return MessageResponse(id="msg", response="Response", sources=[], chatId="test-thread")
        
        mock_anythingllm_client.send_message.side_effect = slow_response
        
        results = await question_service.manage_concurrent_processing(
            questions=sample_questions,
            workspace_id="test-workspace",
            thread_id="test-thread",
            max_concurrent=2,
            timeout=1  # Short timeout
        )
        
        assert len(results) == 3
        # All should have timed out
        for result in results:
            assert result.success is False
            assert "timed out" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_export_results_json(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test JSON export of question results."""
        # Mock job with results
        mock_job = Job(
            id="test-job",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="test-workspace",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "Test question",
                        "response": "Test response",
                        "confidence_score": 0.8,
                        "processing_time": 1.5,
                        "fragments_found": ["test"],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    }
                ],
                "summary": {"total_questions": 1, "successful_questions": 1}
            },
            metadata={}
        )
        mock_job_repository.get_job_with_results.return_value = mock_job
        
        export_data = await question_service.export_results("test-job", ExportFormat.JSON)
        
        assert export_data["content_type"] == "application/json"
        assert "question_results_" in export_data["filename"]
        assert export_data["filename"].endswith(".json")
        
        # Verify JSON content
        content = json.loads(export_data["content"])
        assert content["export_info"]["job_id"] == "test-job"
        assert content["export_info"]["export_format"] == "json"
        assert len(content["results"]) == 1
    
    @pytest.mark.asyncio
    async def test_export_results_csv(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test CSV export of question results."""
        # Mock job with results
        mock_job = Job(
            id="test-job",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="test-workspace",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "Test question",
                        "response": "Test response",
                        "confidence_score": 0.8,
                        "processing_time": 1.5,
                        "fragments_found": ["test"],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    }
                ]
            },
            metadata={}
        )
        mock_job_repository.get_job_with_results.return_value = mock_job
        
        export_data = await question_service.export_results("test-job", ExportFormat.CSV)
        
        assert export_data["content_type"] == "text/csv"
        assert "question_results_" in export_data["filename"]
        assert export_data["filename"].endswith(".csv")
        
        # Verify CSV content has header and data
        lines = export_data["content"].strip().split('\n')
        assert len(lines) >= 2  # Header + at least one data row
        assert "question_id" in lines[0]  # Header row
        assert "q1" in lines[1]  # Data row
    
    @pytest.mark.asyncio
    async def test_export_results_job_not_found(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test export with non-existent job."""
        mock_job_repository.get_job_with_results.return_value = None
        
        with pytest.raises(Exception, match="Job not found"):
            await question_service.export_results("nonexistent-job", ExportFormat.JSON)
    
    def test_route_question_by_document_type(self, question_service):
        """Test question routing by document type."""
        question = Question(
            id="test",
            text="What is the contract value?",
            expected_fragments=[]
        )
        
        doc_types = ["contract", "financial", "technical"]
        result = question_service.route_question_by_document_type(question, doc_types)
        
        assert result == "contract"
    
    def test_calculate_confidence_score(self, question_service):
        """Test confidence score calculation."""
        response = "The contract value is $100,000"
        expected_fragments = ["contract", "value", "$"]
        
        confidence, found_fragments = question_service.calculate_confidence_score(
            response, expected_fragments
        )
        
        assert 0.0 <= confidence <= 1.0
        assert len(found_fragments) == 3
    
    @pytest.mark.asyncio
    async def test_get_question_job_status(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test getting question job status."""
        result = await question_service.get_question_job_status("test-job")
        
        assert result is not None
        assert result.type == JobType.QUESTION_PROCESSING
        
        mock_job_repository.get_by_id.assert_called_once_with("test-job")
    
    @pytest.mark.asyncio
    async def test_get_question_results_completed_job(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test getting results for completed job."""
        # Mock completed job with results
        mock_job = Job(
            id="test-job",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.COMPLETED,
            workspace_id="test-workspace",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0,
            result={
                "results": [
                    {
                        "question_id": "q1",
                        "question_text": "Test question",
                        "response": "Test response",
                        "confidence_score": 0.8,
                        "processing_time": 1.5,
                        "fragments_found": ["test"],
                        "success": True,
                        "error": None,
                        "metadata": {}
                    }
                ],
                "summary": {},
                "total_questions": 1,
                "successful_questions": 1,
                "failed_questions": 0,
                "total_processing_time": 1.5,
                "average_confidence": 0.8
            },
            metadata={}
        )
        mock_job_repository.get_job_with_results.return_value = mock_job
        
        results = await question_service.get_question_results("test-job")
        
        assert results is not None
        assert isinstance(results, QuestionResults)
        assert results.job_id == "test-job"
        assert results.workspace_id == "test-workspace"
        assert len(results.results) == 1
        assert results.total_questions == 1
        assert results.successful_questions == 1
    
    @pytest.mark.asyncio
    async def test_get_question_results_incomplete_job(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test getting results for incomplete job."""
        # Mock incomplete job
        mock_job = Job(
            id="test-job",
            type=JobType.QUESTION_PROCESSING,
            status=JobStatus.PROCESSING,
            workspace_id="test-workspace",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=50.0,
            result=None,
            metadata={}
        )
        mock_job_repository.get_job_with_results.return_value = mock_job
        
        results = await question_service.get_question_results("test-job")
        
        assert results is None  # Should return None for incomplete jobs
    
    @pytest.mark.asyncio
    async def test_cancel_question_job(
        self, 
        question_service, 
        mock_job_repository
    ):
        """Test cancelling question job."""
        result = await question_service.cancel_question_job("test-job", "User requested")
        
        assert result is True
        mock_job_repository.cancel_job.assert_called_once_with("test-job", "User requested")
    
    @pytest.mark.asyncio
    async def test_cleanup_threads(self, question_service):
        """Test thread cleanup."""
        result = await question_service.cleanup_threads(
            "test-workspace", 
            ["thread1", "thread2"]
        )
        
        assert result is True  # Should succeed (placeholder implementation)


class TestQuestionServiceFactory:
    """Test QuestionService factory function."""
    
    def test_create_question_service(
        self, 
        mock_settings, 
        mock_job_repository, 
        mock_anythingllm_client
    ):
        """Test factory function creates service correctly."""
        service = create_question_service(
            settings=mock_settings,
            job_repository=mock_job_repository,
            anythingllm_client=mock_anythingllm_client,
        )
        
        assert isinstance(service, QuestionService)
        assert service.settings == mock_settings
        assert service.job_repository == mock_job_repository
        assert service.anythingllm_client == mock_anythingllm_client


class TestQuestionServiceValidation:
    """Test QuestionService validation methods."""
    
    @pytest.mark.asyncio
    async def test_validate_question_request_invalid_llm_provider(
        self, 
        question_service
    ):
        """Test validation with invalid LLM provider."""
        # This should fail at Pydantic validation level
        with pytest.raises(Exception):  # Pydantic ValidationError
            llm_config = LLMConfig(
                provider="invalid_provider",  # Invalid provider
                model="test-model",
                temperature=0.7
            )
    
    @pytest.mark.asyncio
    async def test_validate_question_request_invalid_temperature(
        self, 
        question_service
    ):
        """Test validation with invalid temperature."""
        # This should fail at Pydantic validation level
        with pytest.raises(Exception):  # Pydantic ValidationError
            llm_config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model="test-model",
                temperature=3.0  # Invalid temperature > 2.0
            )
    
    def test_validate_llm_config_empty_model(self, question_service):
        """Test LLM config validation with empty model name."""
        # This should fail at Pydantic validation level
        with pytest.raises(Exception):  # Pydantic ValidationError
            llm_config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model="",  # Empty model name
                temperature=0.7
            )
    
    def test_validate_llm_config_invalid_timeout(self, question_service):
        """Test LLM config validation with invalid timeout."""
        # This should fail at Pydantic validation level
        with pytest.raises(Exception):  # Pydantic ValidationError
            llm_config = LLMConfig(
                provider=LLMProvider.OPENAI,
                model="test-model",
                temperature=0.7,
                timeout=500  # Invalid timeout > 300
            )


class TestQuestionServiceIntegration:
    """Integration tests for QuestionService."""
    
    @pytest.mark.asyncio
    async def test_full_question_processing_workflow(
        self, 
        question_service, 
        sample_question_request,
        mock_job_repository,
        mock_anythingllm_client
    ):
        """Test complete question processing workflow."""
        # Mock successful responses
        mock_anythingllm_client.send_message.return_value = MessageResponse(
            id="test-message",
            response="The contract value is $100,000 and vendor is ABC Corp.",
            sources=[],
            chatId="test-thread"
        )
        
        # Test direct processing workflow
        questions = [Question(**q.model_dump()) for q in sample_question_request.questions]
        results = await question_service.process_question_set(
            questions=questions,
            workspace_id=sample_question_request.workspace_id,
            default_llm_config=sample_question_request.llm_config,
            max_concurrent=sample_question_request.max_concurrent,
            timeout=sample_question_request.timeout
        )
        
        assert isinstance(results, QuestionResults)
        assert results.total_questions == 3
        assert results.successful_questions > 0
        assert results.average_confidence > 0.0
        
        # Verify thread creation and message sending were called
        mock_anythingllm_client.create_thread.assert_called()
        assert mock_anythingllm_client.send_message.call_count == 3  # One per question
        
        # Test job initiation separately
        job_response = await question_service.execute_questions(sample_question_request)
        
        assert job_response.job.type == JobType.QUESTION_PROCESSING
        assert job_response.job.workspace_id == "test-workspace"