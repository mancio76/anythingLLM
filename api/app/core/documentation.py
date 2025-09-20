"""API documentation configuration and examples."""

from typing import Any, Dict, List
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def custom_openapi(app: FastAPI) -> Dict[str, Any]:
    """Generate custom OpenAPI schema with enhanced documentation."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=app.servers,
        tags=app.openapi_tags,
    )
    
    # Add custom security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token authentication. Include the token in the Authorization header as 'Bearer <token>'."
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "API key authentication. Include your API key in the X-API-Key header."
        }
    }
    
    # Add global security requirement
    openapi_schema["security"] = [
        {"BearerAuth": []},
        {"ApiKeyAuth": []}
    ]
    
    # Add custom response schemas
    openapi_schema["components"]["schemas"].update(get_custom_schemas())
    
    # Add examples to existing schemas
    add_schema_examples(openapi_schema)
    
    # Add custom response headers
    add_response_headers(openapi_schema)
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def get_custom_schemas() -> Dict[str, Any]:
    """Get custom schema definitions for API documentation."""
    return {
        "RateLimitHeaders": {
            "type": "object",
            "properties": {
                "X-RateLimit-Limit": {
                    "type": "integer",
                    "description": "The maximum number of requests allowed in the current window"
                },
                "X-RateLimit-Remaining": {
                    "type": "integer",
                    "description": "The number of requests remaining in the current window"
                },
                "X-RateLimit-Reset": {
                    "type": "integer",
                    "description": "The time when the current window resets (Unix timestamp)"
                },
                "Retry-After": {
                    "type": "integer",
                    "description": "Number of seconds to wait before making another request (when rate limited)"
                }
            }
        },
        "CorrelationHeaders": {
            "type": "object",
            "properties": {
                "X-Correlation-ID": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique identifier for request tracing and correlation"
                },
                "X-Request-ID": {
                    "type": "string",
                    "format": "uuid",
                    "description": "Unique identifier for this specific request"
                }
            }
        }
    }


def add_schema_examples(openapi_schema: Dict[str, Any]) -> None:
    """Add examples to schema definitions."""
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    
    # Job examples
    if "Job" in schemas:
        schemas["Job"]["example"] = {
            "id": "job_abc123def456",
            "type": "document_upload",
            "status": "processing",
            "workspace_id": "ws_789xyz012",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:05:00Z",
            "started_at": "2024-01-15T10:01:00Z",
            "completed_at": None,
            "progress": 65.5,
            "result": None,
            "error": None,
            "metadata": {
                "user_id": "user_123",
                "username": "analyst@company.com",
                "original_filename": "procurement_docs.zip",
                "file_size": 15728640,
                "project_name": "Q1 Procurement Analysis"
            }
        }
    
    # Workspace examples
    if "Workspace" in schemas:
        schemas["Workspace"]["example"] = {
            "id": "ws_789xyz012",
            "name": "Procurement Analysis Q1",
            "slug": "procurement-analysis-q1",
            "description": "Workspace for analyzing Q1 procurement contracts and documents",
            "config": {
                "llm_config": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "timeout": 30
                },
                "procurement_prompts": True,
                "auto_embed": True,
                "max_documents": 1000
            },
            "document_count": 45,
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
            "status": "active"
        }
    
    # Question examples
    if "QuestionCreate" in schemas:
        schemas["QuestionCreate"]["example"] = {
            "text": "What is the total contract value mentioned in this document?",
            "expected_fragments": [
                "total value",
                "contract amount",
                "total cost",
                "$",
                "USD"
            ],
            "llm_config": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.3,
                "max_tokens": 500,
                "timeout": 30
            }
        }
    
    # Question Result examples
    if "QuestionResult" in schemas:
        schemas["QuestionResult"]["example"] = {
            "question_id": "q_456def789",
            "question_text": "What is the total contract value mentioned in this document?",
            "response": "The total contract value mentioned in this document is $2,450,000 USD, as stated in Section 3.1 of the agreement.",
            "confidence_score": 0.92,
            "processing_time": 3.45,
            "fragments_found": ["total value", "$", "USD"],
            "success": True,
            "error": None,
            "metadata": {
                "llm_model": "gpt-4",
                "thread_id": "thread_abc123",
                "document_sources": ["contract_001.pdf", "amendment_002.pdf"]
            }
        }
    
    # Error Response examples
    if "ErrorResponse" in schemas:
        schemas["ErrorResponse"]["example"] = {
            "error": "ValidationError",
            "message": "Invalid file format. Only ZIP files containing PDF, JSON, or CSV documents are allowed.",
            "details": {
                "field": "file",
                "rejected_files": ["document.docx", "image.png"],
                "allowed_types": ["pdf", "json", "csv"]
            },
            "correlation_id": "req_789abc123def",
            "timestamp": "2024-01-15T10:15:30Z"
        }


def add_response_headers(openapi_schema: Dict[str, Any]) -> None:
    """Add common response headers to all endpoints."""
    paths = openapi_schema.get("paths", {})
    
    common_headers = {
        "X-Correlation-ID": {
            "description": "Unique identifier for request tracing",
            "schema": {"type": "string", "format": "uuid"}
        },
        "X-Request-ID": {
            "description": "Unique identifier for this request",
            "schema": {"type": "string", "format": "uuid"}
        },
        "X-RateLimit-Limit": {
            "description": "Maximum requests allowed in current window",
            "schema": {"type": "integer"}
        },
        "X-RateLimit-Remaining": {
            "description": "Requests remaining in current window",
            "schema": {"type": "integer"}
        },
        "X-RateLimit-Reset": {
            "description": "Time when current window resets (Unix timestamp)",
            "schema": {"type": "integer"}
        }
    }
    
    # Add headers to all successful responses
    for path_data in paths.values():
        for method_data in path_data.values():
            if isinstance(method_data, dict) and "responses" in method_data:
                for status_code, response_data in method_data["responses"].items():
                    if status_code.startswith("2"):  # 2xx success responses
                        if "headers" not in response_data:
                            response_data["headers"] = {}
                        response_data["headers"].update(common_headers)


def get_api_examples() -> Dict[str, Any]:
    """Get comprehensive API usage examples."""
    return {
        "document_upload": {
            "summary": "Upload documents for processing",
            "description": "Upload a ZIP file containing procurement documents",
            "request": {
                "method": "POST",
                "url": "/api/v1/documents/upload",
                "headers": {
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "Content-Type": "multipart/form-data"
                },
                "body": {
                    "file": "<binary_zip_data>",
                    "workspace_id": "ws_789xyz012",
                    "project_name": "Q1 Procurement Analysis",
                    "document_type": "contracts"
                }
            },
            "response": {
                "status": 202,
                "headers": {
                    "X-Correlation-ID": "req_789abc123def",
                    "X-RateLimit-Remaining": "95"
                },
                "body": {
                    "job": {
                        "id": "job_abc123def456",
                        "type": "document_upload",
                        "status": "pending",
                        "workspace_id": "ws_789xyz012",
                        "created_at": "2024-01-15T10:00:00Z",
                        "progress": 0.0
                    },
                    "links": {
                        "status": "/api/v1/documents/jobs/job_abc123def456",
                        "cancel": "/api/v1/documents/jobs/job_abc123def456"
                    },
                    "estimated_completion": "2024-01-15T10:15:00Z"
                }
            }
        },
        "workspace_creation": {
            "summary": "Create a new workspace",
            "description": "Create a workspace with procurement-specific configuration",
            "request": {
                "method": "POST",
                "url": "/api/v1/workspaces",
                "headers": {
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "Content-Type": "application/json"
                },
                "body": {
                    "name": "Procurement Analysis Q1",
                    "description": "Workspace for analyzing Q1 procurement contracts",
                    "config": {
                        "llm_config": {
                            "provider": "openai",
                            "model": "gpt-4",
                            "temperature": 0.7,
                            "max_tokens": 2000,
                            "timeout": 30
                        },
                        "procurement_prompts": True,
                        "auto_embed": True,
                        "max_documents": 1000
                    }
                }
            },
            "response": {
                "status": 201,
                "body": {
                    "workspace": {
                        "id": "ws_789xyz012",
                        "name": "Procurement Analysis Q1",
                        "slug": "procurement-analysis-q1",
                        "status": "active"
                    },
                    "links": {
                        "self": "/api/v1/workspaces/ws_789xyz012",
                        "documents": "/api/v1/workspaces/ws_789xyz012/documents",
                        "questions": "/api/v1/workspaces/ws_789xyz012/questions"
                    }
                }
            }
        },
        "question_execution": {
            "summary": "Execute questions against workspace",
            "description": "Run automated questions against documents in a workspace",
            "request": {
                "method": "POST",
                "url": "/api/v1/questions/execute",
                "headers": {
                    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "Content-Type": "application/json"
                },
                "body": {
                    "workspace_id": "ws_789xyz012",
                    "questions": [
                        {
                            "text": "What is the total contract value?",
                            "expected_fragments": ["total value", "$", "USD"]
                        },
                        {
                            "text": "Who are the contracting parties?",
                            "expected_fragments": ["party", "contractor", "client"]
                        }
                    ],
                    "llm_config": {
                        "provider": "openai",
                        "model": "gpt-4",
                        "temperature": 0.3
                    },
                    "max_concurrent": 3,
                    "timeout": 300
                }
            },
            "response": {
                "status": 202,
                "body": {
                    "job": {
                        "id": "job_def456ghi789",
                        "type": "question_processing",
                        "status": "pending",
                        "workspace_id": "ws_789xyz012",
                        "progress": 0.0
                    },
                    "links": {
                        "status": "/api/v1/questions/jobs/job_def456ghi789",
                        "results": "/api/v1/questions/jobs/job_def456ghi789/results"
                    }
                }
            }
        },
        "error_responses": {
            "validation_error": {
                "status": 422,
                "body": {
                    "error": "ValidationError",
                    "message": "Request validation failed",
                    "details": {
                        "field": "questions",
                        "error": "At least one question is required"
                    },
                    "correlation_id": "req_error123",
                    "timestamp": "2024-01-15T10:15:30Z"
                }
            },
            "rate_limit_error": {
                "status": 429,
                "headers": {
                    "Retry-After": "3600",
                    "X-RateLimit-Reset": "1705320000"
                },
                "body": {
                    "error": "RateLimitExceeded",
                    "message": "Rate limit exceeded. Please try again later.",
                    "details": {
                        "limit": 100,
                        "window": "1 hour",
                        "reset_time": "2024-01-15T11:00:00Z"
                    },
                    "correlation_id": "req_rate123",
                    "timestamp": "2024-01-15T10:15:30Z"
                }
            },
            "authentication_error": {
                "status": 401,
                "body": {
                    "error": "AuthenticationRequired",
                    "message": "Valid authentication credentials are required",
                    "details": {
                        "supported_methods": ["Bearer token", "API key"],
                        "headers": ["Authorization", "X-API-Key"]
                    },
                    "correlation_id": "req_auth123",
                    "timestamp": "2024-01-15T10:15:30Z"
                }
            }
        }
    }


def get_authentication_examples() -> Dict[str, Any]:
    """Get authentication examples for API documentation."""
    return {
        "jwt_bearer": {
            "description": "JWT Bearer token authentication",
            "example": {
                "header": "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMyIsImV4cCI6MTcwNTMyMDAwMH0.signature",
                "curl": """curl -X GET "https://api.example.com/api/v1/workspaces" \\
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                """,
                "javascript": """
fetch('https://api.example.com/api/v1/workspaces', {
  headers: {
    'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
  }
});
                """,
                "python": """
import requests

headers = {
    'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
}
response = requests.get('https://api.example.com/api/v1/workspaces', headers=headers)
                """
            }
        },
        "api_key": {
            "description": "API key authentication",
            "example": {
                "header": "X-API-Key: ak_1234567890abcdef",
                "curl": """curl -X GET "https://api.example.com/api/v1/workspaces" \\
  -H "X-API-Key: ak_1234567890abcdef"
                """,
                "javascript": """
fetch('https://api.example.com/api/v1/workspaces', {
  headers: {
    'X-API-Key': 'ak_1234567890abcdef'
  }
});
                """,
                "python": """
import requests

headers = {
    'X-API-Key': 'ak_1234567890abcdef'
}
response = requests.get('https://api.example.com/api/v1/workspaces', headers=headers)
                """
            }
        }
    }


def get_error_code_documentation() -> Dict[str, Any]:
    """Get comprehensive error code documentation."""
    return {
        "400": {
            "name": "Bad Request",
            "description": "The request was invalid or cannot be processed",
            "common_causes": [
                "Invalid file format (non-ZIP files)",
                "Unsupported document types in ZIP",
                "Invalid workspace configuration",
                "Malformed request body"
            ],
            "example": {
                "error": "ValidationError",
                "message": "Invalid file format. Only ZIP files are allowed.",
                "details": {
                    "field": "file",
                    "provided_type": "application/pdf",
                    "expected_type": "application/zip"
                }
            }
        },
        "401": {
            "name": "Unauthorized",
            "description": "Authentication credentials are missing or invalid",
            "common_causes": [
                "Missing Authorization header",
                "Invalid JWT token",
                "Expired token",
                "Invalid API key"
            ],
            "example": {
                "error": "AuthenticationRequired",
                "message": "Valid authentication credentials are required",
                "details": {
                    "supported_methods": ["Bearer token", "API key"]
                }
            }
        },
        "403": {
            "name": "Forbidden",
            "description": "The request is understood but access is denied",
            "common_causes": [
                "Insufficient permissions",
                "Access to workspace denied",
                "Resource ownership restrictions",
                "Admin-only operation"
            ],
            "example": {
                "error": "AccessDenied",
                "message": "Access denied to this workspace",
                "details": {
                    "resource": "workspace",
                    "resource_id": "ws_789xyz012",
                    "required_permission": "read"
                }
            }
        },
        "404": {
            "name": "Not Found",
            "description": "The requested resource was not found",
            "common_causes": [
                "Invalid job ID",
                "Workspace not found",
                "Deleted or expired resource",
                "Incorrect URL path"
            ],
            "example": {
                "error": "ResourceNotFound",
                "message": "Job job_abc123 not found",
                "details": {
                    "resource_type": "job",
                    "resource_id": "job_abc123"
                }
            }
        },
        "409": {
            "name": "Conflict",
            "description": "The request conflicts with the current state",
            "common_causes": [
                "Workspace name already exists",
                "Job cannot be cancelled in current state",
                "Resource is being modified by another process",
                "Concurrent modification conflict"
            ],
            "example": {
                "error": "ConflictError",
                "message": "Job cannot be cancelled - current status: completed",
                "details": {
                    "current_status": "completed",
                    "allowed_statuses": ["pending", "processing"]
                }
            }
        },
        "413": {
            "name": "Payload Too Large",
            "description": "The request payload exceeds size limits",
            "common_causes": [
                "ZIP file too large",
                "Too many files in ZIP",
                "Individual file size exceeded",
                "Request body too large"
            ],
            "example": {
                "error": "PayloadTooLarge",
                "message": "File size 150MB exceeds maximum allowed size 100MB",
                "details": {
                    "file_size": 157286400,
                    "max_size": 104857600,
                    "size_limit": "100MB"
                }
            }
        },
        "422": {
            "name": "Unprocessable Entity",
            "description": "The request is well-formed but contains semantic errors",
            "common_causes": [
                "Invalid field values",
                "Missing required fields",
                "Field validation failures",
                "Invalid date formats"
            ],
            "example": {
                "error": "ValidationError",
                "message": "Request validation failed",
                "details": {
                    "field": "llm_config.temperature",
                    "value": 3.5,
                    "constraint": "must be between 0.0 and 2.0"
                }
            }
        },
        "429": {
            "name": "Too Many Requests",
            "description": "Rate limit exceeded",
            "common_causes": [
                "Too many requests per hour",
                "Concurrent request limit exceeded",
                "API quota exhausted",
                "Burst limit exceeded"
            ],
            "example": {
                "error": "RateLimitExceeded",
                "message": "Rate limit exceeded. Please try again later.",
                "details": {
                    "limit": 100,
                    "window": "1 hour",
                    "reset_time": "2024-01-15T11:00:00Z"
                }
            }
        },
        "500": {
            "name": "Internal Server Error",
            "description": "An unexpected error occurred on the server",
            "common_causes": [
                "Database connection failure",
                "External service unavailable",
                "Unexpected application error",
                "Configuration issues"
            ],
            "example": {
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "details": {
                    "error_id": "err_abc123def456",
                    "support_contact": "support@example.com"
                }
            }
        },
        "502": {
            "name": "Bad Gateway",
            "description": "Error communicating with upstream services",
            "common_causes": [
                "AnythingLLM service unavailable",
                "Database connection timeout",
                "Redis connection failure",
                "External API errors"
            ],
            "example": {
                "error": "BadGateway",
                "message": "AnythingLLM service is currently unavailable",
                "details": {
                    "service": "anythingllm",
                    "status": "unavailable",
                    "retry_after": 60
                }
            }
        },
        "503": {
            "name": "Service Unavailable",
            "description": "The service is temporarily unavailable",
            "common_causes": [
                "System maintenance",
                "Service overload",
                "Resource exhaustion",
                "Graceful degradation active"
            ],
            "example": {
                "error": "ServiceUnavailable",
                "message": "Service is temporarily unavailable due to maintenance",
                "details": {
                    "maintenance_window": "2024-01-15T02:00:00Z to 2024-01-15T04:00:00Z",
                    "estimated_recovery": "2024-01-15T04:00:00Z"
                }
            }
        }
    }