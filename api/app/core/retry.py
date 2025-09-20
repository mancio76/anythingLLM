"""Retry logic with exponential backoff."""

import asyncio
import logging
import random
import time
from typing import Any, Callable, Optional, TypeVar, Union
from dataclasses import dataclass

from app.core.exceptions import ExternalServiceError


logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RetryConfig:
    """Retry configuration."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        ExternalServiceError,
    )


class RetryHandler:
    """Handler for retry logic with exponential backoff."""
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
    
    async def retry_async(
        self,
        func: Callable[..., T],
        *args,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> T:
        """Retry an async function with exponential backoff."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    f"Attempting call (attempt {attempt + 1}/{self.config.max_retries + 1})",
                    extra={
                        "correlation_id": correlation_id,
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "max_attempts": self.config.max_retries + 1,
                    }
                )
                
                result = await func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(
                        f"Function succeeded after {attempt + 1} attempts",
                        extra={
                            "correlation_id": correlation_id,
                            "function": func.__name__,
                            "attempts": attempt + 1,
                        }
                    )
                
                return result
                
            except self.config.retryable_exceptions as e:
                last_exception = e
                
                if attempt == self.config.max_retries:
                    logger.error(
                        f"Function failed after {attempt + 1} attempts",
                        extra={
                            "correlation_id": correlation_id,
                            "function": func.__name__,
                            "attempts": attempt + 1,
                            "error": str(e),
                        }
                    )
                    break
                
                delay = self._calculate_delay(attempt)
                
                logger.warning(
                    f"Function failed, retrying in {delay:.2f}s",
                    extra={
                        "correlation_id": correlation_id,
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "delay": delay,
                        "error": str(e),
                    }
                )
                
                await asyncio.sleep(delay)
            
            except Exception as e:
                # Non-retryable exception
                logger.error(
                    f"Function failed with non-retryable exception",
                    extra={
                        "correlation_id": correlation_id,
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                raise e
        
        # All retries exhausted
        raise last_exception
    
    def retry_sync(
        self,
        func: Callable[..., T],
        *args,
        correlation_id: Optional[str] = None,
        **kwargs
    ) -> T:
        """Retry a sync function with exponential backoff."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(
                    f"Attempting call (attempt {attempt + 1}/{self.config.max_retries + 1})",
                    extra={
                        "correlation_id": correlation_id,
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "max_attempts": self.config.max_retries + 1,
                    }
                )
                
                result = func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(
                        f"Function succeeded after {attempt + 1} attempts",
                        extra={
                            "correlation_id": correlation_id,
                            "function": func.__name__,
                            "attempts": attempt + 1,
                        }
                    )
                
                return result
                
            except self.config.retryable_exceptions as e:
                last_exception = e
                
                if attempt == self.config.max_retries:
                    logger.error(
                        f"Function failed after {attempt + 1} attempts",
                        extra={
                            "correlation_id": correlation_id,
                            "function": func.__name__,
                            "attempts": attempt + 1,
                            "error": str(e),
                        }
                    )
                    break
                
                delay = self._calculate_delay(attempt)
                
                logger.warning(
                    f"Function failed, retrying in {delay:.2f}s",
                    extra={
                        "correlation_id": correlation_id,
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "delay": delay,
                        "error": str(e),
                    }
                )
                
                time.sleep(delay)
            
            except Exception as e:
                # Non-retryable exception
                logger.error(
                    f"Function failed with non-retryable exception",
                    extra={
                        "correlation_id": correlation_id,
                        "function": func.__name__,
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                raise e
        
        # All retries exhausted
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt."""
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            # Add jitter to prevent thundering herd
            jitter = delay * 0.1 * random.random()
            delay += jitter
        
        return delay


# Global retry handler
default_retry_handler = RetryHandler()


async def retry_async(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> T:
    """Retry an async function with exponential backoff."""
    handler = RetryHandler(config) if config else default_retry_handler
    return await handler.retry_async(func, *args, correlation_id=correlation_id, **kwargs)


def retry_sync(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> T:
    """Retry a sync function with exponential backoff."""
    handler = RetryHandler(config) if config else default_retry_handler
    return handler.retry_sync(func, *args, correlation_id=correlation_id, **kwargs)