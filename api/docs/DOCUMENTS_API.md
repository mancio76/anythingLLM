# Document Processing API Endpoints

This document describes the REST API endpoints for document processing functionality in the AnythingLLM API service.

## Overview

The document processing API provides endpoints for:

- Uploading ZIP files containing documents (PDF, JSON, CSV)
- Tracking processing job status and progress
- Cancelling running jobs
- Listing and filtering document processing jobs

All endpoints require authentication and follow RESTful design principles.

## Base URL

All document endpoints are prefixed with `/api/v1/documents`.

## Authentication

All endpoints require authentication via:

- **JWT Bearer Token**: `Authorization: Bearer <token>`
- **API Key**: `X-API-Key: <api-key>`

## Endpoints

### 1. Upload Documents

Upload a ZIP file containing documents for processing.

**Endpoint:** `POST /api/v1/documents/upload`

**Content-Type:** `multipart/form-data`

**Parameters:**

- `file` (required): ZIP file containing documents
- `workspace_id` (required): Target workspace ID
- `project_name` (optional): Project name for organization
- `document_type` (optional): Document type classification

**File Requirements:**

- Must be a valid ZIP file
- Maximum size: 100MB (configurable)
- Must contain only PDF, JSON, or CSV files
- Maximum 100 files per ZIP

**Response:** `202 Accepted`

```json
{
  "job": {
    "id": "job_123456",
    "type": "document_upload",
    "status": "pending",
    "workspace_id": "ws_789",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z",
    "progress": 0.0,
    "metadata": {
      "user_id": "user_123",
      "username": "john_doe",
      "original_filename": "documents.zip",
      "file_size": 1048576,
      "project_name": "Q1 Contracts",
      "document_type": "contracts"
    }
  },
  "links": {
    "status": "/api/v1/documents/jobs/job_123456",
    "cancel": "/api/v1/documents/jobs/job_123456"
  },
  "estimated_completion": "2024-01-15T10:35:00Z"
}
```

**Error Responses:**

- `400 Bad Request`: Invalid file type or processing error
- `413 Content Too Large`: File exceeds size limit
- `422 Unprocessable Entity`: Validation error

**Example:**

```bash
curl -X POST "https://api.example.com/api/v1/documents/upload" \
  -H "Authorization: Bearer <token>" \
  -F "file=@documents.zip" \
  -F "workspace_id=ws_789" \
  -F "project_name=Q1 Contracts" \
  -F "document_type=contracts"
```

### 2. Get Job Status

Get detailed status and progress information for a document processing job.

**Endpoint:** `GET /api/v1/documents/jobs/{job_id}`

**Parameters:**

- `job_id` (path, required): Job ID to retrieve
- `include_results` (query, optional): Include detailed processing results

**Response:** `200 OK`

```json
{
  "id": "job_123456",
  "type": "document_upload",
  "status": "processing",
  "workspace_id": "ws_789",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:32:00Z",
  "started_at": "2024-01-15T10:30:30Z",
  "progress": 65.0,
  "result": {
    "processed_files": 8,
    "failed_files": 1,
    "organized_files": {
      "pdf": 5,
      "json": 2,
      "csv": 1
    },
    "upload_result": {
      "success": true,
      "uploaded_count": 8
    }
  },
  "metadata": {
    "user_id": "user_123",
    "original_filename": "documents.zip",
    "project_name": "Q1 Contracts"
  }
}
```

**Job Status Values:**

- `pending`: Job is queued and waiting to start
- `processing`: Job is currently being processed
- `completed`: Job completed successfully
- `failed`: Job failed with errors
- `cancelled`: Job was cancelled

**Error Responses:**

- `404 Not Found`: Job not found or not a document processing job
- `403 Forbidden`: Access denied to job

**Example:**

```bash
curl -X GET "https://api.example.com/api/v1/documents/jobs/job_123456?include_results=true" \
  -H "Authorization: Bearer <token>"
```

### 3. Cancel Job

Cancel a pending or processing document job.

**Endpoint:** `DELETE /api/v1/documents/jobs/{job_id}`

**Parameters:**

- `job_id` (path, required): Job ID to cancel
- `reason` (query, optional): Cancellation reason

**Response:** `200 OK`

```json
{
  "id": "job_123456",
  "type": "document_upload",
  "status": "cancelled",
  "workspace_id": "ws_789",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:33:00Z",
  "started_at": "2024-01-15T10:30:30Z",
  "progress": 45.0,
  "error": "Cancelled by user john_doe: User requested cancellation",
  "metadata": {
    "user_id": "user_123",
    "original_filename": "documents.zip"
  }
}
```

**Cancellation Rules:**

- Only pending or processing jobs can be cancelled
- Completed, failed, or already cancelled jobs cannot be cancelled
- Users can only cancel their own jobs (unless admin)
- Cancellation triggers cleanup of temporary files and resources

**Error Responses:**

- `404 Not Found`: Job not found
- `403 Forbidden`: Access denied to job
- `409 Conflict`: Job cannot be cancelled in current state

**Example:**

```bash
curl -X DELETE "https://api.example.com/api/v1/documents/jobs/job_123456?reason=User%20requested%20cancellation" \
  -H "Authorization: Bearer <token>"
```

### 4. List Jobs

Get a paginated list of document processing jobs with filtering options.

**Endpoint:** `GET /api/v1/documents/jobs`

**Query Parameters:**

- `page` (optional, default: 1): Page number (1-based)
- `size` (optional, default: 20, max: 100): Page size
- `status` (optional): Filter by job status
- `workspace_id` (optional): Filter by workspace ID
- `project_name` (optional): Filter by project name (partial match)
- `document_type` (optional): Filter by document type
- `created_after` (optional): Filter jobs created after date (ISO format)
- `created_before` (optional): Filter jobs created before date (ISO format)
- `include_metadata` (optional, default: false): Include job metadata

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "job_123456",
      "type": "document_upload",
      "status": "completed",
      "workspace_id": "ws_789",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:35:00Z",
      "completed_at": "2024-01-15T10:35:00Z",
      "progress": 100.0,
      "metadata": {
        "user_id": "user_123",
        "project_name": "Q1 Contracts",
        "document_type": "contracts"
      }
    }
  ],
  "total": 25,
  "page": 1,
  "size": 20,
  "pages": 2
}
```

**Access Control:**

- Users see only their own jobs
- Admins see all jobs
- Workspace-level access control applied

**Error Responses:**

- `422 Unprocessable Entity`: Invalid query parameters

**Example:**

```bash
curl -X GET "https://api.example.com/api/v1/documents/jobs?page=1&size=10&status=completed&workspace_id=ws_789" \
  -H "Authorization: Bearer <token>"
```

## Processing Workflow

The document processing workflow follows these steps:

1. **Upload Validation**
   - Validate ZIP file format and size
   - Check authentication and permissions
   - Create job record for tracking

2. **File Extraction**
   - Extract ZIP file securely (with path traversal protection)
   - Validate extracted file types (PDF, JSON, CSV only)
   - Check individual file sizes

3. **File Organization**
   - Organize files by type
   - Generate file metadata
   - Prepare for upload to AnythingLLM

4. **AnythingLLM Upload**
   - Upload files to specified workspace
   - Configure workspace settings
   - Trigger document embedding

5. **Completion**
   - Update job status and results
   - Clean up temporary files
   - Send notifications (if configured)

## Error Handling

All endpoints return consistent error responses:

```json
{
  "error": "error_type",
  "message": "Human-readable error message",
  "details": {
    "field": "Additional error details"
  },
  "correlation_id": "req_123456",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Common Error Types:**

- `validation_error`: Request validation failed
- `authentication_error`: Authentication required or failed
- `authorization_error`: Insufficient permissions
- `document_processing_error`: Document processing failed
- `job_not_found`: Job not found
- `job_cancellation_error`: Job cannot be cancelled
- `file_too_large`: File exceeds size limits
- `invalid_file_type`: Unsupported file type

## Rate Limiting

API requests are subject to rate limiting:

- Default: 100 requests per hour per user
- Rate limit headers included in responses
- Exceeded limits return `429 Too Many Requests`

## Security Considerations

- All file uploads are scanned for malicious content
- ZIP extraction includes path traversal protection
- File size limits prevent resource exhaustion
- User access control prevents unauthorized job access
- Sensitive data is sanitized from logs

## SDK Examples

### Python

```python
import requests

# Upload documents
with open('documents.zip', 'rb') as f:
    response = requests.post(
        'https://api.example.com/api/v1/documents/upload',
        headers={'Authorization': 'Bearer <token>'},
        files={'file': f},
        data={
            'workspace_id': 'ws_789',
            'project_name': 'Q1 Contracts'
        }
    )
    job = response.json()

# Check status
response = requests.get(
    f'https://api.example.com/api/v1/documents/jobs/{job["job"]["id"]}',
    headers={'Authorization': 'Bearer <token>'}
)
status = response.json()
```

### JavaScript

```javascript
// Upload documents
const formData = new FormData();
formData.append('file', fileInput.files[0]);
formData.append('workspace_id', 'ws_789');
formData.append('project_name', 'Q1 Contracts');

const response = await fetch('/api/v1/documents/upload', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const job = await response.json();

// Check status
const statusResponse = await fetch(`/api/v1/documents/jobs/${job.job.id}`, {
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

const status = await statusResponse.json();
```

## Monitoring and Observability

- All endpoints emit structured logs with correlation IDs
- Metrics available for request counts, response times, and error rates
- Health checks include document processing service status
- Job processing metrics tracked for performance monitoring
