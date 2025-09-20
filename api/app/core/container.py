"""Dependency injection container for the application."""

import logging
from typing import Optional
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.database import DatabaseManager
from app.integrations.anythingllm_client import AnythingLLMClient
from app.integrations.storage_client import StorageClient
from app.integrations.storage_factory import StorageFactory
from app.integrations.file_validator import FileValidator
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository
from app.services.document_service import DocumentService
from app.services.job_service import JobService
from app.services.question_service import QuestionService
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)


class Container:
    """Dependency injection container."""
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize container with settings.
        
        Args:
            settings: Application settings (uses default if not provided)
        """
        self.settings = settings or get_settings()
        self._db_manager: Optional[DatabaseManager] = None
        self._anythingllm_client: Optional[AnythingLLMClient] = None
        self._storage_client: Optional[StorageClient] = None
        self._file_validator: Optional[FileValidator] = None
        
        logger.info("Dependency injection container initialized")
    
    @property
    def db_manager(self) -> DatabaseManager:
        """Get database manager (singleton)."""
        if self._db_manager is None:
            self._db_manager = DatabaseManager()
        return self._db_manager
    
    @property
    def anythingllm_client(self) -> AnythingLLMClient:
        """Get AnythingLLM client (singleton)."""
        if self._anythingllm_client is None:
            self._anythingllm_client = AnythingLLMClient(self.settings)
        return self._anythingllm_client
    
    @property
    def storage_client(self) -> StorageClient:
        """Get storage client (singleton)."""
        if self._storage_client is None:
            self._storage_client = StorageFactory.create_storage_client(self.settings)
        return self._storage_client
    
    @property
    def file_validator(self) -> FileValidator:
        """Get file validator (singleton)."""
        if self._file_validator is None:
            self._file_validator = FileValidator.create_from_settings(self.settings)
        return self._file_validator
    
    def get_job_repository(self, session) -> JobRepository:
        """Get job repository instance.
        
        Args:
            session: Database session
            
        Returns:
            JobRepository instance
        """
        return JobRepository(session)
    
    def get_cache_repository(self, redis_client=None) -> CacheRepository:
        """Get cache repository instance.
        
        Args:
            redis_client: Optional Redis client
            
        Returns:
            CacheRepository instance
        """
        if redis_client is None:
            redis_client = self.db_manager.get_redis()
        return CacheRepository(redis_client)
    
    def get_document_service(self, job_repository: JobRepository) -> DocumentService:
        """Get document service instance.
        
        Args:
            job_repository: Job repository instance
            
        Returns:
            DocumentService instance
        """
        return DocumentService(
            settings=self.settings,
            job_repository=job_repository,
            anythingllm_client=self.anythingllm_client,
            storage_client=self.storage_client,
            file_validator=self.file_validator
        )
    
    def get_job_service(
        self, 
        job_repository: JobRepository,
        cache_repository: Optional[CacheRepository] = None
    ) -> JobService:
        """Get job service instance.
        
        Args:
            job_repository: Job repository instance
            cache_repository: Optional cache repository instance
            
        Returns:
            JobService instance
        """
        return JobService(
            job_repository=job_repository,
            cache_repository=cache_repository,
            settings=self.settings
        )
    
    def get_workspace_service(
        self, 
        job_repository: JobRepository,
        cache_repository: Optional[CacheRepository] = None
    ) -> WorkspaceService:
        """Get workspace service instance.
        
        Args:
            job_repository: Job repository instance
            cache_repository: Optional cache repository instance
            
        Returns:
            WorkspaceService instance
        """
        return WorkspaceService(
            settings=self.settings,
            anythingllm_client=self.anythingllm_client,
            job_repository=job_repository,
            cache_repository=cache_repository
        )
    
    def get_question_service(
        self,
        job_repository: JobRepository,
        cache_repository: Optional[CacheRepository] = None
    ) -> QuestionService:
        """Get question service instance.
        
        Args:
            job_repository: Job repository instance
            cache_repository: Optional cache repository instance (not used by QuestionService currently)
            
        Returns:
            QuestionService instance
        """
        return QuestionService(
            settings=self.settings,
            job_repository=job_repository,
            anythingllm_client=self.anythingllm_client
        )


# Global container instance
_container: Optional[Container] = None


def get_container() -> Container:
    """Get global container instance."""
    global _container
    if _container is None:
        _container = Container()
    return _container


def set_container(container: Container) -> None:
    """Set global container instance (for testing)."""
    global _container
    _container = container