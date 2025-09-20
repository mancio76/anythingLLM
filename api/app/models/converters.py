"""Model conversion utilities between Pydantic and SQLAlchemy models."""

from typing import Dict, Any, Optional, List
from datetime import datetime

from app.models.pydantic_models import (
    Job,
    JobCreate,
    JobUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspaceConfig,
    Question,
    QuestionCreate,
    QuestionResult,
    LLMConfig,
)
from app.models.sqlalchemy_models import (
    JobModel,
    WorkspaceModel,
    QuestionModel,
    QuestionResultModel,
)


def slugify(text: str) -> str:
    """Convert text to URL-safe slug."""
    import re
    # Convert to lowercase and replace spaces/special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


class JobConverter:
    """Converter for Job models."""
    
    @staticmethod
    def to_pydantic(db_job: JobModel) -> Job:
        """Convert SQLAlchemy JobModel to Pydantic Job."""
        return Job(
            id=db_job.id,
            type=db_job.type,
            status=db_job.status,
            workspace_id=db_job.workspace_id,
            created_at=db_job.created_at,
            updated_at=db_job.updated_at,
            started_at=db_job.started_at,
            completed_at=db_job.completed_at,
            progress=db_job.progress,
            result=db_job.result,
            error=db_job.error,
            metadata=db_job.job_metadata,
        )
    
    @staticmethod
    def from_create(job_create: JobCreate) -> Dict[str, Any]:
        """Convert JobCreate to SQLAlchemy model data."""
        return {
            "type": job_create.type,
            "workspace_id": job_create.workspace_id,
            "job_metadata": job_create.metadata,
        }
    
    @staticmethod
    def from_update(job_update: JobUpdate) -> Dict[str, Any]:
        """Convert JobUpdate to SQLAlchemy model update data."""
        update_data = {}
        
        if job_update.status is not None:
            update_data["status"] = job_update.status
            # Set timing fields based on status
            if job_update.status.value == "processing" and "started_at" not in update_data:
                update_data["started_at"] = datetime.utcnow()
            elif job_update.status.value in ["completed", "failed", "cancelled"]:
                update_data["completed_at"] = datetime.utcnow()
        
        if job_update.progress is not None:
            update_data["progress"] = job_update.progress
        
        if job_update.result is not None:
            update_data["result"] = job_update.result
        
        if job_update.error is not None:
            update_data["error"] = job_update.error
        
        if job_update.metadata is not None:
            update_data["job_metadata"] = job_update.metadata
        
        # Always update the updated_at timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        return update_data


class WorkspaceConverter:
    """Converter for Workspace models."""
    
    @staticmethod
    def to_pydantic(db_workspace: WorkspaceModel) -> Workspace:
        """Convert SQLAlchemy WorkspaceModel to Pydantic Workspace."""
        # Reconstruct LLMConfig from individual fields
        llm_config = LLMConfig(
            provider=db_workspace.llm_provider,
            model=db_workspace.llm_model,
            temperature=db_workspace.llm_temperature,
            max_tokens=db_workspace.llm_max_tokens,
            timeout=db_workspace.llm_timeout,
        )
        
        # Reconstruct WorkspaceConfig
        config = WorkspaceConfig(
            llm_config=llm_config,
            procurement_prompts=db_workspace.procurement_prompts,
            auto_embed=db_workspace.auto_embed,
            max_documents=db_workspace.max_documents,
        )
        
        return Workspace(
            id=db_workspace.id,
            name=db_workspace.name,
            slug=db_workspace.slug,
            description=db_workspace.description,
            config=config,
            document_count=db_workspace.document_count,
            created_at=db_workspace.created_at,
            updated_at=db_workspace.updated_at,
            status=db_workspace.status,
        )
    
    @staticmethod
    def from_create(workspace_create: WorkspaceCreate) -> Dict[str, Any]:
        """Convert WorkspaceCreate to SQLAlchemy model data."""
        slug = slugify(workspace_create.name)
        
        return {
            "name": workspace_create.name,
            "slug": slug,
            "description": workspace_create.description,
            "llm_provider": workspace_create.config.llm_config.provider,
            "llm_model": workspace_create.config.llm_config.model,
            "llm_temperature": workspace_create.config.llm_config.temperature,
            "llm_max_tokens": workspace_create.config.llm_config.max_tokens,
            "llm_timeout": workspace_create.config.llm_config.timeout,
            "procurement_prompts": workspace_create.config.procurement_prompts,
            "auto_embed": workspace_create.config.auto_embed,
            "max_documents": workspace_create.config.max_documents,
        }
    
    @staticmethod
    def from_update(workspace_update: WorkspaceUpdate) -> Dict[str, Any]:
        """Convert WorkspaceUpdate to SQLAlchemy model update data."""
        update_data = {}
        
        if workspace_update.name is not None:
            update_data["name"] = workspace_update.name
            update_data["slug"] = slugify(workspace_update.name)
        
        if workspace_update.description is not None:
            update_data["description"] = workspace_update.description
        
        if workspace_update.status is not None:
            update_data["status"] = workspace_update.status
        
        if workspace_update.config is not None:
            config = workspace_update.config
            update_data.update({
                "llm_provider": config.llm_config.provider,
                "llm_model": config.llm_config.model,
                "llm_temperature": config.llm_config.temperature,
                "llm_max_tokens": config.llm_config.max_tokens,
                "llm_timeout": config.llm_config.timeout,
                "procurement_prompts": config.procurement_prompts,
                "auto_embed": config.auto_embed,
                "max_documents": config.max_documents,
            })
        
        # Always update the updated_at timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        return update_data


class QuestionConverter:
    """Converter for Question models."""
    
    @staticmethod
    def to_pydantic(db_question: QuestionModel) -> Question:
        """Convert SQLAlchemy QuestionModel to Pydantic Question."""
        # Reconstruct LLMConfig if override exists
        llm_config = None
        if db_question.llm_provider is not None:
            llm_config = LLMConfig(
                provider=db_question.llm_provider,
                model=db_question.llm_model or "default",
                temperature=db_question.llm_temperature or 0.7,
                max_tokens=db_question.llm_max_tokens,
                timeout=db_question.llm_timeout or 30,
            )
        
        return Question(
            id=db_question.id,
            text=db_question.text,
            expected_fragments=db_question.expected_fragments or [],
            llm_config=llm_config,
        )
    
    @staticmethod
    def from_create(question_create: QuestionCreate, workspace_id: str) -> Dict[str, Any]:
        """Convert QuestionCreate to SQLAlchemy model data."""
        data = {
            "workspace_id": workspace_id,
            "text": question_create.text,
            "expected_fragments": question_create.expected_fragments,
        }
        
        # Add LLM config override if provided
        if question_create.llm_config is not None:
            config = question_create.llm_config
            data.update({
                "llm_provider": config.provider,
                "llm_model": config.model,
                "llm_temperature": config.temperature,
                "llm_max_tokens": config.max_tokens,
                "llm_timeout": config.timeout,
            })
        
        return data


class QuestionResultConverter:
    """Converter for QuestionResult models."""
    
    @staticmethod
    def to_pydantic(db_result: QuestionResultModel) -> QuestionResult:
        """Convert SQLAlchemy QuestionResultModel to Pydantic QuestionResult."""
        return QuestionResult(
            question_id=db_result.question_id,
            question_text=db_result.question_text,
            response=db_result.response,
            confidence_score=db_result.confidence_score,
            processing_time=db_result.processing_time,
            fragments_found=db_result.fragments_found or [],
            success=db_result.success,
            error=db_result.error,
            metadata=db_result.result_metadata,
        )
    
    @staticmethod
    def from_result(
        result: QuestionResult,
        job_id: str,
        question_id: str
    ) -> Dict[str, Any]:
        """Convert QuestionResult to SQLAlchemy model data."""
        return {
            "job_id": job_id,
            "question_id": question_id,
            "question_text": result.question_text,
            "response": result.response,
            "confidence_score": result.confidence_score,
            "processing_time": result.processing_time,
            "fragments_found": result.fragments_found,
            "success": result.success,
            "error": result.error,
            "result_metadata": result.metadata,
        }


# Utility functions for batch conversions
def jobs_to_pydantic(db_jobs: List[JobModel]) -> List[Job]:
    """Convert list of SQLAlchemy JobModel to list of Pydantic Job."""
    return [JobConverter.to_pydantic(job) for job in db_jobs]


def workspaces_to_pydantic(db_workspaces: List[WorkspaceModel]) -> List[Workspace]:
    """Convert list of SQLAlchemy WorkspaceModel to list of Pydantic Workspace."""
    return [WorkspaceConverter.to_pydantic(workspace) for workspace in db_workspaces]


def questions_to_pydantic(db_questions: List[QuestionModel]) -> List[Question]:
    """Convert list of SQLAlchemy QuestionModel to list of Pydantic Question."""
    return [QuestionConverter.to_pydantic(question) for question in db_questions]


def question_results_to_pydantic(db_results: List[QuestionResultModel]) -> List[QuestionResult]:
    """Convert list of SQLAlchemy QuestionResultModel to list of Pydantic QuestionResult."""
    return [QuestionResultConverter.to_pydantic(result) for result in db_results]