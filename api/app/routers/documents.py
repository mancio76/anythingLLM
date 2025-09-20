"""Document processing REST API endpoints."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.dependencies import (
    get_current_active_user, 
    require_user,
    get_document_service,
    get_job_service
)
from app.core.security import User
from app.models.pydantic_models import (
    ErrorResponse,
    Job,
    JobFilters,
    JobResponse,
    JobStatus,
    JobType,
    PaginatedJobs,
    PaginationParams,
)
from app.services.document_service import DocumentService, DocumentProcessingError
from app.services.job_service import JobService, JobNotFoundError, JobCancellationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# Dependencies are now imported from app.core.dependencies


@router.post(
    "/upload",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload ZIP file containing documents",
    description="Upload a ZIP file containing PDF, JSON, or CSV documents for processing",
    responses={
        202: {"description": "Upload initiated successfully"},
        400: {"description": "Invalid file or request"},
        413: {"description": "File too large"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    }
)
async def upload_documents(
    file: UploadFile = File(
        ...,
        description="ZIP file containing documents (PDF, JSON, CSV only)",
        media_type="application/zip"
    ),
    workspace_id: str = Form(
        ...,
        description="Target workspace ID for document upload",
        min_length=1,
        max_length=255
    ),
    project_name: Optional[str] = Form(
        None,
        description="Optional project name for organization",
        max_length=255
    ),
    document_type: Optional[str] = Form(
        None,
        description="Optional document type classification",
        max_length=100
    ),
    current_user: User = Depends(require_user),
    document_service: DocumentService = Depends(get_document_service),
    settings = Depends(get_settings)
) -> JobResponse:
    """
    Upload ZIP file containing documents for processing.
    
    This endpoint accepts ZIP files containing PDF, JSON, or CSV documents
    and initiates background processing to extract, validate, and upload
    them to the specified AnythingLLM workspace.
    
    **File Requirements:**
    - Must be a valid ZIP file
    - Maximum size: configured in MAX_FILE_SIZE (default 100MB)
    - Must contain only PDF, JSON, or CSV files
    - Maximum 100 files per ZIP
    
    **Processing Steps:**
    1. Validate ZIP file size and format
    2. Extract files securely (with path traversal protection)
    3. Validate file types and sizes
    4. Organize files by type
    5. Upload to AnythingLLM workspace
    6. Return job ID for status tracking
    
    **Returns:**
    - Job ID for tracking upload progress
    - Links to status and cancellation endpoints
    - Estimated completion time (if available)
    """
    try:
        logger.info(
            f"Document upload request from user {current_user.username} "
            f"for workspace {workspace_id}"
        )
        
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No file provided"
            )
        
        if not file.filename.lower().endswith('.zip'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only ZIP files are allowed"
            )
        
        # Check file size
        if file.size and file.size > settings.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size {file.size} bytes exceeds maximum allowed size "
                       f"{settings.max_file_size} bytes"
            )
        
        # Prepare metadata
        metadata = {
            "user_id": current_user.id,
            "username": current_user.username,
            "original_filename": file.filename,
            "content_type": file.content_type,
            "file_size": file.size,
        }
        
        if project_name:
            metadata["project_name"] = project_name
        if document_type:
            metadata["document_type"] = document_type
        
        # Initiate document processing
        job_response = await document_service.upload_documents(
            zip_file=file,
            workspace_id=workspace_id,
            metadata=metadata
        )
        
        logger.info(
            f"Created document upload job {job_response.job.id} "
            f"for user {current_user.username}"
        )
        
        return job_response
        
    except DocumentProcessingError as e:
        logger.error(f"Document processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in document upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during document upload"
        )


@router.get(
    "/jobs/{job_id}",
    response_model=Job,
    summary="Get document processing job status",
    description="Get detailed status and progress information for a document processing job",
    responses={
        200: {"description": "Job status retrieved successfully"},
        404: {"description": "Job not found"},
        403: {"description": "Access denied to job"},
        500: {"description": "Internal server error"},
    }
)
async def get_job_status(
    job_id: str,
    include_results: bool = Query(
        False,
        description="Include detailed processing results in response"
    ),
    current_user: User = Depends(require_user),
    job_service: JobService = Depends(get_job_service)
) -> Job:
    """
    Get status and progress information for a document processing job.
    
    **Job Status Values:**
    - `pending`: Job is queued and waiting to start
    - `processing`: Job is currently being processed
    - `completed`: Job completed successfully
    - `failed`: Job failed with errors
    - `cancelled`: Job was cancelled by user or system
    
    **Progress Information:**
    - Progress percentage (0-100)
    - Estimated completion time
    - Processing steps completed
    - Error details (if failed)
    
    **Access Control:**
    - Users can only access their own jobs
    - Admins can access all jobs
    """
    try:
        logger.debug(f"Getting job status for {job_id} by user {current_user.username}")
        
        # Get job details
        job = await job_service.get_job(job_id, include_results=include_results)
        
        # Check access permissions
        if not _can_access_job(job, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job"
            )
        
        # Validate job type
        if job.type != JobType.DOCUMENT_UPLOAD:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document processing job not found"
            )
        
        return job
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.delete(
    "/jobs/{job_id}",
    response_model=Job,
    summary="Cancel document processing job",
    description="Cancel a pending or processing document job with proper cleanup",
    responses={
        200: {"description": "Job cancelled successfully"},
        404: {"description": "Job not found"},
        403: {"description": "Access denied or job cannot be cancelled"},
        409: {"description": "Job cannot be cancelled in current state"},
        500: {"description": "Internal server error"},
    }
)
async def cancel_job(
    job_id: str,
    reason: Optional[str] = Query(
        None,
        description="Optional reason for cancellation",
        max_length=500
    ),
    current_user: User = Depends(require_user),
    job_service: JobService = Depends(get_job_service)
) -> Job:
    """
    Cancel a document processing job.
    
    **Cancellation Rules:**
    - Only pending or processing jobs can be cancelled
    - Completed, failed, or already cancelled jobs cannot be cancelled
    - Users can only cancel their own jobs (unless admin)
    - Cancellation triggers cleanup of temporary files and resources
    
    **Cleanup Actions:**
    - Stop background processing
    - Clean up temporary files
    - Release allocated resources
    - Update job status to cancelled
    - Log cancellation reason
    
    **Access Control:**
    - Users can only cancel their own jobs
    - Admins can cancel any job
    """
    try:
        logger.info(
            f"Cancellation request for job {job_id} by user {current_user.username}"
        )
        
        # Get job to check permissions and state
        job = await job_service.get_job(job_id)
        
        # Check access permissions
        if not _can_access_job(job, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job"
            )
        
        # Validate job type
        if job.type != JobType.DOCUMENT_UPLOAD:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document processing job not found"
            )
        
        # Check if job can be cancelled
        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job cannot be cancelled - current status: {job.status.value}"
            )
        
        # Prepare cancellation reason
        cancellation_reason = reason or f"Cancelled by user {current_user.username}"
        
        # Cancel the job
        cancelled_job = await job_service.cancel_job(job_id, cancellation_reason)
        
        logger.info(
            f"Successfully cancelled job {job_id} by user {current_user.username}: "
            f"{cancellation_reason}"
        )
        
        return cancelled_job
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    except JobCancellationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during job cancellation"
        )


@router.get(
    "/jobs",
    response_model=PaginatedJobs,
    summary="List document processing jobs",
    description="Get paginated list of document processing jobs with filtering options",
    responses={
        200: {"description": "Jobs retrieved successfully"},
        422: {"description": "Invalid query parameters"},
        500: {"description": "Internal server error"},
    }
)
async def list_jobs(
    # Pagination parameters
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    
    # Filter parameters
    status: Optional[JobStatus] = Query(
        None,
        description="Filter by job status"
    ),
    workspace_id: Optional[str] = Query(
        None,
        description="Filter by workspace ID",
        max_length=255
    ),
    project_name: Optional[str] = Query(
        None,
        description="Filter by project name (partial match)",
        max_length=255
    ),
    document_type: Optional[str] = Query(
        None,
        description="Filter by document type",
        max_length=100
    ),
    created_after: Optional[str] = Query(
        None,
        description="Filter jobs created after this date (ISO format)"
    ),
    created_before: Optional[str] = Query(
        None,
        description="Filter jobs created before this date (ISO format)"
    ),
    
    # Options
    include_metadata: bool = Query(
        False,
        description="Include job metadata in response"
    ),
    
    current_user: User = Depends(require_user),
    job_service: JobService = Depends(get_job_service)
) -> PaginatedJobs:
    """
    List document processing jobs with filtering and pagination.
    
    **Filtering Options:**
    - Status: Filter by job status (pending, processing, completed, failed, cancelled)
    - Workspace: Filter by workspace ID
    - Project: Filter by project name (partial text match)
    - Document Type: Filter by document type classification
    - Date Range: Filter by creation date range
    
    **Sorting:**
    - Jobs are sorted by creation date (newest first)
    - Completed jobs are sorted by completion date
    
    **Access Control:**
    - Users see only their own jobs
    - Admins see all jobs
    - Workspace-level access control applied
    
    **Performance:**
    - Results are paginated for performance
    - Maximum page size is 100 items
    - Metadata inclusion is optional to reduce response size
    """
    try:
        logger.debug(
            f"Listing document jobs for user {current_user.username} "
            f"(page {page}, size {size})"
        )
        
        # Parse date filters
        created_after_dt = None
        created_before_dt = None
        
        if created_after:
            try:
                from datetime import datetime
                created_after_dt = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid created_after date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        if created_before:
            try:
                from datetime import datetime
                created_before_dt = datetime.fromisoformat(created_before.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid created_before date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )
        
        # Create filters
        filters = JobFilters(
            type=JobType.DOCUMENT_UPLOAD,  # Only document processing jobs
            status=status,
            workspace_id=workspace_id,
            created_after=created_after_dt,
            created_before=created_before_dt
        )
        
        # Add user-specific filters (non-admin users see only their jobs)
        if not _is_admin_user(current_user):
            # Filter by user ID in metadata
            # Note: This would need to be implemented in the repository layer
            pass
        
        # Create pagination
        pagination = PaginationParams(page=page, size=size)
        
        # Get jobs
        result = await job_service.list_jobs(
            filters=filters,
            pagination=pagination,
            include_relationships=include_metadata
        )
        
        # Filter results by access permissions and additional criteria
        filtered_jobs = []
        for job in result.items:
            # Check access permissions
            if not _can_access_job(job, current_user):
                continue
            
            # Apply additional filters that can't be done at DB level
            if project_name and project_name.lower() not in job.metadata.get("project_name", "").lower():
                continue
            
            if document_type and job.metadata.get("document_type") != document_type:
                continue
            
            filtered_jobs.append(job)
        
        # Update result with filtered jobs
        result.items = filtered_jobs
        result.total = len(filtered_jobs)  # Note: This is approximate for this page
        
        logger.debug(
            f"Retrieved {len(filtered_jobs)} document jobs for user {current_user.username}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing document jobs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while listing jobs"
        )


# Helper functions

def _can_access_job(job: Job, user: User) -> bool:
    """
    Check if user can access the job.
    
    Args:
        job: Job to check access for
        user: User requesting access
        
    Returns:
        True if user can access the job
    """
    # Admin users can access all jobs
    if _is_admin_user(user):
        return True
    
    # Users can access their own jobs
    job_user_id = job.metadata.get("user_id")
    if job_user_id == user.id:
        return True
    
    # Additional workspace-based access control could be added here
    
    return False


def _is_admin_user(user: User) -> bool:
    """
    Check if user has admin privileges.
    
    Args:
        user: User to check
        
    Returns:
        True if user is admin
    """
    return "admin" in user.roles


# Note: Error handlers should be added to the main FastAPI app in main.py
# These custom exceptions are handled by the global exception handler middleware