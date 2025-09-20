"""Job repository for database operations."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sqlalchemy_models import JobModel, WorkspaceModel, QuestionResultModel
from app.models.pydantic_models import (
    JobCreate, 
    JobUpdate, 
    JobStatus, 
    JobType, 
    JobFilters,
    PaginationParams,
    PaginatedJobs,
    Job
)
from app.repositories.base import BaseRepository, RepositoryError, NotFoundError

logger = logging.getLogger(__name__)


class JobRepository(BaseRepository[JobModel, JobCreate, JobUpdate]):
    """Repository for job database operations."""
    
    def __init__(self, session: AsyncSession):
        """Initialize job repository.
        
        Args:
            session: Database session
        """
        super().__init__(JobModel, session)
    
    def _add_relationship_loading(self, query):
        """Add relationship loading for job queries.
        
        Args:
            query: SQLAlchemy query
            
        Returns:
            Query with relationship loading options
        """
        return query.options(
            selectinload(JobModel.workspace),
            selectinload(JobModel.question_results)
        )
    
    async def create_job(
        self, 
        job_type: JobType, 
        workspace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> JobModel:
        """Create a new job.
        
        Args:
            job_type: Type of job
            workspace_id: Associated workspace ID
            metadata: Additional job metadata
            
        Returns:
            Created job model
            
        Raises:
            RepositoryError: If job creation fails
        """
        try:
            job_create = JobCreate(
                type=job_type,
                workspace_id=workspace_id,
                metadata=metadata or {}
            )
            
            job = await self.create(job_create)
            
            self.logger.info(
                f"Created job {job.id} of type {job_type} "
                f"for workspace {workspace_id}"
            )
            
            return job
            
        except Exception as e:
            self.logger.error(f"Failed to create job: {e}")
            raise RepositoryError(f"Failed to create job: {str(e)}")
    
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> JobModel:
        """Update job status and related fields.
        
        Args:
            job_id: Job ID
            status: New job status
            progress: Job progress percentage (0-100)
            result: Job result data
            error: Error message if failed
            metadata: Additional metadata to merge
            
        Returns:
            Updated job model
            
        Raises:
            NotFoundError: If job not found
            RepositoryError: If update fails
        """
        try:
            # Get existing job
            job = await self.get_by_id_or_raise(job_id)
            
            # Prepare update data
            update_data = {"status": status}
            
            # Set timing fields based on status
            now = datetime.utcnow()
            if status == JobStatus.PROCESSING and not job.started_at:
                update_data["started_at"] = now
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                if not job.completed_at:
                    update_data["completed_at"] = now
            
            # Update progress if provided
            if progress is not None:
                update_data["progress"] = max(0.0, min(100.0, progress))
            
            # Update result if provided
            if result is not None:
                update_data["result"] = result
            
            # Update error if provided
            if error is not None:
                update_data["error"] = error
            
            # Merge metadata if provided
            if metadata is not None:
                current_metadata = job.metadata or {}
                current_metadata.update(metadata)
                update_data["metadata"] = current_metadata
            
            # Perform update
            updated_job = await self.update(job_id, update_data)
            
            self.logger.info(
                f"Updated job {job_id} status to {status} "
                f"with progress {progress}%"
            )
            
            return updated_job
            
        except NotFoundError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to update job {job_id} status: {e}")
            raise RepositoryError(f"Failed to update job status: {str(e)}")
    
    async def get_job_with_results(self, job_id: str) -> Optional[JobModel]:
        """Get job with question results loaded.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job model with results or None if not found
        """
        try:
            query = (
                select(JobModel)
                .where(JobModel.id == job_id)
                .options(
                    selectinload(JobModel.workspace),
                    selectinload(JobModel.question_results)
                )
            )
            
            result = await self.session.execute(query)
            job = result.scalar_one_or_none()
            
            if job:
                self.logger.debug(f"Found job {job_id} with {len(job.question_results)} results")
            
            return job
            
        except Exception as e:
            self.logger.error(f"Error getting job {job_id} with results: {e}")
            raise RepositoryError(f"Failed to get job with results: {str(e)}")
    
    async def list_jobs_with_filters(
        self,
        filters: JobFilters,
        pagination: PaginationParams,
        load_relationships: bool = False
    ) -> Tuple[List[JobModel], int]:
        """List jobs with filtering and pagination.
        
        Args:
            filters: Job filter parameters
            pagination: Pagination parameters
            load_relationships: Whether to load relationships
            
        Returns:
            Tuple of (job list, total count)
        """
        try:
            # Build filter conditions
            filter_conditions = []
            
            if filters.status:
                filter_conditions.append(JobModel.status == filters.status)
            
            if filters.type:
                filter_conditions.append(JobModel.type == filters.type)
            
            if filters.workspace_id:
                filter_conditions.append(JobModel.workspace_id == filters.workspace_id)
            
            if filters.created_after:
                filter_conditions.append(JobModel.created_at >= filters.created_after)
            
            if filters.created_before:
                filter_conditions.append(JobModel.created_at <= filters.created_before)
            
            # Build base queries
            query = select(JobModel)
            count_query = select(func.count(JobModel.id))
            
            # Apply filters
            if filter_conditions:
                filter_clause = and_(*filter_conditions)
                query = query.where(filter_clause)
                count_query = count_query.where(filter_clause)
            
            # Add relationship loading if requested
            if load_relationships:
                query = query.options(
                    selectinload(JobModel.workspace),
                    selectinload(JobModel.question_results)
                )
            
            # Apply ordering (newest first)
            query = query.order_by(desc(JobModel.created_at))
            
            # Apply pagination
            query = query.offset(pagination.offset).limit(pagination.size)
            
            # Execute queries
            result = await self.session.execute(query)
            jobs = result.scalars().all()
            
            count_result = await self.session.execute(count_query)
            total_count = count_result.scalar()
            
            self.logger.debug(
                f"Listed {len(jobs)} jobs (page {pagination.page}, total {total_count})"
            )
            
            return list(jobs), total_count
            
        except Exception as e:
            self.logger.error(f"Error listing jobs with filters: {e}")
            raise RepositoryError(f"Failed to list jobs: {str(e)}")
    
    async def get_jobs_by_workspace(
        self,
        workspace_id: str,
        status: Optional[JobStatus] = None,
        limit: Optional[int] = None
    ) -> List[JobModel]:
        """Get jobs for a specific workspace.
        
        Args:
            workspace_id: Workspace ID
            status: Optional status filter
            limit: Optional result limit
            
        Returns:
            List of job models
        """
        try:
            query = select(JobModel).where(JobModel.workspace_id == workspace_id)
            
            if status:
                query = query.where(JobModel.status == status)
            
            # Order by creation date (newest first)
            query = query.order_by(desc(JobModel.created_at))
            
            if limit:
                query = query.limit(limit)
            
            result = await self.session.execute(query)
            jobs = result.scalars().all()
            
            self.logger.debug(
                f"Found {len(jobs)} jobs for workspace {workspace_id} "
                f"with status {status}"
            )
            
            return list(jobs)
            
        except Exception as e:
            self.logger.error(f"Error getting jobs for workspace {workspace_id}: {e}")
            raise RepositoryError(f"Failed to get workspace jobs: {str(e)}")
    
    async def get_active_jobs(self, job_type: Optional[JobType] = None) -> List[JobModel]:
        """Get currently active (processing) jobs.
        
        Args:
            job_type: Optional job type filter
            
        Returns:
            List of active job models
        """
        try:
            query = select(JobModel).where(
                JobModel.status.in_([JobStatus.PENDING, JobStatus.PROCESSING])
            )
            
            if job_type:
                query = query.where(JobModel.type == job_type)
            
            # Order by creation date (oldest first for processing queue)
            query = query.order_by(JobModel.created_at)
            
            result = await self.session.execute(query)
            jobs = result.scalars().all()
            
            self.logger.debug(f"Found {len(jobs)} active jobs of type {job_type}")
            
            return list(jobs)
            
        except Exception as e:
            self.logger.error(f"Error getting active jobs: {e}")
            raise RepositoryError(f"Failed to get active jobs: {str(e)}")
    
    async def cleanup_old_jobs(self, older_than_days: int) -> int:
        """Clean up old completed jobs.
        
        Args:
            older_than_days: Delete jobs older than this many days
            
        Returns:
            Number of deleted jobs
            
        Raises:
            RepositoryError: If cleanup fails
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
            
            # Only delete completed, failed, or cancelled jobs
            completed_statuses = [
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED
            ]
            
            # Count jobs to be deleted
            count_query = (
                select(func.count(JobModel.id))
                .where(
                    and_(
                        JobModel.status.in_(completed_statuses),
                        JobModel.completed_at < cutoff_date
                    )
                )
            )
            
            count_result = await self.session.execute(count_query)
            jobs_to_delete = count_result.scalar()
            
            if jobs_to_delete == 0:
                self.logger.debug("No old jobs to clean up")
                return 0
            
            # Delete old jobs (cascade will handle related records)
            delete_query = (
                select(JobModel.id)
                .where(
                    and_(
                        JobModel.status.in_(completed_statuses),
                        JobModel.completed_at < cutoff_date
                    )
                )
            )
            
            result = await self.session.execute(delete_query)
            job_ids = [row[0] for row in result.fetchall()]
            
            # Use bulk delete from base repository
            deleted_count = await self.bulk_delete(job_ids)
            
            self.logger.info(
                f"Cleaned up {deleted_count} old jobs "
                f"(older than {older_than_days} days)"
            )
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old jobs: {e}")
            raise RepositoryError(f"Failed to cleanup old jobs: {str(e)}")
    
    async def get_job_statistics(
        self,
        workspace_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get job statistics for the specified period.
        
        Args:
            workspace_id: Optional workspace filter
            days: Number of days to include in statistics
            
        Returns:
            Dictionary with job statistics
        """
        try:
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Build base query
            base_query = select(JobModel).where(JobModel.created_at >= since_date)
            
            if workspace_id:
                base_query = base_query.where(JobModel.workspace_id == workspace_id)
            
            # Get total count
            total_query = select(func.count(JobModel.id)).select_from(base_query.subquery())
            total_result = await self.session.execute(total_query)
            total_jobs = total_result.scalar()
            
            # Get status counts
            status_query = (
                select(JobModel.status, func.count(JobModel.id))
                .where(JobModel.created_at >= since_date)
                .group_by(JobModel.status)
            )
            
            if workspace_id:
                status_query = status_query.where(JobModel.workspace_id == workspace_id)
            
            status_result = await self.session.execute(status_query)
            status_counts = dict(status_result.fetchall())
            
            # Get type counts
            type_query = (
                select(JobModel.type, func.count(JobModel.id))
                .where(JobModel.created_at >= since_date)
                .group_by(JobModel.type)
            )
            
            if workspace_id:
                type_query = type_query.where(JobModel.workspace_id == workspace_id)
            
            type_result = await self.session.execute(type_query)
            type_counts = dict(type_result.fetchall())
            
            # Calculate average processing time for completed jobs
            avg_time_query = (
                select(func.avg(
                    func.extract('epoch', JobModel.completed_at - JobModel.started_at)
                ))
                .where(
                    and_(
                        JobModel.created_at >= since_date,
                        JobModel.status == JobStatus.COMPLETED,
                        JobModel.started_at.isnot(None),
                        JobModel.completed_at.isnot(None)
                    )
                )
            )
            
            if workspace_id:
                avg_time_query = avg_time_query.where(JobModel.workspace_id == workspace_id)
            
            avg_time_result = await self.session.execute(avg_time_query)
            avg_processing_time = avg_time_result.scalar() or 0.0
            
            statistics = {
                "period_days": days,
                "workspace_id": workspace_id,
                "total_jobs": total_jobs,
                "status_counts": status_counts,
                "type_counts": type_counts,
                "average_processing_time_seconds": float(avg_processing_time),
                "success_rate": (
                    status_counts.get(JobStatus.COMPLETED, 0) / total_jobs * 100
                    if total_jobs > 0 else 0.0
                )
            }
            
            self.logger.debug(
                f"Generated job statistics for {days} days "
                f"(workspace: {workspace_id}): {total_jobs} total jobs"
            )
            
            return statistics
            
        except Exception as e:
            self.logger.error(f"Error getting job statistics: {e}")
            raise RepositoryError(f"Failed to get job statistics: {str(e)}")
    
    async def cancel_job(self, job_id: str, reason: Optional[str] = None) -> JobModel:
        """Cancel a pending or processing job.
        
        Args:
            job_id: Job ID to cancel
            reason: Optional cancellation reason
            
        Returns:
            Updated job model
            
        Raises:
            NotFoundError: If job not found
            RepositoryError: If job cannot be cancelled or update fails
        """
        try:
            # Get existing job
            job = await self.get_by_id_or_raise(job_id)
            
            # Check if job can be cancelled
            if job.status not in [JobStatus.PENDING, JobStatus.PROCESSING]:
                raise RepositoryError(
                    f"Job {job_id} cannot be cancelled (status: {job.status})"
                )
            
            # Update job status to cancelled
            error_message = f"Job cancelled"
            if reason:
                error_message += f": {reason}"
            
            updated_job = await self.update_job_status(
                job_id=job_id,
                status=JobStatus.CANCELLED,
                progress=0.0,
                error=error_message
            )
            
            self.logger.info(f"Cancelled job {job_id}: {reason}")
            
            return updated_job
            
        except NotFoundError:
            raise
        except RepositoryError:
            raise
        except Exception as e:
            self.logger.error(f"Error cancelling job {job_id}: {e}")
            raise RepositoryError(f"Failed to cancel job: {str(e)}")
    
    async def get_job_queue_position(self, job_id: str) -> Optional[int]:
        """Get the queue position of a pending job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Queue position (1-based) or None if job is not pending
        """
        try:
            # Get the job
            job = await self.get_by_id(job_id)
            if not job or job.status != JobStatus.PENDING:
                return None
            
            # Count jobs created before this one that are still pending
            query = (
                select(func.count(JobModel.id))
                .where(
                    and_(
                        JobModel.status == JobStatus.PENDING,
                        JobModel.created_at < job.created_at
                    )
                )
            )
            
            result = await self.session.execute(query)
            position = result.scalar() + 1  # 1-based position
            
            self.logger.debug(f"Job {job_id} is at queue position {position}")
            
            return position
            
        except Exception as e:
            self.logger.error(f"Error getting queue position for job {job_id}: {e}")
            raise RepositoryError(f"Failed to get queue position: {str(e)}")