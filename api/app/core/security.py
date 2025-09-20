"""Security utilities for authentication and authorization."""

import time
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.core.config import get_settings


class TokenData(BaseModel):
    """Token payload data."""
    sub: str  # Subject (user ID)
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    jti: str  # JWT ID
    type: str = "access"  # Token type


class User(BaseModel):
    """User model for authentication."""
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool = True
    roles: list[str] = []


class JWTHandler:
    """JWT token handler with configurable expiration."""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initialize JWT handler.
        
        Args:
            secret_key: Secret key for signing tokens
            algorithm: JWT signing algorithm
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    def create_access_token(
        self, 
        subject: str, 
        expires_delta: Optional[timedelta] = None,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new access token.
        
        Args:
            subject: Token subject (usually user ID)
            expires_delta: Token expiration time
            additional_claims: Additional claims to include
            
        Returns:
            Encoded JWT token
        """
        settings = get_settings()
        
        # Use current timestamp directly to avoid timezone issues
        current_timestamp = int(time.time())
        
        if expires_delta:
            expire_timestamp = current_timestamp + int(expires_delta.total_seconds())
        else:
            expire_timestamp = current_timestamp + (settings.jwt_expire_minutes * 60)
        
        # Create token payload
        payload = {
            "sub": subject,
            "exp": expire_timestamp,
            "iat": current_timestamp,
            "jti": f"{subject}_{current_timestamp}",
            "type": "access"
        }
        
        # Add additional claims if provided
        if additional_claims:
            payload.update(additional_claims)
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify and decode a JWT token.
        
        Args:
            token: JWT token to verify
            
        Returns:
            Token data if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return TokenData(**payload)
            
        except JWTError:
            return None
    
    def hash_password(self, password: str) -> str:
        """Hash a password.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password
        """
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            True if password matches, False otherwise
        """
        return self.pwd_context.verify(plain_password, hashed_password)


class APIKeyHandler:
    """API key authentication handler."""
    
    def __init__(self):
        """Initialize API key handler."""
        # In a real implementation, this would be loaded from database
        # For now, we'll use a simple in-memory store
        self._api_keys: Dict[str, User] = {}
    
    def add_api_key(self, api_key: str, user: User) -> None:
        """Add an API key for a user.
        
        Args:
            api_key: API key string
            user: User associated with the key
        """
        self._api_keys[api_key] = user
    
    def verify_api_key(self, api_key: str) -> Optional[User]:
        """Verify an API key and return associated user.
        
        Args:
            api_key: API key to verify
            
        Returns:
            User if key is valid, None otherwise
        """
        return self._api_keys.get(api_key)
    
    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key.
        
        Args:
            api_key: API key to revoke
            
        Returns:
            True if key was revoked, False if not found
        """
        if api_key in self._api_keys:
            del self._api_keys[api_key]
            return True
        return False


# Global instances
_jwt_handler: Optional[JWTHandler] = None
_api_key_handler: Optional[APIKeyHandler] = None


def get_jwt_handler() -> JWTHandler:
    """Get JWT handler instance."""
    global _jwt_handler
    if _jwt_handler is None:
        settings = get_settings()
        _jwt_handler = JWTHandler(settings.secret_key, settings.jwt_algorithm)
    return _jwt_handler


def get_api_key_handler() -> APIKeyHandler:
    """Get API key handler instance."""
    global _api_key_handler
    if _api_key_handler is None:
        _api_key_handler = APIKeyHandler()
    return _api_key_handler