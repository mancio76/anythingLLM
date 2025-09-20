"""Authentication endpoints for testing and token management."""

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.security import get_jwt_handler, get_api_key_handler, User
from app.core.dependencies import get_current_user, get_current_user_optional


router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """User response model."""
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool
    roles: list[str]


@router.post("/login", response_model=TokenResponse)
async def login(login_request: LoginRequest):
    """Login with username and password to get JWT token.
    
    This is a simplified implementation for testing purposes.
    In a real application, you would validate credentials against a database.
    """
    jwt_handler = get_jwt_handler()
    
    # Simple validation (in real app, check against database)
    if login_request.username == "admin" and login_request.password == "admin123":
        # Create token for admin user
        token = jwt_handler.create_access_token(
            subject=login_request.username,
            expires_delta=timedelta(minutes=60),
            additional_claims={"roles": ["admin"]}
        )
        
        return TokenResponse(
            access_token=token,
            expires_in=3600
        )
    elif login_request.username == "user" and login_request.password == "user123":
        # Create token for regular user
        token = jwt_handler.create_access_token(
            subject=login_request.username,
            expires_delta=timedelta(minutes=60),
            additional_claims={"roles": ["user"]}
        )
        
        return TokenResponse(
            access_token=token,
            expires_in=3600
        )
    else:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        roles=current_user.roles
    )


@router.post("/test-api-key")
async def create_test_api_key():
    """Create a test API key for development purposes."""
    api_key_handler = get_api_key_handler()
    
    # Create test API key
    test_api_key = "test-api-key-12345"
    test_user = User(
        id="test-user",
        username="test-user",
        email="test@example.com",
        is_active=True,
        roles=["user"]
    )
    
    api_key_handler.add_api_key(test_api_key, test_user)
    
    return {
        "api_key": test_api_key,
        "user": test_user.dict(),
        "usage": f"Add header: X-API-Key: {test_api_key}"
    }


@router.get("/status")
async def auth_status(current_user: Optional[User] = Depends(get_current_user_optional)):
    """Get authentication status."""
    if current_user:
        return {
            "authenticated": True,
            "user": UserResponse(
                id=current_user.id,
                username=current_user.username,
                email=current_user.email,
                is_active=current_user.is_active,
                roles=current_user.roles
            )
        }
    else:
        return {"authenticated": False}


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout current user.
    
    Note: JWT tokens are stateless, so logout is mainly for client-side cleanup.
    In a real implementation, you might maintain a token blacklist.
    """
    return {"message": "Logged out successfully"}