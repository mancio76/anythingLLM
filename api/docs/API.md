# API Documentation

## Overview

The AnythingLLM API provides endpoints for document processing, workspace management, and automated question-answer testing.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

The API supports two authentication methods:

### 1. API Key Authentication
Include the API key in the request header:
```http
X-API-Key: your-api-key-here
```

### 2. JWT Token Authentication
Include the JWT token in the Authorization header:
```http
Authorization: Bearer your-jwt-token-here
```

## Health Check Endpoints

### Basic Health Check
```http
GET /api/v1/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "version": "1.0.0"
}
```

### Detailed Health Check
```http
GET /api/v1/health/detailed
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "version": "1.0.0",
  "services": {
    "database": {
      "status": "healthy",
      "message": "Connection successful"
    },
    "redis": {
      "status": "healthy",
      "message": "Connection successful"
    },
    "anythingllm": {
      "status": "healthy",
      "message": "API accessible"
    }
  }
}
```

## Error Responses

All endpoints return consistent error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": {
      "field": "email",
      "issue": "Invalid email format"
    }
  },
  "correlation_id": "abc123-def456"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `AUTHENTICATION_ERROR` | 401 | Invalid or missing authentication |
| `AUTHORIZATION_ERROR` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

## Rate Limiting

API requests are rate-limited per user/IP address:
- **Default**: 100 requests per hour
- **Headers**: Rate limit information is included in response headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642248600
```

## Request/Response Format

### Content Types
- **Request**: `application/json` or `multipart/form-data` (for file uploads)
- **Response**: `application/json`

### Common Headers
```http
Content-Type: application/json
X-Correlation-ID: abc123-def456
X-Process-Time: 0.123
```

## Pagination

List endpoints support pagination:

```http
GET /api/v1/documents?page=1&size=20&sort=created_at&order=desc
```

**Parameters:**
- `page`: Page number (default: 1)
- `size`: Items per page (default: 20, max: 100)
- `sort`: Sort field
- `order`: Sort order (`asc` or `desc`)

**Response:**
```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "size": 20,
    "total": 150,
    "pages": 8
  }
}
```

## Interactive Documentation

When the API is running, you can access interactive documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

## Future Endpoints

The following endpoints will be implemented in subsequent tasks:

### Document Management
- `POST /api/v1/documents/upload` - Upload document ZIP files
- `GET /api/v1/documents` - List documents
- `GET /api/v1/documents/{id}` - Get document details
- `DELETE /api/v1/documents/{id}` - Delete document

### Workspace Management
- `POST /api/v1/workspaces` - Create workspace
- `GET /api/v1/workspaces` - List workspaces
- `GET /api/v1/workspaces/{id}` - Get workspace details
- `PUT /api/v1/workspaces/{id}` - Update workspace
- `DELETE /api/v1/workspaces/{id}` - Delete workspace

### Question Processing
- `POST /api/v1/questions/process` - Process question set
- `GET /api/v1/questions/jobs` - List processing jobs
- `GET /api/v1/questions/jobs/{id}` - Get job status
- `GET /api/v1/questions/jobs/{id}/results` - Get job results

### Job Management
- `GET /api/v1/jobs` - List all jobs
- `GET /api/v1/jobs/{id}` - Get job details
- `POST /api/v1/jobs/{id}/cancel` - Cancel job
- `DELETE /api/v1/jobs/{id}` - Delete job

## SDK and Client Libraries

Future releases will include:
- Python SDK
- JavaScript/TypeScript SDK
- CLI tool integration

## Webhooks

Future releases will support webhooks for:
- Job completion notifications
- Document processing status
- Workspace updates

## Examples

### cURL Examples

**Health Check:**
```bash
curl -X GET "http://localhost:8000/api/v1/health" \
  -H "accept: application/json"
```

**With API Key:**
```bash
curl -X GET "http://localhost:8000/api/v1/documents" \
  -H "accept: application/json" \
  -H "X-API-Key: your-api-key"
```

### Python Examples

```python
import httpx

# Health check
response = httpx.get("http://localhost:8000/api/v1/health")
print(response.json())

# With authentication
headers = {"X-API-Key": "your-api-key"}
response = httpx.get("http://localhost:8000/api/v1/documents", headers=headers)
print(response.json())
```

### JavaScript Examples

```javascript
// Health check
const response = await fetch('http://localhost:8000/api/v1/health');
const data = await response.json();
console.log(data);

// With authentication
const authResponse = await fetch('http://localhost:8000/api/v1/documents', {
  headers: {
    'X-API-Key': 'your-api-key'
  }
});
const authData = await authResponse.json();
console.log(authData);
```