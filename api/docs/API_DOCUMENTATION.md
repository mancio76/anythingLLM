# AnythingLLM API Documentation

This document provides comprehensive information about the AnythingLLM API documentation system, including interactive documentation, versioning strategy, and usage examples.

## Overview

The AnythingLLM API provides a complete REST interface for document processing, workspace management, and automated question-answer testing. The API is designed with comprehensive documentation, examples, and developer tools to ensure easy integration and usage.

## Documentation Features

### 1. Interactive Documentation

The API provides multiple interactive documentation interfaces:

- **Swagger UI**: Available at `/api/v1/docs`
  - Interactive API explorer with request/response examples
  - Built-in authentication testing
  - Real-time API testing capabilities

- **ReDoc**: Available at `/api/v1/redoc`
  - Clean, responsive documentation interface
  - Detailed schema documentation
  - Code examples in multiple languages

- **OpenAPI Schema**: Available at `/api/v1/openapi.json`
  - Machine-readable API specification
  - Compatible with OpenAPI 3.0 standard
  - Suitable for code generation tools

### 2. Documentation Endpoints

The API includes dedicated documentation endpoints:

| Endpoint | Description |
|----------|-------------|
| `/api/v1/docs/versions` | API version information and compatibility |
| `/api/v1/docs/examples` | Comprehensive usage examples |
| `/api/v1/docs/authentication` | Authentication methods and examples |
| `/api/v1/docs/errors` | Error codes and troubleshooting |
| `/api/v1/docs/rate-limits` | Rate limiting information |
| `/api/v1/docs/status` | Current API status and version |

### 3. Code Examples

The documentation includes examples in multiple programming languages:

- **cURL**: Command-line examples for all endpoints
- **Python**: Complete client implementation with error handling
- **JavaScript**: Browser and Node.js examples
- **Postman**: Ready-to-import collection for API testing

## API Versioning Strategy

### Version Format

The API uses URL path versioning with the format `/api/{version}/...`:

- Current version: `v1`
- Example: `/api/v1/documents/upload`

### Version Detection

The API supports multiple methods for version specification:

1. **URL Path** (Primary): `/api/v1/...`
2. **API-Version Header**: `API-Version: v1`
3. **Accept Header**: `Accept: application/vnd.api+json;version=1`
4. **Query Parameter**: `?version=v1`

### Backward Compatibility

- **Stable versions**: No breaking changes within major version
- **Deprecation process**: 6-month notice before deprecation
- **Migration support**: Documentation and tooling provided
- **Sunset period**: 12 months minimum support after deprecation

## Authentication

### Supported Methods

1. **JWT Bearer Tokens**
   ```
   Authorization: Bearer <jwt_token>
   ```

2. **API Keys**
   ```
   X-API-Key: <api_key>
   ```

### Security Features

- Token-based authentication with configurable expiration
- Role-based access control (RBAC)
- Rate limiting per user/IP
- Request correlation IDs for tracing
- Comprehensive audit logging

## Error Handling

### Error Response Format

All errors follow a consistent JSON format:

```json
{
  "error": "ErrorType",
  "message": "Human-readable error message",
  "details": {
    "field": "specific_field",
    "constraint": "validation_rule"
  },
  "correlation_id": "req_abc123def456",
  "timestamp": "2024-01-15T10:15:30Z"
}
```

### Common HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| 400 | Bad Request | Invalid file format, malformed request |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 409 | Conflict | Resource state conflict |
| 413 | Payload Too Large | File size exceeds limits |
| 422 | Unprocessable Entity | Validation errors |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unexpected server error |
| 502 | Bad Gateway | External service unavailable |

## Rate Limiting

### Default Limits

- **Requests per hour**: 100 per user/IP
- **Burst limit**: 10 requests per minute
- **Concurrent requests**: 5 per user

### Rate Limit Headers

All responses include rate limiting information:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705320000
Retry-After: 3600 (when rate limited)
```

### Best Practices

- Monitor rate limit headers in responses
- Implement exponential backoff when rate limited
- Cache responses to reduce API calls
- Use batch operations when available

## Usage Examples

### Document Upload

```bash
curl -X POST "https://api.example.com/api/v1/documents/upload" \
  -H "Authorization: Bearer <token>" \
  -F "file=@documents.zip" \
  -F "workspace_id=ws_123" \
  -F "project_name=Q1 Analysis"
```

### Workspace Creation

```bash
curl -X POST "https://api.example.com/api/v1/workspaces" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Procurement Analysis",
    "config": {
      "llm_config": {
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7
      }
    }
  }'
```

### Question Processing

```bash
curl -X POST "https://api.example.com/api/v1/questions/execute" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "ws_123",
    "questions": [
      {
        "text": "What is the contract value?",
        "expected_fragments": ["value", "$", "USD"]
      }
    ]
  }'
```

## Client Libraries

### Python Client

```python
from anythingllm_api import Client

client = Client(api_key="your-api-key")
workspaces = client.workspaces.list()
```

### JavaScript Client

```javascript
import { AnythingLLMClient } from '@anythingllm/api-client';

const client = new AnythingLLMClient({ apiKey: 'your-api-key' });
const workspaces = await client.workspaces.list();
```

### OpenAPI Code Generation

Generate clients using the OpenAPI specification:

```bash
openapi-generator generate \
  -i https://api.example.com/api/v1/openapi.json \
  -g python \
  -o ./python-client
```

## Testing and Development

### Postman Collection

Import the complete API collection for testing:

1. Download from `/api/v1/docs/examples`
2. Import into Postman
3. Configure environment variables
4. Start testing endpoints

### Development Environment

1. Set up environment variables:
   ```bash
   export DATABASE_URL="postgresql://..."
   export ANYTHINGLLM_URL="http://localhost:3001"
   export ANYTHINGLLM_API_KEY="your-key"
   export SECRET_KEY="your-secret"
   ```

2. Start the development server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. Access documentation:
   - Swagger UI: http://localhost:8000/api/v1/docs
   - ReDoc: http://localhost:8000/api/v1/redoc

## Monitoring and Observability

### Health Checks

- **Basic**: `/api/v1/health` - Simple liveness check
- **Detailed**: `/api/v1/health/detailed` - Full dependency check

### Metrics

- **Prometheus**: `/api/v1/health/metrics` - Metrics endpoint
- **Request tracking**: Correlation IDs in all responses
- **Performance monitoring**: Response time tracking

### Logging

- **Structured logging**: JSON format with correlation IDs
- **Sensitive data sanitization**: Automatic PII redaction
- **Error tracking**: Detailed error context and stack traces

## Support and Resources

### Documentation Resources

- **API Reference**: Interactive documentation at `/api/v1/docs`
- **Examples**: Code samples at `/api/v1/docs/examples`
- **Error Reference**: Error codes at `/api/v1/docs/errors`

### Community and Support

- **GitHub Issues**: Report bugs and request features
- **Documentation**: Comprehensive guides and tutorials
- **Community Forum**: Ask questions and share solutions

### Migration Guides

When new API versions are released:

1. **Deprecation Notice**: 6 months advance notice
2. **Migration Guide**: Step-by-step upgrade instructions
3. **Compatibility Layer**: Temporary backward compatibility
4. **Support Period**: 12 months minimum support

## Changelog

### Version 1.0.0 (2024-01-15)

**Added:**
- Initial API release
- Document upload and processing
- Workspace management
- Question processing with multiple LLM models
- Job tracking and status monitoring
- Comprehensive documentation system
- Authentication and authorization
- Rate limiting and security features

**Security:**
- JWT and API key authentication
- Request rate limiting
- Input validation and sanitization
- Secure file handling

## Future Roadmap

### Planned Features

- **Webhooks**: Event notifications (Q2 2024)
- **Batch Operations**: Bulk processing capabilities
- **GraphQL API**: Alternative query interface
- **Real-time Subscriptions**: Live updates via WebSocket
- **Advanced Analytics**: Usage and performance insights

### API Evolution

- **Version 1.1.0**: Enhanced filtering and batch operations
- **Version 2.0.0**: GraphQL support and breaking changes
- **Long-term**: Multi-tenant support and advanced features

---

For the most up-to-date information, always refer to the interactive documentation at `/api/v1/docs` and the version-specific endpoints at `/api/v1/docs/versions`.