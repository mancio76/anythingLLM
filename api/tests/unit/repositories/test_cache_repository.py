"""Comprehensive unit tests for CacheRepository."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

import pytest

from app.repositories.cache_repository import CacheRepository, CacheError
from tests.fixtures.mock_data import mock_data


class TestCacheRepository:
    """Test cases for CacheRepository."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        client = AsyncMock()
        client.get.return_value = None
        client.set.return_value = True
        client.delete.return_value = 1
        client.exists.return_value = 1
        client.mget.return_value = []
        client.ping.return_value = True
        return client

    @pytest.fixture
    def cache_repository_redis(self, mock_redis_client):
        """Create CacheRepository with Redis backend."""
        return CacheRepository(redis_client=mock_redis_client, use_memory_fallback=False)

    @pytest.fixture
    def cache_repository_memory(self):
        """Create CacheRepository with memory backend."""
        return CacheRepository(redis_client=None, use_memory_fallback=True)

    @pytest.mark.asyncio
    async def test_get_redis_success(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test successful get operation with Redis."""
        key = "test_key"
        value = {"data": "test_value"}
        mock_redis_client.get.return_value = json.dumps(value)
        
        result = await cache_repository_redis.get(key)
        
        assert result == value
        mock_redis_client.get.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_get_redis_not_found(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test get operation when key doesn't exist in Redis."""
        mock_redis_client.get.return_value = None
        
        result = await cache_repository_redis.get("nonexistent_key")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_redis_json_decode_error(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test get operation with JSON decode error."""
        mock_redis_client.get.return_value = "invalid json"
        
        with pytest.raises(CacheError) as exc_info:
            await cache_repository_redis.get("test_key")
        
        assert "JSON decode error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_redis_success(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test successful set operation with Redis."""
        key = "test_key"
        value = {"data": "test_value"}
        ttl = 3600
        
        result = await cache_repository_redis.set(key, value, ttl)
        
        assert result is True
        mock_redis_client.set.assert_called_once_with(
            key, json.dumps(value), ex=ttl
        )

    @pytest.mark.asyncio
    async def test_set_redis_without_ttl(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test set operation without TTL."""
        key = "test_key"
        value = {"data": "test_value"}
        
        result = await cache_repository_redis.set(key, value)
        
        assert result is True
        mock_redis_client.set.assert_called_once_with(
            key, json.dumps(value), ex=None
        )

    @pytest.mark.asyncio
    async def test_set_redis_json_encode_error(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test set operation with JSON encode error."""
        # Create an object that can't be JSON serialized
        class NonSerializable:
            pass
        
        with pytest.raises(CacheError) as exc_info:
            await cache_repository_redis.set("test_key", NonSerializable())
        
        assert "JSON encode error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_redis_success(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test successful delete operation with Redis."""
        key = "test_key"
        mock_redis_client.delete.return_value = 1
        
        result = await cache_repository_redis.delete(key)
        
        assert result is True
        mock_redis_client.delete.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_delete_redis_not_found(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test delete operation when key doesn't exist."""
        mock_redis_client.delete.return_value = 0
        
        result = await cache_repository_redis.delete("nonexistent_key")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_redis_success(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test successful exists operation with Redis."""
        key = "test_key"
        mock_redis_client.exists.return_value = 1
        
        result = await cache_repository_redis.exists(key)
        
        assert result is True
        mock_redis_client.exists.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_exists_redis_not_found(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test exists operation when key doesn't exist."""
        mock_redis_client.exists.return_value = 0
        
        result = await cache_repository_redis.exists("nonexistent_key")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_many_redis_success(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test successful get_many operation with Redis."""
        keys = ["key1", "key2", "key3"]
        values = [
            json.dumps({"data": "value1"}),
            json.dumps({"data": "value2"}),
            None,  # key3 doesn't exist
        ]
        mock_redis_client.mget.return_value = values
        
        result = await cache_repository_redis.get_many(keys)
        
        expected = {
            "key1": {"data": "value1"},
            "key2": {"data": "value2"},
        }
        assert result == expected
        mock_redis_client.mget.assert_called_once_with(keys)

    @pytest.mark.asyncio
    async def test_get_memory_success(
        self,
        cache_repository_memory,
    ):
        """Test successful get operation with memory backend."""
        key = "test_key"
        value = {"data": "test_value"}
        
        # First set the value
        await cache_repository_memory.set(key, value)
        
        # Then get it
        result = await cache_repository_memory.get(key)
        
        assert result == value

    @pytest.mark.asyncio
    async def test_get_memory_not_found(
        self,
        cache_repository_memory,
    ):
        """Test get operation when key doesn't exist in memory."""
        result = await cache_repository_memory.get("nonexistent_key")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_set_memory_success(
        self,
        cache_repository_memory,
    ):
        """Test successful set operation with memory backend."""
        key = "test_key"
        value = {"data": "test_value"}
        
        result = await cache_repository_memory.set(key, value)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_set_memory_with_ttl(
        self,
        cache_repository_memory,
    ):
        """Test set operation with TTL in memory backend."""
        key = "test_key"
        value = {"data": "test_value"}
        ttl = 1  # 1 second
        
        result = await cache_repository_memory.set(key, value, ttl)
        
        assert result is True
        
        # Verify value exists immediately
        immediate_result = await cache_repository_memory.get(key)
        assert immediate_result == value
        
        # Wait for TTL to expire (in real implementation)
        # This would require actual time-based testing

    @pytest.mark.asyncio
    async def test_delete_memory_success(
        self,
        cache_repository_memory,
    ):
        """Test successful delete operation with memory backend."""
        key = "test_key"
        value = {"data": "test_value"}
        
        # First set the value
        await cache_repository_memory.set(key, value)
        
        # Then delete it
        result = await cache_repository_memory.delete(key)
        
        assert result is True
        
        # Verify it's gone
        get_result = await cache_repository_memory.get(key)
        assert get_result is None

    @pytest.mark.asyncio
    async def test_delete_memory_not_found(
        self,
        cache_repository_memory,
    ):
        """Test delete operation when key doesn't exist in memory."""
        result = await cache_repository_memory.delete("nonexistent_key")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_memory_success(
        self,
        cache_repository_memory,
    ):
        """Test successful exists operation with memory backend."""
        key = "test_key"
        value = {"data": "test_value"}
        
        # First set the value
        await cache_repository_memory.set(key, value)
        
        # Then check if it exists
        result = await cache_repository_memory.exists(key)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_memory_not_found(
        self,
        cache_repository_memory,
    ):
        """Test exists operation when key doesn't exist in memory."""
        result = await cache_repository_memory.exists("nonexistent_key")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_many_memory_success(
        self,
        cache_repository_memory,
    ):
        """Test successful get_many operation with memory backend."""
        # Set up test data
        test_data = {
            "key1": {"data": "value1"},
            "key2": {"data": "value2"},
        }
        
        for key, value in test_data.items():
            await cache_repository_memory.set(key, value)
        
        # Test get_many
        keys = ["key1", "key2", "key3"]  # key3 doesn't exist
        result = await cache_repository_memory.get_many(keys)
        
        expected = {
            "key1": {"data": "value1"},
            "key2": {"data": "value2"},
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_redis_connection_error_fallback(
        self,
        mock_redis_client,
    ):
        """Test fallback to memory when Redis connection fails."""
        mock_redis_client.get.side_effect = Exception("Connection failed")
        
        cache_repo = CacheRepository(
            redis_client=mock_redis_client,
            use_memory_fallback=True
        )
        
        # Should fallback to memory backend
        result = await cache_repo.get("test_key")
        assert result is None  # Not found in memory

    @pytest.mark.asyncio
    async def test_redis_connection_error_no_fallback(
        self,
        mock_redis_client,
    ):
        """Test error when Redis fails and no fallback is configured."""
        mock_redis_client.get.side_effect = Exception("Connection failed")
        
        cache_repo = CacheRepository(
            redis_client=mock_redis_client,
            use_memory_fallback=False
        )
        
        with pytest.raises(CacheError) as exc_info:
            await cache_repo.get("test_key")
        
        assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_complex_data_serialization(
        self,
        cache_repository_redis,
        mock_redis_client,
    ):
        """Test serialization of complex data structures."""
        complex_data = {
            "workspace": mock_data.create_mock_workspace().model_dump(),
            "jobs": [mock_data.create_mock_job().model_dump() for _ in range(3)],
            "metadata": {
                "nested": {"deep": {"value": 123}},
                "list": [1, 2, 3, {"inner": "value"}],
                "boolean": True,
                "null": None,
            }
        }
        
        # Mock successful set
        mock_redis_client.set.return_value = True
        mock_redis_client.get.return_value = json.dumps(complex_data)
        
        # Set complex data
        set_result = await cache_repository_redis.set("complex_key", complex_data)
        assert set_result is True
        
        # Get complex data
        get_result = await cache_repository_redis.get("complex_key")
        assert get_result == complex_data

    @pytest.mark.asyncio
    async def test_cache_key_patterns(
        self,
        cache_repository_memory,
    ):
        """Test various cache key patterns."""
        key_patterns = [
            "simple_key",
            "namespace:key",
            "user:123:profile",
            "workspace:ws_456:documents",
            "job:job_789:status",
        ]
        
        for key in key_patterns:
            value = {"pattern": key, "data": f"value_for_{key}"}
            
            # Set and get each key pattern
            set_result = await cache_repository_memory.set(key, value)
            assert set_result is True
            
            get_result = await cache_repository_memory.get(key)
            assert get_result == value

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(
        self,
        cache_repository_memory,
    ):
        """Test concurrent cache operations."""
        import asyncio
        
        # Concurrent set operations
        set_tasks = [
            cache_repository_memory.set(f"key_{i}", {"value": i})
            for i in range(10)
        ]
        
        set_results = await asyncio.gather(*set_tasks)
        assert all(result is True for result in set_results)
        
        # Concurrent get operations
        get_tasks = [
            cache_repository_memory.get(f"key_{i}")
            for i in range(10)
        ]
        
        get_results = await asyncio.gather(*get_tasks)
        assert len(get_results) == 10
        assert all(result is not None for result in get_results)

    @pytest.mark.asyncio
    async def test_cache_performance_large_data(
        self,
        cache_repository_memory,
    ):
        """Test cache performance with large data sets."""
        # Create large data structure
        large_data = {
            "items": [{"id": i, "data": f"item_{i}" * 100} for i in range(1000)],
            "metadata": {"size": "large", "count": 1000},
        }
        
        import time
        
        # Measure set performance
        start_time = time.time()
        set_result = await cache_repository_memory.set("large_data", large_data)
        set_time = time.time() - start_time
        
        assert set_result is True
        assert set_time < 1.0  # Should complete within 1 second
        
        # Measure get performance
        start_time = time.time()
        get_result = await cache_repository_memory.get("large_data")
        get_time = time.time() - start_time
        
        assert get_result == large_data
        assert get_time < 1.0  # Should complete within 1 second

    @pytest.mark.asyncio
    async def test_cache_cleanup_and_memory_management(
        self,
        cache_repository_memory,
    ):
        """Test cache cleanup and memory management."""
        # Fill cache with data
        for i in range(100):
            await cache_repository_memory.set(f"temp_key_{i}", {"data": i})
        
        # Verify data exists
        exists_results = await asyncio.gather(*[
            cache_repository_memory.exists(f"temp_key_{i}")
            for i in range(10)
        ])
        assert all(exists_results)
        
        # Clean up data
        delete_results = await asyncio.gather(*[
            cache_repository_memory.delete(f"temp_key_{i}")
            for i in range(100)
        ])
        assert all(delete_results)
        
        # Verify data is gone
        final_exists_results = await asyncio.gather(*[
            cache_repository_memory.exists(f"temp_key_{i}")
            for i in range(10)
        ])
        assert not any(final_exists_results)