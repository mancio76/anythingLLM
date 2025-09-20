"""Tests for workspace service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.workspace_service import (
    WorkspaceService,
    WorkspaceServiceError,
    WorkspaceNotFoundError,
    WorkspaceCreationError,
    WorkspaceConfigurationError,
    create_workspace_service
)
from app.models.pydantic_models import (
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceConfig,
    WorkspaceFilters,
    WorkspaceResponse,
    WorkspaceStatus,
    LLMConfig,
    LLMProvider,
    Job,
    JobResponse,
    JobStatus,
    JobType,
)
from app.integrations.anythingllm_client import (
    WorkspaceInfo,
    WorkspaceResponse as AnythingLLMWorkspaceResponse
)


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = MagicMock()
    settings.anythingllm_url = "http://localhost:3001"
    settings.anythingllm_api_key = "test-key"
    return settings


@pytest.fixture
def mock_anythingllm_client():
    """Mock AnythingLLM client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_job_repository():
    """Mock job repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_cache_repository():
    """Mock cache repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def workspace_service(mock_settings, mock_anythingllm_client, mock_job_repository, mock_cache_repository):
    """Create workspace service with mocked dependencies."""
    return WorkspaceService(
        settings=mock_settings,
        anythingllm_client=mock_anythingllm_client,
        job_repository=mock_job_repository,
        cache_repository=mock_cache_repository
    )


@pytest.fixture
def sample_llm_config():
    """Sample LLM configuration."""
    return LLMConfig(
        provider=LLMProvider.OPENAI,
        model="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=1000,
        timeout=30
    )


@pytest.fixture
def sample_workspace_config(sample_llm_config):
    """Sample workspace configuration."""
    return WorkspaceConfig(
        llm_config=sample_llm_config,
        procurement_prompts=True,
        auto_embed=True,
        max_documents=100
    )


@pytest.fixture
def sample_workspace_create(sample_workspace_config):
    """Sample workspace creation data."""
    return WorkspaceCreate(
        name="Test Procurement Workspace",
        description="Test workspace for procurement documents",
        config=sample_workspace_config
    )


@pytest.fixture
def sample_anythingllm_workspace():
    """Sample AnythingLLM workspace info."""
    return WorkspaceInfo(
        id="ws_123456",
        name="Test Procurement Workspace",
        slug="test-procurement-workspace",
        createdAt="2024-01-15T10:00:00Z",
        openAiTemp=0.7,
        lastUpdatedAt="2024-01-15T10:00:00Z"
    )


@pytest.fixture
def sample_workspace(sample_workspace_config):
    """Sample workspace model."""
    return Workspace(
        id="ws_123456",
        name="Test Procurement Workspace",
        slug="test-procurement-workspace-20240115-100000",
        description="Test workspace for procurement documents",
        config=sample_workspace_config,
        document_count=0,
        created_at=datetime(2024, 1, 15, 10, 0, 0),
        updated_at=datetime(2024, 1, 15, 10, 0, 0),
        status=WorkspaceStatus.ACTIVE
    )


class TestWorkspaceService:
    """Test workspace service functionality."""
    
    async def test_create_workspace_success(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_job_repository,
        mock_cache_repository,
        sample_workspace_create,
        sample_anythingllm_workspace
    ):
        """Test successful workspace creation."""
        # Setup mocks
        anythingllm_response = AnythingLLMWorkspaceResponse(
            workspace=sample_anythingllm_workspace,
            message="Workspace created successfully"
        )
        mock_anythingllm_client.create_workspace.return_value = anythingllm_response
        mock_anythingllm_client.find_workspace_by_name.return_value = None
        mock_cache_repository.set.return_value = True
        
        # Execute
        result = await workspace_service.create_workspace(sample_workspace_create)
        
        # Verify
        assert isinstance(result, WorkspaceResponse)
        assert result.workspace.name == sample_workspace_create.name
        assert result.workspace.id == sample_anythingllm_workspace.id
        assert result.workspace.status == WorkspaceStatus.ACTIVE
        assert "self" in result.links
        assert "update" in result.links
        assert "delete" in result.links
        
        # Verify AnythingLLM client was called
        mock_anythingllm_client.create_workspace.assert_called_once()
        
        # Verify caching was attempted
        mock_cache_repository.set.assert_called()
    
    async def test_create_workspace_anythingllm_error(
        self,
        workspace_service,
        mock_anythingllm_client,
        sample_workspace_create
    ):
        """Test workspace creation with AnythingLLM error."""
        # Setup mock to raise error
        mock_anythingllm_client.create_workspace.side_effect = Exception("AnythingLLM error")
        mock_anythingllm_client.find_workspace_by_name.return_value = None
        
        # Execute and verify exception
        with pytest.raises(WorkspaceCreationError, match="Failed to create workspace"):
            await workspace_service.create_workspace(sample_workspace_create)
    
    async def test_create_or_reuse_workspace_new(
        self,
        workspace_service,
        mock_anythingllm_client,
        sample_workspace_config,
        sample_anythingllm_workspace
    ):
        """Test create or reuse workspace when workspace doesn't exist."""
        # Setup mocks
        mock_anythingllm_client.find_workspace_by_name.return_value = None
        anythingllm_response = AnythingLLMWorkspaceResponse(
            workspace=sample_anythingllm_workspace,
            message="Workspace created successfully"
        )
        mock_anythingllm_client.create_workspace.return_value = anythingllm_response
        
        # Execute
        result = await workspace_service.create_or_reuse_workspace(
            name="New Workspace",
            config=sample_workspace_config
        )
        
        # Verify
        assert isinstance(result, WorkspaceResponse)
        assert result.workspace.name == "New Workspace"
        mock_anythingllm_client.create_workspace.assert_called_once()
    
    async def test_create_or_reuse_workspace_existing(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
        sample_workspace_config,
        sample_workspace,
        sample_anythingllm_workspace
    ):
        """Test create or reuse workspace when workspace exists."""
        # Create a workspace with the same config to avoid update path
        existing_workspace = Workspace(
            id=sample_anythingllm_workspace.id,
            name=sample_anythingllm_workspace.name,
            slug=sample_anythingllm_workspace.slug,
            description=None,
            config=sample_workspace_config,  # Same config to avoid update
            document_count=0,
            created_at=datetime(2024, 1, 15, 10, 0, 0),
            updated_at=datetime(2024, 1, 15, 10, 0, 0),
            status=WorkspaceStatus.ACTIVE
        )
        
        # Setup mocks
        mock_anythingllm_client.find_workspace_by_name.return_value = sample_anythingllm_workspace
        mock_cache_repository.get.return_value = None  # Not in cache
        
        # Mock the conversion to return our existing workspace
        workspace_service._convert_anythingllm_workspace = lambda x: existing_workspace
        
        # Execute
        result = await workspace_service.create_or_reuse_workspace(
            name=sample_workspace.name,
            config=sample_workspace_config
        )
        
        # Verify
        assert isinstance(result, WorkspaceResponse)
        assert result.workspace.name == sample_anythingllm_workspace.name
        assert result.workspace.id == sample_anythingllm_workspace.id
        
        # Verify create was not called
        mock_anythingllm_client.create_workspace.assert_not_called()
    
    async def test_get_workspace_from_cache(
        self,
        workspace_service,
        mock_cache_repository,
        sample_workspace
    ):
        """Test getting workspace from cache."""
        # Setup mock
        mock_cache_repository.get.return_value = sample_workspace.model_dump()
        
        # Execute
        result = await workspace_service.get_workspace(sample_workspace.id)
        
        # Verify
        assert isinstance(result, Workspace)
        assert result.id == sample_workspace.id
        assert result.name == sample_workspace.name
        
        # Verify cache was checked
        mock_cache_repository.get.assert_called_once()
    
    async def test_get_workspace_from_anythingllm(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
        sample_anythingllm_workspace
    ):
        """Test getting workspace from AnythingLLM when not in cache."""
        # Setup mocks
        mock_cache_repository.get.return_value = None  # Not in cache
        mock_anythingllm_client.get_workspace.return_value = sample_anythingllm_workspace
        mock_cache_repository.set.return_value = True
        
        # Execute
        result = await workspace_service.get_workspace(sample_anythingllm_workspace.id)
        
        # Verify
        assert isinstance(result, Workspace)
        assert result.id == sample_anythingllm_workspace.id
        assert result.name == sample_anythingllm_workspace.name
        
        # Verify AnythingLLM was called
        mock_anythingllm_client.get_workspace.assert_called_once_with(sample_anythingllm_workspace.id)
        
        # Verify caching was attempted
        mock_cache_repository.set.assert_called()
    
    async def test_get_workspace_not_found(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository
    ):
        """Test getting non-existent workspace."""
        # Setup mocks
        mock_cache_repository.get.return_value = None
        mock_anythingllm_client.get_workspace.side_effect = WorkspaceNotFoundError("Not found")
        
        # Execute and verify exception
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.get_workspace("nonexistent")
    
    async def test_list_workspaces_from_cache(
        self,
        workspace_service,
        mock_cache_repository,
        sample_workspace
    ):
        """Test listing workspaces from cache."""
        # Setup mock
        cached_data = [sample_workspace.model_dump()]
        mock_cache_repository.get.return_value = cached_data
        
        # Execute
        result = await workspace_service.list_workspaces()
        
        # Verify
        assert len(result) == 1
        assert isinstance(result[0], Workspace)
        assert result[0].id == sample_workspace.id
        
        # Verify cache was checked
        mock_cache_repository.get.assert_called_once()
    
    async def test_list_workspaces_from_anythingllm(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
        sample_anythingllm_workspace
    ):
        """Test listing workspaces from AnythingLLM when not in cache."""
        # Setup mocks
        mock_cache_repository.get.return_value = None  # Not in cache
        mock_anythingllm_client.get_workspaces.return_value = [sample_anythingllm_workspace]
        mock_cache_repository.set.return_value = True
        
        # Execute
        result = await workspace_service.list_workspaces()
        
        # Verify
        assert len(result) == 1
        assert isinstance(result[0], Workspace)
        assert result[0].id == sample_anythingllm_workspace.id
        
        # Verify AnythingLLM was called
        mock_anythingllm_client.get_workspaces.assert_called_once()
        
        # Verify caching was attempted
        mock_cache_repository.set.assert_called()
    
    async def test_list_workspaces_with_filters(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
        sample_anythingllm_workspace
    ):
        """Test listing workspaces with filters."""
        # Setup mocks
        mock_cache_repository.get.return_value = None
        mock_anythingllm_client.get_workspaces.return_value = [sample_anythingllm_workspace]
        
        # Create filters
        filters = WorkspaceFilters(
            status=WorkspaceStatus.ACTIVE,
            name_contains="Test"
        )
        
        # Execute
        result = await workspace_service.list_workspaces(filters)
        
        # Verify
        assert len(result) == 1
        assert result[0].name == sample_anythingllm_workspace.name
    
    async def test_update_workspace_success(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_cache_repository,
        sample_workspace,
        sample_workspace_config
    ):
        """Test successful workspace update."""
        # Setup mocks
        mock_cache_repository.get.return_value = sample_workspace.model_dump()
        mock_cache_repository.delete.return_value = True
        mock_cache_repository.delete_many.return_value = 1
        mock_cache_repository.get_keys.return_value = ["workspaces:list:hash1"]
        mock_cache_repository.set.return_value = True
        
        # Create update data
        update_data = WorkspaceUpdate(
            name="Updated Workspace",
            config=sample_workspace_config
        )
        
        # Execute
        result = await workspace_service.update_workspace(sample_workspace.id, update_data)
        
        # Verify
        assert isinstance(result, WorkspaceResponse)
        assert result.workspace.name == "Updated Workspace"
        assert result.workspace.id == sample_workspace.id
        
        # Verify cache invalidation
        mock_cache_repository.delete.assert_called()
    
    async def test_update_workspace_not_found(
        self,
        workspace_service,
        mock_cache_repository,
        mock_anythingllm_client,
        sample_workspace_config
    ):
        """Test updating non-existent workspace."""
        # Setup mocks
        mock_cache_repository.get.return_value = None
        mock_anythingllm_client.get_workspace.side_effect = WorkspaceNotFoundError("Not found")
        
        # Create update data
        update_data = WorkspaceUpdate(name="Updated Workspace")
        
        # Execute and verify exception
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.update_workspace("nonexistent", update_data)
    
    async def test_delete_workspace_success(
        self,
        workspace_service,
        mock_job_repository,
        sample_workspace
    ):
        """Test successful workspace deletion initiation."""
        # Setup mock
        mock_job = Job(
            id="job_123",
            type=JobType.WORKSPACE_DELETION,
            status=JobStatus.PENDING,
            workspace_id=sample_workspace.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={"workspace_id": sample_workspace.id}
        )
        mock_job_repository.create_job.return_value = mock_job
        
        # Execute
        result = await workspace_service.delete_workspace(sample_workspace.id)
        
        # Verify
        assert result is True
        
        # Verify job was created
        mock_job_repository.create_job.assert_called_once_with(
            job_type=JobType.WORKSPACE_DELETION,
            workspace_id=sample_workspace.id,
            metadata={"workspace_id": sample_workspace.id}
        )
    
    async def test_find_workspace_by_name_found(
        self,
        workspace_service,
        mock_anythingllm_client,
        sample_anythingllm_workspace
    ):
        """Test finding workspace by name when it exists."""
        # Setup mock
        mock_anythingllm_client.find_workspace_by_name.return_value = sample_anythingllm_workspace
        
        # Execute
        result = await workspace_service.find_workspace_by_name(sample_anythingllm_workspace.name)
        
        # Verify
        assert result is not None
        assert isinstance(result, Workspace)
        assert result.name == sample_anythingllm_workspace.name
        assert result.id == sample_anythingllm_workspace.id
    
    async def test_find_workspace_by_name_not_found(
        self,
        workspace_service,
        mock_anythingllm_client
    ):
        """Test finding workspace by name when it doesn't exist."""
        # Setup mock
        mock_anythingllm_client.find_workspace_by_name.return_value = None
        
        # Execute
        result = await workspace_service.find_workspace_by_name("Nonexistent Workspace")
        
        # Verify
        assert result is None
    
    async def test_trigger_document_embedding_success(
        self,
        workspace_service,
        mock_anythingllm_client,
        mock_job_repository,
        mock_cache_repository,
        sample_workspace
    ):
        """Test successful document embedding trigger."""
        # Setup mocks
        mock_cache_repository.get.return_value = sample_workspace.model_dump()
        mock_job = Job(
            id="job_456",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.PENDING,
            workspace_id=sample_workspace.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            progress=0.0,
            metadata={
                "operation": "document_embedding",
                "workspace_id": sample_workspace.id
            }
        )
        mock_job_repository.create_job.return_value = mock_job
        
        # Execute
        result = await workspace_service.trigger_document_embedding(sample_workspace.id)
        
        # Verify
        assert isinstance(result, JobResponse)
        assert result.job.id == mock_job.id
        assert "status" in result.links
        assert "cancel" in result.links
        
        # Verify job was created
        mock_job_repository.create_job.assert_called_once()
    
    async def test_trigger_document_embedding_workspace_not_found(
        self,
        workspace_service,
        mock_cache_repository,
        mock_anythingllm_client
    ):
        """Test document embedding trigger for non-existent workspace."""
        # Setup mocks
        mock_cache_repository.get.return_value = None
        mock_anythingllm_client.get_workspace.side_effect = WorkspaceNotFoundError("Not found")
        
        # Execute and verify exception
        with pytest.raises(WorkspaceNotFoundError):
            await workspace_service.trigger_document_embedding("nonexistent")
    
    def test_generate_workspace_slug(self, workspace_service):
        """Test workspace slug generation."""
        # Test normal name
        with patch('app.services.workspace_service.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20240115-100000"
            
            slug = workspace_service._generate_workspace_slug("Test Procurement Workspace")
            assert slug == "test-procurement-workspace-20240115-100000"
        
        # Test name with special characters
        with patch('app.services.workspace_service.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20240115-100000"
            
            slug = workspace_service._generate_workspace_slug("Test & Special! Workspace@#$")
            assert slug == "test-special-workspace-20240115-100000"
        
        # Test empty name
        with patch('app.services.workspace_service.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value.strftime.return_value = "20240115-100000"
            
            slug = workspace_service._generate_workspace_slug("")
            assert slug.startswith("workspace-")
            assert slug.endswith("-20240115-100000")
    
    def test_prepare_anythingllm_config(self, workspace_service, sample_workspace_config):
        """Test AnythingLLM configuration preparation."""
        config = workspace_service._prepare_anythingllm_config(sample_workspace_config)
        
        assert config["LLMProvider"] == "openai"
        assert config["OpenAiModel"] == "gpt-3.5-turbo"
        assert config["OpenAiTemp"] == 0.7
        assert config["OpenAiMaxTokens"] == 1000
        assert config["maxDocuments"] == 100
    
    def test_apply_workspace_filters(self, workspace_service, sample_workspace):
        """Test workspace filtering."""
        workspaces = [sample_workspace]
        
        # Test status filter
        filters = WorkspaceFilters(status=WorkspaceStatus.ACTIVE)
        result = workspace_service._apply_workspace_filters(workspaces, filters)
        assert len(result) == 1
        
        # Test status filter (no match)
        filters = WorkspaceFilters(status=WorkspaceStatus.INACTIVE)
        result = workspace_service._apply_workspace_filters(workspaces, filters)
        assert len(result) == 0
        
        # Test name filter
        filters = WorkspaceFilters(name_contains="Test")
        result = workspace_service._apply_workspace_filters(workspaces, filters)
        assert len(result) == 1
        
        # Test name filter (no match)
        filters = WorkspaceFilters(name_contains="Nonexistent")
        result = workspace_service._apply_workspace_filters(workspaces, filters)
        assert len(result) == 0
        
        # Test document count filters
        filters = WorkspaceFilters(min_documents=0, max_documents=10)
        result = workspace_service._apply_workspace_filters(workspaces, filters)
        assert len(result) == 1
        
        filters = WorkspaceFilters(min_documents=5)
        result = workspace_service._apply_workspace_filters(workspaces, filters)
        assert len(result) == 0
    
    def test_convert_anythingllm_workspace(self, workspace_service, sample_anythingllm_workspace):
        """Test conversion from AnythingLLM workspace to our model."""
        result = workspace_service._convert_anythingllm_workspace(sample_anythingllm_workspace)
        
        assert isinstance(result, Workspace)
        assert result.id == sample_anythingllm_workspace.id
        assert result.name == sample_anythingllm_workspace.name
        assert result.slug == sample_anythingllm_workspace.slug
        assert result.status == WorkspaceStatus.ACTIVE
        assert result.config.llm_config.temperature == 0.7
        assert result.config.procurement_prompts is True
    
    def test_procurement_prompts(self, workspace_service):
        """Test procurement prompts configuration."""
        prompts = workspace_service._get_procurement_prompts()
        
        assert "system_prompt" in prompts
        assert "document_analysis_prompt" in prompts
        assert "question_context_prompt" in prompts
        
        # Verify prompts contain procurement-specific content
        assert "procurement" in prompts["system_prompt"].lower()
        assert "contract" in prompts["document_analysis_prompt"].lower()
        assert "compliance" in prompts["question_context_prompt"].lower()


class TestWorkspaceServiceFactory:
    """Test workspace service factory function."""
    
    def test_create_workspace_service(
        self,
        mock_settings,
        mock_anythingllm_client,
        mock_job_repository,
        mock_cache_repository
    ):
        """Test workspace service factory function."""
        service = create_workspace_service(
            settings=mock_settings,
            anythingllm_client=mock_anythingllm_client,
            job_repository=mock_job_repository,
            cache_repository=mock_cache_repository
        )
        
        assert isinstance(service, WorkspaceService)
        assert service.settings == mock_settings
        assert service.anythingllm_client == mock_anythingllm_client
        assert service.job_repository == mock_job_repository
        assert service.cache_repository == mock_cache_repository
    
    def test_create_workspace_service_without_cache(
        self,
        mock_settings,
        mock_anythingllm_client,
        mock_job_repository
    ):
        """Test workspace service factory function without cache."""
        service = create_workspace_service(
            settings=mock_settings,
            anythingllm_client=mock_anythingllm_client,
            job_repository=mock_job_repository
        )
        
        assert isinstance(service, WorkspaceService)
        assert service.cache_repository is None


if __name__ == "__main__":
    pytest.main([__file__])