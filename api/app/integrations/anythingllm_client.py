"""AnythingLLM integration client with resilience patterns."""

import asyncio
import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AnythingLLMError(Exception):
    """Base exception for AnythingLLM client errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message)


class WorkspaceNotFoundError(AnythingLLMError):
    """Workspace not found error."""
    pass


class DocumentUploadError(AnythingLLMError):
    """Document upload error."""
    pass


class ThreadError(AnythingLLMError):
    """Thread operation error."""
    pass


class MessageError(AnythingLLMError):
    """Message sending error."""
    pass


# Response Models
class WorkspaceInfo(BaseModel):
    """Workspace information model."""
    id: str = Field(..., description="Workspace ID")
    name: str = Field(..., description="Workspace name")
    slug: str = Field(..., description="Workspace slug")
    createdAt: str = Field(..., description="Creation timestamp")
    openAiTemp: Optional[float] = Field(None, description="OpenAI temperature")
    lastUpdatedAt: Optional[str] = Field(None, description="Last update timestamp")


class WorkspaceResponse(BaseModel):
    """Workspace creation/update response."""
    workspace: WorkspaceInfo = Field(..., description="Workspace details")
    message: str = Field(..., description="Response message")


class UploadResponse(BaseModel):
    """Document upload response."""
    success: bool = Field(..., description="Upload success status")
    message: str = Field(..., description="Response message")
    files: List[Dict[str, Any]] = Field(default_factory=list, description="Uploaded files info")


class ThreadInfo(BaseModel):
    """Thread information model."""
    id: str = Field(..., description="Thread ID")
    name: str = Field(..., description="Thread name")
    workspace_id: str = Field(..., description="Associated workspace ID")
    created_at: str = Field(..., description="Creation timestamp")


class ThreadResponse(BaseModel):
    """Thread creation response."""
    thread: ThreadInfo = Field(..., description="Thread details")
    message: str = Field(..., description="Response message")


class MessageResponse(BaseModel):
    """Message response model."""
    id: str = Field(..., description="Message ID")
    response: str = Field(..., description="LLM response")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Source documents")
    chatId: str = Field(..., description="Chat/thread ID")


class HealthStatus(BaseModel):
    """Health check status."""
    status: str = Field(..., description="Health status")
    version: Optional[str] = Field(None, description="AnythingLLM version")
    uptime: Optional[int] = Field(None, description="Uptime in seconds")


class CircuitBreaker:
    """Circuit breaker implementation for resilience."""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED
        self._lock = asyncio.Lock()
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self.last_failure_time and time.time() - self.last_failure_time > self.timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise AnythingLLMError("Circuit breaker is OPEN - service unavailable")
        
        try:
            result = await func(*args, **kwargs)
            
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit breaker transitioning to CLOSED")
            
            return result
            
        except Exception as e:
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(f"Circuit breaker transitioning to OPEN after {self.failure_count} failures")
            
            raise e


class RetryHandler:
    """Retry handler with exponential backoff."""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with retry and exponential backoff."""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt == self.max_retries:
                    logger.error(f"Max retries ({self.max_retries}) exceeded for {func.__name__}")
                    break
                
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
        
        raise last_exception


class AnythingLLMClient:
    """AnythingLLM integration client with resilience patterns."""
    
    def __init__(self, settings: Settings):
        self.base_url = settings.anythingllm_url.rstrip('/')
        self.api_key = settings.anythingllm_api_key
        self.timeout = settings.anythingllm_timeout
        self.api_base = "/api/v1"
        
        # Resilience components
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        self.retry_handler = RetryHandler(max_retries=3, base_delay=1.0, max_delay=30.0)
        
        # HTTP session will be created when needed
        self._session: Optional[httpx.AsyncClient] = None
    
    async def _get_session(self) -> httpx.AsyncClient:
        """Get or create HTTP session."""
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        return self._session
    
    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.is_closed:
            await self._session.aclose()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with error handling."""
        session = await self._get_session()
        url = urljoin(self.base_url, f"{self.api_base}{endpoint}")
        
        # Prepare request kwargs
        kwargs = {}
        if params:
            kwargs["params"] = params
        
        if files:
            # For file uploads, don't set Content-Type header
            headers = {k: v for k, v in session.headers.items() if k.lower() != "content-type"}
            kwargs["headers"] = headers
            kwargs["files"] = files
        elif data:
            kwargs["json"] = data
        
        logger.debug(f"Making {method} request to {url}")
        
        try:
            response = await session.request(method, url, **kwargs)
            response_text = response.text
            
            if response.status_code >= 400:
                try:
                    error_data = json.loads(response_text)
                except json.JSONDecodeError:
                    error_data = {"error": response_text}
                
                error_msg = f"AnythingLLM API error: {response.status_code} - {error_data.get('error', response_text)}"
                logger.error(f"{error_msg} for {method} {url}")
                
                raise AnythingLLMError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data
                )
            
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON response from {url}: {response_text}")
                return {"message": response_text, "status": "success"}
                
        except httpx.RequestError as e:
            error_msg = f"HTTP client error for {method} {url}: {e}"
            logger.error(error_msg)
            raise AnythingLLMError(error_msg)
    
    async def _request_with_resilience(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make request with circuit breaker and retry logic."""
        return await self.circuit_breaker.call(
            self.retry_handler.retry_with_backoff,
            self._make_request,
            method,
            endpoint,
            **kwargs
        )
    
    # Workspace Management Methods
    
    async def create_workspace(self, name: str, config: Optional[Dict] = None) -> WorkspaceResponse:
        """Create a new workspace in AnythingLLM."""
        logger.info(f"Creating workspace: {name}")
        
        payload = {"name": name}
        if config:
            payload.update(config)
        
        try:
            response_data = await self._request_with_resilience(
                "POST", "/workspace/new", data=payload
            )
            
            logger.info(f"Successfully created workspace: {name}")
            return WorkspaceResponse(**response_data)
            
        except Exception as e:
            logger.error(f"Failed to create workspace {name}: {e}")
            raise AnythingLLMError(f"Failed to create workspace: {e}")
    
    async def get_workspaces(self) -> List[WorkspaceInfo]:
        """Get list of all workspaces."""
        logger.debug("Fetching workspaces list")
        
        try:
            response_data = await self._request_with_resilience("GET", "/workspaces")
            
            # Handle different response formats
            if isinstance(response_data, list):
                workspaces = response_data
            elif isinstance(response_data, dict) and "workspaces" in response_data:
                workspaces = response_data["workspaces"]
            else:
                logger.warning(f"Unexpected workspaces response format: {response_data}")
                workspaces = []
            
            workspace_list = [WorkspaceInfo(**ws) for ws in workspaces]
            logger.debug(f"Found {len(workspace_list)} workspaces")
            return workspace_list
            
        except Exception as e:
            logger.error(f"Failed to fetch workspaces: {e}")
            raise AnythingLLMError(f"Failed to fetch workspaces: {e}")
    
    async def get_workspace(self, workspace_id: str) -> WorkspaceInfo:
        """Get workspace by ID or slug."""
        logger.debug(f"Fetching workspace: {workspace_id}")
        
        try:
            response_data = await self._request_with_resilience(
                "GET", f"/workspace/{workspace_id}"
            )
            
            if "workspace" in response_data:
                workspace_data = response_data["workspace"]
            else:
                workspace_data = response_data
            
            logger.debug(f"Successfully fetched workspace: {workspace_id}")
            return WorkspaceInfo(**workspace_data)
            
        except AnythingLLMError as e:
            if e.status_code == 404:
                raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch workspace {workspace_id}: {e}")
            raise AnythingLLMError(f"Failed to fetch workspace: {e}")
    
    async def delete_workspace(self, workspace_id: str) -> bool:
        """Delete workspace by ID or slug."""
        logger.info(f"Deleting workspace: {workspace_id}")
        
        try:
            await self._request_with_resilience("DELETE", f"/workspace/{workspace_id}")
            logger.info(f"Successfully deleted workspace: {workspace_id}")
            return True
            
        except AnythingLLMError as e:
            if e.status_code == 404:
                logger.warning(f"Workspace not found for deletion: {workspace_id}")
                return False
            raise
        except Exception as e:
            logger.error(f"Failed to delete workspace {workspace_id}: {e}")
            raise AnythingLLMError(f"Failed to delete workspace: {e}")
    
    async def find_workspace_by_name(self, name: str) -> Optional[WorkspaceInfo]:
        """Find workspace by name."""
        logger.debug(f"Searching for workspace by name: {name}")
        
        try:
            workspaces = await self.get_workspaces()
            for workspace in workspaces:
                if workspace.name == name:
                    logger.debug(f"Found workspace by name: {name} -> {workspace.id}")
                    return workspace
            
            logger.debug(f"No workspace found with name: {name}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to search workspace by name {name}: {e}")
            raise AnythingLLMError(f"Failed to search workspace by name: {e}")
    
    # Document Upload Methods
    
    async def upload_documents(self, workspace_id: str, files: List[Path]) -> UploadResponse:
        """Upload documents to workspace."""
        logger.info(f"Uploading {len(files)} documents to workspace: {workspace_id}")
        
        if not files:
            raise DocumentUploadError("No files provided for upload")
        
        # Prepare files for upload
        file_data = {}
        file_handles = []
        
        try:
            for i, file_path in enumerate(files):
                if not file_path.exists():
                    raise DocumentUploadError(f"File not found: {file_path}")
                
                # Open file and add to files dict
                file_handle = open(file_path, 'rb')
                file_handles.append(file_handle)
                file_data[f'files'] = (file_path.name, file_handle, 'application/octet-stream')
            
            # Use the standard request method for file upload
            response_data = await self._request_with_resilience(
                "POST", f"/workspace/{workspace_id}/upload", files=file_data
            )
            
            logger.info(f"Successfully uploaded {len(files)} documents to workspace: {workspace_id}")
            
            # Ensure response has required fields
            if not isinstance(response_data, dict):
                response_data = {"success": True, "message": str(response_data), "files": []}
            
            if "success" not in response_data:
                response_data["success"] = True
            if "files" not in response_data:
                response_data["files"] = []
            
            return UploadResponse(**response_data)
                
        except DocumentUploadError:
            raise
        except Exception as e:
            logger.error(f"Failed to upload documents to workspace {workspace_id}: {e}")
            raise DocumentUploadError(f"Failed to upload documents: {e}")
        finally:
            # Close file handles
            for file_handle in file_handles:
                file_handle.close()
    
    # Thread Management Methods
    
    async def create_thread(self, workspace_id: str, name: str) -> ThreadResponse:
        """Create a new thread in workspace."""
        logger.info(f"Creating thread '{name}' in workspace: {workspace_id}")
        
        payload = {"name": name}
        
        try:
            response_data = await self._request_with_resilience(
                "POST", f"/workspace/{workspace_id}/thread/new", data=payload
            )
            
            logger.info(f"Successfully created thread '{name}' in workspace: {workspace_id}")
            return ThreadResponse(**response_data)
            
        except Exception as e:
            logger.error(f"Failed to create thread '{name}' in workspace {workspace_id}: {e}")
            raise ThreadError(f"Failed to create thread: {e}")
    
    async def send_message(
        self,
        workspace_id: str,
        thread_id: str,
        message: str,
        mode: str = "query"
    ) -> MessageResponse:
        """Send message to thread and get response."""
        logger.debug(f"Sending message to thread {thread_id} in workspace {workspace_id}")
        
        payload = {
            "message": message,
            "mode": mode
        }
        
        try:
            response_data = await self._request_with_resilience(
                "POST", f"/workspace/{workspace_id}/thread/{thread_id}/chat", data=payload
            )
            
            logger.debug(f"Successfully sent message to thread {thread_id}")
            return MessageResponse(**response_data)
            
        except Exception as e:
            logger.error(f"Failed to send message to thread {thread_id}: {e}")
            raise MessageError(f"Failed to send message: {e}")
    
    # Health Check Methods
    
    async def health_check(self) -> HealthStatus:
        """Perform health check on AnythingLLM service."""
        logger.debug("Performing health check")
        
        try:
            # Try a simple API call to check connectivity
            response_data = await self._request_with_resilience("GET", "/system/system-vectors")
            
            # If we get here, the service is responding
            return HealthStatus(
                status="healthy",
                version=response_data.get("version"),
                uptime=response_data.get("uptime")
            )
            
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return HealthStatus(status="unhealthy")
    
    # Utility Methods
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Factory function for dependency injection
def create_anythingllm_client(settings: Settings) -> AnythingLLMClient:
    """Create AnythingLLM client from settings."""
    return AnythingLLMClient(settings)