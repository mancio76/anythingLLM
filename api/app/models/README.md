# Data Models Documentation

This directory contains the core data models for the AnythingLLM API service, implementing Task 2 of the specification.

## Overview

The models are organized into several modules:

- **`pydantic_models.py`** - Pydantic models for API serialization and validation
- **`sqlalchemy_models.py`** - SQLAlchemy models for database schema
- **`converters.py`** - Conversion utilities between Pydantic and SQLAlchemy models
- **`validators.py`** - Custom validation logic and utilities
- **`__init__.py`** - Module exports and public API

## Pydantic Models

### Core Domain Models

#### Job Models
- `Job` - Complete job representation with all fields
- `JobCreate` - Job creation request model
- `JobUpdate` - Job update request model
- `JobResponse` - Job response with additional metadata
- `JobFilters` - Job filtering parameters
- `PaginatedJobs` - Paginated job results

#### Workspace Models
- `Workspace` - Complete workspace representation
- `WorkspaceCreate` - Workspace creation request
- `WorkspaceUpdate` - Workspace update request
- `WorkspaceResponse` - Workspace response with metadata
- `WorkspaceConfig` - Workspace configuration settings
- `WorkspaceFilters` - Workspace filtering parameters

#### Question Models
- `Question` - Question representation
- `QuestionCreate` - Question creation request
- `QuestionResult` - Question execution result
- `QuestionRequest` - Question execution request
- `QuestionResults` - Batch question results

#### Configuration Models
- `LLMConfig` - LLM configuration settings
- `WorkspaceConfig` - Workspace-specific configuration

#### Common Models
- `PaginationParams` - Pagination parameters
- `ErrorResponse` - Standardized error response

### Enums
- `JobStatus` - Job status values (pending, processing, completed, failed, cancelled)
- `JobType` - Job type values (document_upload, question_processing, etc.)
- `WorkspaceStatus` - Workspace status values (active, inactive, deleted, error)
- `LLMProvider` - LLM provider values (openai, ollama, anthropic)

## SQLAlchemy Models

### Database Schema

#### Tables
1. **`workspaces`** - Workspace storage with LLM configuration
2. **`jobs`** - Job tracking and status management
3. **`questions`** - Question definitions with workspace association
4. **`question_results`** - Question execution results

#### Key Features
- **Timestamps** - All models include `created_at` and `updated_at` fields
- **Relationships** - Proper foreign key relationships with cascade options
- **Indexes** - Optimized indexes for common query patterns
- **Constraints** - Data integrity constraints and unique constraints
- **JSON Fields** - Flexible metadata storage using PostgreSQL JSON

#### Model Relationships
```
Workspace (1) -> (N) Jobs
Workspace (1) -> (N) Questions
Job (1) -> (N) QuestionResults
Question (1) -> (N) QuestionResults
```

## Converters

The converter module provides utilities to transform between Pydantic and SQLAlchemy models:

### Key Functions
- `JobConverter.to_pydantic()` - Convert SQLAlchemy Job to Pydantic
- `JobConverter.from_create()` - Convert JobCreate to SQLAlchemy data
- `WorkspaceConverter.to_pydantic()` - Convert SQLAlchemy Workspace to Pydantic
- `WorkspaceConverter.from_create()` - Convert WorkspaceCreate to SQLAlchemy data
- `slugify()` - Generate URL-safe slugs from workspace names

### Batch Conversion Functions
- `jobs_to_pydantic()` - Convert list of SQLAlchemy jobs
- `workspaces_to_pydantic()` - Convert list of SQLAlchemy workspaces
- `questions_to_pydantic()` - Convert list of SQLAlchemy questions
- `question_results_to_pydantic()` - Convert list of SQLAlchemy results

## Validators

The validator module provides comprehensive validation logic:

### Validator Classes
- `JobValidator` - Job-specific validation (status transitions, progress, timing)
- `WorkspaceValidator` - Workspace validation (names, slugs, LLM config)
- `QuestionValidator` - Question validation (text, fragments, confidence)
- `GeneralValidator` - General utilities (UUIDs, pagination, sanitization)

### Key Validation Features
- **Status Transitions** - Validates allowed job status changes
- **Data Consistency** - Ensures related fields are consistent
- **Input Sanitization** - Removes dangerous characters from user input
- **Format Validation** - Validates UUIDs, slugs, and other formats
- **Business Rules** - Enforces domain-specific business rules

## Database Migrations

Alembic is configured for database schema management:

### Files
- `alembic.ini` - Alembic configuration
- `alembic/env.py` - Migration environment setup
- `alembic/versions/0001_initial_schema.py` - Initial schema migration

### Migration Features
- **Async Support** - Configured for async SQLAlchemy
- **Environment Variables** - Uses DATABASE_URL from environment
- **PostgreSQL Enums** - Proper enum type creation and cleanup
- **Indexes and Constraints** - Complete schema with optimizations

## Usage Examples

### Creating Models

```python
from app.models import JobCreate, JobType, WorkspaceCreate, WorkspaceConfig, LLMConfig, LLMProvider

# Create LLM configuration
llm_config = LLMConfig(
    provider=LLMProvider.OPENAI,
    model="gpt-3.5-turbo",
    temperature=0.7
)

# Create workspace configuration
workspace_config = WorkspaceConfig(llm_config=llm_config)

# Create workspace
workspace_create = WorkspaceCreate(
    name="Procurement Analysis",
    description="Workspace for contract analysis",
    config=workspace_config
)

# Create job
job_create = JobCreate(
    type=JobType.DOCUMENT_UPLOAD,
    workspace_id="ws_123",
    metadata={"file_count": 5, "total_size": 1024000}
)
```

### Using Converters

```python
from app.models import WorkspaceConverter

# Convert Pydantic to SQLAlchemy data
db_data = WorkspaceConverter.from_create(workspace_create)

# Convert SQLAlchemy model to Pydantic
workspace = WorkspaceConverter.to_pydantic(db_workspace)
```

### Using Validators

```python
from app.models import JobValidator, WorkspaceValidator

# Validate job status transition
is_valid = JobValidator.validate_job_status_transition(
    current_status=JobStatus.PENDING,
    new_status=JobStatus.PROCESSING
)

# Validate workspace name
is_valid = WorkspaceValidator.validate_workspace_name("My Workspace")
```

## Testing

The models include comprehensive tests in `tests/test_models.py`:

- **Pydantic Model Tests** - Validation, serialization, properties
- **Converter Tests** - Conversion between model types
- **Validator Tests** - All validation logic
- **Edge Cases** - Error conditions and boundary values

## Requirements Satisfied

This implementation satisfies the following requirements from Task 2:

✅ **Create Pydantic models** - Complete set of API models with validation
✅ **Implement SQLAlchemy models** - Database schema with relationships and constraints  
✅ **Create Alembic migrations** - Initial schema migration with proper setup
✅ **Add model validation** - Comprehensive validation utilities and custom validators
✅ **Add serialization methods** - Converter utilities for model transformation

### Specific Requirements Coverage

- **6.1** - Job management models with status tracking and metadata
- **6.2** - Job progress monitoring with validation
- **6.3** - Job result persistence with proper relationships
- **10.2** - API documentation support through Pydantic models

## Next Steps

1. **Install Dependencies** - `pip install -r requirements.txt`
2. **Database Setup** - Configure PostgreSQL connection
3. **Run Migrations** - `alembic upgrade head`
4. **Run Tests** - `pytest tests/test_models.py`
5. **Integration** - Use models in repository and service layers