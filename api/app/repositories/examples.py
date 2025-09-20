"""Examples of repository usage patterns."""

from typing import Optional, Dict, Any
from datetime import datetime

from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository
from app.models.pydantic_models import JobType, JobStatus, JobFilters, PaginationParams


class RepositoryService:
    """Example service showing repository usage patterns."""
    
    def __init__(self, job_repo: JobRepository, cache_repo: CacheRepository):
        """Initialize service with repositories.
        
        Args:
            job_repo: Job repository instance
            cache_repo: Cache repository instance
        """
        self.job_repo = job_repo
        self.cache_repo = cache_repo
    
    async def create_and_cache_job(
        self, 
        job_type: JobType, 
        workspace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a job and cache its initial state.
        
        Args:
            job_type: Type of job to create
            workspace_id: Associated workspace ID
            metadata: Job metadata
            
        Returns:
            Created job ID
        """
        # Create job in database
        job = await self.job_repo.create_job(
            job_type=job_type,
            workspace_id=workspace_id,
            metadata=metadata
        )
        
        # Cache job data for quick access
        cache_key = f"job:{job.id}"
        job_data = {
            "id": job.id,
            "type": job.type.value,
            "status": job.status.value,
            "workspace_id": job.workspace_id,
            "created_at": job.created_at.isoformat(),
            "metadata": job.metadata
        }
        
        # Cache for 1 hour
        await self.cache_repo.set(cache_key, job_data, ttl=3600)
        
        # Update workspace job count cache
        if workspace_id:
            workspace_jobs_key = f"workspace:{workspace_id}:job_count"
            await self.cache_repo.increment(workspace_jobs_key)
        
        return job.id
    
    async def get_job_with_cache(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job data with caching.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job data or None if not found
        """
        cache_key = f"job:{job_id}"
        
        # Try cache first
        cached_data = await self.cache_repo.get(cache_key)
        if cached_data:
            return cached_data
        
        # Fall back to database
        job = await self.job_repo.get_by_id(job_id)
        if not job:
            return None
        
        # Cache the result
        job_data = {
            "id": job.id,
            "type": job.type.value,
            "status": job.status.value,
            "workspace_id": job.workspace_id,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "progress": job.progress,
            "metadata": job.metadata
        }
        
        await self.cache_repo.set(cache_key, job_data, ttl=3600)
        return job_data
    
    async def update_job_with_cache_invalidation(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update job and invalidate related cache entries.
        
        Args:
            job_id: Job ID
            status: New job status
            progress: Job progress
            result: Job result data
            
        Returns:
            True if update successful
        """
        try:
            # Update job in database
            updated_job = await self.job_repo.update_job_status(
                job_id=job_id,
                status=status,
                progress=progress,
                result=result
            )
            
            # Invalidate job cache
            cache_key = f"job:{job_id}"
            await self.cache_repo.delete(cache_key)
            
            # Invalidate workspace-related caches if needed
            if updated_job.workspace_id:
                workspace_pattern = f"workspace:{updated_job.workspace_id}:*"
                await self.cache_repo.invalidate_pattern(workspace_pattern)
            
            # Invalidate job list caches
            await self.cache_repo.invalidate_pattern("jobs:list:*")
            
            return True
            
        except Exception:
            return False
    
    async def get_workspace_job_stats(self, workspace_id: str) -> Dict[str, Any]:
        """Get workspace job statistics with caching.
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            Job statistics
        """
        cache_key = f"workspace:{workspace_id}:job_stats"
        
        # Use cache with TTL pattern
        async def generate_stats():
            return await self.job_repo.get_job_statistics(
                workspace_id=workspace_id,
                days=30
            )
        
        # Cache for 5 minutes
        return await self.cache_repo.cache_with_ttl(
            key=cache_key,
            value_factory=generate_stats,
            ttl=300
        )
    
    async def cleanup_old_data(self, days: int = 7) -> Dict[str, int]:
        """Clean up old jobs and related cache entries.
        
        Args:
            days: Delete data older than this many days
            
        Returns:
            Cleanup statistics
        """
        # Clean up old jobs from database
        deleted_jobs = await self.job_repo.cleanup_old_jobs(days)
        
        # Clean up related cache entries
        # This is a simple approach - in production you might want more sophisticated cache management
        job_cache_keys = await self.cache_repo.get_keys("job:*")
        deleted_cache_entries = 0
        
        if job_cache_keys:
            deleted_cache_entries = await self.cache_repo.delete_many(job_cache_keys)
        
        # Clean up workspace caches
        workspace_cache_keys = await self.cache_repo.get_keys("workspace:*")
        if workspace_cache_keys:
            deleted_cache_entries += await self.cache_repo.delete_many(workspace_cache_keys)
        
        return {
            "deleted_jobs": deleted_jobs,
            "deleted_cache_entries": deleted_cache_entries
        }
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get system health including repository status.
        
        Returns:
            System health information
        """
        # Check cache health
        cache_healthy = await self.cache_repo.health_check()
        cache_stats = await self.cache_repo.get_cache_stats()
        
        # Get job statistics
        try:
            job_stats = await self.job_repo.get_job_statistics(days=1)
            db_healthy = True
        except Exception:
            job_stats = {}
            db_healthy = False
        
        # Get active jobs count
        try:
            active_jobs = await self.job_repo.get_active_jobs()
            active_job_count = len(active_jobs)
        except Exception:
            active_job_count = -1
        
        return {
            "database": {
                "healthy": db_healthy,
                "active_jobs": active_job_count,
                "daily_stats": job_stats
            },
            "cache": {
                "healthy": cache_healthy,
                "backend_type": cache_stats.get("backend_type"),
                "total_keys": cache_stats.get("total_keys", 0)
            },
            "overall_healthy": cache_healthy and db_healthy
        }