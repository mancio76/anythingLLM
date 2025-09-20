"""Cache repository with Redis/memory backend abstraction."""

import json
import logging
import pickle
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

import redis.asyncio as redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from app.repositories.base import RepositoryError

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract cache backend interface."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value pair with optional TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass
    
    @abstractmethod
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values by keys."""
        pass
    
    @abstractmethod
    async def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs."""
        pass
    
    @abstractmethod
    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys."""
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """Clear all cached data."""
        pass
    
    @abstractmethod
    async def get_keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern."""
        pass
    
    @abstractmethod
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value."""
        pass
    
    @abstractmethod
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for key."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check backend health."""
        pass


class RedisBackend(CacheBackend):
    """Redis cache backend implementation."""
    
    def __init__(self, redis_client: redis.Redis):
        """Initialize Redis backend.
        
        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client
        self.logger = logging.getLogger(f"{__name__}.RedisBackend")
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for storage.
        
        Args:
            value: Value to serialize
            
        Returns:
            Serialized bytes
        """
        try:
            # Try JSON first for simple types
            if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                return json.dumps(value).encode('utf-8')
            else:
                # Use pickle for complex objects
                return pickle.dumps(value)
        except Exception as e:
            self.logger.error(f"Error serializing value: {e}")
            raise RepositoryError(f"Failed to serialize value: {str(e)}")
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize value from storage.
        
        Args:
            data: Serialized bytes
            
        Returns:
            Deserialized value
        """
        try:
            # Try JSON first
            try:
                return json.loads(data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Fall back to pickle
                return pickle.loads(data)
        except Exception as e:
            self.logger.error(f"Error deserializing value: {e}")
            raise RepositoryError(f"Failed to deserialize value: {str(e)}")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key from Redis.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            data = await self.redis.get(key)
            if data is None:
                return None
            
            value = self._deserialize_value(data)
            self.logger.debug(f"Retrieved key '{key}' from Redis cache")
            return value
            
        except RedisError as e:
            self.logger.error(f"Redis error getting key '{key}': {e}")
            raise RepositoryError(f"Cache get failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error getting key '{key}' from cache: {e}")
            raise RepositoryError(f"Cache get failed: {str(e)}")
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value pair in Redis.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            data = self._serialize_value(value)
            
            if ttl:
                result = await self.redis.setex(key, ttl, data)
            else:
                result = await self.redis.set(key, data)
            
            success = bool(result)
            if success:
                self.logger.debug(f"Set key '{key}' in Redis cache (TTL: {ttl})")
            
            return success
            
        except RedisError as e:
            self.logger.error(f"Redis error setting key '{key}': {e}")
            raise RepositoryError(f"Cache set failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error setting key '{key}' in cache: {e}")
            raise RepositoryError(f"Cache set failed: {str(e)}")
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted
        """
        try:
            result = await self.redis.delete(key)
            deleted = result > 0
            
            if deleted:
                self.logger.debug(f"Deleted key '{key}' from Redis cache")
            
            return deleted
            
        except RedisError as e:
            self.logger.error(f"Redis error deleting key '{key}': {e}")
            raise RepositoryError(f"Cache delete failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error deleting key '{key}' from cache: {e}")
            raise RepositoryError(f"Cache delete failed: {str(e)}")
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists
        """
        try:
            result = await self.redis.exists(key)
            exists = result > 0
            
            self.logger.debug(f"Key '{key}' exists in Redis cache: {exists}")
            return exists
            
        except RedisError as e:
            self.logger.error(f"Redis error checking key '{key}': {e}")
            raise RepositoryError(f"Cache exists check failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error checking key '{key}' in cache: {e}")
            raise RepositoryError(f"Cache exists check failed: {str(e)}")
    
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from Redis.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dictionary of key-value pairs
        """
        try:
            if not keys:
                return {}
            
            # Use pipeline for efficiency
            pipe = self.redis.pipeline()
            for key in keys:
                pipe.get(key)
            
            results = await pipe.execute()
            
            values = {}
            for key, data in zip(keys, results):
                if data is not None:
                    values[key] = self._deserialize_value(data)
            
            self.logger.debug(f"Retrieved {len(values)} keys from Redis cache")
            return values
            
        except RedisError as e:
            self.logger.error(f"Redis error getting multiple keys: {e}")
            raise RepositoryError(f"Cache get_many failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error getting multiple keys from cache: {e}")
            raise RepositoryError(f"Cache get_many failed: {str(e)}")
    
    async def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs in Redis.
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            if not mapping:
                return True
            
            # Use pipeline for efficiency
            pipe = self.redis.pipeline()
            
            for key, value in mapping.items():
                data = self._serialize_value(value)
                if ttl:
                    pipe.setex(key, ttl, data)
                else:
                    pipe.set(key, data)
            
            results = await pipe.execute()
            success = all(results)
            
            if success:
                self.logger.debug(f"Set {len(mapping)} keys in Redis cache (TTL: {ttl})")
            
            return success
            
        except RedisError as e:
            self.logger.error(f"Redis error setting multiple keys: {e}")
            raise RepositoryError(f"Cache set_many failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error setting multiple keys in cache: {e}")
            raise RepositoryError(f"Cache set_many failed: {str(e)}")
    
    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys from Redis.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Number of keys deleted
        """
        try:
            if not keys:
                return 0
            
            result = await self.redis.delete(*keys)
            deleted_count = int(result)
            
            self.logger.debug(f"Deleted {deleted_count} keys from Redis cache")
            return deleted_count
            
        except RedisError as e:
            self.logger.error(f"Redis error deleting multiple keys: {e}")
            raise RepositoryError(f"Cache delete_many failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error deleting multiple keys from cache: {e}")
            raise RepositoryError(f"Cache delete_many failed: {str(e)}")
    
    async def clear(self) -> bool:
        """Clear all data from Redis.
        
        Returns:
            True if successful
        """
        try:
            result = await self.redis.flushdb()
            success = bool(result)
            
            if success:
                self.logger.info("Cleared all data from Redis cache")
            
            return success
            
        except RedisError as e:
            self.logger.error(f"Redis error clearing cache: {e}")
            raise RepositoryError(f"Cache clear failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error clearing cache: {e}")
            raise RepositoryError(f"Cache clear failed: {str(e)}")
    
    async def get_keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern from Redis.
        
        Args:
            pattern: Key pattern (supports wildcards)
            
        Returns:
            List of matching keys
        """
        try:
            keys = await self.redis.keys(pattern)
            key_list = [key.decode('utf-8') if isinstance(key, bytes) else key for key in keys]
            
            self.logger.debug(f"Found {len(key_list)} keys matching pattern '{pattern}'")
            return key_list
            
        except RedisError as e:
            self.logger.error(f"Redis error getting keys with pattern '{pattern}': {e}")
            raise RepositoryError(f"Cache get_keys failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error getting keys with pattern '{pattern}': {e}")
            raise RepositoryError(f"Cache get_keys failed: {str(e)}")
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value in Redis.
        
        Args:
            key: Cache key
            amount: Amount to increment
            
        Returns:
            New value after increment
        """
        try:
            result = await self.redis.incrby(key, amount)
            new_value = int(result)
            
            self.logger.debug(f"Incremented key '{key}' by {amount} to {new_value}")
            return new_value
            
        except RedisError as e:
            self.logger.error(f"Redis error incrementing key '{key}': {e}")
            raise RepositoryError(f"Cache increment failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error incrementing key '{key}': {e}")
            raise RepositoryError(f"Cache increment failed: {str(e)}")
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for key in Redis.
        
        Args:
            key: Cache key
            ttl: Time to live in seconds
            
        Returns:
            True if expiration was set
        """
        try:
            result = await self.redis.expire(key, ttl)
            success = bool(result)
            
            if success:
                self.logger.debug(f"Set expiration for key '{key}' to {ttl} seconds")
            
            return success
            
        except RedisError as e:
            self.logger.error(f"Redis error setting expiration for key '{key}': {e}")
            raise RepositoryError(f"Cache expire failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Error setting expiration for key '{key}': {e}")
            raise RepositoryError(f"Cache expire failed: {str(e)}")
    
    async def health_check(self) -> bool:
        """Check Redis health.
        
        Returns:
            True if Redis is healthy
        """
        try:
            result = await self.redis.ping()
            healthy = bool(result)
            
            self.logger.debug(f"Redis health check: {'healthy' if healthy else 'unhealthy'}")
            return healthy
            
        except (RedisError, RedisConnectionError) as e:
            self.logger.error(f"Redis health check failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error during Redis health check: {e}")
            return False


class MemoryBackend(CacheBackend):
    """In-memory cache backend implementation."""
    
    def __init__(self):
        """Initialize memory backend."""
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(f"{__name__}.MemoryBackend")
    
    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired.
        
        Args:
            entry: Cache entry with 'expires_at' field
            
        Returns:
            True if expired
        """
        expires_at = entry.get('expires_at')
        if expires_at is None:
            return False
        return datetime.utcnow() > expires_at
    
    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        expired_keys = []
        for key, entry in self._cache.items():
            if self._is_expired(entry):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            self.logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key from memory.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            self._cleanup_expired()
            
            entry = self._cache.get(key)
            if entry is None or self._is_expired(entry):
                return None
            
            value = entry['value']
            self.logger.debug(f"Retrieved key '{key}' from memory cache")
            return value
            
        except Exception as e:
            self.logger.error(f"Error getting key '{key}' from memory cache: {e}")
            raise RepositoryError(f"Memory cache get failed: {str(e)}")
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value pair in memory.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            expires_at = None
            if ttl:
                expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            
            self._cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': datetime.utcnow()
            }
            
            self.logger.debug(f"Set key '{key}' in memory cache (TTL: {ttl})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting key '{key}' in memory cache: {e}")
            raise RepositoryError(f"Memory cache set failed: {str(e)}")
    
    async def delete(self, key: str) -> bool:
        """Delete key from memory.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted
        """
        try:
            deleted = key in self._cache
            if deleted:
                del self._cache[key]
                self.logger.debug(f"Deleted key '{key}' from memory cache")
            
            return deleted
            
        except Exception as e:
            self.logger.error(f"Error deleting key '{key}' from memory cache: {e}")
            raise RepositoryError(f"Memory cache delete failed: {str(e)}")
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in memory.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists
        """
        try:
            self._cleanup_expired()
            
            entry = self._cache.get(key)
            exists = entry is not None and not self._is_expired(entry)
            
            self.logger.debug(f"Key '{key}' exists in memory cache: {exists}")
            return exists
            
        except Exception as e:
            self.logger.error(f"Error checking key '{key}' in memory cache: {e}")
            raise RepositoryError(f"Memory cache exists check failed: {str(e)}")
    
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from memory.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dictionary of key-value pairs
        """
        try:
            if not keys:
                return {}
            
            self._cleanup_expired()
            
            values = {}
            for key in keys:
                entry = self._cache.get(key)
                if entry is not None and not self._is_expired(entry):
                    values[key] = entry['value']
            
            self.logger.debug(f"Retrieved {len(values)} keys from memory cache")
            return values
            
        except Exception as e:
            self.logger.error(f"Error getting multiple keys from memory cache: {e}")
            raise RepositoryError(f"Memory cache get_many failed: {str(e)}")
    
    async def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs in memory.
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            if not mapping:
                return True
            
            expires_at = None
            if ttl:
                expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            
            created_at = datetime.utcnow()
            
            for key, value in mapping.items():
                self._cache[key] = {
                    'value': value,
                    'expires_at': expires_at,
                    'created_at': created_at
                }
            
            self.logger.debug(f"Set {len(mapping)} keys in memory cache (TTL: {ttl})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting multiple keys in memory cache: {e}")
            raise RepositoryError(f"Memory cache set_many failed: {str(e)}")
    
    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys from memory.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Number of keys deleted
        """
        try:
            if not keys:
                return 0
            
            deleted_count = 0
            for key in keys:
                if key in self._cache:
                    del self._cache[key]
                    deleted_count += 1
            
            self.logger.debug(f"Deleted {deleted_count} keys from memory cache")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Error deleting multiple keys from memory cache: {e}")
            raise RepositoryError(f"Memory cache delete_many failed: {str(e)}")
    
    async def clear(self) -> bool:
        """Clear all data from memory.
        
        Returns:
            True if successful
        """
        try:
            self._cache.clear()
            self.logger.info("Cleared all data from memory cache")
            return True
            
        except Exception as e:
            self.logger.error(f"Error clearing memory cache: {e}")
            raise RepositoryError(f"Memory cache clear failed: {str(e)}")
    
    async def get_keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern from memory.
        
        Args:
            pattern: Key pattern (supports wildcards)
            
        Returns:
            List of matching keys
        """
        try:
            self._cleanup_expired()
            
            import fnmatch
            
            matching_keys = []
            for key in self._cache.keys():
                if fnmatch.fnmatch(key, pattern):
                    matching_keys.append(key)
            
            self.logger.debug(f"Found {len(matching_keys)} keys matching pattern '{pattern}'")
            return matching_keys
            
        except Exception as e:
            self.logger.error(f"Error getting keys with pattern '{pattern}' from memory cache: {e}")
            raise RepositoryError(f"Memory cache get_keys failed: {str(e)}")
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value in memory.
        
        Args:
            key: Cache key
            amount: Amount to increment
            
        Returns:
            New value after increment
        """
        try:
            self._cleanup_expired()
            
            entry = self._cache.get(key)
            if entry is None or self._is_expired(entry):
                # Initialize with amount if key doesn't exist
                new_value = amount
                await self.set(key, new_value)
            else:
                # Increment existing value
                current_value = entry['value']
                if not isinstance(current_value, (int, float)):
                    raise RepositoryError(f"Cannot increment non-numeric value for key '{key}'")
                
                new_value = current_value + amount
                entry['value'] = new_value
            
            self.logger.debug(f"Incremented key '{key}' by {amount} to {new_value}")
            return int(new_value)
            
        except Exception as e:
            self.logger.error(f"Error incrementing key '{key}' in memory cache: {e}")
            raise RepositoryError(f"Memory cache increment failed: {str(e)}")
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for key in memory.
        
        Args:
            key: Cache key
            ttl: Time to live in seconds
            
        Returns:
            True if expiration was set
        """
        try:
            entry = self._cache.get(key)
            if entry is None or self._is_expired(entry):
                return False
            
            entry['expires_at'] = datetime.utcnow() + timedelta(seconds=ttl)
            
            self.logger.debug(f"Set expiration for key '{key}' to {ttl} seconds")
            return True
            
        except Exception as e:
            self.logger.error(f"Error setting expiration for key '{key}' in memory cache: {e}")
            raise RepositoryError(f"Memory cache expire failed: {str(e)}")
    
    async def health_check(self) -> bool:
        """Check memory cache health.
        
        Returns:
            True (memory cache is always healthy)
        """
        try:
            # Memory cache is always healthy if we can access it
            _ = len(self._cache)
            self.logger.debug("Memory cache health check: healthy")
            return True
            
        except Exception as e:
            self.logger.error(f"Memory cache health check failed: {e}")
            return False


class CacheRepository:
    """Cache repository with Redis/memory backend abstraction."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize cache repository.
        
        Args:
            redis_client: Optional Redis client (uses memory backend if None)
        """
        if redis_client:
            self.backend = RedisBackend(redis_client)
            self.backend_type = "redis"
        else:
            self.backend = MemoryBackend()
            self.backend_type = "memory"
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initialized cache repository with {self.backend_type} backend")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        return await self.backend.get(key)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key-value pair with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        return await self.backend.set(key, value, ttl)
    
    async def delete(self, key: str) -> bool:
        """Delete key.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted
        """
        return await self.backend.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists
        """
        return await self.backend.exists(key)
    
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values by keys.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dictionary of key-value pairs
        """
        return await self.backend.get_many(keys)
    
    async def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs.
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        return await self.backend.set_many(mapping, ttl)
    
    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys.
        
        Args:
            keys: List of cache keys
            
        Returns:
            Number of keys deleted
        """
        return await self.backend.delete_many(keys)
    
    async def clear(self) -> bool:
        """Clear all cached data.
        
        Returns:
            True if successful
        """
        return await self.backend.clear()
    
    async def get_keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern.
        
        Args:
            pattern: Key pattern (supports wildcards)
            
        Returns:
            List of matching keys
        """
        return await self.backend.get_keys(pattern)
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment numeric value.
        
        Args:
            key: Cache key
            amount: Amount to increment
            
        Returns:
            New value after increment
        """
        return await self.backend.increment(key, amount)
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for key.
        
        Args:
            key: Cache key
            ttl: Time to live in seconds
            
        Returns:
            True if expiration was set
        """
        return await self.backend.expire(key, ttl)
    
    async def health_check(self) -> bool:
        """Check cache backend health.
        
        Returns:
            True if backend is healthy
        """
        return await self.backend.health_check()
    
    def get_backend_type(self) -> str:
        """Get the backend type.
        
        Returns:
            Backend type ("redis" or "memory")
        """
        return self.backend_type
    
    # Convenience methods for common caching patterns
    
    async def cache_with_ttl(
        self, 
        key: str, 
        value_factory, 
        ttl: int = 3600,
        *args, 
        **kwargs
    ) -> Any:
        """Cache value with TTL using factory function.
        
        Args:
            key: Cache key
            value_factory: Function to generate value if not cached
            ttl: Time to live in seconds
            *args: Arguments for value_factory
            **kwargs: Keyword arguments for value_factory
            
        Returns:
            Cached or generated value
        """
        try:
            # Try to get from cache first
            cached_value = await self.get(key)
            if cached_value is not None:
                self.logger.debug(f"Cache hit for key '{key}'")
                return cached_value
            
            # Generate value using factory
            self.logger.debug(f"Cache miss for key '{key}', generating value")
            value = await value_factory(*args, **kwargs) if callable(value_factory) else value_factory
            
            # Cache the generated value
            await self.set(key, value, ttl)
            
            return value
            
        except Exception as e:
            self.logger.error(f"Error in cache_with_ttl for key '{key}': {e}")
            # Fall back to generating value without caching
            return await value_factory(*args, **kwargs) if callable(value_factory) else value_factory
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern.
        
        Args:
            pattern: Key pattern to invalidate
            
        Returns:
            Number of keys invalidated
        """
        try:
            keys = await self.get_keys(pattern)
            if not keys:
                return 0
            
            deleted_count = await self.delete_many(keys)
            self.logger.info(f"Invalidated {deleted_count} keys matching pattern '{pattern}'")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Error invalidating pattern '{pattern}': {e}")
            raise RepositoryError(f"Failed to invalidate pattern: {str(e)}")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            stats = {
                "backend_type": self.backend_type,
                "healthy": await self.health_check()
            }
            
            # Get key count
            try:
                all_keys = await self.get_keys("*")
                stats["total_keys"] = len(all_keys)
            except Exception:
                stats["total_keys"] = "unknown"
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting cache stats: {e}")
            return {
                "backend_type": self.backend_type,
                "healthy": False,
                "error": str(e)
            }