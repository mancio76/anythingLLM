"""API versioning strategy and backward compatibility management."""

from enum import Enum
from typing import Dict, List, Optional, Any
from fastapi import Request, HTTPException, status
from pydantic import BaseModel


class APIVersion(str, Enum):
    """Supported API versions."""
    V1 = "v1"
    # Future versions can be added here
    # V2 = "v2"


class VersionInfo(BaseModel):
    """Version information model."""
    version: str
    status: str  # "stable", "deprecated", "beta"
    release_date: str
    deprecation_date: Optional[str] = None
    sunset_date: Optional[str] = None
    changelog_url: Optional[str] = None
    migration_guide_url: Optional[str] = None


class APIVersionManager:
    """Manages API versioning and backward compatibility."""
    
    def __init__(self):
        self.versions = {
            APIVersion.V1: VersionInfo(
                version="1.0.0",
                status="stable",
                release_date="2024-01-15",
                changelog_url="https://docs.example.com/changelog/v1",
                migration_guide_url="https://docs.example.com/migration/v1"
            )
        }
        self.default_version = APIVersion.V1
        self.supported_versions = [APIVersion.V1]
        self.deprecated_versions: List[APIVersion] = []
    
    def get_version_from_request(self, request: Request) -> APIVersion:
        """
        Extract API version from request.
        
        Version can be specified in:
        1. URL path: /api/v1/...
        2. Accept header: Accept: application/vnd.api+json;version=1
        3. Custom header: API-Version: v1
        4. Query parameter: ?version=v1
        
        Args:
            request: FastAPI request object
            
        Returns:
            APIVersion enum value
            
        Raises:
            HTTPException: If version is not supported
        """
        # 1. Check URL path (primary method)
        path_parts = request.url.path.split('/')
        if len(path_parts) >= 3 and path_parts[2].startswith('v'):
            version_str = path_parts[2]
            try:
                return APIVersion(version_str)
            except ValueError:
                pass
        
        # 2. Check API-Version header
        version_header = request.headers.get("API-Version")
        if version_header:
            try:
                return APIVersion(version_header.lower())
            except ValueError:
                pass
        
        # 3. Check Accept header
        accept_header = request.headers.get("Accept", "")
        if "version=" in accept_header:
            import re
            version_match = re.search(r'version=(\d+)', accept_header)
            if version_match:
                version_num = version_match.group(1)
                try:
                    return APIVersion(f"v{version_num}")
                except ValueError:
                    pass
        
        # 4. Check query parameter
        version_param = request.query_params.get("version")
        if version_param:
            try:
                if not version_param.startswith('v'):
                    version_param = f"v{version_param}"
                return APIVersion(version_param)
            except ValueError:
                pass
        
        # 5. Return default version
        return self.default_version
    
    def validate_version(self, version: APIVersion) -> None:
        """
        Validate that the requested version is supported.
        
        Args:
            version: API version to validate
            
        Raises:
            HTTPException: If version is not supported or deprecated
        """
        if version not in self.supported_versions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"API version {version.value} is not supported. "
                       f"Supported versions: {[v.value for v in self.supported_versions]}",
                headers={
                    "Supported-Versions": ", ".join(v.value for v in self.supported_versions)
                }
            )
        
        if version in self.deprecated_versions:
            version_info = self.versions[version]
            headers = {
                "Deprecation": "true",
                "Sunset": version_info.sunset_date or "TBD"
            }
            if version_info.migration_guide_url:
                headers["Link"] = f'<{version_info.migration_guide_url}>; rel="migration-guide"'
            
            # For deprecated versions, add warning headers but don't fail
            # The actual deprecation handling would be done in middleware
    
    def get_version_info(self, version: APIVersion) -> VersionInfo:
        """Get information about a specific API version."""
        return self.versions.get(version, VersionInfo(
            version="unknown",
            status="unsupported",
            release_date="unknown"
        ))
    
    def get_all_versions(self) -> Dict[str, VersionInfo]:
        """Get information about all API versions."""
        return {v.value: info for v, info in self.versions.items()}
    
    def is_version_deprecated(self, version: APIVersion) -> bool:
        """Check if a version is deprecated."""
        return version in self.deprecated_versions
    
    def get_migration_path(self, from_version: APIVersion, to_version: APIVersion) -> Dict[str, Any]:
        """
        Get migration information between versions.
        
        Args:
            from_version: Source version
            to_version: Target version
            
        Returns:
            Migration information including breaking changes and migration steps
        """
        # This would contain actual migration logic between versions
        # For now, return basic information
        return {
            "from_version": from_version.value,
            "to_version": to_version.value,
            "breaking_changes": [],
            "migration_steps": [],
            "automated_migration": False,
            "migration_guide_url": self.versions[to_version].migration_guide_url
        }


# Global version manager instance
version_manager = APIVersionManager()


def get_version_manager() -> APIVersionManager:
    """Get the global version manager instance."""
    return version_manager


class VersioningMiddleware:
    """Middleware to handle API versioning."""
    
    def __init__(self, app, version_manager: APIVersionManager):
        self.app = app
        self.version_manager = version_manager
    
    async def __call__(self, scope, receive, send):
        """Process request with version handling."""
        if scope["type"] == "http":
            request = Request(scope, receive)
            
            try:
                # Extract and validate version
                version = self.version_manager.get_version_from_request(request)
                self.version_manager.validate_version(version)
                
                # Add version info to request state
                scope["state"] = getattr(scope, "state", {})
                scope["state"]["api_version"] = version
                scope["state"]["version_info"] = self.version_manager.get_version_info(version)
                
                # Add deprecation headers if needed
                if self.version_manager.is_version_deprecated(version):
                    version_info = self.version_manager.get_version_info(version)
                    
                    async def send_with_deprecation_headers(message):
                        if message["type"] == "http.response.start":
                            headers = list(message.get("headers", []))
                            headers.append((b"deprecation", b"true"))
                            if version_info.sunset_date:
                                headers.append((b"sunset", version_info.sunset_date.encode()))
                            if version_info.migration_guide_url:
                                headers.append((
                                    b"link",
                                    f'<{version_info.migration_guide_url}>; rel="migration-guide"'.encode()
                                ))
                            message["headers"] = headers
                        await send(message)
                    
                    await self.app(scope, receive, send_with_deprecation_headers)
                else:
                    await self.app(scope, receive, send)
                    
            except HTTPException as e:
                # Handle version validation errors
                import json
                
                response = {
                    "type": "http.response.start",
                    "status": e.status_code,
                    "headers": [
                        (b"content-type", b"application/json"),
                        *[(k.encode(), v.encode()) for k, v in (e.headers or {}).items()]
                    ]
                }
                await send(response)
                
                body = {
                    "error": "UnsupportedVersion",
                    "message": e.detail,
                    "supported_versions": [v.value for v in self.version_manager.supported_versions]
                }
                
                await send({
                    "type": "http.response.body",
                    "body": json.dumps(body).encode()
                })
        else:
            await self.app(scope, receive, send)


def get_backward_compatibility_info() -> Dict[str, Any]:
    """Get backward compatibility information for documentation."""
    return {
        "versioning_strategy": {
            "type": "URL path versioning",
            "format": "/api/{version}/...",
            "example": "/api/v1/documents/upload",
            "fallback_methods": [
                "API-Version header",
                "Accept header with version parameter",
                "Query parameter"
            ]
        },
        "version_lifecycle": {
            "stable": "Fully supported, no breaking changes",
            "deprecated": "Still supported but will be removed in future",
            "sunset": "No longer supported, returns 410 Gone"
        },
        "breaking_change_policy": {
            "major_version": "Breaking changes allowed",
            "minor_version": "Backward compatible additions only",
            "patch_version": "Bug fixes and security updates only"
        },
        "deprecation_process": {
            "announcement": "6 months before deprecation",
            "deprecation_period": "12 months minimum",
            "migration_support": "Documentation and tooling provided",
            "sunset_notice": "3 months before removal"
        },
        "compatibility_guarantees": [
            "Request/response schemas remain compatible within major version",
            "HTTP status codes remain consistent",
            "Authentication methods remain supported",
            "Rate limiting behavior remains consistent"
        ]
    }