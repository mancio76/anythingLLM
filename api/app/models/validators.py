"""Model validation utilities and custom validators."""

import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from pydantic import field_validator, ValidationError

from app.models.pydantic_models import (
    JobStatus,
    JobType,
    WorkspaceStatus,
    LLMProvider,
)


class ModelValidationError(Exception):
    """Custom exception for model validation errors."""
    
    def __init__(self, message: str, field: str = None, details: Dict[str, Any] = None):
        self.message = message
        self.field = field
        self.details = details or {}
        super().__init__(message)


class JobValidator:
    """Validator for Job-related models."""
    
    @staticmethod
    def validate_job_status_transition(current_status: JobStatus, new_status: JobStatus) -> bool:
        """Validate if job status transition is allowed."""
        # Define allowed transitions
        allowed_transitions = {
            JobStatus.PENDING: [JobStatus.PROCESSING, JobStatus.CANCELLED],
            JobStatus.PROCESSING: [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED],
            JobStatus.COMPLETED: [],  # Terminal state
            JobStatus.FAILED: [],     # Terminal state
            JobStatus.CANCELLED: [],  # Terminal state
        }
        
        return new_status in allowed_transitions.get(current_status, [])
    
    @staticmethod
    def validate_progress_value(progress: float, status: JobStatus) -> bool:
        """Validate progress value based on job status."""
        if status == JobStatus.PENDING and progress != 0.0:
            return False
        elif status == JobStatus.COMPLETED and progress != 100.0:
            return False
        elif status in [JobStatus.FAILED, JobStatus.CANCELLED] and progress > 100.0:
            return False
        return True
    
    @staticmethod
    def validate_job_timing(
        created_at: datetime,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """Validate job timing consistency."""
        if started_at and started_at < created_at:
            return False
        if completed_at and started_at and completed_at < started_at:
            return False
        if completed_at and completed_at < created_at:
            return False
        return True
    
    @staticmethod
    def validate_job_metadata(metadata: Dict[str, Any], job_type: JobType) -> bool:
        """Validate job metadata based on job type."""
        if job_type == JobType.DOCUMENT_UPLOAD:
            required_fields = ["file_count", "total_size"]
            return all(field in metadata for field in required_fields)
        elif job_type == JobType.QUESTION_PROCESSING:
            required_fields = ["question_count"]
            return all(field in metadata for field in required_fields)
        return True


class WorkspaceValidator:
    """Validator for Workspace-related models."""
    
    @staticmethod
    def validate_workspace_name(name: str) -> bool:
        """Validate workspace name format."""
        if not name or len(name.strip()) == 0:
            return False
        if len(name) > 255:
            return False
        
        # Check for invalid characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        return not any(char in name for char in invalid_chars)
    
    @staticmethod
    def validate_workspace_slug(slug: str) -> bool:
        """Validate workspace slug format."""
        if not slug:
            return False
        
        # Slug should be lowercase, alphanumeric with hyphens
        pattern = r'^[a-z0-9-]+$'
        return bool(re.match(pattern, slug))
    
    @staticmethod
    def validate_document_count(count: int, max_documents: Optional[int] = None) -> bool:
        """Validate document count against limits."""
        if count < 0:
            return False
        if max_documents is not None and count > max_documents:
            return False
        return True
    
    @staticmethod
    def validate_llm_config(
        provider: LLMProvider,
        model: str,
        temperature: float,
        max_tokens: Optional[int] = None,
        timeout: int = 30
    ) -> bool:
        """Validate LLM configuration parameters."""
        # Validate temperature range
        if not 0.0 <= temperature <= 2.0:
            return False
        
        # Validate timeout
        if not 1 <= timeout <= 300:
            return False
        
        # Validate max_tokens if provided
        if max_tokens is not None and max_tokens < 1:
            return False
        
        # Validate model name based on provider
        if provider == LLMProvider.OPENAI:
            valid_models = [
                "gpt-3.5-turbo", "gpt-3.5-turbo-16k",
                "gpt-4", "gpt-4-32k", "gpt-4-turbo-preview"
            ]
            return model in valid_models
        elif provider == LLMProvider.ANTHROPIC:
            valid_models = [
                "claude-3-haiku-20240307", "claude-3-sonnet-20240229",
                "claude-3-opus-20240229"
            ]
            return model in valid_models
        elif provider == LLMProvider.OLLAMA:
            # For Ollama, we accept any model name as it's user-configurable
            return bool(model and model.strip())
        
        return True


class QuestionValidator:
    """Validator for Question-related models."""
    
    @staticmethod
    def validate_question_text(text: str) -> bool:
        """Validate question text format."""
        if not text or len(text.strip()) == 0:
            return False
        if len(text) > 2000:
            return False
        return True
    
    @staticmethod
    def validate_expected_fragments(fragments: List[str]) -> bool:
        """Validate expected fragments list."""
        if not isinstance(fragments, list):
            return False
        
        # Check each fragment
        for fragment in fragments:
            if not isinstance(fragment, str) or len(fragment.strip()) == 0:
                return False
            if len(fragment) > 500:  # Reasonable limit for fragments
                return False
        
        return True
    
    @staticmethod
    def validate_confidence_score(score: float) -> bool:
        """Validate confidence score range."""
        return 0.0 <= score <= 1.0
    
    @staticmethod
    def validate_processing_time(time_seconds: float) -> bool:
        """Validate processing time value."""
        return time_seconds >= 0.0
    
    @staticmethod
    def validate_question_batch_size(questions: List[Any]) -> bool:
        """Validate question batch size limits."""
        return 1 <= len(questions) <= 50


class GeneralValidator:
    """General validation utilities."""
    
    @staticmethod
    def validate_uuid_format(uuid_string: str) -> bool:
        """Validate UUID string format."""
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        return bool(re.match(uuid_pattern, uuid_string, re.IGNORECASE))
    
    @staticmethod
    def validate_pagination_params(page: int, size: int) -> bool:
        """Validate pagination parameters."""
        return page >= 1 and 1 <= size <= 100
    
    @staticmethod
    def validate_datetime_range(
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> bool:
        """Validate datetime range consistency."""
        if start_date and end_date:
            return start_date <= end_date
        return True
    
    @staticmethod
    def validate_json_size(json_data: Dict[str, Any], max_size_kb: int = 100) -> bool:
        """Validate JSON data size."""
        import json
        json_string = json.dumps(json_data)
        size_kb = len(json_string.encode('utf-8')) / 1024
        return size_kb <= max_size_kb
    
    @staticmethod
    def sanitize_string_input(input_string: str, max_length: int = None) -> str:
        """Sanitize string input by removing dangerous characters."""
        if not input_string:
            return ""
        
        # Remove null bytes and control characters
        sanitized = ''.join(char for char in input_string if ord(char) >= 32 or char in '\t\n\r')
        
        # Trim whitespace
        sanitized = sanitized.strip()
        
        # Apply length limit if specified
        if max_length and len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized


def validate_model_data(model_class, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate data against a Pydantic model and return validated data."""
    try:
        model_instance = model_class(**data)
        return model_instance.model_dump()
    except ValidationError as e:
        raise ModelValidationError(
            message=f"Validation failed for {model_class.__name__}",
            details={"validation_errors": e.errors()}
        )


def validate_model_update(
    model_class,
    current_data: Dict[str, Any],
    update_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate update data against current model state."""
    # Merge current data with updates
    merged_data = {**current_data, **update_data}
    
    # Validate the merged data
    return validate_model_data(model_class, merged_data)