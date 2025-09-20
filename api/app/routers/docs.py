"""API documentation and information endpoints."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.versioning import get_version_manager, get_backward_compatibility_info
from app.core.documentation import (
    get_api_examples,
    get_authentication_examples,
    get_error_code_documentation
)

logger = logging.getLogger(__name__)

# Documentation endpoints should be public (no authentication required)
router = APIRouter(
    prefix="/docs", 
    tags=["documentation"],
    dependencies=[]  # No authentication dependencies
)


@router.get("/versions")
async def get_api_versions():
    """
    Get information about all API versions.
    
    Returns version information including status, release dates,
    deprecation information, and migration guides.
    """
    version_manager = get_version_manager()
    versions = version_manager.get_all_versions()
    
    return {
        "versions": versions,
        "default_version": version_manager.default_version.value,
        "supported_versions": [v.value for v in version_manager.supported_versions],
        "deprecated_versions": [v.value for v in version_manager.deprecated_versions],
        "backward_compatibility": get_backward_compatibility_info()
    }


@router.get("/examples")
async def get_usage_examples():
    """
    Get comprehensive API usage examples.
    
    Returns examples for common API operations including
    request/response formats, authentication, and error handling.
    """
    return {
        "api_examples": get_api_examples(),
        "authentication": get_authentication_examples(),
        "error_codes": get_error_code_documentation()
    }


@router.get("/authentication")
async def get_authentication_info():
    """
    Get detailed authentication information.
    
    Returns information about supported authentication methods,
    token formats, and usage examples.
    """
    return {
        "methods": {
            "jwt_bearer": {
                "description": "JWT Bearer token authentication",
                "header": "Authorization: Bearer <token>",
                "format": "JWT (JSON Web Token)",
                "expiration": "Configurable (default: 1 hour)",
                "refresh": "Not supported (obtain new token)",
                "scopes": ["read", "write", "admin"]
            },
            "api_key": {
                "description": "API key authentication",
                "header": "X-API-Key: <key>",
                "format": "Alphanumeric string with prefix",
                "expiration": "No expiration (revocable)",
                "refresh": "Not applicable",
                "scopes": "Configured per key"
            }
        },
        "examples": get_authentication_examples(),
        "security_considerations": {
            "token_storage": "Store tokens securely, never in client-side code",
            "https_required": "Always use HTTPS in production",
            "token_rotation": "Rotate tokens regularly",
            "scope_limitation": "Use minimum required scopes",
            "rate_limiting": "Respect rate limits to avoid blocking"
        }
    }


@router.get("/errors")
async def get_error_documentation():
    """
    Get comprehensive error code documentation.
    
    Returns detailed information about all possible error responses,
    including status codes, error types, and resolution guidance.
    """
    return {
        "error_format": {
            "description": "All errors follow a consistent JSON format",
            "schema": {
                "error": "Error type identifier (string)",
                "message": "Human-readable error message (string)",
                "details": "Additional error context (object, optional)",
                "correlation_id": "Request correlation ID for tracing (string)",
                "timestamp": "Error occurrence time in ISO format (string)"
            }
        },
        "status_codes": get_error_code_documentation(),
        "error_handling_best_practices": {
            "retry_logic": "Implement exponential backoff for 5xx errors",
            "correlation_tracking": "Use correlation_id for support requests",
            "validation_errors": "Check details field for specific validation failures",
            "rate_limiting": "Respect Retry-After header for 429 responses",
            "circuit_breaker": "Implement circuit breaker for repeated failures"
        }
    }


@router.get("/rate-limits")
async def get_rate_limit_info():
    """
    Get rate limiting information.
    
    Returns details about rate limits, headers, and best practices
    for handling rate-limited requests.
    """
    return {
        "default_limits": {
            "requests_per_hour": 100,
            "burst_limit": 10,
            "concurrent_requests": 5
        },
        "headers": {
            "X-RateLimit-Limit": "Maximum requests allowed in current window",
            "X-RateLimit-Remaining": "Requests remaining in current window",
            "X-RateLimit-Reset": "Time when current window resets (Unix timestamp)",
            "Retry-After": "Seconds to wait before next request (when rate limited)"
        },
        "response_codes": {
            "200": "Request successful, check rate limit headers",
            "429": "Rate limit exceeded, check Retry-After header"
        },
        "best_practices": {
            "check_headers": "Always check rate limit headers in responses",
            "implement_backoff": "Use exponential backoff when rate limited",
            "batch_requests": "Batch operations when possible to reduce request count",
            "cache_responses": "Cache responses to reduce API calls",
            "monitor_usage": "Monitor your usage patterns and adjust accordingly"
        },
        "exemptions": {
            "health_checks": "Health check endpoints have higher limits",
            "authentication": "Authentication endpoints have separate limits",
            "admin_users": "Admin users may have higher limits"
        }
    }


@router.get("/webhooks")
async def get_webhook_info():
    """
    Get webhook information (future feature).
    
    Returns information about webhook support, event types,
    and configuration options.
    """
    return {
        "status": "planned",
        "description": "Webhook support is planned for future releases",
        "planned_events": [
            "job.completed",
            "job.failed",
            "workspace.created",
            "workspace.deleted",
            "document.processed",
            "question.completed"
        ],
        "planned_features": {
            "event_filtering": "Subscribe to specific event types",
            "retry_logic": "Automatic retry with exponential backoff",
            "signature_verification": "HMAC signature verification",
            "delivery_confirmation": "Delivery status tracking",
            "payload_customization": "Customize webhook payload format"
        },
        "timeline": "Target: Q2 2024"
    }


@router.get("/sdk")
async def get_sdk_info():
    """
    Get SDK and client library information.
    
    Returns information about available SDKs, client libraries,
    and code examples for different programming languages.
    """
    return {
        "official_sdks": {
            "status": "planned",
            "languages": ["Python", "JavaScript/TypeScript", "Go", "Java"],
            "timeline": "Target: Q2 2024"
        },
        "community_libraries": {
            "status": "welcome",
            "description": "Community-contributed libraries are welcome",
            "guidelines": "https://docs.example.com/community-sdk-guidelines"
        },
        "code_examples": {
            "python": {
                "installation": "pip install anythingllm-api-client",
                "basic_usage": """
from anythingllm_api import Client

client = Client(api_key="your-api-key")
workspaces = client.workspaces.list()
                """,
                "async_usage": """
import asyncio
from anythingllm_api import AsyncClient

async def main():
    async with AsyncClient(api_key="your-api-key") as client:
        workspaces = await client.workspaces.list()

asyncio.run(main())
                """
            },
            "javascript": {
                "installation": "npm install @anythingllm/api-client",
                "basic_usage": """
import { AnythingLLMClient } from '@anythingllm/api-client';

const client = new AnythingLLMClient({ apiKey: 'your-api-key' });
const workspaces = await client.workspaces.list();
                """,
                "node_usage": """
const { AnythingLLMClient } = require('@anythingllm/api-client');

const client = new AnythingLLMClient({ apiKey: 'your-api-key' });
client.workspaces.list().then(workspaces => {
    console.log(workspaces);
});
                """
            }
        },
        "openapi_generators": {
            "description": "Generate clients using OpenAPI specification",
            "openapi_url": "/api/v1/openapi.json",
            "generators": [
                "openapi-generator",
                "swagger-codegen",
                "autorest"
            ],
            "example_command": "openapi-generator generate -i /api/v1/openapi.json -g python -o ./python-client"
        }
    }


@router.get("/changelog")
async def get_changelog():
    """
    Get API changelog information.
    
    Returns recent changes, version history, and migration information.
    """
    return {
        "current_version": "1.0.0",
        "releases": {
            "1.0.0": {
                "release_date": "2024-01-15",
                "status": "stable",
                "changes": {
                    "added": [
                        "Initial API release",
                        "Document upload and processing",
                        "Workspace management",
                        "Question processing with multiple LLM models",
                        "Job tracking and status monitoring",
                        "Health checks and metrics",
                        "Comprehensive error handling",
                        "Rate limiting and security features"
                    ],
                    "changed": [],
                    "deprecated": [],
                    "removed": [],
                    "fixed": [],
                    "security": [
                        "JWT and API key authentication",
                        "Request rate limiting",
                        "Input validation and sanitization",
                        "Secure file handling"
                    ]
                },
                "migration_guide": None,
                "breaking_changes": []
            }
        },
        "upcoming": {
            "1.1.0": {
                "planned_date": "2024-03-15",
                "status": "planned",
                "planned_features": [
                    "Webhook support",
                    "Batch operations",
                    "Advanced filtering options",
                    "Performance improvements"
                ]
            },
            "2.0.0": {
                "planned_date": "2024-06-15",
                "status": "planned",
                "planned_features": [
                    "GraphQL API support",
                    "Real-time subscriptions",
                    "Advanced analytics",
                    "Multi-tenant support"
                ],
                "breaking_changes": [
                    "Authentication method changes",
                    "Response format updates",
                    "Deprecated endpoint removal"
                ]
            }
        }
    }


@router.get("/status")
async def get_api_status(request: Request):
    """
    Get current API status and version information.
    
    Returns the current API version being used for this request
    and general API status information.
    """
    # Get version from request state (set by versioning middleware)
    api_version = getattr(request.state, "api_version", "unknown")
    version_info = getattr(request.state, "version_info", None)
    
    return {
        "api_status": "operational",
        "current_version": api_version.value if hasattr(api_version, 'value') else str(api_version),
        "version_info": version_info.model_dump() if version_info else None,
        "server_time": "2024-01-15T10:00:00Z",  # This would be actual server time
        "uptime": "72h 15m 30s",  # This would be actual uptime
        "request_id": request.headers.get("X-Request-ID", "unknown"),
        "correlation_id": request.headers.get("X-Correlation-ID", "unknown")
    }