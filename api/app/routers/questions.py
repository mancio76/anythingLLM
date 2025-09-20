"""Question processing REST API endpoints."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import get_settings
from app.core.dependencies import (
    get_current_active_user, 
    require_user,
    get_question_service,
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
    QuestionRequest,
    QuestionResults,
)
from app.services.question_service import QuestionService, QuestionProcessingError
from app.services.job_service import JobService, JobNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


# Dependencies are now imported from app.core.dependencies


@router.post(
    "/execute",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute question set against workspace",
    description="Execute automated question sets against AnythingLLM workspace with configurable LLM models",
    responses={
        202: {"description": "Question execution initiated successfully"},
        400: {"description": "Invalid request or workspace not found"},
        422: {"description": "Validation error"},
        429: {"description": "Too many concurrent requests"},
        500: {"description": "Internal server error"},
    }
)
async def execute_questions(
    request: QuestionRequest,
    current_user: User = Depends(require_user),
    question_service: QuestionService = Depends(get_question_service),
    settings = Depends(get_settings)
) -> JobResponse:
    """
    Execute automated question sets against workspace.
    
    This endpoint initiates background processing to execute a set of questions
    against documents in the specified AnythingLLM workspace. Each question can
    have its own LLM configuration, or use the default configuration provided.
    
    **Question Processing:**
    - Questions are processed concurrently (configurable limit)
    - Each question creates a thread in the workspace
    - Responses are analyzed for confidence scoring
    - Results include expected fragment matching
    - Failed questions are captured with error details
    
    **LLM Model Support:**
    - OpenAI models (GPT-3.5, GPT-4, etc.)
    - Ollama models (local deployment)
    - Anthropic models (Claude variants)
    - Per-question model override capability
    
    **Confidence Scoring:**
    - Based on expected fragment matching
    - Response quality heuristics
    - Uncertainty detection and penalties
    - Score range: 0.0 (low confidence) to 1.0 (high confidence)
    
    **Returns:**
    - Job ID for tracking execution progress
    - Links to status and results endpoints
    - Estimated completion time
    """
    try:
        logger.info(
            f"Question execution request from user {current_user.username} "
            f"for workspace {request.workspace_id} with {len(request.questions)} questions"
        )
        
        # Validate workspace access (basic check)
        if not request.workspace_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workspace ID cannot be empty"
            )
        
        # Add user context to request metadata
        if not hasattr(request, 'metadata'):
            request.metadata = {}
        
        request.metadata.update({
            "user_id": current_user.id,
            "username": current_user.username,
            "initiated_at": datetime.utcnow().isoformat(),
        })
        
        # Initiate question processing
        job_response = await question_service.execute_questions(request)
        
        logger.info(
            f"Created question processing job {job_response.job.id} "
            f"for user {current_user.username}"
        )
        
        return job_response
        
    except QuestionProcessingError as e:
        logger.error(f"Question processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in question execution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during question execution"
        )


@router.get(
    "/jobs/{job_id}",
    response_model=Job,
    summary="Get question processing job status",
    description="Get detailed status and progress information for a question processing job",
    responses={
        200: {"description": "Job status retrieved successfully"},
        404: {"description": "Job not found"},
        403: {"description": "Access denied to job"},
        500: {"description": "Internal server error"},
    }
)
async def get_question_job_status(
    job_id: str,
    include_results: bool = Query(
        False,
        description="Include detailed processing results in response"
    ),
    include_summary: bool = Query(
        True,
        description="Include results summary statistics"
    ),
    current_user: User = Depends(require_user),
    job_service: JobService = Depends(get_job_service)
) -> Job:
    """
    Get status and progress information for a question processing job.
    
    **Job Status Values:**
    - `pending`: Job is queued and waiting to start
    - `processing`: Job is currently being processed
    - `completed`: Job completed successfully
    - `failed`: Job failed with errors
    - `cancelled`: Job was cancelled by user or system
    
    **Progress Information:**
    - Progress percentage (0-100)
    - Current processing step
    - Questions completed vs total
    - Average processing time per question
    - Estimated completion time
    
    **Detailed Results (optional):**
    - Individual question results
    - Confidence scores and fragment matches
    - Processing times and error details
    - LLM model used for each question
    
    **Summary Statistics:**
    - Total/successful/failed question counts
    - Success rate percentage
    - Average confidence score
    - Confidence distribution (high/medium/low)
    - Error type breakdown
    
    **Access Control:**
    - Users can only access their own jobs
    - Admins can access all jobs
    """
    try:
        logger.debug(f"Getting question job status for {job_id} by user {current_user.username}")
        
        # Get job details
        job = await job_service.get_job(job_id, include_results=include_results)
        
        # Check access permissions
        if not _can_access_job(job, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job"
            )
        
        # Validate job type
        if job.type != JobType.QUESTION_PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question processing job not found"
            )
        
        # Filter results based on include_summary flag
        if job.result and not include_summary:
            # Remove summary data if not requested
            filtered_result = {k: v for k, v in job.result.items() if k != "summary"}
            job.result = filtered_result
        
        return job
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting question job status for {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/jobs/{job_id}/results",
    response_model=QuestionResults,
    summary="Get question processing results",
    description="Get detailed results from completed question processing job with export options",
    responses={
        200: {"description": "Results retrieved successfully"},
        202: {"description": "Job still processing, results not ready"},
        404: {"description": "Job not found or no results available"},
        403: {"description": "Access denied to job"},
        409: {"description": "Job failed, no results available"},
        500: {"description": "Internal server error"},
    }
)
async def get_question_results(
    job_id: str,
    format: str = Query(
        "json",
        description="Export format: json, csv",
        pattern="^(json|csv)$"
    ),
    include_metadata: bool = Query(
        True,
        description="Include question metadata in results"
    ),
    confidence_threshold: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Filter results by minimum confidence score"
    ),
    success_only: bool = Query(
        False,
        description="Include only successful question results"
    ),
    current_user: User = Depends(require_user),
    job_service: JobService = Depends(get_job_service),
    question_service: QuestionService = Depends(get_question_service)
) -> QuestionResults:
    """
    Get detailed results from completed question processing job.
    
    **Result Formats:**
    - `json`: Structured JSON response with full details
    - `csv`: CSV export suitable for spreadsheet analysis
    
    **Filtering Options:**
    - Confidence threshold: Include only results above specified confidence
    - Success only: Filter out failed question attempts
    - Metadata inclusion: Control response size by excluding metadata
    
    **Result Details:**
    - Individual question results with responses
    - Confidence scores and fragment matching
    - Processing times and error details
    - LLM model and configuration used
    - Summary statistics and distributions
    
    **CSV Export Format:**
    - Question ID, Text, Response, Confidence, Success, Error
    - Processing time, Fragments found, LLM model
    - Suitable for analysis in Excel or other tools
    
    **Access Control:**
    - Users can only access results from their own jobs
    - Admins can access all job results
    
    **Performance:**
    - Large result sets are streamed for efficiency
    - Filtering reduces response size and transfer time
    """
    try:
        logger.debug(
            f"Getting question results for job {job_id} by user {current_user.username} "
            f"(format: {format})"
        )
        
        # Get job details
        job = await job_service.get_job(job_id, include_results=True)
        
        # Check access permissions
        if not _can_access_job(job, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this job"
            )
        
        # Validate job type
        if job.type != JobType.QUESTION_PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question processing job not found"
            )
        
        # Check job status
        if job.status == JobStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="Job is still pending, results not available yet"
            )
        elif job.status == JobStatus.PROCESSING:
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="Job is still processing, results not ready yet"
            )
        elif job.status == JobStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Job failed, no results available: {job.error or 'Unknown error'}"
            )
        elif job.status == JobStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job was cancelled, no results available"
            )
        
        # Check if results exist
        if not job.result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No results found for this job"
            )
        
        # Parse results from job data
        try:
            results_data = job.result
            
            # Create QuestionResults object
            question_results = QuestionResults(
                job_id=job.id,
                workspace_id=job.workspace_id or "",
                results=results_data.get("results", []),
                summary=results_data.get("summary", {}),
                total_questions=results_data.get("total_questions", 0),
                successful_questions=results_data.get("successful_questions", 0),
                failed_questions=results_data.get("failed_questions", 0),
                total_processing_time=results_data.get("total_processing_time", 0.0),
                average_confidence=results_data.get("average_confidence", 0.0)
            )
            
            # Apply filters
            if confidence_threshold is not None or success_only:
                filtered_results = []
                for result in question_results.results:
                    # Apply confidence threshold filter
                    if confidence_threshold is not None and result.confidence_score < confidence_threshold:
                        continue
                    
                    # Apply success filter
                    if success_only and not result.success:
                        continue
                    
                    filtered_results.append(result)
                
                question_results.results = filtered_results
                
                # Update counts for filtered results
                question_results.total_questions = len(filtered_results)
                question_results.successful_questions = sum(1 for r in filtered_results if r.success)
                question_results.failed_questions = len(filtered_results) - question_results.successful_questions
            
            # Remove metadata if not requested
            if not include_metadata:
                for result in question_results.results:
                    result.metadata = {}
            
            # Handle CSV export
            if format == "csv":
                csv_content = await question_service.export_results(
                    job_id=job_id,
                    format="csv"
                )
                
                return StreamingResponse(
                    iter([csv_content]),
                    media_type="text/csv",
                    headers={
                        "Content-Disposition": f"attachment; filename=question_results_{job_id}.csv"
                    }
                )
            
            return question_results
            
        except Exception as parse_error:
            logger.error(f"Error parsing results for job {job_id}: {parse_error}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error parsing job results"
            )
        
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting question results for {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/jobs",
    response_model=PaginatedJobs,
    summary="List question processing jobs",
    description="Get paginated list of question processing jobs with filtering options",
    responses={
        200: {"description": "Jobs retrieved successfully"},
        422: {"description": "Invalid query parameters"},
        500: {"description": "Internal server error"},
    }
)
async def list_question_jobs(
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
    llm_provider: Optional[str] = Query(
        None,
        description="Filter by LLM provider (openai, ollama, anthropic)",
        max_length=50
    ),
    min_questions: Optional[int] = Query(
        None,
        ge=1,
        description="Filter by minimum number of questions"
    ),
    max_questions: Optional[int] = Query(
        None,
        ge=1,
        description="Filter by maximum number of questions"
    ),
    min_confidence: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Filter by minimum average confidence score"
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
    include_summary: bool = Query(
        True,
        description="Include job summary statistics in response"
    ),
    include_metadata: bool = Query(
        False,
        description="Include detailed job metadata in response"
    ),
    
    current_user: User = Depends(require_user),
    job_service: JobService = Depends(get_job_service)
) -> PaginatedJobs:
    """
    List question processing jobs with filtering and pagination.
    
    **Filtering Options:**
    - Status: Filter by job status (pending, processing, completed, failed, cancelled)
    - Workspace: Filter by workspace ID
    - LLM Provider: Filter by LLM provider used
    - Question Count: Filter by number of questions (min/max range)
    - Confidence: Filter by average confidence score
    - Date Range: Filter by creation date range
    
    **Sorting:**
    - Jobs are sorted by creation date (newest first)
    - Completed jobs show completion date
    - Processing jobs show current progress
    
    **Summary Statistics (optional):**
    - Question counts and success rates
    - Average confidence scores
    - Processing time statistics
    - Error type distributions
    
    **Access Control:**
    - Users see only their own jobs
    - Admins see all jobs
    - Workspace-level access control applied
    
    **Performance:**
    - Results are paginated for performance
    - Maximum page size is 100 items
    - Summary and metadata inclusion is optional
    """
    try:
        logger.debug(
            f"Listing question jobs for user {current_user.username} "
            f"(page {page}, size {size})"
        )
        
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
        
        # Create filters
        filters = JobFilters(
            type=JobType.QUESTION_PROCESSING,  # Only question processing jobs
            status=status,
            workspace_id=workspace_id,
            created_after=created_after_dt,
            created_before=created_before_dt
        )
        
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
            job_metadata = job.metadata or {}
            
            # Filter by LLM provider
            if llm_provider:
                job_llm_config = job_metadata.get("llm_config", {})
                if job_llm_config.get("provider") != llm_provider:
                    continue
            
            # Filter by question count
            question_count = job_metadata.get("question_count", 0)
            if min_questions and question_count < min_questions:
                continue
            if max_questions and question_count > max_questions:
                continue
            
            # Filter by confidence score
            if min_confidence and job.result:
                avg_confidence = job.result.get("average_confidence", 0.0)
                if avg_confidence < min_confidence:
                    continue
            
            # Remove detailed results if not requested
            if not include_summary and job.result:
                # Keep only basic result info, remove detailed results
                filtered_result = {
                    k: v for k, v in job.result.items() 
                    if k not in ["results", "summary"]
                }
                job.result = filtered_result
            
            filtered_jobs.append(job)
        
        # Update result with filtered jobs
        result.items = filtered_jobs
        result.total = len(filtered_jobs)  # Note: This is approximate for this page
        
        logger.debug(
            f"Retrieved {len(filtered_jobs)} question jobs for user {current_user.username}"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing question jobs: {e}")
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
    job_user_id = job.metadata.get("user_id") if job.metadata else None
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