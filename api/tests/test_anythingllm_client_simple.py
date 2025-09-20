"""Simple tests for AnythingLLM integration client."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.integrations.anythingllm_client import (
    AnythingLLMClient,
    AnythingLLMError,
    WorkspaceNotFoundError,
    DocumentUploadError,
    ThreadError,
    MessageError,
    CircuitBreaker,
    RetryHandler,
    CircuitState,
    WorkspaceInfo,
    WorkspaceResponse,
    UploadResponse,
    ThreadResponse,
    MessageResponse,
    HealthStatus,
    create_anythingllm_client
)


@pytest.fixture
def settings():
    """Create test settings."""
    # Set required environment variables for testing
    os.environ.update({
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "ANYTHINGLLM_URL": "http://localhost:3001",
        "ANYTHINGLLM_API_KEY": "test-api-key",
        "SECRET_KEY": "test-secret-key"
    })
    
    return Settings(
        database_url="postgresql://test:test@localhost/test",
        anythingllm_url="http://localhost:3001",
        anythingllm_api_key="test-api-key",
        anythingllm_timeout=30,
        secret_key="test-secret-key"
    )


@pytest.fixture
def client(settings):
    """Create AnythingLLM client."""
    return AnythingLLMClient(settings)


class TestAnythingLLMClientBasics:
    """Test basic AnythingLLM client functionality."""
    
    def test_client_initialization(self, settings):
        """Test client initialization."""
        client = AnythingLLMClient(settings)
        
        assert client.base_url == "http://localhost:3001"
        assert client.api_key == "test-api-key"
        assert client.timeout == 30
        assert client.api_base == "/api/v1"
        assert isinstance(client.circuit_breaker, CircuitBreaker)
        assert isinstance(client.retry_handler, RetryHandler)
        assert client._session is None
    
    def test_factory_function(self, settings):
        """Test factory function for creating client."""
        client = create_anythingllm_client(settings)
        assert isinstance(client, AnythingLLMClient)
        assert client.base_url == "http://localhost:3001"
        assert client.api_key == "test-api-key"
    
    @pytest.mark.asyncio
    async def test_session_creation(self, client):
        """Test HTTP session creation."""
        # Session should be None initially
        assert client._session is None
        
        # Get session should create one
        session = await client._get_session()
        assert session is not None
        assert not session.is_closed
        
        # Should reuse existing session
        session2 = await client._get_session()
        assert session is session2
        
        # Clean up
        await client.close()
    
    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager."""
        async with client as c:
            assert c is client
            session = await c._get_session()
            assert not session.is_closed
        
        # Session should be closed after context exit
        assert client._session.is_closed


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state."""
        cb = CircuitBreaker(failure_threshold=3, timeout=1)
        
        async def success_func():
            return "success"
        
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1)
        
        async def failing_func():
            raise Exception("Test failure")
        
        # First failure
        with pytest.raises(Exception, match="Test failure"):
            await cb.call(failing_func)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1
        
        # Second failure - should open circuit
        with pytest.raises(Exception, match="Test failure"):
            await cb.call(failing_func)
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == 2
        
        # Third call should fail immediately due to open circuit
        with pytest.raises(AnythingLLMError, match="Circuit breaker is OPEN"):
            await cb.call(failing_func)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_transition(self):
        """Test circuit breaker transitions to half-open after timeout."""
        cb = CircuitBreaker(failure_threshold=1, timeout=0.1)  # Short timeout for testing
        
        async def failing_func():
            raise Exception("Test failure")
        
        # Trigger failure to open circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        await asyncio.sleep(0.2)
        
        # Next call should transition to half-open, but still fail
        with pytest.raises(Exception):
            await cb.call(failing_func)
        # State should remain open after failure in half-open
        assert cb.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery from half-open to closed."""
        cb = CircuitBreaker(failure_threshold=1, timeout=0.1)
        
        async def failing_func():
            raise Exception("Test failure")
        
        async def success_func():
            return "success"
        
        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitState.OPEN
        
        # Wait for timeout
        await asyncio.sleep(0.2)
        
        # Successful call should close the circuit
        result = await cb.call(success_func)
        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0


class TestRetryHandler:
    """Test retry handler functionality."""
    
    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        """Test successful execution on first attempt."""
        retry_handler = RetryHandler(max_retries=3, base_delay=0.01)
        
        async def success_func():
            return "success"
        
        result = await retry_handler.retry_with_backoff(success_func)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test successful execution after some failures."""
        retry_handler = RetryHandler(max_retries=3, base_delay=0.01)
        call_count = 0
        
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception(f"Failure {call_count}")
            return "success"
        
        result = await retry_handler.retry_with_backoff(flaky_func)
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_max_retries_exceeded(self):
        """Test behavior when max retries are exceeded."""
        retry_handler = RetryHandler(max_retries=2, base_delay=0.01)
        call_count = 0
        
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception(f"Failure {call_count}")
        
        with pytest.raises(Exception, match="Failure 3"):
            await retry_handler.retry_with_backoff(always_failing_func)
        
        assert call_count == 3  # Initial call + 2 retries
    
    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self):
        """Test exponential backoff timing."""
        retry_handler = RetryHandler(max_retries=2, base_delay=0.1, max_delay=1.0)
        call_times = []
        
        async def failing_func():
            call_times.append(asyncio.get_event_loop().time())
            raise Exception("Test failure")
        
        with pytest.raises(Exception):
            await retry_handler.retry_with_backoff(failing_func)
        
        # Verify timing between calls (approximate due to test timing variations)
        assert len(call_times) == 3
        
        # First retry should be after ~0.1s
        delay1 = call_times[1] - call_times[0]
        assert 0.08 <= delay1 <= 0.15
        
        # Second retry should be after ~0.2s
        delay2 = call_times[2] - call_times[1]
        assert 0.18 <= delay2 <= 0.25


class TestDataModels:
    """Test Pydantic data models."""
    
    def test_workspace_info_model(self):
        """Test WorkspaceInfo model."""
        data = {
            "id": "ws_123",
            "name": "Test Workspace",
            "slug": "test-workspace",
            "createdAt": "2024-01-01T00:00:00Z",
            "openAiTemp": 0.7,
            "lastUpdatedAt": "2024-01-01T00:00:00Z"
        }
        
        workspace = WorkspaceInfo(**data)
        assert workspace.id == "ws_123"
        assert workspace.name == "Test Workspace"
        assert workspace.slug == "test-workspace"
        assert workspace.openAiTemp == 0.7
    
    def test_workspace_response_model(self):
        """Test WorkspaceResponse model."""
        workspace_data = {
            "id": "ws_123",
            "name": "Test Workspace",
            "slug": "test-workspace",
            "createdAt": "2024-01-01T00:00:00Z"
        }
        
        data = {
            "workspace": workspace_data,
            "message": "Workspace created successfully"
        }
        
        response = WorkspaceResponse(**data)
        assert response.workspace.id == "ws_123"
        assert response.message == "Workspace created successfully"
    
    def test_upload_response_model(self):
        """Test UploadResponse model."""
        data = {
            "success": True,
            "message": "Files uploaded successfully",
            "files": [
                {"name": "test.pdf", "status": "uploaded"},
                {"name": "test.json", "status": "uploaded"}
            ]
        }
        
        response = UploadResponse(**data)
        assert response.success is True
        assert response.message == "Files uploaded successfully"
        assert len(response.files) == 2
    
    def test_thread_response_model(self):
        """Test ThreadResponse model."""
        thread_data = {
            "id": "thread_123",
            "name": "Test Thread",
            "workspace_id": "ws_123",
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        data = {
            "thread": thread_data,
            "message": "Thread created successfully"
        }
        
        response = ThreadResponse(**data)
        assert response.thread.id == "thread_123"
        assert response.thread.name == "Test Thread"
        assert response.message == "Thread created successfully"
    
    def test_message_response_model(self):
        """Test MessageResponse model."""
        data = {
            "id": "msg_123",
            "response": "This is the LLM response",
            "sources": [{"document": "test.pdf", "page": 1}],
            "chatId": "thread_123"
        }
        
        response = MessageResponse(**data)
        assert response.id == "msg_123"
        assert response.response == "This is the LLM response"
        assert response.chatId == "thread_123"
        assert len(response.sources) == 1
    
    def test_health_status_model(self):
        """Test HealthStatus model."""
        data = {
            "status": "healthy",
            "version": "1.0.0",
            "uptime": 3600
        }
        
        health = HealthStatus(**data)
        assert health.status == "healthy"
        assert health.version == "1.0.0"
        assert health.uptime == 3600


class TestExceptionClasses:
    """Test custom exception classes."""
    
    def test_anythingllm_error(self):
        """Test AnythingLLMError exception."""
        error = AnythingLLMError("Test error", status_code=500, response_data={"error": "details"})
        
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.status_code == 500
        assert error.response_data == {"error": "details"}
    
    def test_workspace_not_found_error(self):
        """Test WorkspaceNotFoundError exception."""
        error = WorkspaceNotFoundError("Workspace not found")
        
        assert str(error) == "Workspace not found"
        assert isinstance(error, AnythingLLMError)
    
    def test_document_upload_error(self):
        """Test DocumentUploadError exception."""
        error = DocumentUploadError("Upload failed")
        
        assert str(error) == "Upload failed"
        assert isinstance(error, AnythingLLMError)
    
    def test_thread_error(self):
        """Test ThreadError exception."""
        error = ThreadError("Thread operation failed")
        
        assert str(error) == "Thread operation failed"
        assert isinstance(error, AnythingLLMError)
    
    def test_message_error(self):
        """Test MessageError exception."""
        error = MessageError("Message sending failed")
        
        assert str(error) == "Message sending failed"
        assert isinstance(error, AnythingLLMError)


class TestClientMethods:
    """Test client methods with mocked HTTP calls."""
    
    @pytest.mark.asyncio
    async def test_upload_documents_empty_list(self, client):
        """Test document upload with empty file list."""
        with pytest.raises(DocumentUploadError, match="No files provided"):
            await client.upload_documents("ws_123", [])
    
    @pytest.mark.asyncio
    async def test_upload_documents_file_not_found(self, client):
        """Test document upload with non-existent file."""
        files = [Path("/nonexistent/file.pdf")]
        
        with pytest.raises(DocumentUploadError, match="File not found"):
            await client.upload_documents("ws_123", files)
    
    @pytest.mark.asyncio
    async def test_upload_documents_with_valid_files(self, client, tmp_path):
        """Test document upload with valid files (mocked HTTP call)."""
        # Create test files
        test_file1 = tmp_path / "test1.pdf"
        test_file2 = tmp_path / "test2.json"
        test_file1.write_text("PDF content")
        test_file2.write_text('{"test": "data"}')
        
        files = [test_file1, test_file2]
        
        # Mock the HTTP request
        with patch.object(client, '_request_with_resilience') as mock_request:
            mock_request.return_value = {
                "success": True,
                "message": "Files uploaded successfully",
                "files": [
                    {"name": "test1.pdf", "status": "uploaded"},
                    {"name": "test2.json", "status": "uploaded"}
                ]
            }
            
            result = await client.upload_documents("ws_123", files)
            
            assert isinstance(result, UploadResponse)
            assert result.success is True
            assert len(result.files) == 2
            
            # Verify the request was made correctly
            mock_request.assert_called_once()
            args, kwargs = mock_request.call_args
            assert args[0] == "POST"
            assert args[1] == "/workspace/ws_123/upload"
            assert "files" in kwargs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])