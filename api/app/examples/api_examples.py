"""Comprehensive API usage examples and code samples."""

from typing import Dict, Any


def get_curl_examples() -> Dict[str, Any]:
    """Get cURL command examples for all API endpoints."""
    return {
        "authentication": {
            "jwt_bearer": """
# Using JWT Bearer token
curl -X GET "https://api.example.com/api/v1/workspaces" \\
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            """,
            "api_key": """
# Using API key
curl -X GET "https://api.example.com/api/v1/workspaces" \\
  -H "X-API-Key: ak_1234567890abcdef"
            """
        },
        "document_upload": """
# Upload documents
curl -X POST "https://api.example.com/api/v1/documents/upload" \\
  -H "Authorization: Bearer <token>" \\
  -F "file=@procurement_docs.zip" \\
  -F "workspace_id=ws_789xyz012" \\
  -F "project_name=Q1 Procurement Analysis" \\
  -F "document_type=contracts"
        """,
        "job_status": """
# Check job status
curl -X GET "https://api.example.com/api/v1/documents/jobs/job_abc123def456" \\
  -H "Authorization: Bearer <token>" \\
  -G -d "include_results=true"
        """,
        "workspace_creation": """
# Create workspace
curl -X POST "https://api.example.com/api/v1/workspaces" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Procurement Analysis Q1",
    "description": "Workspace for Q1 procurement contracts",
    "config": {
      "llm_config": {
        "provider": "openai",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 2000,
        "timeout": 30
      },
      "procurement_prompts": true,
      "auto_embed": true,
      "max_documents": 1000
    }
  }'
        """,
        "question_execution": """
# Execute questions
curl -X POST "https://api.example.com/api/v1/questions/execute" \\
  -H "Authorization: Bearer <token>" \\
  -H "Content-Type: application/json" \\
  -d '{
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
  }'
        """,
        "health_check": """
# Basic health check
curl -X GET "https://api.example.com/api/v1/health"

# Detailed health check
curl -X GET "https://api.example.com/api/v1/health/detailed"
        """
    }


def get_python_examples() -> Dict[str, Any]:
    """Get Python code examples using requests library."""
    return {
        "setup": """
import requests
import json
from typing import Dict, Any, Optional

class AnythingLLMClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}/api/v1{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response

# Initialize client
client = AnythingLLMClient(
    base_url="https://api.example.com",
    api_key="your-api-key-here"
)
        """,
        "document_upload": """
# Upload documents
def upload_documents(client, file_path: str, workspace_id: str, 
                    project_name: str = None, document_type: str = None):
    with open(file_path, 'rb') as f:
        files = {'file': f}
        data = {
            'workspace_id': workspace_id,
            'project_name': project_name,
            'document_type': document_type
        }
        
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        response = client.session.post(
            f"{client.base_url}/api/v1/documents/upload",
            files=files,
            data=data
        )
        response.raise_for_status()
        return response.json()

# Usage
job_response = upload_documents(
    client,
    file_path="procurement_docs.zip",
    workspace_id="ws_789xyz012",
    project_name="Q1 Procurement Analysis",
    document_type="contracts"
)
print(f"Job ID: {job_response['job']['id']}")
        """,
        "job_monitoring": """
# Monitor job progress
import time

def wait_for_job_completion(client, job_id: str, timeout: int = 300):
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = client._request('GET', f'/documents/jobs/{job_id}')
        job = response.json()
        
        status = job['status']
        progress = job['progress']
        
        print(f"Job {job_id}: {status} ({progress:.1f}%)")
        
        if status in ['completed', 'failed', 'cancelled']:
            return job
        
        time.sleep(5)  # Poll every 5 seconds
    
    raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

# Usage
completed_job = wait_for_job_completion(client, job_response['job']['id'])
if completed_job['status'] == 'completed':
    print("Document upload completed successfully!")
else:
    print(f"Job failed: {completed_job.get('error', 'Unknown error')}")
        """,
        "workspace_management": """
# Create workspace
def create_workspace(client, name: str, description: str = None, 
                    llm_provider: str = "openai", llm_model: str = "gpt-4"):
    workspace_data = {
        "name": name,
        "description": description,
        "config": {
            "llm_config": {
                "provider": llm_provider,
                "model": llm_model,
                "temperature": 0.7,
                "max_tokens": 2000,
                "timeout": 30
            },
            "procurement_prompts": True,
            "auto_embed": True,
            "max_documents": 1000
        }
    }
    
    response = client._request('POST', '/workspaces', json=workspace_data)
    return response.json()

# List workspaces
def list_workspaces(client, status: str = None, name_contains: str = None):
    params = {}
    if status:
        params['status'] = status
    if name_contains:
        params['name_contains'] = name_contains
    
    response = client._request('GET', '/workspaces', params=params)
    return response.json()

# Usage
workspace = create_workspace(
    client,
    name="Procurement Analysis Q1",
    description="Workspace for Q1 procurement contracts"
)
print(f"Created workspace: {workspace['workspace']['id']}")

workspaces = list_workspaces(client, status="active")
print(f"Found {len(workspaces)} active workspaces")
        """,
        "question_processing": """
# Execute questions
def execute_questions(client, workspace_id: str, questions: list, 
                     llm_provider: str = "openai", llm_model: str = "gpt-4"):
    question_data = {
        "workspace_id": workspace_id,
        "questions": questions,
        "llm_config": {
            "provider": llm_provider,
            "model": llm_model,
            "temperature": 0.3,
            "max_tokens": 1000,
            "timeout": 30
        },
        "max_concurrent": 3,
        "timeout": 300
    }
    
    response = client._request('POST', '/questions/execute', json=question_data)
    return response.json()

# Get question results
def get_question_results(client, job_id: str, format: str = "json"):
    params = {'format': format}
    response = client._request('GET', f'/questions/jobs/{job_id}/results', params=params)
    return response.json()

# Usage
questions = [
    {
        "text": "What is the total contract value mentioned in this document?",
        "expected_fragments": ["total value", "contract amount", "$", "USD"]
    },
    {
        "text": "Who are the contracting parties in this agreement?",
        "expected_fragments": ["party", "contractor", "client", "vendor"]
    },
    {
        "text": "What is the contract duration or term?",
        "expected_fragments": ["duration", "term", "period", "months", "years"]
    }
]

job_response = execute_questions(client, "ws_789xyz012", questions)
job_id = job_response['job']['id']

# Wait for completion and get results
completed_job = wait_for_job_completion(client, job_id)
if completed_job['status'] == 'completed':
    results = get_question_results(client, job_id)
    
    print(f"Processed {results['total_questions']} questions")
    print(f"Success rate: {results['successful_questions']}/{results['total_questions']}")
    print(f"Average confidence: {results['average_confidence']:.2f}")
    
    for result in results['results']:
        print(f"\\nQ: {result['question_text']}")
        print(f"A: {result['response']}")
        print(f"Confidence: {result['confidence_score']:.2f}")
        print(f"Success: {result['success']}")
        """,
        "error_handling": """
# Comprehensive error handling
import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout

def handle_api_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPError as e:
            response = e.response
            
            if response.status_code == 400:
                error_data = response.json()
                print(f"Bad Request: {error_data['message']}")
                if 'details' in error_data:
                    print(f"Details: {error_data['details']}")
            
            elif response.status_code == 401:
                print("Authentication failed. Check your API key or token.")
            
            elif response.status_code == 403:
                print("Access denied. Check your permissions.")
            
            elif response.status_code == 404:
                print("Resource not found.")
            
            elif response.status_code == 409:
                error_data = response.json()
                print(f"Conflict: {error_data['message']}")
            
            elif response.status_code == 413:
                print("File too large. Check size limits.")
            
            elif response.status_code == 422:
                error_data = response.json()
                print(f"Validation error: {error_data['message']}")
                if 'details' in error_data:
                    print(f"Field: {error_data['details'].get('field', 'unknown')}")
            
            elif response.status_code == 429:
                retry_after = response.headers.get('Retry-After', '60')
                print(f"Rate limited. Retry after {retry_after} seconds.")
            
            elif response.status_code >= 500:
                error_data = response.json()
                correlation_id = error_data.get('correlation_id', 'unknown')
                print(f"Server error. Correlation ID: {correlation_id}")
            
            raise
        
        except ConnectionError:
            print("Connection error. Check your network connection.")
            raise
        
        except Timeout:
            print("Request timeout. The server may be overloaded.")
            raise
    
    return wrapper

# Apply error handling to client methods
@handle_api_errors
def safe_upload_documents(client, *args, **kwargs):
    return upload_documents(client, *args, **kwargs)

@handle_api_errors
def safe_execute_questions(client, *args, **kwargs):
    return execute_questions(client, *args, **kwargs)
        """
    }


def get_javascript_examples() -> Dict[str, Any]:
    """Get JavaScript/Node.js code examples."""
    return {
        "setup": """
// Using fetch API (browser/Node.js with node-fetch)
class AnythingLLMClient {
    constructor(baseUrl, apiKey) {
        this.baseUrl = baseUrl.replace(/\\/$/, '');
        this.apiKey = apiKey;
        this.defaultHeaders = {
            'Authorization': `Bearer ${apiKey}`,
            'Content-Type': 'application/json'
        };
    }
    
    async request(method, endpoint, options = {}) {
        const url = `${this.baseUrl}/api/v1${endpoint}`;
        const config = {
            method,
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };
        
        const response = await fetch(url, config);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(`API Error: ${error.message}`);
        }
        
        return response.json();
    }
}

// Initialize client
const client = new AnythingLLMClient(
    'https://api.example.com',
    'your-api-key-here'
);
        """,
        "document_upload": """
// Upload documents
async function uploadDocuments(client, file, workspaceId, options = {}) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('workspace_id', workspaceId);
    
    if (options.projectName) {
        formData.append('project_name', options.projectName);
    }
    if (options.documentType) {
        formData.append('document_type', options.documentType);
    }
    
    const response = await fetch(`${client.baseUrl}/api/v1/documents/upload`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${client.apiKey}`
            // Don't set Content-Type for FormData
        },
        body: formData
    });
    
    if (!response.ok) {
        const error = await response.json();
        throw new Error(`Upload failed: ${error.message}`);
    }
    
    return response.json();
}

// Usage (browser)
const fileInput = document.getElementById('file-input');
const file = fileInput.files[0];

try {
    const jobResponse = await uploadDocuments(client, file, 'ws_789xyz012', {
        projectName: 'Q1 Procurement Analysis',
        documentType: 'contracts'
    });
    
    console.log(`Job ID: ${jobResponse.job.id}`);
} catch (error) {
    console.error('Upload failed:', error.message);
}
        """,
        "workspace_management": """
// Create workspace
async function createWorkspace(client, name, description, config = {}) {
    const workspaceData = {
        name,
        description,
        config: {
            llm_config: {
                provider: config.provider || 'openai',
                model: config.model || 'gpt-4',
                temperature: config.temperature || 0.7,
                max_tokens: config.maxTokens || 2000,
                timeout: config.timeout || 30
            },
            procurement_prompts: config.procurementPrompts !== false,
            auto_embed: config.autoEmbed !== false,
            max_documents: config.maxDocuments || 1000
        }
    };
    
    return client.request('POST', '/workspaces', {
        body: JSON.stringify(workspaceData)
    });
}

// List workspaces
async function listWorkspaces(client, filters = {}) {
    const params = new URLSearchParams();
    
    if (filters.status) params.append('status', filters.status);
    if (filters.nameContains) params.append('name_contains', filters.nameContains);
    if (filters.includeStats !== undefined) params.append('include_stats', filters.includeStats);
    
    const endpoint = `/workspaces${params.toString() ? '?' + params.toString() : ''}`;
    return client.request('GET', endpoint);
}

// Usage
try {
    const workspace = await createWorkspace(
        client,
        'Procurement Analysis Q1',
        'Workspace for Q1 procurement contracts',
        { provider: 'openai', model: 'gpt-4' }
    );
    
    console.log(`Created workspace: ${workspace.workspace.id}`);
    
    const workspaces = await listWorkspaces(client, { status: 'active' });
    console.log(`Found ${workspaces.length} active workspaces`);
} catch (error) {
    console.error('Workspace operation failed:', error.message);
}
        """,
        "question_processing": """
// Execute questions
async function executeQuestions(client, workspaceId, questions, config = {}) {
    const questionData = {
        workspace_id: workspaceId,
        questions: questions.map(q => ({
            text: q.text,
            expected_fragments: q.expectedFragments || [],
            llm_config: q.llmConfig
        })),
        llm_config: {
            provider: config.provider || 'openai',
            model: config.model || 'gpt-4',
            temperature: config.temperature || 0.3,
            max_tokens: config.maxTokens || 1000,
            timeout: config.timeout || 30
        },
        max_concurrent: config.maxConcurrent || 3,
        timeout: config.totalTimeout || 300
    };
    
    return client.request('POST', '/questions/execute', {
        body: JSON.stringify(questionData)
    });
}

// Monitor job progress
async function waitForJobCompletion(client, jobId, timeout = 300000) {
    const startTime = Date.now();
    
    while (Date.now() - startTime < timeout) {
        const job = await client.request('GET', `/documents/jobs/${jobId}`);
        
        console.log(`Job ${jobId}: ${job.status} (${job.progress.toFixed(1)}%)`);
        
        if (['completed', 'failed', 'cancelled'].includes(job.status)) {
            return job;
        }
        
        await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds
    }
    
    throw new Error(`Job ${jobId} did not complete within timeout`);
}

// Get question results
async function getQuestionResults(client, jobId, format = 'json') {
    const params = new URLSearchParams({ format });
    return client.request('GET', `/questions/jobs/${jobId}/results?${params}`);
}

// Usage
const questions = [
    {
        text: 'What is the total contract value mentioned in this document?',
        expectedFragments: ['total value', 'contract amount', '$', 'USD']
    },
    {
        text: 'Who are the contracting parties in this agreement?',
        expectedFragments: ['party', 'contractor', 'client', 'vendor']
    }
];

try {
    const jobResponse = await executeQuestions(client, 'ws_789xyz012', questions);
    const jobId = jobResponse.job.id;
    
    console.log(`Started question processing job: ${jobId}`);
    
    const completedJob = await waitForJobCompletion(client, jobId);
    
    if (completedJob.status === 'completed') {
        const results = await getQuestionResults(client, jobId);
        
        console.log(`Processed ${results.total_questions} questions`);
        console.log(`Success rate: ${results.successful_questions}/${results.total_questions}`);
        console.log(`Average confidence: ${results.average_confidence.toFixed(2)}`);
        
        results.results.forEach(result => {
            console.log(`\\nQ: ${result.question_text}`);
            console.log(`A: ${result.response}`);
            console.log(`Confidence: ${result.confidence_score.toFixed(2)}`);
            console.log(`Success: ${result.success}`);
        });
    } else {
        console.error(`Job failed: ${completedJob.error || 'Unknown error'}`);
    }
} catch (error) {
    console.error('Question processing failed:', error.message);
}
        """,
        "error_handling": """
// Comprehensive error handling
class APIError extends Error {
    constructor(message, status, details) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.details = details;
    }
}

async function handleApiResponse(response) {
    if (!response.ok) {
        const errorData = await response.json();
        
        switch (response.status) {
            case 400:
                throw new APIError(`Bad Request: ${errorData.message}`, 400, errorData.details);
            case 401:
                throw new APIError('Authentication failed. Check your API key or token.', 401);
            case 403:
                throw new APIError('Access denied. Check your permissions.', 403);
            case 404:
                throw new APIError('Resource not found.', 404);
            case 409:
                throw new APIError(`Conflict: ${errorData.message}`, 409, errorData.details);
            case 413:
                throw new APIError('File too large. Check size limits.', 413);
            case 422:
                throw new APIError(`Validation error: ${errorData.message}`, 422, errorData.details);
            case 429:
                const retryAfter = response.headers.get('Retry-After') || '60';
                throw new APIError(`Rate limited. Retry after ${retryAfter} seconds.`, 429, { retryAfter });
            default:
                if (response.status >= 500) {
                    const correlationId = errorData.correlation_id || 'unknown';
                    throw new APIError(`Server error. Correlation ID: ${correlationId}`, response.status, errorData);
                }
                throw new APIError(`HTTP ${response.status}: ${errorData.message}`, response.status, errorData);
        }
    }
    
    return response.json();
}

// Enhanced client with error handling
class EnhancedAnythingLLMClient extends AnythingLLMClient {
    async request(method, endpoint, options = {}) {
        const url = `${this.baseUrl}/api/v1${endpoint}`;
        const config = {
            method,
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };
        
        try {
            const response = await fetch(url, config);
            return await handleApiResponse(response);
        } catch (error) {
            if (error instanceof APIError) {
                console.error(`API Error (${error.status}): ${error.message}`);
                if (error.details) {
                    console.error('Details:', error.details);
                }
            } else {
                console.error('Network or other error:', error.message);
            }
            throw error;
        }
    }
}
        """
    }


def get_postman_collection() -> Dict[str, Any]:
    """Get Postman collection for API testing."""
    return {
        "info": {
            "name": "AnythingLLM API",
            "description": "Complete API collection for AnythingLLM document processing service",
            "version": "1.0.0",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "auth": {
            "type": "bearer",
            "bearer": [
                {
                    "key": "token",
                    "value": "{{api_token}}",
                    "type": "string"
                }
            ]
        },
        "variable": [
            {
                "key": "base_url",
                "value": "https://api.example.com",
                "type": "string"
            },
            {
                "key": "api_token",
                "value": "your-jwt-token-here",
                "type": "string"
            },
            {
                "key": "workspace_id",
                "value": "ws_example123",
                "type": "string"
            },
            {
                "key": "job_id",
                "value": "job_example456",
                "type": "string"
            }
        ],
        "item": [
            {
                "name": "Authentication",
                "item": [
                    {
                        "name": "Get API Token",
                        "request": {
                            "method": "POST",
                            "header": [
                                {
                                    "key": "Content-Type",
                                    "value": "application/json"
                                }
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": "{\n  \"username\": \"your-username\",\n  \"password\": \"your-password\"\n}"
                            },
                            "url": {
                                "raw": "{{base_url}}/api/v1/auth/token",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "auth", "token"]
                            }
                        }
                    }
                ]
            },
            {
                "name": "Documents",
                "item": [
                    {
                        "name": "Upload Documents",
                        "request": {
                            "method": "POST",
                            "header": [],
                            "body": {
                                "mode": "formdata",
                                "formdata": [
                                    {
                                        "key": "file",
                                        "type": "file",
                                        "src": []
                                    },
                                    {
                                        "key": "workspace_id",
                                        "value": "{{workspace_id}}",
                                        "type": "text"
                                    },
                                    {
                                        "key": "project_name",
                                        "value": "Test Project",
                                        "type": "text"
                                    },
                                    {
                                        "key": "document_type",
                                        "value": "contracts",
                                        "type": "text"
                                    }
                                ]
                            },
                            "url": {
                                "raw": "{{base_url}}/api/v1/documents/upload",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "documents", "upload"]
                            }
                        }
                    },
                    {
                        "name": "Get Job Status",
                        "request": {
                            "method": "GET",
                            "header": [],
                            "url": {
                                "raw": "{{base_url}}/api/v1/documents/jobs/{{job_id}}?include_results=true",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "documents", "jobs", "{{job_id}}"],
                                "query": [
                                    {
                                        "key": "include_results",
                                        "value": "true"
                                    }
                                ]
                            }
                        }
                    }
                ]
            },
            {
                "name": "Workspaces",
                "item": [
                    {
                        "name": "Create Workspace",
                        "request": {
                            "method": "POST",
                            "header": [
                                {
                                    "key": "Content-Type",
                                    "value": "application/json"
                                }
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": "{\n  \"name\": \"Test Workspace\",\n  \"description\": \"Workspace for testing\",\n  \"config\": {\n    \"llm_config\": {\n      \"provider\": \"openai\",\n      \"model\": \"gpt-4\",\n      \"temperature\": 0.7,\n      \"max_tokens\": 2000,\n      \"timeout\": 30\n    },\n    \"procurement_prompts\": true,\n    \"auto_embed\": true,\n    \"max_documents\": 1000\n  }\n}"
                            },
                            "url": {
                                "raw": "{{base_url}}/api/v1/workspaces",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "workspaces"]
                            }
                        }
                    },
                    {
                        "name": "List Workspaces",
                        "request": {
                            "method": "GET",
                            "header": [],
                            "url": {
                                "raw": "{{base_url}}/api/v1/workspaces?status=active&include_stats=true",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "workspaces"],
                                "query": [
                                    {
                                        "key": "status",
                                        "value": "active"
                                    },
                                    {
                                        "key": "include_stats",
                                        "value": "true"
                                    }
                                ]
                            }
                        }
                    }
                ]
            },
            {
                "name": "Questions",
                "item": [
                    {
                        "name": "Execute Questions",
                        "request": {
                            "method": "POST",
                            "header": [
                                {
                                    "key": "Content-Type",
                                    "value": "application/json"
                                }
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": "{\n  \"workspace_id\": \"{{workspace_id}}\",\n  \"questions\": [\n    {\n      \"text\": \"What is the total contract value?\",\n      \"expected_fragments\": [\"total value\", \"$\", \"USD\"]\n    },\n    {\n      \"text\": \"Who are the contracting parties?\",\n      \"expected_fragments\": [\"party\", \"contractor\", \"client\"]\n    }\n  ],\n  \"llm_config\": {\n    \"provider\": \"openai\",\n    \"model\": \"gpt-4\",\n    \"temperature\": 0.3\n  },\n  \"max_concurrent\": 3,\n  \"timeout\": 300\n}"
                            },
                            "url": {
                                "raw": "{{base_url}}/api/v1/questions/execute",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "questions", "execute"]
                            }
                        }
                    },
                    {
                        "name": "Get Question Results",
                        "request": {
                            "method": "GET",
                            "header": [],
                            "url": {
                                "raw": "{{base_url}}/api/v1/questions/jobs/{{job_id}}/results?format=json&include_metadata=true",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "questions", "jobs", "{{job_id}}", "results"],
                                "query": [
                                    {
                                        "key": "format",
                                        "value": "json"
                                    },
                                    {
                                        "key": "include_metadata",
                                        "value": "true"
                                    }
                                ]
                            }
                        }
                    }
                ]
            },
            {
                "name": "Health",
                "item": [
                    {
                        "name": "Basic Health Check",
                        "request": {
                            "method": "GET",
                            "header": [],
                            "url": {
                                "raw": "{{base_url}}/api/v1/health",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "health"]
                            }
                        }
                    },
                    {
                        "name": "Detailed Health Check",
                        "request": {
                            "method": "GET",
                            "header": [],
                            "url": {
                                "raw": "{{base_url}}/api/v1/health/detailed",
                                "host": ["{{base_url}}"],
                                "path": ["api", "v1", "health", "detailed"]
                            }
                        }
                    }
                ]
            }
        ]
    }