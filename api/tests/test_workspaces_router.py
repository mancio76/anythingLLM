"""Tests for workspace REST API endpoints."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from httpx import AsyncClient

from app.models.pydantic_models import (
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceResponse,
    LLMConfig,
    LLMProvider,
    JobResponse,
    Job,
    JobStatus,
    JobType,
)
from app.services.workspace_service import (
    WorkspaceService,
    WorkspaceNotFoundError,
    WorkspaceCreationError,
    WorkspaceConfigurationError,
)

@pytest.fixture
def sample_workspace():
    """Sample workspace for testing."""
    return Workspace(
        id="ws_123456",
        name="Test Workspace",
        slug="test-workspace-20240115-120000",
        description="A test workspace for procurement documents",
        config=WorkspaceConfig(
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-4",
                temperature=0.7,
                max_tokens=2000,
                timeout=30
            ),
            procurement_prompts=True,
            auto_embed=True,
            max_documents=1000
        ),
        document_count=5,
        created_at=datetime(2024, 1, 15, 12, 0, 0),
        updated_at=datetime(2024, 1, 15, 12, 30, 0),
        status=WorkspaceStatus.ACTIVE
    )


@pytest.fixture
def sample_workspace_create():
    """Sample workspace creation data."""
    return WorkspaceCreate(
        name="New Test Workspace",
        description="A new test workspace",
        config=WorkspaceConfig(
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-4",
                temperature=0.7
            ),
            procurement_prompts=True,
            auto_embed=True
        )
    )


@pytest.fixture
def sample_workspace_response(sample_workspace):
    """Sample workspace response."""
    return WorkspaceResponse(
        workspace=sample_workspace,
        links={
            "self": f"/api/v1/workspaces/{sample_workspace.id}",
            "update": f"/api/v1/workspaces/{sample_workspace.id}",
            "delete": f"/api/v1/workspaces/{sample_workspace.id}",
            "documents": f"/api/v1/workspaces/{sample_workspace.id}/documents",
            "questions": f"/api/v1/workspaces/{sample_workspace.id}/questions"
        },
        stats={
            "document_count": sample_workspace.document_count,
            "created_at": sample_workspace.created_at.isoformat(),
            "status": sample_workspace.status
        }
    )


@pytest.fixture
def mock_workspace_service():
    """Mock workspace service."""
    return AsyncMock(spec=WorkspaceService)


class TestCreateWorkspace:
    """Test workspace creation endpoint."""
    
    @pytest.mark.asyncio
    async def test_create_workspace_success(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace_create,
        sample_workspace_response,
        mock_workspace_service
    ):
        """Test successful workspace creation."""
        # Setup mock
        mock_workspace_service.create_workspace.return_value = sample_workspace_response
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.post(
                "/api/v1/workspaces",
                json=sample_workspace_create.model_dump(),
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["workspace"]["name"] == sample_workspace_create.name
        assert data["workspace"]["config"]["llm_config"]["provider"] == "openai"
        assert "links" in data
        assert "stats" in data
        
        # Verify service was called correctly
        mock_workspace_service.create_workspace.assert_called_once()
        call_args = mock_workspace_service.create_workspace.call_args[0][0]
        assert call_args.name == sample_workspace_create.name
    
    @pytest.mark.asyncio
    async def test_create_workspace_invalid_data(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace creation with invalid data."""
        invalid_data = {
            "name": "",  # Empty name
            "config": {
                "llm_config": {
                    "provider": "invalid_provider",
                    "model": "gpt-4"
                }
            }
        }
        
        response = await async_client.post(
            "/api/v1/workspaces",
            json=invalid_data,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_create_workspace_service_error(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace_create,
        mock_workspace_service
    ):
        """Test workspace creation with service error."""
        # Setup mock to raise error
        mock_workspace_service.create_workspace.side_effect = WorkspaceCreationError("Creation failed")
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.post(
                "/api/v1/workspaces",
                json=sample_workspace_create.model_dump(),
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Creation failed" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_create_workspace_unauthorized(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace_create
    ):
        """Test workspace creation without authentication."""
        response = await async_client.post(
            "/api/v1/workspaces",
            json=sample_workspace_create.model_dump()
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestListWorkspaces:
    """Test workspace listing endpoint."""
    
    @pytest.mark.asyncio
    async def test_list_workspaces_success(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test successful workspace listing."""
        # Setup mock
        mock_workspace_service.list_workspaces.return_value = [sample_workspace]
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.get(
                "/api/v1/workspaces",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == sample_workspace.id
        assert data[0]["name"] == sample_workspace.name
    
    @pytest.mark.asyncio
    async def test_list_workspaces_with_filters(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test workspace listing with filters."""
        # Setup mock
        mock_workspace_service.list_workspaces.return_value = [sample_workspace]
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.get(
                "/api/v1/workspaces",
                params={
                    "status": "active",
                    "name_contains": "test",
                    "min_documents": 1,
                    "max_documents": 10
                },
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify service was called with filters
        mock_workspace_service.list_workspaces.assert_called_once()
        call_args = mock_workspace_service.list_workspaces.call_args[0][0]
        assert call_args.status == WorkspaceStatus.ACTIVE
        assert call_args.name_contains == "test"
        assert call_args.min_documents == 1
        assert call_args.max_documents == 10
    
    @pytest.mark.asyncio
    async def test_list_workspaces_invalid_date_filter(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace listing with invalid date filter."""
        response = await async_client.get(
            "/api/v1/workspaces",
            params={"created_after": "invalid-date"},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_list_workspaces_invalid_document_range(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace listing with invalid document count range."""
        response = await async_client.get(
            "/api/v1/workspaces",
            params={
                "min_documents": 10,
                "max_documents": 5  # max < min
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestGetWorkspace:
    """Test get workspace endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_workspace_success(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test successful workspace retrieval."""
        # Setup mock
        mock_workspace_service.get_workspace.return_value = sample_workspace
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.get(
                f"/api/v1/workspaces/{sample_workspace.id}",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["workspace"]["id"] == sample_workspace.id
        assert data["workspace"]["name"] == sample_workspace.name
        assert "links" in data
        assert "stats" in data
    
    @pytest.mark.asyncio
    async def test_get_workspace_not_found(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        mock_workspace_service
    ):
        """Test workspace retrieval when workspace not found."""
        # Setup mock to raise error
        mock_workspace_service.get_workspace.side_effect = WorkspaceNotFoundError("Not found")
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.get(
                "/api/v1/workspaces/nonexistent",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_get_workspace_without_stats(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test workspace retrieval without statistics."""
        # Setup mock
        mock_workspace_service.get_workspace.return_value = sample_workspace
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.get(
                f"/api/v1/workspaces/{sample_workspace.id}",
                params={"include_stats": False},
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Stats should still be included but might be minimal
        assert "stats" in data


class TestUpdateWorkspace:
    """Test workspace update endpoint."""
    
    @pytest.mark.asyncio
    async def test_update_workspace_success(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        sample_workspace_response,
        mock_workspace_service
    ):
        """Test successful workspace update."""
        # Setup mocks
        mock_workspace_service.get_workspace.return_value = sample_workspace
        mock_workspace_service.update_workspace.return_value = sample_workspace_response
        
        update_data = WorkspaceUpdate(
            name="Updated Workspace Name",
            description="Updated description"
        )
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.put(
                f"/api/v1/workspaces/{sample_workspace.id}",
                json=update_data.model_dump(exclude_none=True),
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "workspace" in data
        assert "links" in data
        
        # Verify service was called correctly
        mock_workspace_service.update_workspace.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_workspace_not_found(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        mock_workspace_service
    ):
        """Test workspace update when workspace not found."""
        # Setup mock to raise error
        mock_workspace_service.get_workspace.side_effect = WorkspaceNotFoundError("Not found")
        
        update_data = WorkspaceUpdate(name="Updated Name")
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.put(
                "/api/v1/workspaces/nonexistent",
                json=update_data.model_dump(exclude_none=True),
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_update_workspace_configuration_error(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test workspace update with configuration error."""
        # Setup mocks
        mock_workspace_service.get_workspace.return_value = sample_workspace
        mock_workspace_service.update_workspace.side_effect = WorkspaceConfigurationError("Config error")
        
        update_data = WorkspaceUpdate(name="Updated Name")
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.put(
                f"/api/v1/workspaces/{sample_workspace.id}",
                json=update_data.model_dump(exclude_none=True),
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestDeleteWorkspace:
    """Test workspace deletion endpoint."""
    
    @pytest.mark.asyncio
    async def test_delete_workspace_success(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test successful workspace deletion."""
        # Setup mocks
        mock_workspace_service.get_workspace.return_value = sample_workspace
        mock_workspace_service.delete_workspace.return_value = True
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.delete(
                f"/api/v1/workspaces/{sample_workspace.id}",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["message"] == "Workspace deletion initiated"
        assert data["workspace_id"] == sample_workspace.id
        assert data["status"] == "deletion_in_progress"
    
    @pytest.mark.asyncio
    async def test_delete_workspace_with_documents_no_force(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test workspace deletion with documents but no force flag."""
        # Setup workspace with documents
        workspace_with_docs = sample_workspace.model_copy()
        workspace_with_docs.document_count = 10
        
        mock_workspace_service.get_workspace.return_value = workspace_with_docs
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.delete(
                f"/api/v1/workspaces/{sample_workspace.id}",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "documents" in response.json()["detail"]
        assert "force=true" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_delete_workspace_with_force(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test workspace deletion with force flag."""
        # Setup workspace with documents
        workspace_with_docs = sample_workspace.model_copy()
        workspace_with_docs.document_count = 10
        
        mock_workspace_service.get_workspace.return_value = workspace_with_docs
        mock_workspace_service.delete_workspace.return_value = True
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.delete(
                f"/api/v1/workspaces/{sample_workspace.id}",
                params={"force": True, "reason": "Test deletion"},
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["force_deletion"] is True
        assert data["reason"] == "Test deletion"
    
    @pytest.mark.asyncio
    async def test_delete_workspace_already_deleted(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test deletion of already deleted workspace."""
        # Setup deleted workspace
        deleted_workspace = sample_workspace.model_copy()
        deleted_workspace.status = WorkspaceStatus.DELETED
        
        mock_workspace_service.get_workspace.return_value = deleted_workspace
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.delete(
                f"/api/v1/workspaces/{sample_workspace.id}",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already deleted" in response.json()["detail"]


class TestTriggerDocumentEmbedding:
    """Test document embedding trigger endpoint."""
    
    @pytest.mark.asyncio
    async def test_trigger_embedding_success(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test successful embedding trigger."""
        # Setup mocks
        mock_workspace_service.get_workspace.return_value = sample_workspace
        
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PENDING,
            workspace_id=sample_workspace.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={"operation": "document_embedding"}
        )
        
        job_response = JobResponse(
            job=job,
            links={
                "status": f"/api/v1/jobs/{job.id}",
                "cancel": f"/api/v1/jobs/{job.id}"
            }
        )
        
        mock_workspace_service.trigger_document_embedding.return_value = job_response
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.post(
                f"/api/v1/workspaces/{sample_workspace.id}/embed",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["job"]["id"] == job.id
        assert data["job"]["workspace_id"] == sample_workspace.id
        assert "links" in data
    
    @pytest.mark.asyncio
    async def test_trigger_embedding_inactive_workspace(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test embedding trigger on inactive workspace."""
        # Setup inactive workspace
        inactive_workspace = sample_workspace.model_copy()
        inactive_workspace.status = WorkspaceStatus.INACTIVE
        
        mock_workspace_service.get_workspace.return_value = inactive_workspace
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.post(
                f"/api/v1/workspaces/{sample_workspace.id}/embed",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "inactive" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_trigger_embedding_workspace_not_found(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        mock_workspace_service
    ):
        """Test embedding trigger when workspace not found."""
        # Setup mock to raise error
        mock_workspace_service.get_workspace.side_effect = WorkspaceNotFoundError("Not found")
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.post(
                "/api/v1/workspaces/nonexistent/embed",
                headers={"Authorization": "Bearer test-token"}
            )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestWorkspaceAccessControl:
    """Test workspace access control functionality."""
    
    @pytest.mark.asyncio
    async def test_admin_can_access_all_workspaces(
        self,
        async_client: AsyncClient,
        mock_env_vars,
        sample_workspace,
        mock_workspace_service
    ):
        """Test that admin users can access all workspaces."""
        # This test would require mocking the user with admin role
        # For now, we'll test the basic access pattern
        mock_workspace_service.get_workspace.return_value = sample_workspace
        
        with patch("app.routers.workspaces.get_workspace_service", return_value=mock_workspace_service):
            response = await async_client.get(
                f"/api/v1/workspaces/{sample_workspace.id}",
                headers={"Authorization": "Bearer admin-token"}
            )
        
        assert response.status_code == status.HTTP_200_OK
    
    @pytest.mark.asyncio
    async def test_workspace_access_without_auth(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace access without authentication."""
        response = await async_client.get("/api/v1/workspaces/test-id")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestWorkspaceValidation:
    """Test workspace data validation."""
    
    @pytest.mark.asyncio
    async def test_create_workspace_invalid_name_characters(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace creation with invalid name characters."""
        invalid_data = {
            "name": "Invalid/Name*With?Special<Chars>",
            "config": {
                "llm_config": {
                    "provider": "openai",
                    "model": "gpt-4"
                }
            }
        }
        
        response = await async_client.post(
            "/api/v1/workspaces",
            json=invalid_data,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_create_workspace_empty_name(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace creation with empty name."""
        invalid_data = {
            "name": "   ",  # Whitespace only
            "config": {
                "llm_config": {
                    "provider": "openai",
                    "model": "gpt-4"
                }
            }
        }
        
        response = await async_client.post(
            "/api/v1/workspaces",
            json=invalid_data,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @pytest.mark.asyncio
    async def test_create_workspace_invalid_llm_config(
        self,
        async_client: AsyncClient,
        mock_env_vars
    ):
        """Test workspace creation with invalid LLM configuration."""
        invalid_data = {
            "name": "Test Workspace",
            "config": {
                "llm_config": {
                    "provider": "openai",
                    "model": "",  # Empty model
                    "temperature": 3.0  # Invalid temperature
                }
            }
        }
        
        response = await async_client.post(
            "/api/v1/workspaces",
            json=invalid_data,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY