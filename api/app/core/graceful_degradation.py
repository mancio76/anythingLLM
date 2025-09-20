"""Graceful degradation system for service overload."""

import asyncio
import logging
import psutil
import time
from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass

from app.core.exceptions import ServiceUnavailableError


logger = logging.getLogger(__name__)


class ServiceLevel(Enum):
    """Service degradation levels."""
    FULL = "full"
    DEGRADED = "degraded"
    MINIMAL = "minimal"
    MAINTENANCE = "maintenance"


@dataclass
class ResourceThresholds:
    """Resource usage thresholds for degradation."""
    cpu_warning: float = 70.0  # CPU percentage
    cpu_critical: float = 85.0
    memory_warning: float = 70.0  # Memory percentage
    memory_critical: float = 85.0
    disk_warning: float = 80.0  # Disk percentage
    disk_critical: float = 90.0
    active_connections_warning: int = 100
    active_connections_critical: int = 200


@dataclass
class ServiceLimits:
    """Service limits for different degradation levels."""
    full_service: Dict[str, Any] = None
    degraded_service: Dict[str, Any] = None
    minimal_service: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.full_service is None:
            self.full_service = {
                "max_concurrent_uploads": 10,
                "max_concurrent_questions": 5,
                "max_file_size": 100 * 1024 * 1024,  # 100MB
                "enable_caching": True,
                "enable_metrics": True,
                "enable_detailed_logging": True,
            }
        
        if self.degraded_service is None:
            self.degraded_service = {
                "max_concurrent_uploads": 5,
                "max_concurrent_questions": 3,
                "max_file_size": 50 * 1024 * 1024,  # 50MB
                "enable_caching": True,
                "enable_metrics": True,
                "enable_detailed_logging": False,
            }
        
        if self.minimal_service is None:
            self.minimal_service = {
                "max_concurrent_uploads": 2,
                "max_concurrent_questions": 1,
                "max_file_size": 10 * 1024 * 1024,  # 10MB
                "enable_caching": False,
                "enable_metrics": False,
                "enable_detailed_logging": False,
            }


class GracefulDegradationManager:
    """Manager for graceful service degradation."""
    
    def __init__(
        self,
        thresholds: Optional[ResourceThresholds] = None,
        limits: Optional[ServiceLimits] = None,
    ):
        self.thresholds = thresholds or ResourceThresholds()
        self.limits = limits or ServiceLimits()
        self.current_level = ServiceLevel.FULL
        self.active_connections = 0
        self.last_check_time = 0
        self.check_interval = 30  # seconds
        self._lock = asyncio.Lock()
    
    async def check_and_update_service_level(self) -> ServiceLevel:
        """Check system resources and update service level."""
        current_time = time.time()
        
        # Rate limit resource checks
        if current_time - self.last_check_time < self.check_interval:
            return self.current_level
        
        async with self._lock:
            try:
                # Get system resource usage
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # Determine appropriate service level
                new_level = self._determine_service_level(
                    cpu_percent,
                    memory.percent,
                    disk.percent,
                    self.active_connections
                )
                
                # Update service level if changed
                if new_level != self.current_level:
                    old_level = self.current_level
                    self.current_level = new_level
                    
                    logger.warning(
                        f"Service level changed from {old_level.value} to {new_level.value}",
                        extra={
                            "old_level": old_level.value,
                            "new_level": new_level.value,
                            "cpu_percent": cpu_percent,
                            "memory_percent": memory.percent,
                            "disk_percent": disk.percent,
                            "active_connections": self.active_connections,
                        }
                    )
                
                self.last_check_time = current_time
                return self.current_level
                
            except Exception as e:
                logger.error(f"Error checking system resources: {e}")
                return self.current_level
    
    def _determine_service_level(
        self,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        connections: int,
    ) -> ServiceLevel:
        """Determine appropriate service level based on resource usage."""
        # Check for critical conditions (minimal service)
        if (
            cpu_percent >= self.thresholds.cpu_critical or
            memory_percent >= self.thresholds.memory_critical or
            disk_percent >= self.thresholds.disk_critical or
            connections >= self.thresholds.active_connections_critical
        ):
            return ServiceLevel.MINIMAL
        
        # Check for warning conditions (degraded service)
        if (
            cpu_percent >= self.thresholds.cpu_warning or
            memory_percent >= self.thresholds.memory_warning or
            disk_percent >= self.thresholds.disk_warning or
            connections >= self.thresholds.active_connections_warning
        ):
            return ServiceLevel.DEGRADED
        
        # Normal conditions (full service)
        return ServiceLevel.FULL
    
    def get_current_limits(self) -> Dict[str, Any]:
        """Get current service limits based on degradation level."""
        if self.current_level == ServiceLevel.FULL:
            return self.limits.full_service
        elif self.current_level == ServiceLevel.DEGRADED:
            return self.limits.degraded_service
        elif self.current_level == ServiceLevel.MINIMAL:
            return self.limits.minimal_service
        else:  # MAINTENANCE
            return {}
    
    def check_operation_allowed(self, operation: str) -> bool:
        """Check if an operation is allowed at current service level."""
        if self.current_level == ServiceLevel.MAINTENANCE:
            return False
        
        limits = self.get_current_limits()
        
        # Check specific operation limits
        if operation == "upload" and self.active_connections >= limits.get("max_concurrent_uploads", 0):
            return False
        elif operation == "questions" and self.active_connections >= limits.get("max_concurrent_questions", 0):
            return False
        
        return True
    
    def validate_file_size(self, file_size: int) -> bool:
        """Validate file size against current limits."""
        limits = self.get_current_limits()
        max_size = limits.get("max_file_size", 0)
        return file_size <= max_size
    
    def increment_connections(self):
        """Increment active connection count."""
        self.active_connections += 1
    
    def decrement_connections(self):
        """Decrement active connection count."""
        self.active_connections = max(0, self.active_connections - 1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current degradation status."""
        try:
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "service_level": self.current_level.value,
                "active_connections": self.active_connections,
                "resource_usage": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "disk_percent": disk.percent,
                },
                "thresholds": {
                    "cpu_warning": self.thresholds.cpu_warning,
                    "cpu_critical": self.thresholds.cpu_critical,
                    "memory_warning": self.thresholds.memory_warning,
                    "memory_critical": self.thresholds.memory_critical,
                    "disk_warning": self.thresholds.disk_warning,
                    "disk_critical": self.thresholds.disk_critical,
                },
                "current_limits": self.get_current_limits(),
                "last_check_time": self.last_check_time,
            }
        except Exception as e:
            logger.error(f"Error getting degradation status: {e}")
            return {
                "service_level": self.current_level.value,
                "active_connections": self.active_connections,
                "error": str(e),
            }
    
    def set_maintenance_mode(self, enabled: bool):
        """Enable or disable maintenance mode."""
        if enabled:
            self.current_level = ServiceLevel.MAINTENANCE
            logger.warning("Service set to maintenance mode")
        else:
            self.current_level = ServiceLevel.FULL
            logger.info("Service restored from maintenance mode")


# Global degradation manager
degradation_manager = GracefulDegradationManager()


def get_degradation_manager() -> GracefulDegradationManager:
    """Get the global degradation manager."""
    return degradation_manager


async def check_service_availability(operation: str = "general"):
    """Check if service is available for the given operation."""
    manager = get_degradation_manager()
    await manager.check_and_update_service_level()
    
    if not manager.check_operation_allowed(operation):
        raise ServiceUnavailableError(
            message=f"Service temporarily unavailable for {operation} operations",
            retry_after=60,
        )