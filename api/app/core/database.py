"""Database configuration and connection management."""

import logging
from typing import Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, QueuePool
import redis.asyncio as redis

from app.core.config import Settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


class DatabaseManager:
    """Database connection manager."""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self.redis_client: Optional[redis.Redis] = None
    
    async def init_db(self, settings: Settings) -> None:
        """Initialize database connections."""
        logger.info("Initializing database connections")
        
        # Initialize PostgreSQL connection
        await self._init_postgresql(settings)
        
        # Initialize Redis connection if enabled
        if settings.redis_enabled:
            await self._init_redis(settings)
        
        logger.info("Database connections initialized successfully")
    
    async def _init_postgresql(self, settings: Settings) -> None:
        """Initialize PostgreSQL connection."""
        try:
            # Create async engine
            self.engine = create_async_engine(
                settings.database_url,
                poolclass=QueuePool,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
                echo=False,  # Set to True for SQL query logging
            )
            
            # Create session factory
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # Test connection
            async with self.engine.begin() as conn:
                await conn.execute("SELECT 1")
            
            logger.info("PostgreSQL connection established")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection: {e}")
            raise
    
    async def _init_redis(self, settings: Settings) -> None:
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                max_connections=settings.redis_pool_size,
                decode_responses=True,
            )
            
            # Test connection
            await self.redis_client.ping()
            
            logger.info("Redis connection established")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis connection: {e}")
            # Redis is optional, so we don't raise the exception
            self.redis_client = None
            logger.warning("Continuing without Redis support")
    
    async def close_db(self) -> None:
        """Close database connections."""
        logger.info("Closing database connections")
        
        if self.engine:
            await self.engine.dispose()
            logger.info("PostgreSQL connection closed")
        
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session context manager."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
        
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    def get_redis(self) -> Optional[redis.Redis]:
        """Get Redis client."""
        return self.redis_client


# Global database manager instance
db_manager = DatabaseManager()


async def init_db(settings: Settings) -> None:
    """Initialize database connections."""
    await db_manager.init_db(settings)


async def close_db() -> None:
    """Close database connections."""
    await db_manager.close_db()


async def get_db_session():
    """Dependency to get database session."""
    async with db_manager.get_session() as session:
        yield session


def get_redis() -> Optional[redis.Redis]:
    """Dependency to get Redis client."""
    return db_manager.get_redis()