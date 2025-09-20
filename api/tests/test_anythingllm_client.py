"""Tests for AnythingLLM integration client."""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

import pytest
import httpx
from httpx import Response

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
    HealthStatus
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


@pytest.fixture
def mock_workspace_data():
    """Mock workspace data."""
    return {
        "id": "ws_123",
        "name": "Test Workspace",
        "slug": "test-workspace",
        "createdAt": "2024-01-01T00:00:00Z",
        "openAiTemp": 0.7,
        "lastUpdatedAt": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def mock_thread_data():
    """Mock thread data."""
    return {
        "id": "thread_123",
        "name": "Test Thread",
        "workspace_id": "ws_123",
        "created_at": "2024-01-01T00:00:00Z"
    }


class TestAnythingLLMClient:
    """Test AnythingLLM client functionality."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, settings):
        """Test client initialization."""
        client = AnythingLLMClient(settings)
        
        assert client.base_url == "http://localhost:3001"
        assert client.api_key == "test-api-key"
        assert client.timeout == 30
        assert client.api_base == "/api/v1"
        assert isinstance(client.circuit_breaker, CircuitBreaker)
        assert isinstance(client.retry_handler, RetryHandler)
    
    @pytest.mark.asyncio
    async def test_session_management(self, client):
        """Test HTTP session management."""
        # Session should be None initially
        assert client._session is None
        
        # Get session should create one
        session = await client._get_session()
        assert isinstance(session, httpx.AsyncClient)
        assert not session.is_closed
        
        # Should reuse existing session
        session2 = await client._get_session()
        assert session is session2
        
        # Close should work
        await client.close()
        assert session.is_closed
    
    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test async context manager."""
        async with client as c:
            assert c is client
            session = await c._get_session()
            assert not session.closed
        
        # Session should be closed after context exit
        assert client._session.closed
    
    @pytest.mark.asyncio
    async def test_make_request_success(self, client):
        """Test successful HTTP request."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/test",
                payload={"status": "success", "data": "test"}
            )
            
            result = await client._make_request("GET", "/test")
            assert result == {"status": "success", "data": "test"}
    
    @pytest.mark.asyncio
    async def test_make_request_error(self, client):
        """Test HTTP request error handling."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/test",
                status=404,
                payload={"error": "Not found"}
            )
            
            with pytest.raises(AnythingLLMError) as exc_info:
                await client._make_request("GET", "/test")
            
            assert "404" in str(exc_info.value)
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_make_request_non_json_response(self, client):
        """Test handling of non-JSON responses."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/test",
                body="Plain text response"
            )
            
            result = await client._make_request("GET", "/test")
            assert result == {"message": "Plain text response", "status": "success"}
    
    @pytest.mark.asyncio
    async def test_create_workspace_success(self, client, mock_workspace_data):
        """Test successful workspace creation."""
        response_data = {
            "workspace": mock_workspace_data,
            "message": "Workspace created successfully"
        }
        
        with aioresponses() as m:
            m.post(
                "http://localhost:3001/api/v1/workspace/new",
                payload=response_data
            )
            
            result = await client.create_workspace("Test Workspace")
            
            assert isinstance(result, WorkspaceResponse)
            assert result.workspace.name == "Test Workspace"
            assert result.message == "Workspace created successfully"
    
    @pytest.mark.asyncio
    async def test_create_workspace_with_config(self, client, mock_workspace_data):
        """Test workspace creation with configuration."""
        config = {"openAiTemp": 0.5, "chatProvider": "openai"}
        response_data = {
            "workspace": mock_workspace_data,
            "message": "Workspace created successfully"
        }
        
        with aioresponses() as m:
            m.post(
                "http://localhost:3001/api/v1/workspace/new",
                payload=response_data
            )
            
            result = await client.create_workspace("Test Workspace", config)
            
            assert isinstance(result, WorkspaceResponse)
            # Verify config was sent in request
            request_data = m.requests[('POST', 'http://localhost:3001/api/v1/workspace/new')][0].kwargs['json']
            assert request_data['openAiTemp'] == 0.5
            assert request_data['chatProvider'] == "openai"
    
    @pytest.mark.asyncio
    async def test_get_workspaces_list_format(self, client, mock_workspace_data):
        """Test getting workspaces with list response format."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/workspaces",
                payload=[mock_workspace_data]
            )
            
            result = await client.get_workspaces()
            
            assert len(result) == 1
            assert isinstance(result[0], WorkspaceInfo)
            assert result[0].name == "Test Workspace"
    
    @pytest.mark.asyncio
    async def test_get_workspaces_dict_format(self, client, mock_workspace_data):
        """Test getting workspaces with dict response format."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/workspaces",
                payload={"workspaces": [mock_workspace_data]}
            )
            
            result = await client.get_workspaces()
            
            assert len(result) == 1
            assert isinstance(result[0], WorkspaceInfo)
            assert result[0].name == "Test Workspace"
    
    @pytest.mark.asyncio
    async def test_get_workspace_success(self, client, mock_workspace_data):
        """Test successful workspace retrieval."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/workspace/ws_123",
                payload={"workspace": mock_workspace_data}
            )
            
            result = await client.get_workspace("ws_123")
            
            assert isinstance(result, WorkspaceInfo)
            assert result.id == "ws_123"
            assert result.name == "Test Workspace"
    
    @pytest.mark.asyncio
    async def test_get_workspace_not_found(self, client):
        """Test workspace not found error."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/workspace/nonexistent",
                status=404,
                payload={"error": "Workspace not found"}
            )
            
            with pytest.raises(WorkspaceNotFoundError):
                await client.get_workspace("nonexistent")
    
    @pytest.mark.asyncio
    async def test_delete_workspace_success(self, client):
        """Test successful workspace deletion."""
        with aioresponses() as m:
            m.delete(
                "http://localhost:3001/api/v1/workspace/ws_123",
                payload={"message": "Workspace deleted"}
            )
            
            result = await client.delete_workspace("ws_123")
            assert result is True
    
    @pytest.mark.asyncio
    async def test_delete_workspace_not_found(self, client):
        """Test workspace deletion when not found."""
        with aioresponses() as m:
            m.delete(
                "http://localhost:3001/api/v1/workspace/nonexistent",
                status=404,
                payload={"error": "Workspace not found"}
            )
            
            result = await client.delete_workspace("nonexistent")
            assert result is False
    
    @pytest.mark.asyncio
    async def test_find_workspace_by_name_found(self, client, mock_workspace_data):
        """Test finding workspace by name when it exists."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/workspaces",
                payload=[mock_workspace_data]
            )
            
            result = await client.find_workspace_by_name("Test Workspace")
            
            assert result is not None
            assert isinstance(result, WorkspaceInfo)
            assert result.name == "Test Workspace"
    
    @pytest.mark.asyncio
    async def test_find_workspace_by_name_not_found(self, client, mock_workspace_data):
        """Test finding workspace by name when it doesn't exist."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/workspaces",
                payload=[mock_workspace_data]
            )
            
            result = await client.find_workspace_by_name("Nonexistent Workspace")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_upload_documents_success(self, client, tmp_path):
        """Test successful document upload."""
        # Create test files
        test_file1 = tmp_path / "test1.pdf"
        test_file2 = tmp_path / "test2.json"
        test_file1.write_text("PDF content")
        test_file2.write_text('{"test": "data"}')
        
        files = [test_file1, test_file2]
        
        response_data = {
            "success": True,
            "message": "Files uploaded successfully",
            "files": [
                {"name": "test1.pdf", "status": "uploaded"},
                {"name": "test2.json", "status": "uploaded"}
            ]
        }
        
        with aioresponses() as m:
            m.post(
                "http://localhost:3001/api/v1/workspace/ws_123/upload",
                payload=response_data
            )
            
            result = await client.upload_documents("ws_123", files)
            
            assert isinstance(result, UploadResponse)
            assert result.success is True
            assert len(result.files) == 2
    
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
    async def test_create_thread_success(self, client, mock_thread_data):
        """Test successful thread creation."""
        response_data = {
            "thread": mock_thread_data,
            "message": "Thread created successfully"
        }
        
        with aioresponses() as m:
            m.post(
                "http://localhost:3001/api/v1/workspace/ws_123/thread/new",
                payload=response_data
            )
            
            result = await client.create_thread("ws_123", "Test Thread")
            
            assert isinstance(result, ThreadResponse)
            assert result.thread.name == "Test Thread"
            assert result.message == "Thread created successfully"
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, client):
        """Test successful message sending."""
        response_data = {
            "id": "msg_123",
            "response": "This is the LLM response",
            "sources": [{"document": "test.pdf", "page": 1}],
            "chatId": "thread_123"
        }
        
        with aioresponses() as m:
            m.post(
                "http://localhost:3001/api/v1/workspace/ws_123/thread/thread_123/chat",
                payload=response_data
            )
            
            result = await client.send_message("ws_123", "thread_123", "Test message")
            
            assert isinstance(result, MessageResponse)
            assert result.response == "This is the LLM response"
            assert result.chatId == "thread_123"
            assert len(result.sources) == 1
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, client):
        """Test health check when service is healthy."""
        response_data = {
            "version": "1.0.0",
            "uptime": 3600,
            "status": "ok"
        }
        
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/system/system-vectors",
                payload=response_data
            )
            
            result = await client.health_check()
            
            assert isinstance(result, HealthStatus)
            assert result.status == "healthy"
            assert result.version == "1.0.0"
            assert result.uptime == 3600
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, client):
        """Test health check when service is unhealthy."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/system/system-vectors",
                status=500,
                payload={"error": "Internal server error"}
            )
            
            result = await client.health_check()
            
            assert isinstance(result, HealthStatus)
            assert result.status == "unhealthy"


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
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=2, timeout=1)
        
        async def failing_func():
            raise Exception("Test failure")
        
        # First failure
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitState.CLOSED
        
        # Second failure - should open circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.state == CircuitState.OPEN
        
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
        
        start_time = asyncio.get_event_loop().time()
        
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


class TestIntegrationWithResilience:
    """Test integration of client with resilience patterns."""
    
    @pytest.mark.asyncio
    async def test_request_with_resilience_success(self, client):
        """Test successful request with resilience patterns."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/test",
                payload={"status": "success"}
            )
            
            result = await client._request_with_resilience("GET", "/test")
            assert result == {"status": "success"}
    
    @pytest.mark.asyncio
    async def test_request_with_resilience_retry_success(self, client):
        """Test request succeeds after retries."""
        call_count = 0
        
        def response_callback(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return aioresponses.CallbackResult(status=500, payload={"error": "Server error"})
            return aioresponses.CallbackResult(status=200, payload={"status": "success"})
        
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/test",
                callback=response_callback,
                repeat=True
            )
            
            result = await client._request_with_resilience("GET", "/test")
            assert result == {"status": "success"}
            assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_request_with_resilience_circuit_breaker_opens(self, client):
        """Test circuit breaker opens after repeated failures."""
        with aioresponses() as m:
            m.get(
                "http://localhost:3001/api/v1/test",
                status=500,
                payload={"error": "Server error"},
                repeat=True
            )
            
            # Make enough requests to open circuit breaker
            for _ in range(6):  # More than failure threshold (5)
                try:
                    await client._request_with_resilience("GET", "/test")
                except (AnythingLLMError, Exception):
                    pass
            
            # Circuit should now be open
            assert client.circuit_breaker.state == CircuitState.OPEN
            
            # Next request should fail immediately
            with pytest.raises(AnythingLLMError, match="Circuit breaker is OPEN"):
                await client._request_with_resilience("GET", "/test")


@pytest.mark.asyncio
async def test_create_anythingllm_client_factory(settings):
    """Test factory function for creating client."""
    from app.integrations.anythingllm_client import create_anythingllm_client
    
    client = create_anythingllm_client(settings)
    assert isinstance(client, AnythingLLMClient)
    assert client.base_url == "http://localhost:3001"
    assert client.api_key == "test-api-key"