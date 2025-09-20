"""Tests for security middleware components."""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from app.core.security import JWTHandler, APIKeyHandler, User
from app.middleware.authentication import AuthenticationMiddleware
from app.middleware.rate_limiting import RateLimitingMiddleware, MemoryRateLimiter
from app.middleware.logging import LoggingMiddleware, DataSanitizer


class TestJWTHandler:
    """Test JWT token handler."""
    
    def test_create_and_verify_token(self):
        """Test token creation and verification."""
        handler = JWTHandler("test-secret-key")
        
        # Create token
        token = handler.create_access_token("test-user")
        assert token is not None
        assert isinstance(token, str)
        
        # Verify token
        token_data = handler.verify_token(token)
        assert token_data is not None
        assert token_data.sub == "test-user"
        assert token_data.type == "access"
    
    def test_verify_invalid_token(self):
        """Test verification of invalid token."""
        handler = JWTHandler("test-secret-key")
        
        # Test invalid token
        token_data = handler.verify_token("invalid-token")
        assert token_data is None
    
    def test_verify_expired_token(self):
        """Test verification of expired token."""
        handler = JWTHandler("test-secret-key")
        
        # Create token with past expiration
        with patch('app.core.security.datetime') as mock_datetime:
            # Mock current time to be in the past
            mock_datetime.utcnow.return_value.timestamp.return_value = 1000
            token = handler.create_access_token("test-user")
            
            # Reset mock to current time
            mock_datetime.utcnow.return_value.timestamp.return_value = 2000
            
            # Token should be expired
            token_data = handler.verify_token(token)
            assert token_data is None
    
    def test_password_hashing(self):
        """Test password hashing and verification."""
        handler = JWTHandler("test-secret-key")
        
        password = "test-password"
        hashed = handler.hash_password(password)
        
        assert hashed != password
        assert handler.verify_password(password, hashed)
        assert not handler.verify_password("wrong-password", hashed)


class TestAPIKeyHandler:
    """Test API key handler."""
    
    def test_add_and_verify_api_key(self):
        """Test adding and verifying API keys."""
        handler = APIKeyHandler()
        user = User(id="test-user", username="test", is_active=True)
        api_key = "test-api-key"
        
        # Add API key
        handler.add_api_key(api_key, user)
        
        # Verify API key
        verified_user = handler.verify_api_key(api_key)
        assert verified_user is not None
        assert verified_user.id == user.id
        assert verified_user.username == user.username
    
    def test_verify_invalid_api_key(self):
        """Test verification of invalid API key."""
        handler = APIKeyHandler()
        
        verified_user = handler.verify_api_key("invalid-key")
        assert verified_user is None
    
    def test_revoke_api_key(self):
        """Test API key revocation."""
        handler = APIKeyHandler()
        user = User(id="test-user", username="test", is_active=True)
        api_key = "test-api-key"
        
        # Add and verify API key
        handler.add_api_key(api_key, user)
        assert handler.verify_api_key(api_key) is not None
        
        # Revoke API key
        revoked = handler.revoke_api_key(api_key)
        assert revoked is True
        assert handler.verify_api_key(api_key) is None
        
        # Try to revoke non-existent key
        revoked = handler.revoke_api_key("non-existent")
        assert revoked is False


class TestMemoryRateLimiter:
    """Test memory-based rate limiter."""
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test basic rate limiting functionality."""
        limiter = MemoryRateLimiter(requests_per_window=2, window_seconds=60)
        identifier = "test-user"
        
        # First request should be allowed
        allowed, retry_after = await limiter.is_allowed(identifier)
        assert allowed is True
        assert retry_after == 0
        
        # Second request should be allowed
        allowed, retry_after = await limiter.is_allowed(identifier)
        assert allowed is True
        assert retry_after == 0
        
        # Third request should be denied
        allowed, retry_after = await limiter.is_allowed(identifier)
        assert allowed is False
        assert retry_after > 0
    
    @pytest.mark.asyncio
    async def test_window_expiration(self):
        """Test that rate limit window expires correctly."""
        limiter = MemoryRateLimiter(requests_per_window=1, window_seconds=1)
        identifier = "test-user"
        
        # First request should be allowed
        allowed, retry_after = await limiter.is_allowed(identifier)
        assert allowed is True
        
        # Second request should be denied
        allowed, retry_after = await limiter.is_allowed(identifier)
        assert allowed is False
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Request should be allowed again
        allowed, retry_after = await limiter.is_allowed(identifier)
        assert allowed is True


class TestDataSanitizer:
    """Test data sanitization for logging."""
    
    def test_sanitize_dict_with_sensitive_data(self):
        """Test sanitization of dictionary with sensitive fields."""
        data = {
            "username": "test-user",
            "password": "secret123",
            "api_key": "key123",
            "Authorization": "Bearer token123",
            "normal_field": "normal_value"
        }
        
        with patch('app.core.config.get_settings') as mock_settings:
            mock_settings.return_value.log_sanitize_sensitive = True
            
            sanitized = DataSanitizer.sanitize_data(data)
            
            assert sanitized["username"] == "test-user"
            assert sanitized["password"] == "[REDACTED]"
            assert sanitized["api_key"] == "[REDACTED]"
            assert sanitized["Authorization"] == "[REDACTED]"
            assert sanitized["normal_field"] == "normal_value"
    
    def test_sanitize_nested_dict(self):
        """Test sanitization of nested dictionary."""
        data = {
            "user": {
                "username": "test-user",
                "password": "secret123"
            },
            "config": {
                "api_key": "key123",
                "timeout": 30
            }
        }
        
        with patch('app.core.config.get_settings') as mock_settings:
            mock_settings.return_value.log_sanitize_sensitive = True
            
            sanitized = DataSanitizer.sanitize_data(data)
            
            assert sanitized["user"]["username"] == "test-user"
            assert sanitized["user"]["password"] == "[REDACTED]"
            assert sanitized["config"]["api_key"] == "[REDACTED]"
            assert sanitized["config"]["timeout"] == 30
    
    def test_sanitization_disabled(self):
        """Test that sanitization can be disabled."""
        data = {
            "password": "secret123",
            "api_key": "key123"
        }
        
        with patch('app.core.config.get_settings') as mock_settings:
            mock_settings.return_value.log_sanitize_sensitive = False
            
            sanitized = DataSanitizer.sanitize_data(data)
            
            assert sanitized["password"] == "secret123"
            assert sanitized["api_key"] == "key123"


class TestAuthenticationMiddleware:
    """Test authentication middleware."""
    
    @pytest.mark.asyncio
    async def test_public_path_access(self):
        """Test that public paths don't require authentication."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)
        
        # Mock request for public path
        request = Mock(spec=Request)
        request.url.path = "/docs"
        
        # Mock call_next
        call_next = AsyncMock()
        expected_response = Mock(spec=Response)
        call_next.return_value = expected_response
        
        # Process request
        response = await middleware.dispatch(request, call_next)
        
        # Should call next without authentication
        assert response == expected_response
        call_next.assert_called_once_with(request)
    
    @pytest.mark.asyncio
    async def test_jwt_authentication(self):
        """Test JWT authentication."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)
        
        # Create valid JWT token
        jwt_handler = JWTHandler("test-secret")
        token = jwt_handler.create_access_token("test-user")
        
        # Mock request with JWT token
        request = Mock(spec=Request)
        request.url.path = "/protected"
        request.headers.get.side_effect = lambda key: {
            "authorization": f"Bearer {token}"
        }.get(key)
        request.state = Mock()
        
        # Mock call_next
        call_next = AsyncMock()
        expected_response = Mock(spec=Response)
        call_next.return_value = expected_response
        
        # Process request
        with patch('app.middleware.authentication.get_jwt_handler', return_value=jwt_handler):
            response = await middleware.dispatch(request, call_next)
        
        # Should set user in request state
        assert hasattr(request.state, 'user')
        assert request.state.user.id == "test-user"
        assert response == expected_response


if __name__ == "__main__":
    pytest.main([__file__])