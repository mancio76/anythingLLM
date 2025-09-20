"""Data models package."""

from .pydantic_models import (
    # Job models
    Job,
    JobCreate,
    JobUpdate,
    JobResponse,
    JobStatus,
    JobType,
    JobFilters,
    PaginatedJobs,
    
    # Workspace models
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceResponse,
    WorkspaceStatus,
    WorkspaceConfig,
    WorkspaceFilters,
    
    # Question models
    Question,
    QuestionCreate,
    QuestionResult,
    QuestionRequest,
    QuestionResults,
    
    # Configuration models
    LLMConfig,
    LLMProvider,
    
    # Common models
    PaginationParams,
    ErrorResponse,
)

from .sqlalchemy_models import (
    JobModel,
    WorkspaceModel,
    QuestionModel,
    QuestionResultModel,
)

from .converters import (
    JobConverter,
    WorkspaceConverter,
    QuestionConverter,
    QuestionResultConverter,
    jobs_to_pydantic,
    workspaces_to_pydantic,
    questions_to_pydantic,
    question_results_to_pydantic,
)

from .validators import (
    ModelValidationError,
    JobValidator,
    WorkspaceValidator,
    QuestionValidator,
    GeneralValidator,
    validate_model_data,
    validate_model_update,
)

__all__ = [
    # Pydantic models
    "Job",
    "JobCreate", 
    "JobUpdate",
    "JobResponse",
    "JobStatus",
    "JobType",
    "JobFilters",
    "PaginatedJobs",
    "Workspace",
    "WorkspaceCreate",
    "WorkspaceUpdate", 
    "WorkspaceResponse",
    "WorkspaceStatus",
    "WorkspaceConfig",
    "WorkspaceFilters",
    "Question",
    "QuestionCreate",
    "QuestionResult",
    "QuestionRequest",
    "QuestionResults",
    "LLMConfig",
    "LLMProvider",
    "PaginationParams",
    "ErrorResponse",
    
    # SQLAlchemy models
    "JobModel",
    "WorkspaceModel",
    "QuestionModel",
    "QuestionResultModel",
    
    # Converters
    "JobConverter",
    "WorkspaceConverter",
    "QuestionConverter",
    "QuestionResultConverter",
    "jobs_to_pydantic",
    "workspaces_to_pydantic",
    "questions_to_pydantic",
    "question_results_to_pydantic",
    
    # Validators
    "ModelValidationError",
    "JobValidator",
    "WorkspaceValidator",
    "QuestionValidator",
    "GeneralValidator",
    "validate_model_data",
    "validate_model_update",
]