"""Comprehensive unit tests for WorkspaceService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.integrations.anythingllm_client import AnythingLLMClient, WorkspaceError
from app.models.pydantic_models import (
    LLMConfig,
    LLMProvider,
    WorkspaceConfig,
    WorkspaceFilters,
    WorkspaceStatus,
    WorkspaceUpdate,
)
from app.repositories.cache_repository import CacheRepository
from app.services.workspace_service import (
    WorkspaceNotFoundError,
    WorkspaceService,
    WorkspaceValidationError,
)
from tests.fixtures.mock_data import mock_data


class TestWorkspaceService:
    """Test cases for WorkspaceService."""

    @pytest.fixture
    def mock_anythingllm_client(self):
        """Mock AnythingLLM client."""
        client = AsyncMock(spec=AnythingLLMClient)
        client.create_workspace.return_value = mock_data.create_mock_anythingllm_responses()["workspace_create"]
        client.get_workspaces.return_value = mock_data.create_mock_anythingllm_responses()["workspace_list"]
        client.delete_workspace.return_value = True
        return client

    @pytest.fixture
    def mock_cache_repository(self):
        """Mock cache repository."""
        repo = AsyncMock(spec=CacheRepository)
        repo.get.return_value = None
        repo.set.return_value = True
        repo.delete.return_value = True
        return repo

    @pytest.fixture
    def workspace_service(self, mock_anythingllm_client, mock_cache_repository):
        """Create WorkspaceService instance with mocked dependencies."""
        return WorkspaceService(
            anythingllm_client=mock_anythingllm_client,
            cache_repository=mock_cache_repository,
        )

    @pytest.fixture
    def sample_workspace_config(self):
        """Sample workspace configuration."""
        return WorkspaceConfig(
            name="Test Workspace",
            description="Test workspace for unit tests",
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=1000,
                timeout=30,
            ),
            max_documents=100,
            enable_chat=True,
        )

    @pytest.mark.asyncio
    async def test_create_workspace_success(
        self,
        workspace_service,
        sample_workspace_config,
        mock_anythingllm_client,
        mock_cache_repository,
    ):
        """Test successful workspace creation."""
        result = await workspace_service.create_workspace(sample_workspace_config)
        
        assert result.name == sample_workspace_config.name
        assert result.status == WorkspaceStatus.ACTIVE
        mock_anythingllm_client.create_workspace.assert_called_once()
        mock_cache_repository.set.assert_called()

    @pytest.mark.asyncio
    async def test_create_workspace_duplicate_name(
        self,
        workspace_service,
        sample_workspace_config,
        mock_anythingllm_client,
    ):
        """Test workspace creation with duplicate name."""
        mock_anythingllm_client.create_workspace.side_effect = WorkspaceError("Workspace already exists")
        
        with pytest.raises(WorkspaceValidationError) as exc_info:
            await workspace_service.create_workspace(sample_workspace_config)
        
        assert "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_or_reuse_workspace_new(
        self,
        workspace_service,
        sample_workspace_config,
        mock_anythingllm_client,
    ):
        """Test create or reuse workspace when workspace doesn't exist."""
        mock_anythingllm_client.get_workspaces.return_value = {"workspaces": []}
        
        result = await workspace_service.create_or_reuse_workspace(
            sample_workspace_config.name,
            sample_workspace_config
        )
        
        assert result.name == sample_workspace_config.name
        mock_anythingllm_client.create_workspace.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_or_reuse_workspace_existing(
        self,
        workspace_service,
        sample_workspace_config,
        mock_anythingllm_client,
    ):
        """Test create or reuse workspace when workspace exists."""
        existing_workspace = mock_data.create_mock_workspace(name=sample_workspace_config.name)
        mock_anythingllm_client.get_workspaces.return_value = {
            "workspaces": [existing_workspace.model_dump()]
        }
        
        result = await workspace_service.create_or_reuse_workspace(
            sample_workspace_config.name,
            sample_workspace_config
        )
        
        assert result.name == sample_workspace_config.name
        mock_anythingllm_client.create_workspace.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_workspaces_success(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
    ):
        """Test successful workspace listing."""
        # Mock cache miss
        mock_cache_repository.get.return_value = None
        
        filters = WorkspaceFilters(status=WorkspaceStatus.ACTIVE)
        result = await workspace_service.list_workspaces(filters)
        
        assert len(result) >= 0
        mock_anythingllm_client.get_workspaces.assert_called_once()
        mock_cache_repository.set.assert_called()

    @pytest.mark.asyncio
    async def test_list_workspaces_cached(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
    ):
        """Test workspace listing with cached results."""
        cached_workspaces = [mock_data.create_mock_workspace().model_dump()]
        mock_cache_repository.get.return_value = cached_workspaces
        
        filters = WorkspaceFilters()
        result = await workspace_service.list_workspaces(filters)
        
        assert len(result) == 1
        mock_anythingllm_client.get_workspaces.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_workspace_success(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test successful workspace retrieval."""
        workspace_id = "ws_123"
        mock_workspace = mock_data.create_mock_workspace(workspace_id=workspace_id)
        mock_anythingllm_client.get_workspaces.return_value = {
            "workspaces": [mock_workspace.model_dump()]
        }
        
        result = await workspace_service.get_workspace(workspace_id)
        
        assert result.id == workspace_id
        mock_anythingllm_client.get_workspaces.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test workspace retrieval when workspace doesn't exist."""
        mock_anythingllm_client.get_workspaces.return_value = {"workspaces": []}
        
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.get_workspace("nonexistent")

    @pytest.mark.asyncio
    async def test_update_workspace_success(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
    ):
        """Test successful workspace update."""
        workspace_id = "ws_123"
        mock_workspace = mock_data.create_mock_workspace(workspace_id=workspace_id)
        mock_anythingllm_client.get_workspaces.return_value = {
            "workspaces": [mock_workspace.model_dump()]
        }
        
        updates = WorkspaceUpdate(
            name="Updated Workspace",
            description="Updated description",
        )
        
        result = await workspace_service.update_workspace(workspace_id, updates)
        
        assert result.name == "Updated Workspace"
        mock_cache_repository.delete.assert_called()  # Cache invalidation

    @pytest.mark.asyncio
    async def test_update_workspace_not_found(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test workspace update when workspace doesn't exist."""
        mock_anythingllm_client.get_workspaces.return_value = {"workspaces": []}
        
        updates = WorkspaceUpdate(name="Updated Workspace")
        
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.update_workspace("nonexistent", updates)

    @pytest.mark.asyncio
    async def test_delete_workspace_success(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
    ):
        """Test successful workspace deletion."""
        workspace_id = "ws_123"
        mock_workspace = mock_data.create_mock_workspace(workspace_id=workspace_id)
        mock_anythingllm_client.get_workspaces.return_value = {
            "workspaces": [mock_workspace.model_dump()]
        }
        
        result = await workspace_service.delete_workspace(workspace_id)
        
        assert result is True
        mock_anythingllm_client.delete_workspace.assert_called_once_with(workspace_id)
        mock_cache_repository.delete.assert_called()

    @pytest.mark.asyncio
    async def test_delete_workspace_not_found(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test workspace deletion when workspace doesn't exist."""
        mock_anythingllm_client.get_workspaces.return_value = {"workspaces": []}
        
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.delete_workspace("nonexistent")

    @pytest.mark.asyncio
    async def test_configure_llm_settings_success(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test successful LLM configuration."""
        workspace_id = "ws_123"
        llm_config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            model="claude-3-sonnet",
            temperature=0.5,
            max_tokens=2000,
            timeout=45,
        )
        
        result = await workspace_service.configure_llm_settings(workspace_id, llm_config)
        
        assert result is True
        mock_anythingllm_client.update_workspace_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_procurement_prompts(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test procurement-specific prompt configuration."""
        workspace_id = "ws_123"
        
        result = await workspace_service.configure_procurement_prompts(workspace_id)
        
        assert result is True
        mock_anythingllm_client.update_workspace_config.assert_called_once()
        
        # Verify procurement-specific prompts were configured
        call_args = mock_anythingllm_client.update_workspace_config.call_args
        config = call_args[0][1]
        assert "procurement" in config.get("systemPrompt", "").lower()

    @pytest.mark.asyncio
    async def test_trigger_document_embedding_success(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test successful document embedding trigger."""
        workspace_id = "ws_123"
        
        result = await workspace_service.trigger_document_embedding(workspace_id)
        
        assert result.job_id is not None
        assert result.status.value in ["pending", "processing"]
        mock_anythingllm_client.trigger_embedding.assert_called_once_with(workspace_id)

    @pytest.mark.asyncio
    async def test_organize_workspace_folders_success(
        self,
        workspace_service,
        mock_anythingllm_client,
    ):
        """Test successful workspace folder organization."""
        workspace_id = "ws_123"
        document_types = ["contracts", "invoices", "reports"]
        
        result = await workspace_service.organize_workspace_folders(workspace_id, document_types)
        
        assert result is True
        mock_anythingllm_client.create_folders.assert_called_once()
        
        # Verify folders were created for each document type
        call_args = mock_anythingllm_client.create_folders.call_args
        folders = call_args[0][1]
        assert len(folders) == len(document_types)
        assert all(doc_type in folders for doc_type in document_types)

    @pytest.mark.asyncio
    async def test_workspace_validation_invalid_config(
        self,
        workspace_service,
    ):
        """Test workspace validation with invalid configuration."""
        invalid_config = WorkspaceConfig(
            name="",  # Empty name should be invalid
            llm_config=LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=3.0,  # Invalid temperature > 2.0
                max_tokens=1000,
                timeout=30,
            ),
        )
        
        with pytest.raises(WorkspaceValidationError):
            await workspace_service.create_workspace(invalid_config)

    @pytest.mark.asyncio
    async def test_concurrent_workspace_operations(
        self,
        workspace_service,
        sample_workspace_config,
        mock_anythingllm_client,
    ):
        """Test concurrent workspace operations."""
        import asyncio
        
        # Create multiple workspaces concurrently
        configs = [
            WorkspaceConfig(
                name=f"Workspace {i}",
                llm_config=sample_workspace_config.llm_config,
            )
            for i in range(3)
        ]
        
        tasks = [
            workspace_service.create_workspace(config)
            for config in configs
        ]
        
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        assert all(result.status == WorkspaceStatus.ACTIVE for result in results)
        assert mock_anythingllm_client.create_workspace.call_count == 3

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_updates(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
    ):
        """Test cache invalidation when workspaces are updated."""
        workspace_id = "ws_123"
        mock_workspace = mock_data.create_mock_workspace(workspace_id=workspace_id)
        mock_anythingllm_client.get_workspaces.return_value = {
            "workspaces": [mock_workspace.model_dump()]
        }
        
        # Update workspace
        updates = WorkspaceUpdate(name="Updated Name")
        await workspace_service.update_workspace(workspace_id, updates)
        
        # Verify cache was invalidated
        mock_cache_repository.delete.assert_called()
        
        # Delete workspace
        await workspace_service.delete_workspace(workspace_id)
        
        # Verify cache was invalidated again
        assert mock_cache_repository.delete.call_count >= 2

    @pytest.mark.asyncio
    async def test_error_handling_anythingllm_unavailable(
        self,
        workspace_service,
        sample_workspace_config,
        mock_anythingllm_client,
    ):
        """Test error handling when AnythingLLM is unavailable."""
        mock_anythingllm_client.create_workspace.side_effect = Exception("Connection refused")
        
        with pytest.raises(WorkspaceError):
            await workspace_service.create_workspace(sample_workspace_config)