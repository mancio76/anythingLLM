"""Authentication middleware for JWT and API key validation."""

from typing import Callable, Optional

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import get_jwt_handler, get_api_key_handler, User
from app.core.config import get_settings


class AuthenticationError(HTTPException):
    """Authentication error exception."""
    
    def __init__(self, detail: str = "Authentication required"):
        """Initialize authentication error.
        
        Args:
            detail: Error detail message
        """
        super().__init__(
            status_code=401,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


class AuthorizationError(HTTPException):
    """Authorization error exception."""
    
    def __init__(self, detail: str = "Insufficient permissions"):
        """Initialize authorization error.
        
        Args:
            detail: Error detail message
        """
        super().__init__(status_code=403, detail=detail)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authentication middleware for JWT and API key validation."""
    
    def __init__(self, app):
        """Initialize authentication middleware.
        
        Args:
            app: FastAPI application
        """
        super().__init__(app)
        self.jwt_handler = get_jwt_handler()
        self.api_key_handler = get_api_key_handler()
        
        # Paths that don't require authentication
        self.public_paths = {
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/api/v1/health",
            "/api/v1/health/detailed",
            "/api/v1/auth/login",
            "/api/v1/auth/test-api-key",
            "/api/v1/auth/status",
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Authenticate requests and set user context."""
        
        # Skip authentication for public paths
        if self._is_public_path(request.url.path):
            return await call_next(request)
        
        # Try to authenticate user
        user = await self._authenticate_request(request)
        
        if user:
            # Set user in request state for downstream use
            request.state.user = user
        else:
            # Authentication required but not provided or invalid
            raise AuthenticationError()
        
        # Process request
        response = await call_next(request)
        
        return response
    
    async def _authenticate_request(self, request: Request) -> Optional[User]:
        """Authenticate request using JWT or API key.
        
        Args:
            request: FastAPI request
            
        Returns:
            Authenticated user or None
        """
        settings = get_settings()
        
        # Try JWT authentication first
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            token_data = self.jwt_handler.verify_token(token)
            
            if token_data:
                # In a real implementation, you would fetch user from database
                # For now, create a basic user from token data
                return User(
                    id=token_data.sub,
                    username=token_data.sub,
                    is_active=True,
                    roles=[]
                )
        
        # Try API key authentication
        api_key = request.headers.get(settings.api_key_header)
        if api_key:
            user = self.api_key_handler.verify_api_key(api_key)
            if user and user.is_active:
                return user
        
        return None
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require authentication).
        
        Args:
            path: Request path
            
        Returns:
            True if path is public, False otherwise
        """
        # Check exact matches
        if path in self.public_paths:
            return True
        
        # Check path prefixes
        for public_path in self.public_paths:
            if path.startswith(public_path):
                return True
        
        return False


def require_roles(*required_roles: str):
    """Decorator to require specific roles for endpoint access.
    
    Args:
        required_roles: Required roles for access
        
    Returns:
        Decorator function
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = getattr(request.state, "user", None)
            
            if not user:
                raise AuthenticationError()
            
            if required_roles and not any(role in user.roles for role in required_roles):
                raise AuthorizationError(
                    f"Required roles: {', '.join(required_roles)}"
                )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def get_current_user(request: Request) -> Optional[User]:
    """Get current authenticated user from request.
    
    Args:
        request: FastAPI request
        
    Returns:
        Current user or None
    """
    return getattr(request.state, "user", None)


def require_authentication(request: Request) -> User:
    """Require authentication and return current user.
    
    Args:
        request: FastAPI request
        
    Returns:
        Current authenticated user
        
    Raises:
        AuthenticationError: If user is not authenticated
    """
    user = get_current_user(request)
    if not user:
        raise AuthenticationError()
    return user