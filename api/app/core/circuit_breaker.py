"""Circuit breaker implementation for resilience."""

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional, TypeVar, Union
from dataclasses import dataclass, field

from app.core.exceptions import CircuitBreakerOpenError


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    timeout: int = 60  # seconds
    expected_exception: Union[type, tuple] = Exception
    success_threshold: int = 3  # for half-open state


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changed_time: float = field(default_factory=time.time)


T = TypeVar('T')


class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.stats = CircuitBreakerStats()
        self.state = CircuitState.CLOSED
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            await self._update_state()
            
            if self.state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    service=self.name,
                    retry_after=self._get_retry_after()
                )
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            await self._on_success()
            return result
        except self.config.expected_exception as e:
            await self._on_failure()
            raise e
    
    async def _update_state(self):
        """Update circuit breaker state based on current conditions."""
        current_time = time.time()
        
        if self.state == CircuitState.OPEN:
            if current_time - self.stats.state_changed_time >= self.config.timeout:
                self.state = CircuitState.HALF_OPEN
                self.stats.state_changed_time = current_time
                self.stats.success_count = 0
        
        elif self.state == CircuitState.HALF_OPEN:
            if self.stats.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.stats.state_changed_time = current_time
                self.stats.failure_count = 0
    
    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self.stats.success_count += 1
            self.stats.last_success_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                if self.stats.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.stats.state_changed_time = time.time()
                    self.stats.failure_count = 0
    
    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.stats.failure_count += 1
            self.stats.last_failure_time = time.time()
            
            if self.state == CircuitState.CLOSED:
                if self.stats.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.stats.state_changed_time = time.time()
            
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.stats.state_changed_time = time.time()
    
    def _get_retry_after(self) -> int:
        """Get retry after time in seconds."""
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.stats.state_changed_time
            return max(0, int(self.config.timeout - elapsed))
        return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.stats.failure_count,
            "success_count": self.stats.success_count,
            "last_failure_time": self.stats.last_failure_time,
            "last_success_time": self.stats.last_success_time,
            "state_changed_time": self.stats.state_changed_time,
            "retry_after": self._get_retry_after() if self.state == CircuitState.OPEN else None,
        }


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {name: breaker.get_stats() for name, breaker in self._breakers.items()}
    
    def reset_breaker(self, name: str):
        """Reset a circuit breaker to closed state."""
        if name in self._breakers:
            breaker = self._breakers[name]
            breaker.state = CircuitState.CLOSED
            breaker.stats = CircuitBreakerStats()


# Global circuit breaker registry
circuit_breaker_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get a circuit breaker from the global registry."""
    return circuit_breaker_registry.get_breaker(name, config)