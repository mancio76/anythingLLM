"""Job management service for tracking and managing long-running operations."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.pydantic_models import (
    Job,
    JobCreate,
    JobFilters,
    JobResponse,
    JobStatus,
    JobType,
    JobUpdate,
    PaginatedJobs,
    PaginationParams,
)
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository

logger = get_logger(__name__)


class JobServiceError(Exception):
    """Job service error."""
    pass


class JobNotFoundError(JobServiceError):
    """Job not found error."""
    pass


class JobCancellationError(JobServiceError):
    """Job cancellation error."""
    pass


class ResourceAllocationError(JobServiceError):
    """Resource allocation error."""
    pass


class JobService:
    """Service for managing jobs, progress tracking, and resource allocation."""
    
    def __init__(
        self,
        job_repository: JobRepository,
        cache_repository: Optional[CacheRepository] = None,
        settings: Optional[Settings] = None
    ):
        """Initialize job service.
        
        Args:
            job_repository: Job repository for database operations
            cache_repository: Optional cache repository for performance
            settings: Application settings
        """
        self.job_repository = job_repository
        self.cache_repository = cache_repository
        self.settings = settings or Settings()
        self.logger = logger
        
        # Job management configuration
        self.max_concurrent_jobs = getattr(self.settings, 'max_concurrent_jobs', 5)
        self.job_cleanup_days = getattr(self.settings, 'job_cleanup_days', 7)
        self.default_job_timeout = getattr(self.settings, 'default_job_timeout', 3600)  # 1 hour
        
        # Resource allocation tracking
        self._active_jobs_cache_key = "active_jobs_count"
        self._job_queue_cache_key = "job_queue"
        
        self.logger.info(
            f"JobService initialized with max_concurrent_jobs={self.max_concurrent_jobs}, "
            f"cleanup_days={self.job_cleanup_days}"
        )
    
    async def create_job(
        self,
        job_type: JobType,
        workspace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        estimated_duration: Optional[int] = None
    ) -> JobResponse:
        """Create a new job with resource allocation.
        
        Args:
            job_type: Type of job to create
            workspace_id: Associated workspace ID
            metadata: Additional job metadata
            estimated_duration: Estimated duration in seconds
            
        Returns:
            Job response with creation details
            
        Raises:
            ResourceAllocationError: If resource limits exceeded
            JobServiceError: If job creation fails
        """
        try:
            # Check resource allocation
            await self._check_resource_allocation(job_type)
            
            # Prepare metadata with service information
            job_metadata = metadata or {}
            job_metadata.update({
                "service_version": "1.0.0",
                "estimated_duration": estimated_duration or self.default_job_timeout,
                "max_concurrent_jobs": self.max_concurrent_jobs,
                "created_by_service": "JobService"
            })
            
            # Create job in database
            job_model = await self.job_repository.create_job(
                job_type=job_type,
                workspace_id=workspace_id,
                metadata=job_metadata
            )
            
            # Convert to Pydantic model
            job = Job.model_validate(job_model.__dict__)
            
            # Update resource tracking
            await self._update_resource_tracking(job.id, "created")
            
            # Calculate estimated completion
            estimated_completion = None
            if estimated_duration:
                estimated_completion = datetime.utcnow() + timedelta(seconds=estimated_duration)
            
            # Create response with links
            links = {
                "self": f"/api/v1/jobs/{job.id}",
                "status": f"/api/v1/jobs/{job.id}/status",
                "cancel": f"/api/v1/jobs/{job.id}/cancel"
            }
            
            if workspace_id:
                links["workspace"] = f"/api/v1/workspaces/{workspace_id}"
            
            response = JobResponse(
                job=job,
                links=links,
                estimated_completion=estimated_completion
            )
            
            self.logger.info(
                f"Created job {job.id} of type {job_type} "
                f"for workspace {workspace_id}"
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Failed to create job: {e}")
            if isinstance(e, (ResourceAllocationError, JobServiceError)):
                raise
            raise JobServiceError(f"Failed to create job: {str(e)}")
    
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Job:
        """Update job status with progress tracking.
        
        Args:
            job_id: Job ID to update
            status: New job status
            progress: Job progress percentage (0-100)
            result: Job result data
            error: Error message if failed
            metadata: Additional metadata to merge
            
        Returns:
            Updated job model
            
        Raises:
            JobNotFoundError: If job not found
            JobServiceError: If update fails
        """
        try:
            # Update job in database
            job_model = await self.job_repository.update_job_status(
                job_id=job_id,
                status=status,
                progress=progress,
                result=result,
                error=error,
                metadata=metadata
            )
            
            # Convert to Pydantic model
            job = Job.model_validate(job_model.__dict__)
            
            # Update resource tracking if job completed
            if job.is_completed:
                await self._update_resource_tracking(job_id, "completed")
            
            # Cache job status for quick access
            if self.cache_repository:
                cache_key = f"job_status:{job_id}"
                await self.cache_repository.set(
                    cache_key,
                    {
                        "status": status.value,
                        "progress": progress or job.progress,
                        "updated_at": job.updated_at.isoformat()
                    },
                    ttl=300  # 5 minutes
                )
            
            self.logger.info(
                f"Updated job {job_id} status to {status} "
                f"with progress {progress}%"
            )
            
            return job
            
        except Exception as e:
            self.logger.error(f"Failed to update job {job_id} status: {e}")
            if "not found" in str(e).lower():
                raise JobNotFoundError(f"Job {job_id} not found")
            raise JobServiceError(f"Failed to update job status: {str(e)}")
    
    async def get_job(self, job_id: str, include_results: bool = False) -> Job:
        """Get job by ID with optional results.
        
        Args:
            job_id: Job ID to retrieve
            include_results: Whether to include question results
            
        Returns:
            Job model
            
        Raises:
            JobNotFoundError: If job not found
        """
        try:
            # Try cache first for basic job info
            if self.cache_repository and not include_results:
                cache_key = f"job:{job_id}"
                cached_job = await self.cache_repository.get(cache_key)
                if cached_job:
                    self.logger.debug(f"Retrieved job {job_id} from cache")
                    return Job.model_validate(cached_job)
            
            # Get from database
            if include_results:
                job_model = await self.job_repository.get_job_with_results(job_id)
            else:
                job_model = await self.job_repository.get_by_id(job_id)
            
            if not job_model:
                raise JobNotFoundError(f"Job {job_id} not found")
            
            job = Job.model_validate(job_model.__dict__)
            
            # Cache for future requests
            if self.cache_repository and not include_results:
                cache_key = f"job:{job_id}"
                await self.cache_repository.set(
                    cache_key,
                    job.model_dump(),
                    ttl=300  # 5 minutes
                )
            
            return job
            
        except JobNotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to get job {job_id}: {e}")
            raise JobServiceError(f"Failed to get job: {str(e)}")
    
    async def list_jobs(
        self,
        filters: Optional[JobFilters] = None,
        pagination: Optional[PaginationParams] = None,
        include_relationships: bool = False
    ) -> PaginatedJobs:
        """List jobs with filtering and pagination.
        
        Args:
            filters: Job filter parameters
            pagination: Pagination parameters
            include_relationships: Whether to load relationships
            
        Returns:
            Paginated job results
        """
        try:
            # Set defaults
            filters = filters or JobFilters()
            pagination = pagination or PaginationParams()
            
            # Get jobs from repository
            jobs_models, total_count = await self.job_repository.list_jobs_with_filters(
                filters=filters,
                pagination=pagination,
                load_relationships=include_relationships
            )
            
            # Convert to Pydantic models
            jobs = [Job.model_validate(job.__dict__) for job in jobs_models]
            
            # Calculate pagination info
            total_pages = (total_count + pagination.size - 1) // pagination.size if total_count > 0 else 0
            
            result = PaginatedJobs(
                items=jobs,
                total=total_count,
                page=pagination.page,
                size=pagination.size,
                pages=total_pages
            )
            
            self.logger.debug(
                f"Listed {len(jobs)} jobs (page {pagination.page}, total {total_count})"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to list jobs: {e}")
            raise JobServiceError(f"Failed to list jobs: {str(e)}")
    
    async def cancel_job(self, job_id: str, reason: Optional[str] = None) -> Job:
        """Cancel a pending or processing job.
        
        Args:
            job_id: Job ID to cancel
            reason: Optional cancellation reason
            
        Returns:
            Updated job model
            
        Raises:
            JobNotFoundError: If job not found
            JobCancellationError: If job cannot be cancelled
        """
        try:
            # Cancel job in repository
            job_model = await self.job_repository.cancel_job(job_id, reason)
            
            # Convert to Pydantic model
            job = Job.model_validate(job_model.__dict__)
            
            # Update resource tracking
            await self._update_resource_tracking(job_id, "cancelled")
            
            # Clear cache
            if self.cache_repository:
                cache_key = f"job:{job_id}"
                await self.cache_repository.delete(cache_key)
            
            self.logger.info(f"Cancelled job {job_id}: {reason}")
            
            return job
            
        except Exception as e:
            self.logger.error(f"Failed to cancel job {job_id}: {e}")
            if "not found" in str(e).lower():
                raise JobNotFoundError(f"Job {job_id} not found")
            if "cannot be cancelled" in str(e).lower():
                raise JobCancellationError(str(e))
            raise JobServiceError(f"Failed to cancel job: {str(e)}")
    
    async def get_job_queue_position(self, job_id: str) -> Optional[int]:
        """Get the queue position of a pending job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Queue position (1-based) or None if job is not pending
        """
        try:
            position = await self.job_repository.get_job_queue_position(job_id)
            
            if position:
                self.logger.debug(f"Job {job_id} is at queue position {position}")
            
            return position
            
        except Exception as e:
            self.logger.error(f"Failed to get queue position for job {job_id}: {e}")
            raise JobServiceError(f"Failed to get queue position: {str(e)}")
    
    async def get_job_statistics(
        self,
        workspace_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get job statistics for monitoring and reporting.
        
        Args:
            workspace_id: Optional workspace filter
            days: Number of days to include in statistics
            
        Returns:
            Dictionary with job statistics
        """
        try:
            # Get statistics from repository
            stats = await self.job_repository.get_job_statistics(
                workspace_id=workspace_id,
                days=days
            )
            
            # Add service-level statistics
            active_jobs = await self.job_repository.get_active_jobs()
            stats["current_active_jobs"] = len(active_jobs)
            stats["max_concurrent_jobs"] = self.max_concurrent_jobs
            stats["resource_utilization"] = (
                len(active_jobs) / self.max_concurrent_jobs * 100
                if self.max_concurrent_jobs > 0 else 0.0
            )
            
            # Add queue information
            pending_jobs = [job for job in active_jobs if job.status == JobStatus.PENDING]
            stats["pending_jobs"] = len(pending_jobs)
            
            self.logger.debug(
                f"Generated job statistics for {days} days "
                f"(workspace: {workspace_id}): {stats['total_jobs']} total jobs"
            )
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to get job statistics: {e}")
            raise JobServiceError(f"Failed to get job statistics: {str(e)}")
    
    async def cleanup_old_jobs(self, older_than_days: Optional[int] = None) -> int:
        """Clean up old completed jobs.
        
        Args:
            older_than_days: Delete jobs older than this many days
                           (defaults to configured cleanup days)
            
        Returns:
            Number of deleted jobs
        """
        try:
            cleanup_days = older_than_days or self.job_cleanup_days
            
            # Perform cleanup
            deleted_count = await self.job_repository.cleanup_old_jobs(cleanup_days)
            
            # Clear related cache entries
            if self.cache_repository and deleted_count > 0:
                # Clear job list caches (they might contain deleted jobs)
                await self._clear_job_list_caches()
            
            self.logger.info(
                f"Cleaned up {deleted_count} old jobs "
                f"(older than {cleanup_days} days)"
            )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old jobs: {e}")
            raise JobServiceError(f"Failed to cleanup old jobs: {str(e)}")
    
    async def get_estimated_completion_time(
        self,
        job_id: str,
        job_type: Optional[JobType] = None
    ) -> Optional[datetime]:
        """Calculate estimated completion time for a job.
        
        Args:
            job_id: Job ID
            job_type: Job type for better estimation
            
        Returns:
            Estimated completion datetime or None if cannot estimate
        """
        try:
            # Get the job
            job = await self.get_job(job_id)
            
            # If job is already completed, return completion time
            if job.is_completed:
                return job.completed_at
            
            # If job hasn't started, estimate based on queue position and historical data
            if job.status == JobStatus.PENDING:
                queue_position = await self.get_job_queue_position(job_id)
                if queue_position:
                    # Get average processing time for this job type
                    stats = await self.job_repository.get_job_statistics(days=30)
                    avg_time = stats.get("average_processing_time_seconds", 300)  # 5 min default
                    
                    # Estimate based on queue position and average processing time
                    estimated_wait = queue_position * avg_time
                    return datetime.utcnow() + timedelta(seconds=estimated_wait)
            
            # If job is processing, estimate based on progress and elapsed time
            elif job.status == JobStatus.PROCESSING and job.started_at:
                if job.progress > 0:
                    elapsed = (datetime.utcnow() - job.started_at).total_seconds()
                    estimated_total = elapsed / (job.progress / 100.0)
                    remaining = estimated_total - elapsed
                    return datetime.utcnow() + timedelta(seconds=remaining)
                else:
                    # Use metadata estimated duration if available
                    estimated_duration = job.metadata.get("estimated_duration", 300)
                    return job.started_at + timedelta(seconds=estimated_duration)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to estimate completion time for job {job_id}: {e}")
            return None
    
    async def _check_resource_allocation(self, job_type: JobType) -> None:
        """Check if resources are available for a new job.
        
        Args:
            job_type: Type of job to check resources for
            
        Raises:
            ResourceAllocationError: If resource limits exceeded
        """
        try:
            # Get current active jobs
            active_jobs = await self.job_repository.get_active_jobs()
            
            # Check global concurrent job limit
            if len(active_jobs) >= self.max_concurrent_jobs:
                raise ResourceAllocationError(
                    f"Maximum concurrent jobs limit reached ({self.max_concurrent_jobs}). "
                    f"Currently {len(active_jobs)} active jobs."
                )
            
            # Check job type specific limits (if configured)
            type_specific_limit = getattr(
                self.settings,
                f'max_concurrent_{job_type.value}_jobs',
                None
            )
            
            if type_specific_limit:
                type_active_jobs = [
                    job for job in active_jobs 
                    if job.type == job_type
                ]
                
                if len(type_active_jobs) >= type_specific_limit:
                    raise ResourceAllocationError(
                        f"Maximum concurrent {job_type.value} jobs limit reached "
                        f"({type_specific_limit}). Currently {len(type_active_jobs)} active."
                    )
            
            self.logger.debug(
                f"Resource allocation check passed for {job_type.value}. "
                f"Active jobs: {len(active_jobs)}/{self.max_concurrent_jobs}"
            )
            
        except ResourceAllocationError:
            raise
        except Exception as e:
            self.logger.error(f"Error checking resource allocation: {e}")
            raise JobServiceError(f"Failed to check resource allocation: {str(e)}")
    
    async def _update_resource_tracking(self, job_id: str, action: str) -> None:
        """Update resource tracking information.
        
        Args:
            job_id: Job ID
            action: Action performed (created, completed, cancelled)
        """
        try:
            if not self.cache_repository:
                return
            
            # Update active jobs count
            if action == "created":
                await self.cache_repository.set(
                    f"job_tracking:{job_id}",
                    {"status": "active", "created_at": datetime.utcnow().isoformat()},
                    ttl=86400  # 24 hours
                )
            elif action in ["completed", "cancelled"]:
                await self.cache_repository.delete(f"job_tracking:{job_id}")
            
            self.logger.debug(f"Updated resource tracking for job {job_id}: {action}")
            
        except Exception as e:
            self.logger.warning(f"Failed to update resource tracking: {e}")
    
    async def _clear_job_list_caches(self) -> None:
        """Clear job list related cache entries."""
        try:
            if not self.cache_repository:
                return
            
            # Clear common job list cache patterns
            cache_patterns = [
                "job_list:*",
                "job_stats:*",
                "active_jobs:*"
            ]
            
            for pattern in cache_patterns:
                # Note: This is a simplified approach
                # In production, you might want to use Redis SCAN for pattern matching
                await self.cache_repository.delete(pattern)
            
            self.logger.debug("Cleared job list caches")
            
        except Exception as e:
            self.logger.warning(f"Failed to clear job list caches: {e}")


def create_job_service(
    job_repository: JobRepository,
    cache_repository: Optional[CacheRepository] = None,
    settings: Optional[Settings] = None
) -> JobService:
    """Create job service instance.
    
    Args:
        job_repository: Job repository instance
        cache_repository: Optional cache repository instance
        settings: Application settings
        
    Returns:
        JobService instance
    """
    return JobService(
        job_repository=job_repository,
        cache_repository=cache_repository,
        settings=settings
    )