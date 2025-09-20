"""Rate limiting middleware with Redis/memory backend support."""

import time
import asyncio
from typing import Dict, List, Optional, Callable
from collections import defaultdict

import redis.asyncio as redis
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, retry_after: int):
        """Initialize rate limit exception.
        
        Args:
            retry_after: Seconds until next request is allowed
        """
        super().__init__(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )


class MemoryRateLimiter:
    """In-memory rate limiter for single instance deployments."""
    
    def __init__(self, requests_per_window: int, window_seconds: int):
        """Initialize memory rate limiter.
        
        Args:
            requests_per_window: Maximum requests per window
            window_seconds: Window duration in seconds
        """
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """Check if request is allowed for identifier.
        
        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self.window_seconds
            
            # Clean old requests
            self._requests[identifier] = [
                req_time for req_time in self._requests[identifier]
                if req_time > window_start
            ]
            
            # Check if under limit
            if len(self._requests[identifier]) < self.requests_per_window:
                self._requests[identifier].append(current_time)
                return True, 0
            
            # Calculate retry after
            oldest_request = min(self._requests[identifier])
            retry_after = int(oldest_request + self.window_seconds - current_time) + 1
            
            return False, max(retry_after, 1)


class RedisRateLimiter:
    """Redis-based rate limiter for distributed deployments."""
    
    def __init__(self, redis_client: redis.Redis, requests_per_window: int, window_seconds: int):
        """Initialize Redis rate limiter.
        
        Args:
            redis_client: Redis client instance
            requests_per_window: Maximum requests per window
            window_seconds: Window duration in seconds
        """
        self.redis = redis_client
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
    
    async def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """Check if request is allowed for identifier.
        
        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        try:
            current_time = time.time()
            window_start = current_time - self.window_seconds
            key = f"rate_limit:{identifier}"
            
            # Use Redis pipeline for atomic operations
            pipe = self.redis.pipeline()
            
            # Remove old entries
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, self.window_seconds)
            
            results = await pipe.execute()
            current_count = results[1]
            
            if current_count < self.requests_per_window:
                return True, 0
            
            # Get oldest request to calculate retry after
            oldest_requests = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest_requests:
                oldest_time = oldest_requests[0][1]
                retry_after = int(oldest_time + self.window_seconds - current_time) + 1
                return False, max(retry_after, 1)
            
            return False, self.window_seconds
            
        except Exception:
            # Fall back to allowing request if Redis fails
            return True, 0


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with Redis/memory backend support."""
    
    def __init__(self, app, requests_per_window: int = 100, window_seconds: int = 3600):
        """Initialize rate limiting middleware.
        
        Args:
            app: FastAPI application
            requests_per_window: Maximum requests per window
            window_seconds: Window duration in seconds
        """
        super().__init__(app)
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self._limiter: Optional[MemoryRateLimiter | RedisRateLimiter] = None
        self._redis_client: Optional[redis.Redis] = None
    
    async def _get_limiter(self):
        """Get rate limiter instance (lazy initialization)."""
        if self._limiter is None:
            settings = get_settings()
            
            if settings.redis_enabled and settings.redis_url:
                try:
                    self._redis_client = redis.from_url(
                        settings.redis_url,
                        max_connections=settings.redis_pool_size,
                        decode_responses=True
                    )
                    # Test connection
                    await self._redis_client.ping()
                    self._limiter = RedisRateLimiter(
                        self._redis_client,
                        self.requests_per_window,
                        self.window_seconds
                    )
                except Exception:
                    # Fall back to memory limiter if Redis fails
                    self._limiter = MemoryRateLimiter(
                        self.requests_per_window,
                        self.window_seconds
                    )
            else:
                self._limiter = MemoryRateLimiter(
                    self.requests_per_window,
                    self.window_seconds
                )
        
        return self._limiter
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting to requests."""
        settings = get_settings()
        
        # Skip rate limiting if disabled
        if not settings.rate_limit_enabled:
            return await call_next(request)
        
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)
        
        # Get identifier for rate limiting
        identifier = self._get_identifier(request)
        
        # Check rate limit
        limiter = await self._get_limiter()
        is_allowed, retry_after = await limiter.is_allowed(identifier)
        
        if not is_allowed:
            raise RateLimitExceeded(retry_after)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Window"] = str(self.window_seconds)
        
        return response
    
    def _get_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting.
        
        Args:
            request: FastAPI request
            
        Returns:
            Unique identifier for rate limiting
        """
        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"
        
        # Fall back to IP address
        return f"ip:{self._get_client_ip(request)}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address from request.
        
        Args:
            request: FastAPI request
            
        Returns:
            Client IP address
        """
        # Check for forwarded headers (common in load balancers/proxies)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to direct client IP
        if hasattr(request, "client") and request.client:
            return request.client.host
        
        return "unknown"
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._redis_client:
            await self._redis_client.close()