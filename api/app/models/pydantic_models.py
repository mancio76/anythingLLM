"""Pydantic models for API serialization and validation."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# Enums
class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Job type enumeration."""
    DOCUMENT_UPLOAD = "document_upload"
    QUESTION_PROCESSING = "question_processing"
    WORKSPACE_CREATION = "workspace_creation"
    WORKSPACE_DELETION = "workspace_deletion"


class WorkspaceStatus(str, Enum):
    """Workspace status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"
    ERROR = "error"


class LLMProvider(str, Enum):
    """LLM provider enumeration."""
    OPENAI = "openai"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


# Configuration Models
class LLMConfig(BaseModel):
    """LLM configuration model."""
    provider: LLMProvider = Field(..., description="LLM provider")
    model: str = Field(..., description="Model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Response randomness")
    max_tokens: Optional[int] = Field(None, ge=1, description="Maximum response tokens")
    timeout: int = Field(30, ge=1, le=300, description="Request timeout in seconds")
    
    @field_validator("model")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate model name is not empty."""
        if not v.strip():
            raise ValueError("Model name cannot be empty")
        return v.strip()


class WorkspaceConfig(BaseModel):
    """Workspace configuration model."""
    llm_config: LLMConfig = Field(..., description="LLM configuration")
    procurement_prompts: bool = Field(True, description="Use procurement-specific prompts")
    auto_embed: bool = Field(True, description="Automatically embed documents")
    max_documents: Optional[int] = Field(None, ge=1, description="Maximum documents allowed")


# Common Models
class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(1, ge=1, description="Page number")
    size: int = Field(20, ge=1, le=100, description="Page size")
    
    @property
    def offset(self) -> int:
        """Calculate offset for database queries."""
        return (self.page - 1) * self.size


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    correlation_id: str = Field(..., description="Request correlation ID for tracing")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error occurrence timestamp")


# Job Models
class JobCreate(BaseModel):
    """Job creation model."""
    type: JobType = Field(..., description="Job type")
    workspace_id: Optional[str] = Field(None, description="Associated workspace ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional job metadata")


class JobUpdate(BaseModel):
    """Job update model."""
    status: Optional[JobStatus] = Field(None, description="Job status")
    progress: Optional[float] = Field(None, ge=0.0, le=100.0, description="Job progress percentage")
    result: Optional[Dict[str, Any]] = Field(None, description="Job result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional job metadata")


class Job(BaseModel):
    """Job model."""
    id: str = Field(..., description="Unique job identifier")
    type: JobType = Field(..., description="Type of job")
    status: JobStatus = Field(..., description="Current job status")
    workspace_id: Optional[str] = Field(None, description="Associated workspace ID")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    progress: float = Field(0.0, ge=0.0, le=100.0, description="Job progress percentage")
    result: Optional[Dict[str, Any]] = Field(None, description="Job result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional job metadata")
    
    @property
    def is_completed(self) -> bool:
        """Check if job is completed (success or failure)."""
        return self.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class JobResponse(BaseModel):
    """Job response model with additional metadata."""
    job: Job = Field(..., description="Job details")
    links: Dict[str, str] = Field(default_factory=dict, description="Related resource links")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")


class JobFilters(BaseModel):
    """Job filtering parameters."""
    status: Optional[JobStatus] = Field(None, description="Filter by job status")
    type: Optional[JobType] = Field(None, description="Filter by job type")
    workspace_id: Optional[str] = Field(None, description="Filter by workspace ID")
    created_after: Optional[datetime] = Field(None, description="Filter jobs created after this date")
    created_before: Optional[datetime] = Field(None, description="Filter jobs created before this date")


class PaginatedJobs(BaseModel):
    """Paginated job results."""
    items: List[Job] = Field(..., description="Job items")
    total: int = Field(..., ge=0, description="Total number of jobs")
    page: int = Field(..., ge=1, description="Current page number")
    size: int = Field(..., ge=1, description="Page size")
    pages: int = Field(..., ge=0, description="Total number of pages")
    
    @model_validator(mode="after")
    def validate_pagination(self):
        """Validate pagination consistency."""
        expected_pages = (self.total + self.size - 1) // self.size if self.total > 0 else 0
        if self.pages != expected_pages:
            raise ValueError("Inconsistent pagination data")
        return self


# Workspace Models
class WorkspaceCreate(BaseModel):
    """Workspace creation model."""
    name: str = Field(..., min_length=1, max_length=255, description="Workspace name")
    description: Optional[str] = Field(None, max_length=1000, description="Workspace description")
    config: WorkspaceConfig = Field(..., description="Workspace configuration")
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate workspace name."""
        name = v.strip()
        if not name:
            raise ValueError("Workspace name cannot be empty")
        # Check for invalid characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in name for char in invalid_chars):
            raise ValueError(f"Workspace name cannot contain: {', '.join(invalid_chars)}")
        return name


class WorkspaceUpdate(BaseModel):
    """Workspace update model."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Workspace name")
    description: Optional[str] = Field(None, max_length=1000, description="Workspace description")
    config: Optional[WorkspaceConfig] = Field(None, description="Workspace configuration")
    status: Optional[WorkspaceStatus] = Field(None, description="Workspace status")
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate workspace name if provided."""
        if v is None:
            return v
        name = v.strip()
        if not name:
            raise ValueError("Workspace name cannot be empty")
        # Check for invalid characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in name for char in invalid_chars):
            raise ValueError(f"Workspace name cannot contain: {', '.join(invalid_chars)}")
        return name


class Workspace(BaseModel):
    """Workspace model."""
    id: str = Field(..., description="Unique workspace identifier")
    name: str = Field(..., description="Workspace name")
    slug: str = Field(..., description="URL-safe workspace identifier")
    description: Optional[str] = Field(None, description="Workspace description")
    config: WorkspaceConfig = Field(..., description="Workspace configuration")
    document_count: int = Field(0, ge=0, description="Number of documents in workspace")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    status: WorkspaceStatus = Field(..., description="Workspace status")
    
    @property
    def is_active(self) -> bool:
        """Check if workspace is active."""
        return self.status == WorkspaceStatus.ACTIVE


class WorkspaceResponse(BaseModel):
    """Workspace response model with additional metadata."""
    workspace: Workspace = Field(..., description="Workspace details")
    links: Dict[str, str] = Field(default_factory=dict, description="Related resource links")
    stats: Dict[str, Any] = Field(default_factory=dict, description="Workspace statistics")


class WorkspaceFilters(BaseModel):
    """Workspace filtering parameters."""
    status: Optional[WorkspaceStatus] = Field(None, description="Filter by workspace status")
    name_contains: Optional[str] = Field(None, description="Filter by name containing text")
    created_after: Optional[datetime] = Field(None, description="Filter workspaces created after this date")
    created_before: Optional[datetime] = Field(None, description="Filter workspaces created before this date")
    min_documents: Optional[int] = Field(None, ge=0, description="Filter by minimum document count")
    max_documents: Optional[int] = Field(None, ge=0, description="Filter by maximum document count")


# Question Models
class QuestionCreate(BaseModel):
    """Question creation model."""
    text: str = Field(..., min_length=1, max_length=2000, description="Question text")
    expected_fragments: List[str] = Field(default_factory=list, description="Expected response fragments")
    llm_config: Optional[LLMConfig] = Field(None, description="Override LLM configuration")
    
    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate question text."""
        text = v.strip()
        if not text:
            raise ValueError("Question text cannot be empty")
        return text
    
    @field_validator("expected_fragments")
    @classmethod
    def validate_expected_fragments(cls, v: List[str]) -> List[str]:
        """Validate expected fragments."""
        return [fragment.strip() for fragment in v if fragment.strip()]


class Question(BaseModel):
    """Question model."""
    id: str = Field(default_factory=lambda: str(uuid4()), description="Question identifier")
    text: str = Field(..., description="Question text")
    expected_fragments: List[str] = Field(default_factory=list, description="Expected response fragments")
    llm_config: Optional[LLMConfig] = Field(None, description="Override LLM configuration")


class QuestionResult(BaseModel):
    """Question result model."""
    question_id: str = Field(..., description="Question identifier")
    question_text: str = Field(..., description="Original question text")
    response: str = Field(..., description="LLM response")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Response confidence")
    processing_time: float = Field(..., ge=0.0, description="Processing time in seconds")
    fragments_found: List[str] = Field(default_factory=list, description="Found expected fragments")
    success: bool = Field(..., description="Whether question was answered successfully")
    error: Optional[str] = Field(None, description="Error message if processing failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional result metadata")


class QuestionRequest(BaseModel):
    """Question execution request model."""
    workspace_id: str = Field(..., description="Target workspace ID")
    questions: List[QuestionCreate] = Field(..., min_length=1, description="Questions to execute")
    llm_config: Optional[LLMConfig] = Field(None, description="Default LLM configuration")
    max_concurrent: int = Field(3, ge=1, le=10, description="Maximum concurrent questions")
    timeout: int = Field(300, ge=30, le=3600, description="Total timeout in seconds")
    
    @field_validator("questions")
    @classmethod
    def validate_questions(cls, v: List[QuestionCreate]) -> List[QuestionCreate]:
        """Validate questions list."""
        if not v:
            raise ValueError("At least one question is required")
        if len(v) > 50:  # Reasonable limit
            raise ValueError("Maximum 50 questions allowed per request")
        return v


class QuestionResults(BaseModel):
    """Question execution results model."""
    job_id: str = Field(..., description="Associated job ID")
    workspace_id: str = Field(..., description="Target workspace ID")
    results: List[QuestionResult] = Field(..., description="Question results")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Results summary")
    total_questions: int = Field(..., ge=0, description="Total number of questions")
    successful_questions: int = Field(..., ge=0, description="Number of successful questions")
    failed_questions: int = Field(..., ge=0, description="Number of failed questions")
    total_processing_time: float = Field(..., ge=0.0, description="Total processing time in seconds")
    average_confidence: float = Field(..., ge=0.0, le=1.0, description="Average confidence score")
    
    @model_validator(mode="after")
    def validate_summary_consistency(self):
        """Validate summary data consistency."""
        if self.total_questions != len(self.results):
            raise ValueError("Total questions count doesn't match results length")
        
        successful = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)
        
        if self.successful_questions != successful:
            raise ValueError("Successful questions count is inconsistent")
        if self.failed_questions != failed:
            raise ValueError("Failed questions count is inconsistent")
        
        return self