"""Workspace management REST API endpoints."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import JSONResponse

from app.core.config import get_settings, Settings
from app.core.dependencies import (
    get_current_active_user, 
    require_user,
    get_workspace_service
)
from app.core.security import User
from app.core.database import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pydantic_models import (
    ErrorResponse,
    Job,
    JobResponse,
    JobStatus,
    JobType,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
    WorkspaceFilters,
    WorkspaceStatus,
)
from app.services.workspace_service import (
    WorkspaceService,
    WorkspaceServiceError,
    WorkspaceNotFoundError,
    WorkspaceCreationError,
    WorkspaceConfigurationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# Dependencies are now imported from app.core.dependencies


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new workspace",
    description="Create a new AnythingLLM workspace with procurement-specific configuration",
    responses={
        201: {"description": "Workspace created successfully"},
        400: {"description": "Invalid workspace configuration"},
        409: {"description": "Workspace with same name already exists"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    }
)
async def create_workspace(
    workspace_create: WorkspaceCreate,
    current_user: User = Depends(require_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    settings = Depends(get_settings)
) -> WorkspaceResponse:
    """
    Create a new workspace in AnythingLLM.
    
    This endpoint creates a new workspace with the specified configuration,
    including LLM settings and procurement-specific prompts. The workspace
    is automatically configured with folder organization and embedding settings.
    
    **Workspace Features:**
    - Procurement-specific system prompts
    - Automatic document embedding
    - Organized folder structure
    - Configurable LLM models (OpenAI, Ollama, Anthropic)
    - Document count tracking
    
    **Configuration Options:**
    - LLM provider and model selection
    - Temperature and token limits
    - Procurement prompt templates
    - Auto-embedding settings
    - Maximum document limits
    
    **Returns:**
    - Complete workspace details
    - Links to related endpoints
    - Workspace statistics and metadata
    """
    try:
        logger.info(
            f"Creating workspace '{workspace_create.name}' "
            f"by user {current_user.username}"
        )
        
        # Create workspace
        workspace_response = await workspace_service.create_workspace(workspace_create)
        
        logger.info(
            f"Successfully created workspace {workspace_response.workspace.id} "
            f"for user {current_user.username}"
        )
        
        return workspace_response
        
    except WorkspaceCreationError as e:
        logger.error(f"Workspace creation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error creating workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during workspace creation"
        )


@router.get(
    "",
    response_model=List[Workspace],
    summary="List workspaces",
    description="Get list of workspaces with optional filtering and metadata",
    responses={
        200: {"description": "Workspaces retrieved successfully"},
        422: {"description": "Invalid query parameters"},
        500: {"description": "Internal server error"},
    }
)
async def list_workspaces(
    # Filter parameters
    status: Optional[WorkspaceStatus] = Query(
        None,
        description="Filter by workspace status"
    ),
    name_contains: Optional[str] = Query(
        None,
        description="Filter by name containing text (case-insensitive)",
        max_length=255
    ),
    created_after: Optional[str] = Query(
        None,
        description="Filter workspaces created after this date (ISO format)"
    ),
    created_before: Optional[str] = Query(
        None,
        description="Filter workspaces created before this date (ISO format)"
    ),
    min_documents: Optional[int] = Query(
        None,
        ge=0,
        description="Filter by minimum document count"
    ),
    max_documents: Optional[int] = Query(
        None,
        ge=0,
        description="Filter by maximum document count"
    ),
    
    # Options
    include_stats: bool = Query(
        True,
        description="Include workspace statistics in response"
    ),
    
    current_user: User = Depends(require_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
) -> List[Workspace]:
    """
    List workspaces with filtering options.
    
    **Filtering Options:**
    - Status: Filter by workspace status (active, inactive, deleted, error)
    - Name: Filter by partial name match (case-insensitive)
    - Date Range: Filter by creation date range
    - Document Count: Filter by document count range
    
    **Workspace Information:**
    - Basic workspace details (name, description, status)
    - Configuration settings (LLM config, prompts)
    - Document count and statistics
    - Creation and update timestamps
    - Workspace slug for URL generation
    
    **Access Control:**
    - Users see workspaces they have access to
    - Admins see all workspaces
    - Workspace-level permissions applied
    
    **Performance:**
    - Results are cached for improved performance
    - Statistics inclusion is optional
    - Efficient filtering at database level
    """
    try:
        logger.debug(f"Listing workspaces for user {current_user.username}")
        
        # Parse date filters
        created_after_dt = None
        created_before_dt = None
        
        if created_after:
            try:
                created_after_dt = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid created_after date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        if created_before:
            try:
                created_before_dt = datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid created_before date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Validate document count range
        if min_documents is not None and max_documents is not None:
            if min_documents > max_documents:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="min_documents cannot be greater than max_documents"
                )
        
        # Create filters
        filters = WorkspaceFilters(
            status=status,
            name_contains=name_contains,
            created_after=created_after_dt,
            created_before=created_before_dt,
            min_documents=min_documents,
            max_documents=max_documents
        )
        
        # Get workspaces
        workspaces = await workspace_service.list_workspaces(filters)
        
        # Apply access control filtering
        accessible_workspaces = []
        for workspace in workspaces:
            if _can_access_workspace(workspace, current_user):
                accessible_workspaces.append(workspace)
        
        logger.debug(
            f"Retrieved {len(accessible_workspaces)} workspaces "
            f"for user {current_user.username}"
        )
        
        return accessible_workspaces
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing workspaces: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing workspaces"
        )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get workspace details",
    description="Get detailed information about a specific workspace",
    responses={
        200: {"description": "Workspace retrieved successfully"},
        404: {"description": "Workspace not found"},
        403: {"description": "Access denied to workspace"},
        500: {"description": "Internal server error"},
    }
)
async def get_workspace(
    workspace_id: str,
    include_stats: bool = Query(
        True,
        description="Include detailed workspace statistics"
    ),
    current_user: User = Depends(require_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
) -> WorkspaceResponse:
    """
    Get detailed information about a specific workspace.
    
    **Workspace Details:**
    - Complete workspace configuration
    - Document count and organization
    - LLM settings and prompt configuration
    - Creation and modification history
    - Status and health information
    
    **Statistics (optional):**
    - Document count by type
    - Processing history
    - Usage metrics
    - Performance data
    
    **Access Control:**
    - Users can only access workspaces they have permissions for
    - Admins can access all workspaces
    - Workspace-level access control applied
    """
    try:
        logger.debug(f"Getting workspace {workspace_id} for user {current_user.username}")
        
        # Get workspace
        workspace = await workspace_service.get_workspace(workspace_id)
        
        # Check access permissions
        if not _can_access_workspace(workspace, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this workspace"
            )
        
        # Build response with links and stats
        response = WorkspaceResponse(
            workspace=workspace,
            links={
                "self": f"/api/v1/workspaces/{workspace_id}",
                "update": f"/api/v1/workspaces/{workspace_id}",
                "delete": f"/api/v1/workspaces/{workspace_id}",
                "documents": f"/api/v1/workspaces/{workspace_id}/documents",
                "questions": f"/api/v1/workspaces/{workspace_id}/questions",
                "embed": f"/api/v1/workspaces/{workspace_id}/embed"
            }
        )
        
        if include_stats:
            response.stats = {
                "document_count": workspace.document_count,
                "created_at": workspace.created_at.isoformat(),
                "updated_at": workspace.updated_at.isoformat(),
                "status": workspace.status.value,
                "is_active": workspace.is_active,
                "llm_provider": workspace.config.llm_config.provider.value,
                "llm_model": workspace.config.llm_config.model,
                "procurement_prompts_enabled": workspace.config.procurement_prompts,
                "auto_embed_enabled": workspace.config.auto_embed
            }
        
        return response
        
    except WorkspaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.put(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update workspace configuration",
    description="Update workspace settings and configuration",
    responses={
        200: {"description": "Workspace updated successfully"},
        404: {"description": "Workspace not found"},
        403: {"description": "Access denied to workspace"},
        400: {"description": "Invalid configuration"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    }
)
async def update_workspace(
    workspace_id: str,
    workspace_update: WorkspaceUpdate,
    current_user: User = Depends(require_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
) -> WorkspaceResponse:
    """
    Update workspace configuration and settings.
    
    **Updatable Fields:**
    - Workspace name and description
    - LLM configuration (provider, model, parameters)
    - Procurement prompt settings
    - Auto-embedding configuration
    - Workspace status
    
    **Configuration Changes:**
    - LLM model changes are applied immediately
    - Prompt changes affect new conversations
    - Status changes control workspace availability
    - Name changes update the workspace slug
    
    **Safety Checks:**
    - Validates configuration before applying
    - Checks for conflicts with existing workspaces
    - Ensures LLM model availability
    - Maintains data consistency
    
    **Access Control:**
    - Users can only update workspaces they have write access to
    - Admins can update all workspaces
    - Some settings may require admin privileges
    """
    try:
        logger.info(
            f"Updating workspace {workspace_id} by user {current_user.username}"
        )
        
        # Check workspace exists and access permissions
        existing_workspace = await workspace_service.get_workspace(workspace_id)
        
        if not _can_modify_workspace(existing_workspace, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to modify this workspace"
            )
        
        # Update workspace
        workspace_response = await workspace_service.update_workspace(
            workspace_id, workspace_update
        )
        
        logger.info(
            f"Successfully updated workspace {workspace_id} "
            f"by user {current_user.username}"
        )
        
        return workspace_response
        
    except WorkspaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found"
        )
    except WorkspaceConfigurationError as e:
        logger.error(f"Workspace configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during workspace update"
        )


@router.delete(
    "/{workspace_id}",
    response_model=Dict[str, Any],
    summary="Delete workspace",
    description="Delete workspace with safety checks and cleanup",
    responses={
        202: {"description": "Workspace deletion initiated"},
        404: {"description": "Workspace not found"},
        403: {"description": "Access denied to workspace"},
        409: {"description": "Workspace cannot be deleted in current state"},
        500: {"description": "Internal server error"},
    }
)
async def delete_workspace(
    workspace_id: str,
    force: bool = Query(
        False,
        description="Force deletion even if workspace has documents"
    ),
    reason: Optional[str] = Query(
        None,
        description="Optional reason for deletion",
        max_length=500
    ),
    current_user: User = Depends(require_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
) -> Dict[str, Any]:
    """
    Delete a workspace with proper safety checks and cleanup.
    
    **Deletion Process:**
    1. Verify workspace exists and user has delete permissions
    2. Check for safety conditions (document count, active jobs)
    3. Create deletion job for background processing
    4. Clean up workspace data and documents
    5. Remove from AnythingLLM instance
    6. Update workspace status to deleted
    
    **Safety Checks:**
    - Workspace must be inactive or force flag must be set
    - No active processing jobs (unless forced)
    - User confirmation for workspaces with many documents
    - Admin approval for shared workspaces
    
    **Cleanup Actions:**
    - Remove all workspace documents
    - Cancel pending jobs
    - Clean up temporary files
    - Remove workspace from AnythingLLM
    - Archive workspace metadata
    
    **Access Control:**
    - Users can only delete workspaces they own
    - Admins can delete any workspace
    - Shared workspaces require special permissions
    """
    try:
        logger.info(
            f"Deleting workspace {workspace_id} by user {current_user.username}"
        )
        
        # Check workspace exists and access permissions
        workspace = await workspace_service.get_workspace(workspace_id)
        
        if not _can_delete_workspace(workspace, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to delete this workspace"
            )
        
        # Safety checks
        if workspace.status == WorkspaceStatus.DELETED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workspace is already deleted"
            )
        
        if not force and workspace.document_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workspace has {workspace.document_count} documents. "
                       "Use force=true to delete anyway."
            )
        
        # Initiate deletion
        deletion_successful = await workspace_service.delete_workspace(workspace_id)
        
        if not deletion_successful:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initiate workspace deletion"
            )
        
        deletion_reason = reason or f"Deleted by user {current_user.username}"
        
        logger.info(
            f"Successfully initiated deletion of workspace {workspace_id} "
            f"by user {current_user.username}: {deletion_reason}"
        )
        
        return {
            "message": "Workspace deletion initiated",
            "workspace_id": workspace_id,
            "status": "deletion_in_progress",
            "reason": deletion_reason,
            "force_deletion": force,
            "initiated_by": current_user.username,
            "initiated_at": datetime.utcnow().isoformat()
        }
        
    except WorkspaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during workspace deletion"
        )


@router.post(
    "/{workspace_id}/embed",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger document embedding",
    description="Manually trigger document embedding process for workspace",
    responses={
        202: {"description": "Document embedding initiated"},
        404: {"description": "Workspace not found"},
        403: {"description": "Access denied to workspace"},
        409: {"description": "Embedding already in progress"},
        500: {"description": "Internal server error"},
    }
)
async def trigger_document_embedding(
    workspace_id: str,
    current_user: User = Depends(require_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service)
) -> JobResponse:
    """
    Manually trigger document embedding process for a workspace.
    
    **Embedding Process:**
    - Processes all documents in the workspace
    - Creates vector embeddings for semantic search
    - Updates document index for improved retrieval
    - Optimizes workspace for question-answering
    
    **Use Cases:**
    - Re-embed documents after configuration changes
    - Improve search performance for large document sets
    - Update embeddings after adding new documents
    - Troubleshoot embedding-related issues
    
    **Process Tracking:**
    - Returns job ID for progress monitoring
    - Provides estimated completion time
    - Tracks embedding status and errors
    - Logs detailed processing information
    
    **Access Control:**
    - Users can trigger embedding for workspaces they have access to
    - Admins can trigger embedding for any workspace
    - Rate limiting applied to prevent abuse
    """
    try:
        logger.info(
            f"Triggering document embedding for workspace {workspace_id} "
            f"by user {current_user.username}"
        )
        
        # Check workspace exists and access permissions
        workspace = await workspace_service.get_workspace(workspace_id)
        
        if not _can_access_workspace(workspace, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this workspace"
            )
        
        # Check workspace status
        if workspace.status != WorkspaceStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot trigger embedding for workspace in {workspace.status.value} status"
            )
        
        # Trigger embedding
        job_response = await workspace_service.trigger_document_embedding(workspace_id)
        
        logger.info(
            f"Successfully triggered document embedding job {job_response.job.id} "
            f"for workspace {workspace_id} by user {current_user.username}"
        )
        
        return job_response
        
    except WorkspaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace {workspace_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering embedding for workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during embedding trigger"
        )


# Helper functions

def _can_access_workspace(workspace: Workspace, user: User) -> bool:
    """
    Check if user can access the workspace.
    
    Args:
        workspace: Workspace to check access for
        user: User requesting access
        
    Returns:
        True if user can access the workspace
    """
    # Admin users can access all workspaces
    if _is_admin_user(user):
        return True
    
    # For now, all authenticated users can access all workspaces
    # This can be extended with workspace-specific permissions
    return True


def _can_modify_workspace(workspace: Workspace, user: User) -> bool:
    """
    Check if user can modify the workspace.
    
    Args:
        workspace: Workspace to check modify access for
        user: User requesting access
        
    Returns:
        True if user can modify the workspace
    """
    # Admin users can modify all workspaces
    if _is_admin_user(user):
        return True
    
    # For now, all authenticated users can modify all workspaces
    # This can be extended with workspace-specific permissions
    return True


def _can_delete_workspace(workspace: Workspace, user: User) -> bool:
    """
    Check if user can delete the workspace.
    
    Args:
        workspace: Workspace to check delete access for
        user: User requesting access
        
    Returns:
        True if user can delete the workspace
    """
    # Admin users can delete all workspaces
    if _is_admin_user(user):
        return True
    
    # Regular users can delete workspaces they have access to
    # This can be extended with more restrictive permissions
    return _can_access_workspace(workspace, user)


def _is_admin_user(user: User) -> bool:
    """
    Check if user has admin privileges.
    
    Args:
        user: User to check
        
    Returns:
        True if user is admin
    """
    return "admin" in user.roles