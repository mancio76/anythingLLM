# Installation Guide

## Quick Installation

### 1. Create Virtual Environment
```bash
cd api
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### 2. Install Dependencies

**For Production:**
```bash
pip install -r requirements.txt
```

**For Development:**
```bash
pip install -r requirements-dev.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your configuration
```

### 4. Run the Application
```bash
python run.py
```

## Package Overview

### Core Dependencies
- **FastAPI**: Modern web framework for building APIs
- **Uvicorn**: ASGI server for running FastAPI
- **Pydantic**: Data validation and settings management
- **SQLAlchemy**: Database ORM with async support
- **AsyncPG**: PostgreSQL async driver

### Optional Dependencies
- **Redis**: Caching and session storage
- **Boto3/AioBoto3**: AWS S3 integration
- **Python-JOSE**: JWT token handling
- **Prometheus Client**: Metrics collection

### Development Dependencies
- **Pytest**: Testing framework
- **Black**: Code formatting
- **MyPy**: Type checking
- **Flake8**: Linting

## Troubleshooting

### Common Issues

1. **Import Error for pydantic_settings**
   ```bash
   pip install pydantic-settings==2.1.0
   ```

2. **Database Connection Issues**
   - Ensure PostgreSQL is running
   - Check DATABASE_URL in .env file

3. **Redis Connection Issues**
   - Set REDIS_ENABLED=false if Redis is not available
   - Check REDIS_URL in .env file

### Verification

Test the installation:
```bash
python validate_structure.py
python -c "from app.core.config import get_settings; print('✅ Configuration loaded successfully')"
```