"""Comprehensive unit tests for QuestionService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.integrations.anythingllm_client import AnythingLLMClient, ThreadError
from app.models.pydantic_models import (
    ExportFormat,
    JobStatus,
    LLMConfig,
    LLMProvider,
    Question,
    QuestionRequest,
    QuestionResult,
)
from app.repositories.job_repository import JobRepository
from app.services.question_service import (
    QuestionProcessingError,
    QuestionService,
    ThreadManagementError,
)
from tests.fixtures.mock_data import mock_data


class TestQuestionService:
    """Test cases for QuestionService."""

    @pytest.fixture
    def mock_anythingllm_client(self):
        """Mock AnythingLLM client."""
        client = AsyncMock(spec=AnythingLLMClient)
        client.create_thread.return_value = mock_data.create_mock_anythingllm_responses()["thread_create"]
        client.send_message.return_value = mock_data.create_mock_anythingllm_responses()["message_send"]
        client.delete_thread.return_value = True
        return client

    @pytest.fixture
    def mock_job_repository(self):
        """Mock job repository."""
        repo = AsyncMock(spec=JobRepository)
        repo.create_job.return_value = mock_data.create_mock_job()
        repo.update_job_status.return_value = mock_data.create_mock_job(status=JobStatus.COMPLETED)
        return repo

    @pytest.fixture
    def question_service(self, mock_anythingllm_client, mock_job_repository):
        """Create QuestionService instance with mocked dependencies."""
        return QuestionService(
            anythingllm_client=mock_anythingllm_client,
            job_repository=mock_job_repository,
            max_concurrent_questions=5,
        )

    @pytest.fixture
    def sample_questions(self):
        """Sample questions for testing."""
        return mock_data.create_sample_questions()

    @pytest.fixture
    def sample_question_request(self, sample_questions):
        """Sample question request."""
        return QuestionRequest(
            workspace_id="ws_123",
            questions=sample_questions[:3],  # Use first 3 questions
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=1000,
                timeout=30,
            ),
            export_format=ExportFormat.JSON,
        )

    @pytest.mark.asyncio
    async def test_execute_questions_success(
        self,
        question_service,
        sample_question_request,
        mock_job_repository,
        mock_anythingllm_client,
    ):
        """Test successful question execution."""
        result = await question_service.execute_questions(sample_question_request)
        
        assert result.job_id is not None
        assert result.status == JobStatus.PENDING
        mock_job_repository.create_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_question_set_success(
        self,
        question_service,
        sample_questions,
        mock_anythingllm_client,
    ):
        """Test successful question set processing."""
        workspace_id = "ws_123"
        
        result = await question_service.process_question_set(sample_questions[:3], workspace_id)
        
        assert len(result.results) == 3
        assert all(r.success for r in result.results)
        assert result.total_questions == 3
        assert result.successful_questions == 3
        mock_anythingllm_client.create_thread.assert_called()
        mock_anythingllm_client.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_create_thread_success(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test successful thread creation."""
        workspace_id = "ws_123"
        thread_name = "Test Thread"
        
        result = await question_service.create_thread(workspace_id, thread_name)
        
        assert result.thread_id is not None
        assert result.workspace_id == workspace_id
        mock_anythingllm_client.create_thread.assert_called_once_with(workspace_id, thread_name)

    @pytest.mark.asyncio
    async def test_create_thread_failure(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test thread creation failure."""
        mock_anythingllm_client.create_thread.side_effect = ThreadError("Failed to create thread")
        
        with pytest.raises(ThreadManagementError):
            await question_service.create_thread("ws_123", "Test Thread")

    @pytest.mark.asyncio
    async def test_run_single_question_success(
        self,
        question_service,
        sample_questions,
        mock_anythingllm_client,
    ):
        """Test successful single question execution."""
        question = sample_questions[0]
        thread_id = "thread_123"
        
        result = await question_service.run_single_question(question, thread_id)
        
        assert result.question_id == question.id
        assert result.success is True
        assert result.confidence_score > 0
        mock_anythingllm_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_single_question_failure(
        self,
        question_service,
        sample_questions,
        mock_anythingllm_client,
    ):
        """Test single question execution failure."""
        mock_anythingllm_client.send_message.side_effect = Exception("Network error")
        
        question = sample_questions[0]
        thread_id = "thread_123"
        
        result = await question_service.run_single_question(question, thread_id)
        
        assert result.success is False
        assert "Network error" in result.response

    @pytest.mark.asyncio
    async def test_route_question_by_document_type(
        self,
        question_service,
        sample_questions,
    ):
        """Test question routing by document type."""
        question = sample_questions[0]
        doc_types = ["contracts", "invoices", "reports"]
        
        result = await question_service.route_question_by_document_type(question, doc_types)
        
        assert result in doc_types or result == "general"

    @pytest.mark.asyncio
    async def test_calculate_confidence_score_high(
        self,
        question_service,
    ):
        """Test confidence score calculation with high confidence."""
        response = "The contract value is $100,000 as specified in the agreement."
        expected_fragments = ["contract", "value", "$", "100,000"]
        
        score = await question_service.calculate_confidence_score(response, expected_fragments)
        
        assert score > 0.8  # High confidence
        assert score <= 1.0

    @pytest.mark.asyncio
    async def test_calculate_confidence_score_low(
        self,
        question_service,
    ):
        """Test confidence score calculation with low confidence."""
        response = "I'm not sure about that information."
        expected_fragments = ["contract", "value", "$", "amount"]
        
        score = await question_service.calculate_confidence_score(response, expected_fragments)
        
        assert score < 0.5  # Low confidence
        assert score >= 0.0

    @pytest.mark.asyncio
    async def test_manage_concurrent_processing_success(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test successful concurrent question processing."""
        questions = mock_data.create_large_question_set(10)
        max_concurrent = 3
        
        results = await question_service.manage_concurrent_processing(questions, max_concurrent)
        
        assert len(results) == 10
        assert all(isinstance(r, QuestionResult) for r in results)
        # Verify concurrent execution (should be called multiple times)
        assert mock_anythingllm_client.send_message.call_count == 10

    @pytest.mark.asyncio
    async def test_manage_concurrent_processing_with_failures(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test concurrent processing with some failures."""
        questions = mock_data.create_large_question_set(5)
        
        # Make some calls fail
        def side_effect(*args, **kwargs):
            if mock_anythingllm_client.send_message.call_count % 2 == 0:
                raise Exception("Simulated failure")
            return mock_data.create_mock_anythingllm_responses()["message_send"]
        
        mock_anythingllm_client.send_message.side_effect = side_effect
        
        results = await question_service.manage_concurrent_processing(questions, 2)
        
        assert len(results) == 5
        # Some should succeed, some should fail
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        assert len(successful) > 0
        assert len(failed) > 0

    @pytest.mark.asyncio
    async def test_cleanup_threads_success(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test successful thread cleanup."""
        workspace_id = "ws_123"
        thread_ids = ["thread_1", "thread_2", "thread_3"]
        
        result = await question_service.cleanup_threads(workspace_id, thread_ids)
        
        assert result is True
        assert mock_anythingllm_client.delete_thread.call_count == 3

    @pytest.mark.asyncio
    async def test_cleanup_threads_partial_failure(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test thread cleanup with partial failures."""
        workspace_id = "ws_123"
        thread_ids = ["thread_1", "thread_2", "thread_3"]
        
        # Make some deletions fail
        def side_effect(workspace_id, thread_id):
            if thread_id == "thread_2":
                raise Exception("Deletion failed")
            return True
        
        mock_anythingllm_client.delete_thread.side_effect = side_effect
        
        result = await question_service.cleanup_threads(workspace_id, thread_ids)
        
        # Should still return True even with partial failures
        assert result is True
        assert mock_anythingllm_client.delete_thread.call_count == 3

    @pytest.mark.asyncio
    async def test_export_results_json(
        self,
        question_service,
        mock_job_repository,
    ):
        """Test results export in JSON format."""
        job_id = "job_123"
        mock_results = [mock_data.create_mock_question_result() for _ in range(3)]
        mock_job = mock_data.create_mock_job(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={"results": [r.model_dump() for r in mock_results]}
        )
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await question_service.export_results(job_id, ExportFormat.JSON)
        
        assert result.format == ExportFormat.JSON
        assert result.data is not None
        assert len(result.data["results"]) == 3

    @pytest.mark.asyncio
    async def test_export_results_csv(
        self,
        question_service,
        mock_job_repository,
    ):
        """Test results export in CSV format."""
        job_id = "job_123"
        mock_results = [mock_data.create_mock_question_result() for _ in range(3)]
        mock_job = mock_data.create_mock_job(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            result={"results": [r.model_dump() for r in mock_results]}
        )
        mock_job_repository.get_by_id.return_value = mock_job
        
        result = await question_service.export_results(job_id, ExportFormat.CSV)
        
        assert result.format == ExportFormat.CSV
        assert result.data is not None
        assert "question_id,question_text,response" in result.data

    @pytest.mark.asyncio
    async def test_export_results_job_not_found(
        self,
        question_service,
        mock_job_repository,
    ):
        """Test results export when job is not found."""
        mock_job_repository.get_by_id.return_value = None
        
        with pytest.raises(QuestionProcessingError) as exc_info:
            await question_service.export_results("nonexistent", ExportFormat.JSON)
        
        assert "Job not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_question_processing_with_different_llm_models(
        self,
        question_service,
        sample_questions,
        mock_anythingllm_client,
    ):
        """Test question processing with different LLM models."""
        workspace_id = "ws_123"
        
        # Test with different LLM configurations
        llm_configs = [
            LLMConfig(provider=LLMProvider.OPENAI, model="gpt-3.5-turbo"),
            LLMConfig(provider=LLMProvider.ANTHROPIC, model="claude-3-sonnet"),
            LLMConfig(provider=LLMProvider.OLLAMA, model="llama2"),
        ]
        
        for llm_config in llm_configs:
            # Update questions with specific LLM config
            questions_with_config = [
                Question(
                    id=q.id,
                    text=q.text,
                    expected_fragments=q.expected_fragments,
                    llm_config=llm_config,
                )
                for q in sample_questions[:2]
            ]
            
            result = await question_service.process_question_set(questions_with_config, workspace_id)
            
            assert len(result.results) == 2
            assert all(r.success for r in result.results)

    @pytest.mark.asyncio
    async def test_performance_large_question_set(
        self,
        question_service,
        mock_anythingllm_client,
    ):
        """Test performance with large question set."""
        large_question_set = mock_data.create_large_question_set(50)
        workspace_id = "ws_123"
        
        import time
        start_time = time.time()
        
        result = await question_service.process_question_set(large_question_set, workspace_id)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        assert len(result.results) == 50
        assert processing_time < 30  # Should complete within 30 seconds
        assert result.average_processing_time > 0

    @pytest.mark.asyncio
    async def test_error_recovery_and_retry(
        self,
        question_service,
        sample_questions,
        mock_anythingllm_client,
    ):
        """Test error recovery and retry mechanisms."""
        workspace_id = "ws_123"
        
        # Simulate intermittent failures
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First 2 calls fail
                raise Exception("Temporary failure")
            return mock_data.create_mock_anythingllm_responses()["message_send"]
        
        mock_anythingllm_client.send_message.side_effect = side_effect
        
        # Process single question with retry
        question = sample_questions[0]
        thread_id = "thread_123"
        
        result = await question_service.run_single_question(question, thread_id)
        
        # Should eventually succeed after retries
        assert result.success is True
        assert mock_anythingllm_client.send_message.call_count >= 3