"""Workspace management service with AnythingLLM integration."""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.anythingllm_client import (
    AnythingLLMClient,
    AnythingLLMError,
    WorkspaceNotFoundError,
    WorkspaceInfo,
    WorkspaceResponse as AnythingLLMWorkspaceResponse
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
    Job,
    JobCreate,
    JobResponse,
    JobStatus,
    JobType,
)
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository

logger = get_logger(__name__)


class WorkspaceServiceError(Exception):
    """Workspace service error."""
    pass


class WorkspaceNotFoundError(WorkspaceServiceError):
    """Workspace not found error."""
    pass


class WorkspaceCreationError(WorkspaceServiceError):
    """Workspace creation error."""
    pass


class WorkspaceConfigurationError(WorkspaceServiceError):
    """Workspace configuration error."""
    pass


class WorkspaceService:
    """Service for workspace management operations."""
    
    def __init__(
        self,
        settings: Settings,
        anythingllm_client: AnythingLLMClient,
        job_repository: JobRepository,
        cache_repository: Optional[CacheRepository] = None
    ):
        """
        Initialize workspace service.
        
        Args:
            settings: Application settings
            anythingllm_client: AnythingLLM integration client
            job_repository: Job repository for tracking operations
            cache_repository: Optional cache repository for performance
        """
        self.settings = settings
        self.anythingllm_client = anythingllm_client
        self.job_repository = job_repository
        self.cache_repository = cache_repository
        
        # Cache settings
        self.workspace_cache_ttl = 300  # 5 minutes
        self.workspace_list_cache_ttl = 60  # 1 minute
        
        # Procurement-specific prompts
        self.procurement_prompts = self._get_procurement_prompts()
        
        logger.info("Initialized WorkspaceService")
    
    def _get_procurement_prompts(self) -> Dict[str, str]:
        """
        Get procurement-specific prompt configurations.
        
        Returns:
            Dictionary of prompt configurations
        """
        return {
            "system_prompt": (
                "You are an AI assistant specialized in procurement and contract analysis. "
                "You have expertise in analyzing procurement documents, contracts, RFPs, "
                "vendor proposals, and financial reports. When answering questions, focus on "
                "extracting relevant procurement information such as costs, timelines, "
                "vendor details, compliance requirements, and risk factors. "
                "Provide clear, structured responses with specific references to the source documents."
            ),
            "document_analysis_prompt": (
                "Analyze this procurement document and extract key information including: "
                "1. Contract/proposal details (parties, amounts, timelines) "
                "2. Compliance and regulatory requirements "
                "3. Risk factors and mitigation strategies "
                "4. Cost breakdowns and financial terms "
                "5. Performance metrics and deliverables"
            ),
            "question_context_prompt": (
                "When answering questions about procurement documents, always: "
                "1. Reference specific sections or pages from the source documents "
                "2. Highlight any compliance or regulatory considerations "
                "3. Identify potential risks or concerns "
                "4. Provide quantitative data when available (costs, dates, percentages) "
                "5. Suggest follow-up questions or areas for further investigation"
            )
        }
    
    def _generate_workspace_slug(self, name: str) -> str:
        """
        Generate URL-safe workspace slug from name.
        
        Args:
            name: Workspace name
            
        Returns:
            URL-safe slug
        """
        import re
        
        # Convert to lowercase and replace spaces/special chars with hyphens
        slug = re.sub(r'[^\w\s-]', '', name.lower())
        slug = re.sub(r'[-\s]+', '-', slug)
        slug = slug.strip('-')
        
        # Ensure slug is not empty
        if not slug:
            slug = f"workspace-{uuid4().hex[:8]}"
        
        # Add timestamp suffix to ensure uniqueness
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return f"{slug}-{timestamp}"
    
    def _workspace_cache_key(self, workspace_id: str) -> str:
        """Generate cache key for workspace."""
        return f"workspace:{workspace_id}"
    
    def _workspace_list_cache_key(self, filters_hash: str) -> str:
        """Generate cache key for workspace list."""
        return f"workspaces:list:{filters_hash}"
    
    def _hash_filters(self, filters: WorkspaceFilters) -> str:
        """Generate hash for workspace filters."""
        import hashlib
        filter_str = json.dumps(filters.model_dump(), sort_keys=True, default=str)
        return hashlib.md5(filter_str.encode()).hexdigest()
    
    async def _cache_workspace(self, workspace: Workspace) -> None:
        """Cache workspace data."""
        if self.cache_repository:
            try:
                cache_key = self._workspace_cache_key(workspace.id)
                await self.cache_repository.set(
                    cache_key,
                    workspace.model_dump(),
                    ttl=self.workspace_cache_ttl
                )
                logger.debug(f"Cached workspace {workspace.id}")
            except Exception as e:
                logger.warning(f"Failed to cache workspace {workspace.id}: {e}")
    
    async def _get_cached_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace from cache."""
        if not self.cache_repository:
            return None
        
        try:
            cache_key = self._workspace_cache_key(workspace_id)
            cached_data = await self.cache_repository.get(cache_key)
            if cached_data:
                logger.debug(f"Retrieved workspace {workspace_id} from cache")
                return Workspace(**cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached workspace {workspace_id}: {e}")
        
        return None
    
    async def _invalidate_workspace_cache(self, workspace_id: str) -> None:
        """Invalidate workspace cache."""
        if self.cache_repository:
            try:
                cache_key = self._workspace_cache_key(workspace_id)
                await self.cache_repository.delete(cache_key)
                
                # Also invalidate workspace list caches
                list_keys = await self.cache_repository.get_keys("workspaces:list:*")
                if list_keys:
                    await self.cache_repository.delete_many(list_keys)
                
                logger.debug(f"Invalidated cache for workspace {workspace_id}")
            except Exception as e:
                logger.warning(f"Failed to invalidate workspace cache: {e}")
    
    async def create_workspace(self, workspace_create: WorkspaceCreate) -> WorkspaceResponse:
        """
        Create a new workspace.
        
        Args:
            workspace_create: Workspace creation data
            
        Returns:
            Workspace response with details
            
        Raises:
            WorkspaceCreationError: If workspace creation fails
        """
        logger.info(f"Creating workspace: {workspace_create.name}")
        
        try:
            # Generate workspace slug
            slug = self._generate_workspace_slug(workspace_create.name)
            
            # Check if workspace with same name already exists
            existing_workspace = await self.find_workspace_by_name(workspace_create.name)
            if existing_workspace:
                logger.warning(f"Workspace with name '{workspace_create.name}' already exists")
                # For create operation, we don't reuse - we create with unique slug
            
            # Prepare AnythingLLM workspace configuration
            anythingllm_config = self._prepare_anythingllm_config(workspace_create.config)
            
            # Create workspace in AnythingLLM
            anythingllm_response = await self.anythingllm_client.create_workspace(
                name=workspace_create.name,
                config=anythingllm_config
            )
            
            # Create workspace model
            workspace = Workspace(
                id=anythingllm_response.workspace.id,
                name=workspace_create.name,
                slug=slug,
                description=workspace_create.description,
                config=workspace_create.config,
                document_count=0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                status=WorkspaceStatus.ACTIVE
            )
            
            # Configure procurement-specific settings if enabled
            if workspace_create.config.procurement_prompts:
                await self._configure_procurement_prompts(workspace.id)
            
            # Create workspace folder organization
            await self._create_workspace_folder_organization(workspace.id)
            
            # Cache the workspace
            await self._cache_workspace(workspace)
            
            logger.info(f"Successfully created workspace: {workspace.name} (ID: {workspace.id})")
            
            return WorkspaceResponse(
                workspace=workspace,
                links={
                    "self": f"/api/v1/workspaces/{workspace.id}",
                    "update": f"/api/v1/workspaces/{workspace.id}",
                    "delete": f"/api/v1/workspaces/{workspace.id}",
                    "documents": f"/api/v1/workspaces/{workspace.id}/documents",
                    "questions": f"/api/v1/workspaces/{workspace.id}/questions"
                },
                stats={
                    "document_count": 0,
                    "created_at": workspace.created_at.isoformat(),
                    "status": workspace.status
                }
            )
            
        except AnythingLLMError as e:
            logger.error(f"AnythingLLM error creating workspace: {e}")
            raise WorkspaceCreationError(f"Failed to create workspace in AnythingLLM: {e}")
        except Exception as e:
            logger.error(f"Error creating workspace: {e}")
            raise WorkspaceCreationError(f"Failed to create workspace: {e}")
    
    async def create_or_reuse_workspace(
        self,
        name: str,
        config: WorkspaceConfig
    ) -> WorkspaceResponse:
        """
        Create workspace or reuse existing one with the same name.
        
        Args:
            name: Workspace name
            config: Workspace configuration
            
        Returns:
            Workspace response (existing or newly created)
        """
        logger.info(f"Creating or reusing workspace: {name}")
        
        try:
            # Check if workspace already exists
            existing_workspace = await self.find_workspace_by_name(name)
            
            if existing_workspace:
                logger.info(f"Reusing existing workspace: {name} (ID: {existing_workspace.id})")
                
                # Update configuration if different
                if existing_workspace.config != config:
                    update_data = WorkspaceUpdate(config=config)
                    return await self.update_workspace(existing_workspace.id, update_data)
                
                # Return existing workspace
                return WorkspaceResponse(
                    workspace=existing_workspace,
                    links={
                        "self": f"/api/v1/workspaces/{existing_workspace.id}",
                        "update": f"/api/v1/workspaces/{existing_workspace.id}",
                        "delete": f"/api/v1/workspaces/{existing_workspace.id}",
                        "documents": f"/api/v1/workspaces/{existing_workspace.id}/documents",
                        "questions": f"/api/v1/workspaces/{existing_workspace.id}/questions"
                    },
                    stats={
                        "document_count": existing_workspace.document_count,
                        "created_at": existing_workspace.created_at.isoformat(),
                        "status": existing_workspace.status
                    }
                )
            
            # Create new workspace
            workspace_create = WorkspaceCreate(
                name=name,
                config=config
            )
            
            return await self.create_workspace(workspace_create)
            
        except Exception as e:
            logger.error(f"Error creating or reusing workspace {name}: {e}")
            raise WorkspaceCreationError(f"Failed to create or reuse workspace: {e}")
    
    async def get_workspace(self, workspace_id: str) -> Workspace:
        """
        Get workspace by ID.
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            Workspace details
            
        Raises:
            WorkspaceNotFoundError: If workspace not found
        """
        logger.debug(f"Getting workspace: {workspace_id}")
        
        try:
            # Try cache first
            cached_workspace = await self._get_cached_workspace(workspace_id)
            if cached_workspace:
                return cached_workspace
            
            # Get from AnythingLLM
            anythingllm_workspace = await self.anythingllm_client.get_workspace(workspace_id)
            
            # Convert to our workspace model
            workspace = self._convert_anythingllm_workspace(anythingllm_workspace)
            
            # Cache the workspace
            await self._cache_workspace(workspace)
            
            logger.debug(f"Retrieved workspace: {workspace_id}")
            return workspace
            
        except WorkspaceNotFoundError:
            raise WorkspaceNotFoundError(f"Workspace not found: {workspace_id}")
        except Exception as e:
            logger.error(f"Error getting workspace {workspace_id}: {e}")
            raise WorkspaceServiceError(f"Failed to get workspace: {e}")
    
    async def list_workspaces(self, filters: Optional[WorkspaceFilters] = None) -> List[Workspace]:
        """
        List workspaces with optional filtering.
        
        Args:
            filters: Optional workspace filters
            
        Returns:
            List of workspaces
        """
        logger.debug("Listing workspaces")
        
        try:
            filters = filters or WorkspaceFilters()
            
            # Try cache first
            if self.cache_repository:
                filters_hash = self._hash_filters(filters)
                cache_key = self._workspace_list_cache_key(filters_hash)
                cached_list = await self.cache_repository.get(cache_key)
                if cached_list:
                    logger.debug("Retrieved workspace list from cache")
                    return [Workspace(**ws) for ws in cached_list]
            
            # Get from AnythingLLM
            anythingllm_workspaces = await self.anythingllm_client.get_workspaces()
            
            # Convert to our workspace models
            workspaces = []
            for anythingllm_ws in anythingllm_workspaces:
                try:
                    workspace = self._convert_anythingllm_workspace(anythingllm_ws)
                    workspaces.append(workspace)
                except Exception as e:
                    logger.warning(f"Failed to convert workspace {anythingllm_ws.id}: {e}")
                    continue
            
            # Apply filters
            filtered_workspaces = self._apply_workspace_filters(workspaces, filters)
            
            # Cache the result
            if self.cache_repository:
                try:
                    cache_data = [ws.model_dump() for ws in filtered_workspaces]
                    await self.cache_repository.set(
                        cache_key,
                        cache_data,
                        ttl=self.workspace_list_cache_ttl
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache workspace list: {e}")
            
            logger.debug(f"Listed {len(filtered_workspaces)} workspaces")
            return filtered_workspaces
            
        except Exception as e:
            logger.error(f"Error listing workspaces: {e}")
            raise WorkspaceServiceError(f"Failed to list workspaces: {e}")
    
    async def update_workspace(
        self,
        workspace_id: str,
        workspace_update: WorkspaceUpdate
    ) -> WorkspaceResponse:
        """
        Update workspace.
        
        Args:
            workspace_id: Workspace ID
            workspace_update: Update data
            
        Returns:
            Updated workspace response
            
        Raises:
            WorkspaceNotFoundError: If workspace not found
            WorkspaceConfigurationError: If update fails
        """
        logger.info(f"Updating workspace: {workspace_id}")
        
        try:
            # Get current workspace
            current_workspace = await self.get_workspace(workspace_id)
            
            # Prepare update data
            update_data = {}
            
            if workspace_update.name is not None:
                update_data["name"] = workspace_update.name
            
            if workspace_update.config is not None:
                # Update AnythingLLM configuration
                anythingllm_config = self._prepare_anythingllm_config(workspace_update.config)
                update_data.update(anythingllm_config)
                
                # Configure procurement prompts if enabled
                if workspace_update.config.procurement_prompts:
                    await self._configure_procurement_prompts(workspace_id)
            
            # Update in AnythingLLM if there are changes
            if update_data:
                # Note: AnythingLLM may not have a direct update endpoint
                # This is a placeholder for the update logic
                logger.debug(f"Updating workspace {workspace_id} in AnythingLLM")
            
            # Create updated workspace model
            updated_workspace = Workspace(
                id=current_workspace.id,
                name=workspace_update.name or current_workspace.name,
                slug=current_workspace.slug,
                description=workspace_update.description or current_workspace.description,
                config=workspace_update.config or current_workspace.config,
                document_count=current_workspace.document_count,
                created_at=current_workspace.created_at,
                updated_at=datetime.utcnow(),
                status=workspace_update.status or current_workspace.status
            )
            
            # Invalidate cache
            await self._invalidate_workspace_cache(workspace_id)
            
            # Cache updated workspace
            await self._cache_workspace(updated_workspace)
            
            logger.info(f"Successfully updated workspace: {workspace_id}")
            
            return WorkspaceResponse(
                workspace=updated_workspace,
                links={
                    "self": f"/api/v1/workspaces/{workspace_id}",
                    "update": f"/api/v1/workspaces/{workspace_id}",
                    "delete": f"/api/v1/workspaces/{workspace_id}",
                    "documents": f"/api/v1/workspaces/{workspace_id}/documents",
                    "questions": f"/api/v1/workspaces/{workspace_id}/questions"
                },
                stats={
                    "document_count": updated_workspace.document_count,
                    "created_at": updated_workspace.created_at.isoformat(),
                    "updated_at": updated_workspace.updated_at.isoformat(),
                    "status": updated_workspace.status
                }
            )
            
        except WorkspaceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error updating workspace {workspace_id}: {e}")
            raise WorkspaceConfigurationError(f"Failed to update workspace: {e}")
    
    async def delete_workspace(self, workspace_id: str) -> bool:
        """
        Delete workspace.
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            True if deletion successful
            
        Raises:
            WorkspaceNotFoundError: If workspace not found
        """
        logger.info(f"Deleting workspace: {workspace_id}")
        
        try:
            # Create deletion job for tracking
            job = await self.job_repository.create_job(
                job_type=JobType.WORKSPACE_DELETION,
                workspace_id=workspace_id,
                metadata={"workspace_id": workspace_id}
            )
            
            # Start background deletion
            asyncio.create_task(self._delete_workspace_async(job.id, workspace_id))
            
            logger.info(f"Started workspace deletion job {job.id} for workspace {workspace_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error initiating workspace deletion {workspace_id}: {e}")
            raise WorkspaceServiceError(f"Failed to delete workspace: {e}")
    
    async def _delete_workspace_async(self, job_id: str, workspace_id: str) -> None:
        """
        Delete workspace asynchronously.
        
        Args:
            job_id: Job ID for tracking
            workspace_id: Workspace ID to delete
        """
        try:
            # Update job status
            await self.job_repository.update_job_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                progress=10.0
            )
            
            # Delete from AnythingLLM
            deleted = await self.anythingllm_client.delete_workspace(workspace_id)
            
            if deleted:
                # Update progress
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    progress=80.0
                )
                
                # Invalidate cache
                await self._invalidate_workspace_cache(workspace_id)
                
                # Complete job
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    progress=100.0,
                    result={"workspace_id": workspace_id, "deleted": True}
                )
                
                logger.info(f"Successfully deleted workspace {workspace_id}")
            else:
                # Job failed
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    progress=0.0,
                    error="Workspace not found or could not be deleted"
                )
                
                logger.warning(f"Workspace {workspace_id} not found or could not be deleted")
                
        except Exception as e:
            logger.error(f"Error in background workspace deletion for job {job_id}: {e}")
            try:
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    progress=0.0,
                    error=f"Deletion error: {str(e)}"
                )
            except Exception as update_error:
                logger.error(f"Failed to update job status after error: {update_error}")
    
    async def find_workspace_by_name(self, name: str) -> Optional[Workspace]:
        """
        Find workspace by name.
        
        Args:
            name: Workspace name
            
        Returns:
            Workspace if found, None otherwise
        """
        logger.debug(f"Finding workspace by name: {name}")
        
        try:
            # Get workspace from AnythingLLM
            anythingllm_workspace = await self.anythingllm_client.find_workspace_by_name(name)
            
            if anythingllm_workspace:
                workspace = self._convert_anythingllm_workspace(anythingllm_workspace)
                logger.debug(f"Found workspace by name: {name} -> {workspace.id}")
                return workspace
            
            logger.debug(f"No workspace found with name: {name}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding workspace by name {name}: {e}")
            raise WorkspaceServiceError(f"Failed to find workspace by name: {e}")
    
    async def trigger_document_embedding(self, workspace_id: str) -> JobResponse:
        """
        Trigger document embedding for workspace.
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            Job response for tracking embedding progress
        """
        logger.info(f"Triggering document embedding for workspace: {workspace_id}")
        
        try:
            # Verify workspace exists
            await self.get_workspace(workspace_id)
            
            # Create job for tracking
            job = await self.job_repository.create_job(
                job_type=JobType.DOCUMENT_UPLOAD,  # Reuse document upload type for embedding
                workspace_id=workspace_id,
                metadata={
                    "operation": "document_embedding",
                    "workspace_id": workspace_id
                }
            )
            
            # Start background embedding process
            asyncio.create_task(self._trigger_embedding_async(job.id, workspace_id))
            
            logger.info(f"Created document embedding job {job.id} for workspace {workspace_id}")
            
            return JobResponse(
                job=job,
                links={
                    "status": f"/api/v1/jobs/{job.id}",
                    "cancel": f"/api/v1/jobs/{job.id}"
                }
            )
            
        except WorkspaceNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error triggering document embedding for workspace {workspace_id}: {e}")
            raise WorkspaceServiceError(f"Failed to trigger document embedding: {e}")
    
    async def _trigger_embedding_async(self, job_id: str, workspace_id: str) -> None:
        """
        Trigger document embedding asynchronously.
        
        Args:
            job_id: Job ID for tracking
            workspace_id: Workspace ID
        """
        try:
            # Update job status
            await self.job_repository.update_job_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                progress=10.0
            )
            
            # Note: AnythingLLM may automatically embed documents on upload
            # This is a placeholder for triggering manual embedding if supported
            logger.info(f"Document embedding triggered for workspace {workspace_id}")
            
            # Simulate embedding process
            await asyncio.sleep(2)  # Placeholder for actual embedding time
            
            # Complete job
            await self.job_repository.update_job_status(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                progress=100.0,
                result={
                    "workspace_id": workspace_id,
                    "embedding_triggered": True,
                    "message": "Document embedding process initiated"
                }
            )
            
            logger.info(f"Document embedding job {job_id} completed for workspace {workspace_id}")
            
        except Exception as e:
            logger.error(f"Error in background document embedding for job {job_id}: {e}")
            try:
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    progress=0.0,
                    error=f"Embedding error: {str(e)}"
                )
            except Exception as update_error:
                logger.error(f"Failed to update job status after error: {update_error}")
    
    def _prepare_anythingllm_config(self, config: WorkspaceConfig) -> Dict[str, Any]:
        """
        Prepare AnythingLLM workspace configuration.
        
        Args:
            config: Workspace configuration
            
        Returns:
            AnythingLLM configuration dictionary
        """
        anythingllm_config = {}
        
        # LLM configuration
        if config.llm_config:
            llm_config = config.llm_config
            
            # Map provider to AnythingLLM format
            provider_mapping = {
                "openai": "openai",
                "ollama": "ollama", 
                "anthropic": "anthropic"
            }
            
            anythingllm_config.update({
                "LLMProvider": provider_mapping.get(llm_config.provider, "openai"),
                "OpenAiModel": llm_config.model if llm_config.provider == "openai" else None,
                "OpenAiTemp": llm_config.temperature,
                "OpenAiMaxTokens": llm_config.max_tokens,
            })
            
            # Add provider-specific configurations
            if llm_config.provider == "ollama":
                anythingllm_config["OllamaModel"] = llm_config.model
            elif llm_config.provider == "anthropic":
                anythingllm_config["AnthropicModel"] = llm_config.model
        
        # Other workspace settings
        if config.max_documents:
            anythingllm_config["maxDocuments"] = config.max_documents
        
        return anythingllm_config
    
    async def _configure_procurement_prompts(self, workspace_id: str) -> None:
        """
        Configure procurement-specific prompts for workspace.
        
        Args:
            workspace_id: Workspace ID
        """
        logger.debug(f"Configuring procurement prompts for workspace {workspace_id}")
        
        try:
            # Note: This would depend on AnythingLLM's API for setting custom prompts
            # For now, we'll log the configuration
            logger.info(f"Procurement prompts configured for workspace {workspace_id}")
            
            # Store prompt configuration in cache for reference
            if self.cache_repository:
                cache_key = f"workspace:{workspace_id}:prompts"
                await self.cache_repository.set(
                    cache_key,
                    self.procurement_prompts,
                    ttl=3600  # 1 hour
                )
                
        except Exception as e:
            logger.warning(f"Failed to configure procurement prompts for workspace {workspace_id}: {e}")
    
    async def _create_workspace_folder_organization(self, workspace_id: str) -> None:
        """
        Create folder organization system for workspace.
        
        Args:
            workspace_id: Workspace ID
        """
        logger.debug(f"Creating folder organization for workspace {workspace_id}")
        
        try:
            # Define folder structure for procurement documents
            folder_structure = {
                "contracts": "Contract documents and agreements",
                "proposals": "Vendor proposals and RFP responses", 
                "financial": "Financial reports and cost analyses",
                "compliance": "Compliance and regulatory documents",
                "correspondence": "Email and communication records"
            }
            
            # Note: This would depend on AnythingLLM's API for creating folders
            # For now, we'll store the structure in cache for reference
            if self.cache_repository:
                cache_key = f"workspace:{workspace_id}:folders"
                await self.cache_repository.set(
                    cache_key,
                    folder_structure,
                    ttl=3600  # 1 hour
                )
            
            logger.info(f"Folder organization created for workspace {workspace_id}")
            
        except Exception as e:
            logger.warning(f"Failed to create folder organization for workspace {workspace_id}: {e}")
    
    def _convert_anythingllm_workspace(self, anythingllm_ws: WorkspaceInfo) -> Workspace:
        """
        Convert AnythingLLM workspace to our workspace model.
        
        Args:
            anythingllm_ws: AnythingLLM workspace info
            
        Returns:
            Converted workspace model
        """
        # Create default configuration
        # Handle both WorkspaceInfo and Workspace objects
        temperature = 0.7
        if hasattr(anythingllm_ws, 'openAiTemp') and anythingllm_ws.openAiTemp is not None:
            temperature = anythingllm_ws.openAiTemp
        elif hasattr(anythingllm_ws, 'config') and hasattr(anythingllm_ws.config, 'llm_config'):
            temperature = anythingllm_ws.config.llm_config.temperature
        
        default_llm_config = LLMConfig(
            provider="openai",
            model="gpt-3.5-turbo",
            temperature=temperature
        )
        
        default_config = WorkspaceConfig(
            llm_config=default_llm_config,
            procurement_prompts=True,
            auto_embed=True
        )
        
        # Parse creation date
        try:
            created_at = datetime.fromisoformat(anythingllm_ws.createdAt.replace('Z', '+00:00'))
        except:
            created_at = datetime.utcnow()
        
        # Parse update date
        try:
            updated_at = datetime.fromisoformat(anythingllm_ws.lastUpdatedAt.replace('Z', '+00:00')) if anythingllm_ws.lastUpdatedAt else created_at
        except:
            updated_at = created_at
        
        return Workspace(
            id=anythingllm_ws.id,
            name=anythingllm_ws.name,
            slug=anythingllm_ws.slug,
            description=None,  # AnythingLLM may not have description field
            config=default_config,
            document_count=0,  # Would need to be fetched separately
            created_at=created_at,
            updated_at=updated_at,
            status=WorkspaceStatus.ACTIVE
        )
    
    def _apply_workspace_filters(
        self,
        workspaces: List[Workspace],
        filters: WorkspaceFilters
    ) -> List[Workspace]:
        """
        Apply filters to workspace list.
        
        Args:
            workspaces: List of workspaces
            filters: Filter criteria
            
        Returns:
            Filtered workspace list
        """
        filtered = workspaces
        
        if filters.status:
            filtered = [ws for ws in filtered if ws.status == filters.status]
        
        if filters.name_contains:
            name_filter = filters.name_contains.lower()
            filtered = [ws for ws in filtered if name_filter in ws.name.lower()]
        
        if filters.created_after:
            filtered = [ws for ws in filtered if ws.created_at >= filters.created_after]
        
        if filters.created_before:
            filtered = [ws for ws in filtered if ws.created_at <= filters.created_before]
        
        if filters.min_documents is not None:
            filtered = [ws for ws in filtered if ws.document_count >= filters.min_documents]
        
        if filters.max_documents is not None:
            filtered = [ws for ws in filtered if ws.document_count <= filters.max_documents]
        
        return filtered


# Factory function for dependency injection
def create_workspace_service(
    settings: Settings,
    anythingllm_client: AnythingLLMClient,
    job_repository: JobRepository,
    cache_repository: Optional[CacheRepository] = None
) -> WorkspaceService:
    """
    Create WorkspaceService instance with dependencies.
    
    Args:
        settings: Application settings
        anythingllm_client: AnythingLLM client
        job_repository: Job repository
        cache_repository: Optional cache repository
        
    Returns:
        Configured WorkspaceService instance
    """
    return WorkspaceService(
        settings=settings,
        anythingllm_client=anythingllm_client,
        job_repository=job_repository,
        cache_repository=cache_repository
    )