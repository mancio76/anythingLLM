# AnythingLLM API

A cloud-native FastAPI service for document processing, workspace management, and automated question-answer testing against AnythingLLM instances.

## Features

- **Document Processing**: Upload and process ZIP files containing PDF, JSON, and CSV documents
- **Workspace Management**: Create and manage AnythingLLM workspaces
- **Question-Answer Testing**: Execute automated question sets against document workspaces
- **Job Management**: Track long-running operations with status monitoring
- **Health Monitoring**: Comprehensive health checks and observability
- **Security**: JWT/API key authentication, rate limiting, and security headers
- **Configurable Storage**: Support for local filesystem and AWS S3 storage
- **Optional Redis**: Enhanced performance with Redis caching and queuing

## Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL database
- AnythingLLM instance
- Redis (optional)

### Installation

See [docs/INSTALL.md](docs/INSTALL.md) for detailed installation instructions.

**Quick Start:**
```bash
cd api
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
python run.py
```

The API will be available at `http://localhost:8000`

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI Schema: `http://localhost:8000/openapi.json`

## Configuration

The application uses Pydantic settings with environment variable support. See `.env.example` for all available configuration options.

### Required Configuration

- `DATABASE_URL`: PostgreSQL connection string
- `ANYTHINGLLM_URL`: AnythingLLM instance URL
- `ANYTHINGLLM_API_KEY`: AnythingLLM API key
- `SECRET_KEY`: Secret key for JWT signing

### Optional Configuration

- `REDIS_ENABLED`: Enable Redis support (default: false)
- `STORAGE_TYPE`: Storage backend (local/s3, default: local)
- `LOG_FORMAT`: Log format (json/text, default: json)

## Development

### Project Structure

```
api/
├── app/
│   ├── core/           # Core configuration and utilities
│   ├── middleware/     # Custom middleware
│   ├── routers/        # API route handlers
│   └── main.py         # FastAPI application
├── requirements.txt    # Python dependencies
├── run.py             # Application startup script
└── .env.example       # Environment configuration template
```

### Running in Development

For development with auto-reload:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Health Checks

- Basic health: `GET /api/v1/health`
- Detailed health: `GET /api/v1/health/detailed`

## Security

The API implements multiple security measures:

- JWT and API key authentication
- Rate limiting per user/IP
- Security headers (HSTS, CSP, etc.)
- Sensitive data sanitization in logs
- Input validation and sanitization

## Logging

Structured logging with:

- JSON format for production
- Correlation IDs for request tracing
- Sensitive data sanitization
- Configurable log levels

## Documentation

- **[Installation Guide](docs/INSTALL.md)** - Setup and installation instructions
- **[Development Guide](docs/DEVELOPMENT.md)** - Development workflow and tools
- **[Testing Guide](docs/TESTING.md)** - Testing with pytest and best practices
- **[Git Guide](docs/GIT.md)** - Version control configuration and best practices
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Production deployment instructions
- **[API Documentation](docs/API.md)** - API endpoints and usage examples

## Next Steps

This is the initial project structure. Additional features will be implemented in subsequent tasks:

- Database models and repositories
- Authentication and authorization
- Document processing services
- Workspace management
- Question processing
- Job management
- Comprehensive testing