"""Tests for data models."""

import pytest
from datetime import datetime
from uuid import uuid4

from app.models.pydantic_models import (
    Job,
    JobCreate,
    JobStatus,
    JobType,
    Workspace,
    WorkspaceCreate,
    WorkspaceConfig,
    WorkspaceStatus,
    Question,
    QuestionCreate,
    QuestionResult,
    LLMConfig,
    LLMProvider,
)
from app.models.converters import (
    JobConverter,
    WorkspaceConverter,
    QuestionConverter,
    slugify,
)
from app.models.validators import (
    JobValidator,
    WorkspaceValidator,
    QuestionValidator,
    GeneralValidator,
)


class TestPydanticModels:
    """Test Pydantic model validation."""
    
    def test_llm_config_validation(self):
        """Test LLM configuration validation."""
        # Valid config
        config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-3.5-turbo",
            temperature=0.7,
            max_tokens=1000,
            timeout=30
        )
        assert config.provider == LLMProvider.OPENAI
        assert config.model == "gpt-3.5-turbo"
        assert config.temperature == 0.7
        
        # Invalid temperature
        with pytest.raises(ValueError):
            LLMConfig(
                provider=LLMProvider.OPENAI,
                model="gpt-3.5-turbo",
                temperature=3.0  # Too high
            )
    
    def test_job_create_validation(self):
        """Test job creation validation."""
        job_create = JobCreate(
            type=JobType.DOCUMENT_UPLOAD,
            workspace_id="ws_123",
            metadata={"file_count": 5}
        )
        assert job_create.type == JobType.DOCUMENT_UPLOAD
        assert job_create.workspace_id == "ws_123"
        assert job_create.metadata["file_count"] == 5
    
    def test_workspace_create_validation(self):
        """Test workspace creation validation."""
        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-3.5-turbo"
        )
        workspace_config = WorkspaceConfig(llm_config=llm_config)
        
        workspace_create = WorkspaceCreate(
            name="Test Workspace",
            description="A test workspace",
            config=workspace_config
        )
        assert workspace_create.name == "Test Workspace"
        assert workspace_create.config.llm_config.provider == LLMProvider.OPENAI
        
        # Invalid name with special characters
        with pytest.raises(ValueError):
            WorkspaceCreate(
                name="Test/Workspace",  # Invalid character
                config=workspace_config
            )
    
    def test_question_create_validation(self):
        """Test question creation validation."""
        question = QuestionCreate(
            text="What is the contract value?",
            expected_fragments=["$", "million", "value"]
        )
        assert question.text == "What is the contract value?"
        assert len(question.expected_fragments) == 3
        
        # Empty text should fail
        with pytest.raises(ValueError):
            QuestionCreate(text="")
    
    def test_job_properties(self):
        """Test job model properties."""
        job = Job(
            id="job_123",
            type=JobType.DOCUMENT_UPLOAD,
            status=JobStatus.COMPLETED,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress=100.0
        )
        assert job.is_completed is True
        assert job.duration_seconds is not None


class TestConverters:
    """Test model converters."""
    
    def test_slugify(self):
        """Test slug generation."""
        assert slugify("Test Workspace") == "test-workspace"
        assert slugify("My-Special_Project!") == "my-special_project"
        assert slugify("  Multiple   Spaces  ") == "multiple-spaces"
    
    def test_job_converter_from_create(self):
        """Test job converter from create."""
        job_create = JobCreate(
            type=JobType.DOCUMENT_UPLOAD,
            workspace_id="ws_123",
            metadata={"file_count": 5}
        )
        
        db_data = JobConverter.from_create(job_create)
        assert db_data["type"] == JobType.DOCUMENT_UPLOAD
        assert db_data["workspace_id"] == "ws_123"
        assert db_data["metadata"]["file_count"] == 5
    
    def test_workspace_converter_from_create(self):
        """Test workspace converter from create."""
        llm_config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model="gpt-3.5-turbo",
            temperature=0.8
        )
        workspace_config = WorkspaceConfig(llm_config=llm_config)
        workspace_create = WorkspaceCreate(
            name="Test Workspace",
            description="Test description",
            config=workspace_config
        )
        
        db_data = WorkspaceConverter.from_create(workspace_create)
        assert db_data["name"] == "Test Workspace"
        assert db_data["slug"] == "test-workspace"
        assert db_data["llm_provider"] == LLMProvider.OPENAI
        assert db_data["llm_model"] == "gpt-3.5-turbo"
        assert db_data["llm_temperature"] == 0.8


class TestValidators:
    """Test model validators."""
    
    def test_job_status_transition_validation(self):
        """Test job status transition validation."""
        # Valid transitions
        assert JobValidator.validate_job_status_transition(
            JobStatus.PENDING, JobStatus.PROCESSING
        ) is True
        assert JobValidator.validate_job_status_transition(
            JobStatus.PROCESSING, JobStatus.COMPLETED
        ) is True
        
        # Invalid transitions
        assert JobValidator.validate_job_status_transition(
            JobStatus.COMPLETED, JobStatus.PROCESSING
        ) is False
    
    def test_progress_validation(self):
        """Test progress value validation."""
        assert JobValidator.validate_progress_value(0.0, JobStatus.PENDING) is True
        assert JobValidator.validate_progress_value(100.0, JobStatus.COMPLETED) is True
        assert JobValidator.validate_progress_value(50.0, JobStatus.PROCESSING) is True
        
        # Invalid progress values
        assert JobValidator.validate_progress_value(50.0, JobStatus.PENDING) is False
        assert JobValidator.validate_progress_value(50.0, JobStatus.COMPLETED) is False
    
    def test_workspace_name_validation(self):
        """Test workspace name validation."""
        assert WorkspaceValidator.validate_workspace_name("Valid Name") is True
        assert WorkspaceValidator.validate_workspace_name("Test-Workspace_123") is True
        
        # Invalid names
        assert WorkspaceValidator.validate_workspace_name("") is False
        assert WorkspaceValidator.validate_workspace_name("Test/Workspace") is False
        assert WorkspaceValidator.validate_workspace_name("Test:Workspace") is False
    
    def test_workspace_slug_validation(self):
        """Test workspace slug validation."""
        assert WorkspaceValidator.validate_workspace_slug("test-workspace") is True
        assert WorkspaceValidator.validate_workspace_slug("my-project-123") is True
        
        # Invalid slugs
        assert WorkspaceValidator.validate_workspace_slug("Test_Workspace") is False
        assert WorkspaceValidator.validate_workspace_slug("test workspace") is False
        assert WorkspaceValidator.validate_workspace_slug("") is False
    
    def test_llm_config_validation(self):
        """Test LLM configuration validation."""
        assert WorkspaceValidator.validate_llm_config(
            LLMProvider.OPENAI, "gpt-3.5-turbo", 0.7, 1000, 30
        ) is True
        
        # Invalid temperature
        assert WorkspaceValidator.validate_llm_config(
            LLMProvider.OPENAI, "gpt-3.5-turbo", 3.0, 1000, 30
        ) is False
        
        # Invalid model for provider
        assert WorkspaceValidator.validate_llm_config(
            LLMProvider.OPENAI, "invalid-model", 0.7, 1000, 30
        ) is False
    
    def test_question_text_validation(self):
        """Test question text validation."""
        assert QuestionValidator.validate_question_text("What is the value?") is True
        
        # Invalid text
        assert QuestionValidator.validate_question_text("") is False
        assert QuestionValidator.validate_question_text("   ") is False
        assert QuestionValidator.validate_question_text("x" * 2001) is False
    
    def test_confidence_score_validation(self):
        """Test confidence score validation."""
        assert QuestionValidator.validate_confidence_score(0.0) is True
        assert QuestionValidator.validate_confidence_score(0.5) is True
        assert QuestionValidator.validate_confidence_score(1.0) is True
        
        # Invalid scores
        assert QuestionValidator.validate_confidence_score(-0.1) is False
        assert QuestionValidator.validate_confidence_score(1.1) is False
    
    def test_uuid_format_validation(self):
        """Test UUID format validation."""
        valid_uuid = str(uuid4())
        assert GeneralValidator.validate_uuid_format(valid_uuid) is True
        
        # Invalid UUIDs
        assert GeneralValidator.validate_uuid_format("not-a-uuid") is False
        assert GeneralValidator.validate_uuid_format("") is False
    
    def test_pagination_validation(self):
        """Test pagination parameters validation."""
        assert GeneralValidator.validate_pagination_params(1, 20) is True
        assert GeneralValidator.validate_pagination_params(5, 50) is True
        
        # Invalid pagination
        assert GeneralValidator.validate_pagination_params(0, 20) is False
        assert GeneralValidator.validate_pagination_params(1, 0) is False
        assert GeneralValidator.validate_pagination_params(1, 101) is False
    
    def test_string_sanitization(self):
        """Test string input sanitization."""
        # Normal string
        result = GeneralValidator.sanitize_string_input("Hello World")
        assert result == "Hello World"
        
        # String with control characters
        result = GeneralValidator.sanitize_string_input("Hello\x00World\x01")
        assert result == "HelloWorld"
        
        # String with length limit
        result = GeneralValidator.sanitize_string_input("Hello World", max_length=5)
        assert result == "Hello"
        
        # Empty/whitespace string
        result = GeneralValidator.sanitize_string_input("   ")
        assert result == ""