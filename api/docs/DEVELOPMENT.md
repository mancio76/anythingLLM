# Development Guide

## Development Setup

### Prerequisites

- Python 3.9+
- PostgreSQL database
- Redis (optional)
- Git

### Setup Development Environment

1. **Clone and setup:**

    ```bash
    cd api
    python -m venv venv
    venv\Scripts\activate  # Windows
    # source venv/bin/activate  # macOS/Linux
    ```

2. **Install development dependencies:**

    ```bash
    pip install -r requirements-dev.txt
    ```

3. **Setup pre-commit hooks:**

    ```bash
    pre-commit install
    ```

### Running in Development Mode

**With auto-reload:**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**With environment variables:**

```bash
# Copy and edit environment file
cp .env.example .env

# Run with custom settings
python run.py
```

## Code Quality

### Formatting and Linting

```bash
# Format code
black app/
isort app/

# Lint code
flake8 app/
mypy app/
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_config.py -v

# Run specific test method
pytest tests/test_health.py::TestHealthEndpoints::test_basic_health_check
```

See [TESTING.md](TESTING.md) for comprehensive testing documentation.

## Project Structure

```treemap
api/
├── app/                    # Main application package
│   ├── core/              # Core functionality
│   │   ├── config.py      # Configuration management
│   │   ├── database.py    # Database connections
│   │   └── logging.py     # Logging configuration
│   ├── middleware/        # Custom middleware
│   ├── routers/          # API route handlers
│   ├── models/           # Database models (future)
│   ├── services/         # Business logic (future)
│   └── main.py           # FastAPI application
├── docs/                 # Documentation files
├── tests/               # Test files
├── requirements.txt     # Production dependencies
├── requirements-dev.txt # Development dependencies
└── README.md           # Main documentation
```

## Development Workflow

1. **Create feature branch:**

    ```bash
    git checkout -b feature/your-feature-name
    ```

2. **Make changes and test:**

    ```bash
    # Run tests
    pytest

    # Check code quality
    black app/ && isort app/ && flake8 app/ && mypy app/
    ```

3. **Commit and push:**

    ```bash
    git add .
    git commit -m "feat: your feature description"
    git push origin feature/your-feature-name
    ```

## Environment Variables

See `.env.example` for all available configuration options.

### Required for Development

- `DATABASE_URL`: PostgreSQL connection
- `ANYTHINGLLM_URL`: AnythingLLM instance URL
- `ANYTHINGLLM_API_KEY`: API key for AnythingLLM
- `SECRET_KEY`: JWT signing key

### Optional for Development

- `REDIS_ENABLED=false`: Disable Redis for local dev
- `LOG_LEVEL=DEBUG`: More verbose logging
- `LOG_FORMAT=text`: Human-readable logs

## Debugging

### VS Code Configuration

Create `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "FastAPI Debug",
            "type": "python",
            "request": "launch",
            "program": "run.py",
            "console": "integratedTerminal",
            "env": {
                "LOG_LEVEL": "DEBUG"
            }
        }
    ]
}
```

### Common Debug Commands

```bash
# Check configuration loading
python -c "from app.core.config import get_settings; print(get_settings())"

# Test database connection
python -c "import asyncio; from app.core.database import init_db; from app.core.config import get_settings; asyncio.run(init_db(get_settings()))"

# Validate project structure
python validate_structure.py
```
