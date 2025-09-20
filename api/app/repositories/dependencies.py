"""Repository dependencies for dependency injection."""

from typing import Optional
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.database import get_db_session, get_redis
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository


async def get_job_repository(
    session: AsyncSession = Depends(get_db_session)
) -> JobRepository:
    """Get job repository dependency.
    
    Args:
        session: Database session
        
    Returns:
        JobRepository instance
    """
    return JobRepository(session)


async def get_cache_repository(
    redis_client: Optional[redis.Redis] = Depends(get_redis)
) -> CacheRepository:
    """Get cache repository dependency.
    
    Args:
        redis_client: Optional Redis client
        
    Returns:
        CacheRepository instance
    """
    return CacheRepository(redis_client)