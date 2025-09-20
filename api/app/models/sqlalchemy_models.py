"""SQLAlchemy models for database schema."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.pydantic_models import JobStatus, JobType, WorkspaceStatus, LLMProvider


class TimestampMixin:
    """Mixin for timestamp fields."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True
    )


class JobModel(Base, TimestampMixin):
    """Job database model."""
    
    __tablename__ = "jobs"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False
    )
    
    # Job details
    type: Mapped[JobType] = mapped_column(
        Enum(JobType),
        nullable=False,
        index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus),
        nullable=False,
        default=JobStatus.PENDING,
        index=True
    )
    
    # Workspace relationship
    workspace_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Timing fields
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Progress and results
    progress: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    job_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Relationships
    workspace: Mapped[Optional["WorkspaceModel"]] = relationship(
        "WorkspaceModel",
        back_populates="jobs",
        lazy="select"
    )
    question_results: Mapped[list["QuestionResultModel"]] = relationship(
        "QuestionResultModel",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_jobs_status_type", "status", "type"),
        Index("idx_jobs_workspace_status", "workspace_id", "status"),
        Index("idx_jobs_created_status", "created_at", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<JobModel(id={self.id}, type={self.type}, status={self.status})>"


class WorkspaceModel(Base, TimestampMixin):
    """Workspace database model."""
    
    __tablename__ = "workspaces"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False
    )
    
    # Workspace details
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    slug: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Status and metrics
    status: Mapped[WorkspaceStatus] = mapped_column(
        Enum(WorkspaceStatus),
        nullable=False,
        default=WorkspaceStatus.ACTIVE,
        index=True
    )
    document_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    # Configuration (stored as JSON)
    llm_provider: Mapped[LLMProvider] = mapped_column(
        Enum(LLMProvider),
        nullable=False,
        default=LLMProvider.OPENAI
    )
    llm_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="gpt-3.5-turbo"
    )
    llm_temperature: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.7
    )
    llm_max_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    llm_timeout: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30
    )
    
    # Workspace configuration flags
    procurement_prompts: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    auto_embed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    max_documents: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    # Additional metadata
    workspace_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Relationships
    jobs: Mapped[list["JobModel"]] = relationship(
        "JobModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
        lazy="select"
    )
    questions: Mapped[list["QuestionModel"]] = relationship(
        "QuestionModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_workspaces_name_status", "name", "status"),
        Index("idx_workspaces_status_created", "status", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<WorkspaceModel(id={self.id}, name={self.name}, status={self.status})>"


class QuestionModel(Base, TimestampMixin):
    """Question database model."""
    
    __tablename__ = "questions"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False
    )
    
    # Workspace relationship
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Question details
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    expected_fragments: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )
    
    # LLM configuration override
    llm_provider: Mapped[Optional[LLMProvider]] = mapped_column(
        Enum(LLMProvider),
        nullable=True
    )
    llm_model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    llm_temperature: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    llm_max_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    llm_timeout: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )
    
    # Additional metadata
    question_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship(
        "WorkspaceModel",
        back_populates="questions",
        lazy="select"
    )
    results: Mapped[list["QuestionResultModel"]] = relationship(
        "QuestionResultModel",
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_questions_workspace_created", "workspace_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<QuestionModel(id={self.id}, workspace_id={self.workspace_id})>"


class QuestionResultModel(Base, TimestampMixin):
    """Question result database model."""
    
    __tablename__ = "question_results"
    
    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        nullable=False
    )
    
    # Foreign keys
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Result details
    question_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    response: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    processing_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0
    )
    fragments_found: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list
    )
    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Additional metadata
    result_metadata: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict
    )
    
    # Relationships
    job: Mapped["JobModel"] = relationship(
        "JobModel",
        back_populates="question_results",
        lazy="select"
    )
    question: Mapped["QuestionModel"] = relationship(
        "QuestionModel",
        back_populates="results",
        lazy="select"
    )
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("job_id", "question_id", name="uq_job_question"),
        Index("idx_question_results_job_success", "job_id", "success"),
        Index("idx_question_results_confidence", "confidence_score"),
    )
    
    def __repr__(self) -> str:
        return f"<QuestionResultModel(id={self.id}, job_id={self.job_id}, success={self.success})>"