"""FastAPI dependencies for authentication, authorization, and service injection."""

from typing import Optional

from fastapi import Depends, Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.security import User, get_jwt_handler, get_api_key_handler
from app.core.config import get_settings
from app.core.container import get_container
from app.core.database import get_db_session, get_redis
from app.repositories.job_repository import JobRepository
from app.repositories.cache_repository import CacheRepository
from app.services.document_service import DocumentService
from app.services.job_service import JobService
from app.services.question_service import QuestionService
from app.services.workspace_service import WorkspaceService


# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_optional(request: Request) -> Optional[User]:
    """Get current user from request state (optional).
    
    Args:
        request: FastAPI request
        
    Returns:
        Current user or None if not authenticated
    """
    return getattr(request.state, "user", None)


async def get_current_user(request: Request) -> User:
    """Get current user from request state (required).
    
    Args:
        request: FastAPI request
        
    Returns:
        Current authenticated user
        
    Raises:
        HTTPException: If user is not authenticated
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Current active user
        
    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_roles(*roles: str):
    """Create a dependency that requires specific roles.
    
    Args:
        roles: Required roles
        
    Returns:
        FastAPI dependency function
    """
    async def check_roles(current_user: User = Depends(get_current_active_user)) -> User:
        """Check if user has required roles.
        
        Args:
            current_user: Current authenticated user
            
        Returns:
            Current user if authorized
            
        Raises:
            HTTPException: If user doesn't have required roles
        """
        if roles and not any(role in current_user.roles for role in roles):
            raise HTTPException(
                status_code=403,
                detail=f"Required roles: {', '.join(roles)}"
            )
        return current_user
    
    return check_roles


async def authenticate_with_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Optional[User]:
    """Authenticate user with JWT token.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        Authenticated user or None
    """
    if not credentials:
        return None
    
    jwt_handler = get_jwt_handler()
    token_data = jwt_handler.verify_token(credentials.credentials)
    
    if not token_data:
        return None
    
    # In a real implementation, you would fetch user from database
    return User(
        id=token_data.sub,
        username=token_data.sub,
        is_active=True,
        roles=[]
    )


async def authenticate_with_api_key(request: Request) -> Optional[User]:
    """Authenticate user with API key.
    
    Args:
        request: FastAPI request
        
    Returns:
        Authenticated user or None
    """
    settings = get_settings()
    api_key = request.headers.get(settings.api_key_header)
    
    if not api_key:
        return None
    
    api_key_handler = get_api_key_handler()
    user = api_key_handler.verify_api_key(api_key)
    
    return user if user and user.is_active else None


# Repository Dependencies

async def get_job_repository(
    session: AsyncSession = Depends(get_db_session)
) -> JobRepository:
    """Get job repository dependency."""
    container = get_container()
    return container.get_job_repository(session)


async def get_cache_repository(
    redis_client: Optional[redis.Redis] = Depends(get_redis)
) -> CacheRepository:
    """Get cache repository dependency."""
    container = get_container()
    return container.get_cache_repository(redis_client)


# Service Dependencies

async def get_document_service(
    job_repository: JobRepository = Depends(get_job_repository)
) -> DocumentService:
    """Get document service dependency."""
    container = get_container()
    return container.get_document_service(job_repository)


async def get_job_service(
    job_repository: JobRepository = Depends(get_job_repository),
    cache_repository: CacheRepository = Depends(get_cache_repository)
) -> JobService:
    """Get job service dependency."""
    container = get_container()
    return container.get_job_service(job_repository, cache_repository)


async def get_workspace_service(
    job_repository: JobRepository = Depends(get_job_repository),
    cache_repository: CacheRepository = Depends(get_cache_repository)
) -> WorkspaceService:
    """Get workspace service dependency."""
    container = get_container()
    return container.get_workspace_service(job_repository, cache_repository)


async def get_question_service(
    job_repository: JobRepository = Depends(get_job_repository),
    cache_repository: CacheRepository = Depends(get_cache_repository)
) -> QuestionService:
    """Get question service dependency."""
    container = get_container()
    return container.get_question_service(job_repository, cache_repository)


# Admin role dependency
require_admin = require_roles("admin")

# Manager role dependency  
require_manager = require_roles("manager", "admin")

# User role dependency (any authenticated user)
require_user = get_current_active_user