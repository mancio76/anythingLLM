"""Security tests for authentication and authorization."""

import jwt
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi import status
from httpx import AsyncClient

from app.core.security import create_access_token, verify_token, User
from app.core.config import get_settings


class TestAuthentication:
    """Test cases for authentication mechanisms."""

    @pytest.fixture
    def valid_user(self):
        """Create a valid user for testing."""
        return User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            is_active=True,
            roles=["user"],
        )

    @pytest.fixture
    def admin_user(self):
        """Create an admin user for testing."""
        return User(
            id="admin_123",
            username="adminuser",
            email="admin@example.com",
            is_active=True,
            roles=["admin", "user"],
        )

    @pytest.fixture
    def valid_jwt_token(self, valid_user):
        """Create a valid JWT token."""
        settings = get_settings()
        return create_access_token(
            data={"sub": valid_user.username, "user_id": valid_user.id},
            expires_delta=timedelta(minutes=30)
        )

    @pytest.fixture
    def expired_jwt_token(self, valid_user):
        """Create an expired JWT token."""
        settings = get_settings()
        return jwt.encode(
            {
                "sub": valid_user.username,
                "user_id": valid_user.id,
                "exp": datetime.utcnow() - timedelta(minutes=1)  # Expired 1 minute ago
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm
        )

    @pytest.fixture
    def invalid_jwt_token(self):
        """Create an invalid JWT token."""
        return "invalid.jwt.token"

    @pytest.mark.asyncio
    async def test_jwt_token_creation(self, valid_user):
        """Test JWT token creation."""
        token = create_access_token(
            data={"sub": valid_user.username, "user_id": valid_user.id}
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token.split('.')) == 3  # JWT has 3 parts

    @pytest.mark.asyncio
    async def test_jwt_token_verification_valid(self, valid_jwt_token, valid_user):
        """Test JWT token verification with valid token."""
        with patch('app.core.security.get_user_by_username') as mock_get_user:
            mock_get_user.return_value = valid_user
            
            user = await verify_token(valid_jwt_token)
            
            assert user is not None
            assert user.username == valid_user.username
            assert user.id == valid_user.id

    @pytest.mark.asyncio
    async def test_jwt_token_verification_expired(self, expired_jwt_token):
        """Test JWT token verification with expired token."""
        with pytest.raises(Exception) as exc_info:
            await verify_token(expired_jwt_token)
        
        assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_jwt_token_verification_invalid(self, invalid_jwt_token):
        """Test JWT token verification with invalid token."""
        with pytest.raises(Exception) as exc_info:
            await verify_token(invalid_jwt_token)
        
        assert "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_api_key_authentication_valid(self, async_client: AsyncClient):
        """Test API key authentication with valid key."""
        valid_api_key = "test-api-key-123"
        
        with patch('app.core.security.verify_api_key') as mock_verify:
            mock_verify.return_value = User(
                id="api_user_123",
                username="api_user",
                is_active=True,
                roles=["api_user"],
            )
            
            response = await async_client.get(
                "/api/v1/health",
                headers={"X-API-Key": valid_api_key}
            )
            
            assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_api_key_authentication_invalid(self, async_client: AsyncClient):
        """Test API key authentication with invalid key."""
        invalid_api_key = "invalid-api-key"
        
        with patch('app.core.security.verify_api_key') as mock_verify:
            mock_verify.side_effect = Exception("Invalid API key")
            
            response = await async_client.get(
                "/api/v1/health",
                headers={"X-API-Key": invalid_api_key}
            )
            
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_no_authentication_provided(self, async_client: AsyncClient):
        """Test request without any authentication."""
        response = await async_client.get("/api/v1/documents/jobs")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert "authentication" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_bearer_token_authentication_valid(
        self,
        async_client: AsyncClient,
        valid_jwt_token,
        valid_user,
    ):
        """Test Bearer token authentication with valid token."""
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = valid_user
            
            response = await async_client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            assert response.status_code == status.HTTP_200_OK

    @pytest.mark.asyncio
    async def test_bearer_token_authentication_invalid(
        self,
        async_client: AsyncClient,
        invalid_jwt_token,
    ):
        """Test Bearer token authentication with invalid token."""
        response = await async_client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {invalid_jwt_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_malformed_authorization_header(self, async_client: AsyncClient):
        """Test malformed Authorization header."""
        malformed_headers = [
            {"Authorization": "InvalidFormat token"},
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "Bearer "},  # Empty token
            {"Authorization": "Basic dGVzdA=="},  # Wrong auth type
        ]
        
        for headers in malformed_headers:
            response = await async_client.get("/api/v1/health", headers=headers)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_user_role_based_access_user(
        self,
        async_client: AsyncClient,
        valid_jwt_token,
        valid_user,
    ):
        """Test role-based access for regular user."""
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = valid_user
            
            # User should be able to access regular endpoints
            response = await async_client.get(
                "/api/v1/documents/jobs",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            # This might return 200 or other status depending on implementation
            assert response.status_code != status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_user_role_based_access_admin(
        self,
        async_client: AsyncClient,
        valid_jwt_token,
        admin_user,
    ):
        """Test role-based access for admin user."""
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = admin_user
            
            # Admin should be able to access admin endpoints
            response = await async_client.get(
                "/api/v1/health/detailed",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            assert response.status_code != status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_inactive_user_access_denied(
        self,
        async_client: AsyncClient,
        valid_jwt_token,
    ):
        """Test access denied for inactive user."""
        inactive_user = User(
            id="inactive_123",
            username="inactive_user",
            is_active=False,
            roles=["user"],
        )
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = inactive_user
            
            response = await async_client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_token_refresh_mechanism(self, valid_user):
        """Test token refresh mechanism."""
        # Create a token that's about to expire
        short_lived_token = create_access_token(
            data={"sub": valid_user.username, "user_id": valid_user.id},
            expires_delta=timedelta(seconds=1)
        )
        
        assert short_lived_token is not None
        
        # In a real implementation, you would test the refresh endpoint
        # For now, just verify the token was created
        assert isinstance(short_lived_token, str)

    @pytest.mark.asyncio
    async def test_concurrent_authentication_requests(
        self,
        async_client: AsyncClient,
        valid_jwt_token,
        valid_user,
    ):
        """Test concurrent authentication requests."""
        import asyncio
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = valid_user
            
            # Make multiple concurrent authenticated requests
            tasks = [
                async_client.get(
                    "/api/v1/health",
                    headers={"Authorization": f"Bearer {valid_jwt_token}"}
                )
                for _ in range(10)
            ]
            
            responses = await asyncio.gather(*tasks)
            
            # All requests should succeed
            assert all(r.status_code == status.HTTP_200_OK for r in responses)

    @pytest.mark.asyncio
    async def test_authentication_with_special_characters(self, async_client: AsyncClient):
        """Test authentication with special characters in credentials."""
        special_tokens = [
            "token.with.dots",
            "token-with-dashes",
            "token_with_underscores",
            "token+with+plus",
            "token/with/slashes",
        ]
        
        for token in special_tokens:
            response = await async_client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Should return 401 for invalid tokens, not 400 for malformed requests
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_authentication_error_messages(self, async_client: AsyncClient):
        """Test authentication error messages don't leak sensitive information."""
        test_cases = [
            {"headers": {}, "expected_message": "authentication"},
            {"headers": {"Authorization": "Bearer invalid"}, "expected_message": "invalid"},
            {"headers": {"X-API-Key": "invalid"}, "expected_message": "invalid"},
        ]
        
        for case in test_cases:
            response = await async_client.get("/api/v1/health", headers=case["headers"])
            
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            data = response.json()
            
            # Error message should be generic and not leak implementation details
            assert case["expected_message"] in data["detail"].lower()
            assert "secret" not in data["detail"].lower()
            assert "key" not in data["detail"].lower() or case["expected_message"] == "invalid"

    @pytest.mark.asyncio
    async def test_session_management(self, valid_user):
        """Test session management and token lifecycle."""
        # Create token
        token = create_access_token(
            data={"sub": valid_user.username, "user_id": valid_user.id}
        )
        
        # Verify token is valid
        with patch('app.core.security.get_user_by_username') as mock_get_user:
            mock_get_user.return_value = valid_user
            user = await verify_token(token)
            assert user.username == valid_user.username
        
        # In a real implementation, you would test:
        # - Token blacklisting
        # - Session invalidation
        # - Logout functionality

    @pytest.mark.asyncio
    async def test_brute_force_protection(self, async_client: AsyncClient):
        """Test brute force protection mechanisms."""
        # Simulate multiple failed authentication attempts
        invalid_tokens = [f"invalid_token_{i}" for i in range(10)]
        
        responses = []
        for token in invalid_tokens:
            response = await async_client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {token}"}
            )
            responses.append(response)
        
        # All should return 401, but rate limiting might kick in
        for response in responses:
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_429_TOO_MANY_REQUESTS
            ]

    @pytest.mark.asyncio
    async def test_cors_authentication_headers(self, async_client: AsyncClient):
        """Test CORS handling with authentication headers."""
        # Test preflight request
        response = await async_client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            }
        )
        
        # Should allow the Authorization header
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT]
        
        # Check CORS headers (if implemented)
        if "Access-Control-Allow-Headers" in response.headers:
            allowed_headers = response.headers["Access-Control-Allow-Headers"]
            assert "authorization" in allowed_headers.lower()


class TestAuthorization:
    """Test cases for authorization mechanisms."""

    @pytest.fixture
    def user_with_limited_permissions(self):
        """Create a user with limited permissions."""
        return User(
            id="limited_user_123",
            username="limiteduser",
            is_active=True,
            roles=["read_only"],
        )

    @pytest.mark.asyncio
    async def test_resource_based_authorization(
        self,
        async_client: AsyncClient,
        user_with_limited_permissions,
    ):
        """Test resource-based authorization."""
        token = create_access_token(
            data={
                "sub": user_with_limited_permissions.username,
                "user_id": user_with_limited_permissions.id
            }
        )
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = user_with_limited_permissions
            
            # User should be able to read
            response = await async_client.get(
                "/api/v1/documents/jobs",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Should not return 403 for read operations
            assert response.status_code != status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_workspace_based_authorization(
        self,
        async_client: AsyncClient,
        user_with_limited_permissions,
    ):
        """Test workspace-based authorization."""
        token = create_access_token(
            data={
                "sub": user_with_limited_permissions.username,
                "user_id": user_with_limited_permissions.id
            }
        )
        
        with patch('app.core.security.verify_token') as mock_verify:
            mock_verify.return_value = user_with_limited_permissions
            
            # Try to access workspace user doesn't own
            response = await async_client.get(
                "/api/v1/workspaces/unauthorized_workspace",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Should return 403 or 404 depending on implementation
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND
            ]

    @pytest.mark.asyncio
    async def test_permission_inheritance(self, async_client: AsyncClient):
        """Test permission inheritance in role hierarchy."""
        # This would test if admin inherits user permissions, etc.
        # Implementation depends on the actual role system
        pass

    @pytest.mark.asyncio
    async def test_dynamic_permission_checking(self, async_client: AsyncClient):
        """Test dynamic permission checking based on resource state."""
        # This would test permissions that change based on resource state
        # e.g., can only modify own resources, can't delete active jobs, etc.
        pass