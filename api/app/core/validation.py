"""Input validation utilities with detailed error messages."""

import re
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError


class ValidationResult:
    """Result of validation operation."""
    
    def __init__(self, is_valid: bool = True, errors: Optional[List[str]] = None):
        self.is_valid = is_valid
        self.errors = errors or []
    
    def add_error(self, error: str):
        """Add validation error."""
        self.is_valid = False
        self.errors.append(error)
    
    def merge(self, other: 'ValidationResult'):
        """Merge with another validation result."""
        if not other.is_valid:
            self.is_valid = False
            self.errors.extend(other.errors)


class InputValidator:
    """Comprehensive input validation utilities."""
    
    @staticmethod
    def validate_uuid(value: str, field_name: str = "id") -> ValidationResult:
        """Validate UUID format."""
        result = ValidationResult()
        
        if not value:
            result.add_error(f"{field_name} is required")
            return result
        
        try:
            UUID(value)
        except ValueError:
            result.add_error(f"{field_name} must be a valid UUID")
        
        return result
    
    @staticmethod
    def validate_string(
        value: str,
        field_name: str,
        min_length: int = 1,
        max_length: int = 255,
        pattern: Optional[str] = None,
        required: bool = True,
    ) -> ValidationResult:
        """Validate string with length and pattern constraints."""
        result = ValidationResult()
        
        if not value:
            if required:
                result.add_error(f"{field_name} is required")
            return result
        
        if not isinstance(value, str):
            result.add_error(f"{field_name} must be a string")
            return result
        
        if len(value) < min_length:
            result.add_error(f"{field_name} must be at least {min_length} characters long")
        
        if len(value) > max_length:
            result.add_error(f"{field_name} must be at most {max_length} characters long")
        
        if pattern and not re.match(pattern, value):
            result.add_error(f"{field_name} format is invalid")
        
        return result
    
    @staticmethod
    def validate_email(value: str, field_name: str = "email") -> ValidationResult:
        """Validate email format."""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return InputValidator.validate_string(
            value, field_name, min_length=5, max_length=254, pattern=email_pattern
        )
    
    @staticmethod
    def validate_url(value: str, field_name: str = "url") -> ValidationResult:
        """Validate URL format."""
        url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return InputValidator.validate_string(
            value, field_name, min_length=10, max_length=2048, pattern=url_pattern
        )
    
    @staticmethod
    def validate_integer(
        value: Any,
        field_name: str,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        required: bool = True,
    ) -> ValidationResult:
        """Validate integer with range constraints."""
        result = ValidationResult()
        
        if value is None:
            if required:
                result.add_error(f"{field_name} is required")
            return result
        
        try:
            int_value = int(value)
        except (ValueError, TypeError):
            result.add_error(f"{field_name} must be an integer")
            return result
        
        if min_value is not None and int_value < min_value:
            result.add_error(f"{field_name} must be at least {min_value}")
        
        if max_value is not None and int_value > max_value:
            result.add_error(f"{field_name} must be at most {max_value}")
        
        return result
    
    @staticmethod
    def validate_float(
        value: Any,
        field_name: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        required: bool = True,
    ) -> ValidationResult:
        """Validate float with range constraints."""
        result = ValidationResult()
        
        if value is None:
            if required:
                result.add_error(f"{field_name} is required")
            return result
        
        try:
            float_value = float(value)
        except (ValueError, TypeError):
            result.add_error(f"{field_name} must be a number")
            return result
        
        if min_value is not None and float_value < min_value:
            result.add_error(f"{field_name} must be at least {min_value}")
        
        if max_value is not None and float_value > max_value:
            result.add_error(f"{field_name} must be at most {max_value}")
        
        return result
    
    @staticmethod
    def validate_list(
        value: Any,
        field_name: str,
        min_items: int = 0,
        max_items: Optional[int] = None,
        item_validator: Optional[callable] = None,
        required: bool = True,
    ) -> ValidationResult:
        """Validate list with size and item constraints."""
        result = ValidationResult()
        
        if value is None:
            if required:
                result.add_error(f"{field_name} is required")
            return result
        
        if not isinstance(value, list):
            result.add_error(f"{field_name} must be a list")
            return result
        
        if len(value) < min_items:
            result.add_error(f"{field_name} must contain at least {min_items} items")
        
        if max_items is not None and len(value) > max_items:
            result.add_error(f"{field_name} must contain at most {max_items} items")
        
        if item_validator:
            for i, item in enumerate(value):
                item_result = item_validator(item, f"{field_name}[{i}]")
                result.merge(item_result)
        
        return result
    
    @staticmethod
    def validate_choice(
        value: Any,
        field_name: str,
        choices: List[Any],
        required: bool = True,
    ) -> ValidationResult:
        """Validate value is in allowed choices."""
        result = ValidationResult()
        
        if value is None:
            if required:
                result.add_error(f"{field_name} is required")
            return result
        
        if value not in choices:
            result.add_error(f"{field_name} must be one of: {', '.join(map(str, choices))}")
        
        return result
    
    @staticmethod
    def validate_file_size(
        file_size: int,
        max_size: int,
        field_name: str = "file",
    ) -> ValidationResult:
        """Validate file size."""
        result = ValidationResult()
        
        if file_size <= 0:
            result.add_error(f"{field_name} cannot be empty")
        elif file_size > max_size:
            max_size_mb = max_size / (1024 * 1024)
            current_size_mb = file_size / (1024 * 1024)
            result.add_error(
                f"{field_name} size ({current_size_mb:.1f}MB) exceeds maximum allowed size ({max_size_mb:.1f}MB)"
            )
        
        return result
    
    @staticmethod
    def validate_file_type(
        filename: str,
        allowed_types: List[str],
        field_name: str = "file",
    ) -> ValidationResult:
        """Validate file type by extension."""
        result = ValidationResult()
        
        if not filename:
            result.add_error(f"{field_name} name is required")
            return result
        
        file_extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        if not file_extension:
            result.add_error(f"{field_name} must have a file extension")
        elif file_extension not in [ext.lower() for ext in allowed_types]:
            result.add_error(
                f"{field_name} type '.{file_extension}' is not allowed. "
                f"Allowed types: {', '.join(allowed_types)}"
            )
        
        return result


class ValidationErrorFormatter:
    """Format validation errors for API responses."""
    
    @staticmethod
    def format_pydantic_errors(errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format Pydantic validation errors."""
        formatted_errors = []
        
        for error in errors:
            field_path = '.'.join(str(loc) for loc in error['loc'])
            formatted_errors.append({
                "field": field_path,
                "message": error['msg'],
                "type": error['type'],
                "input": error.get('input'),
            })
        
        return {
            "validation_errors": formatted_errors,
            "error_count": len(formatted_errors),
        }
    
    @staticmethod
    def format_validation_result(result: ValidationResult, field: str = None) -> Dict[str, Any]:
        """Format ValidationResult for API response."""
        return {
            "field": field,
            "errors": result.errors,
            "error_count": len(result.errors),
        }


def validate_and_raise(result: ValidationResult, field: str = None):
    """Validate result and raise ValidationError if invalid."""
    if not result.is_valid:
        details = ValidationErrorFormatter.format_validation_result(result, field)
        raise ValidationError(
            message=f"Validation failed for {field or 'input'}: {'; '.join(result.errors)}",
            field=field,
            details=details,
        )


def create_validation_error(message: str, field: str = None, details: Dict[str, Any] = None) -> ValidationError:
    """Create a ValidationError with proper formatting."""
    return ValidationError(
        message=message,
        field=field,
        details=details or {},
    )