"""File validation utilities for size and type checking."""

import mimetypes
from pathlib import Path
from typing import List, Optional, Set, Tuple

from app.core.logging import get_logger

logger = get_logger(__name__)


class FileValidationError(Exception):
    """File validation error."""
    pass


class FileValidator:
    """Utility class for file validation operations."""
    
    # MIME type mappings for allowed file types
    ALLOWED_MIME_TYPES = {
        'pdf': {'application/pdf'},
        'json': {'application/json', 'text/json'},
        'csv': {'text/csv', 'application/csv', 'text/plain'}
    }
    
    # File extensions for allowed types
    ALLOWED_EXTENSIONS = {
        'pdf': {'.pdf'},
        'json': {'.json'},
        'csv': {'.csv'}
    }
    
    def __init__(self, max_file_size: int, allowed_file_types: List[str]):
        """
        Initialize file validator.
        
        Args:
            max_file_size: Maximum file size in bytes
            allowed_file_types: List of allowed file type extensions (without dots)
        """
        self.max_file_size = max_file_size
        self.allowed_file_types = {file_type.lower() for file_type in allowed_file_types}
        
        # Build allowed extensions and MIME types based on configuration
        self.allowed_extensions: Set[str] = set()
        self.allowed_mime_types: Set[str] = set()
        
        for file_type in self.allowed_file_types:
            if file_type in self.ALLOWED_EXTENSIONS:
                self.allowed_extensions.update(self.ALLOWED_EXTENSIONS[file_type])
            if file_type in self.ALLOWED_MIME_TYPES:
                self.allowed_mime_types.update(self.ALLOWED_MIME_TYPES[file_type])
        
        logger.info(f"Initialized file validator with max size {max_file_size} bytes "
                   f"and allowed types: {self.allowed_file_types}")
    
    def validate_file_size(self, file_path: Path) -> bool:
        """
        Validate file size against maximum allowed size.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            True if file size is valid
            
        Raises:
            FileValidationError: If file is too large or doesn't exist
        """
        try:
            if not file_path.exists():
                raise FileValidationError(f"File does not exist: {file_path}")
            
            file_size = file_path.stat().st_size
            
            if file_size > self.max_file_size:
                raise FileValidationError(
                    f"File size {file_size} bytes exceeds maximum allowed size "
                    f"{self.max_file_size} bytes for file: {file_path.name}"
                )
            
            logger.debug(f"File size validation passed for {file_path.name}: {file_size} bytes")
            return True
            
        except FileValidationError:
            raise
        except Exception as e:
            logger.error(f"Error validating file size for {file_path}: {e}")
            raise FileValidationError(f"Failed to validate file size: {e}") from e
    
    def validate_file_type(self, file_path: Path) -> bool:
        """
        Validate file type based on extension and MIME type.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            True if file type is valid
            
        Raises:
            FileValidationError: If file type is not allowed
        """
        try:
            if not file_path.exists():
                raise FileValidationError(f"File does not exist: {file_path}")
            
            # Check file extension
            file_extension = file_path.suffix.lower()
            if file_extension not in self.allowed_extensions:
                raise FileValidationError(
                    f"File extension '{file_extension}' is not allowed for file: {file_path.name}. "
                    f"Allowed extensions: {sorted(self.allowed_extensions)}"
                )
            
            # Check MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type and mime_type not in self.allowed_mime_types:
                # Some files might not have detectable MIME types, so we'll be lenient
                # if the extension is correct
                logger.warning(f"MIME type '{mime_type}' not in allowed types for {file_path.name}, "
                              f"but extension '{file_extension}' is allowed")
            
            logger.debug(f"File type validation passed for {file_path.name}: "
                        f"extension={file_extension}, mime_type={mime_type}")
            return True
            
        except FileValidationError:
            raise
        except Exception as e:
            logger.error(f"Error validating file type for {file_path}: {e}")
            raise FileValidationError(f"Failed to validate file type: {e}") from e
    
    def validate_file(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate both file size and type.
        
        Args:
            file_path: Path to the file to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.validate_file_size(file_path)
            self.validate_file_type(file_path)
            return True, None
            
        except FileValidationError as e:
            logger.warning(f"File validation failed for {file_path.name}: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error during file validation for {file_path}: {e}")
            return False, f"Validation error: {e}"
    
    def validate_multiple_files(self, file_paths: List[Path]) -> Tuple[List[Path], List[Tuple[Path, str]]]:
        """
        Validate multiple files and return valid and invalid files separately.
        
        Args:
            file_paths: List of file paths to validate
            
        Returns:
            Tuple of (valid_files, invalid_files_with_errors)
        """
        valid_files = []
        invalid_files = []
        
        for file_path in file_paths:
            is_valid, error_message = self.validate_file(file_path)
            if is_valid:
                valid_files.append(file_path)
            else:
                invalid_files.append((file_path, error_message))
        
        logger.info(f"File validation completed: {len(valid_files)} valid, "
                   f"{len(invalid_files)} invalid out of {len(file_paths)} files")
        
        return valid_files, invalid_files
    
    def get_file_type(self, file_path: Path) -> Optional[str]:
        """
        Get the file type category based on extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File type category (pdf, json, csv) or None if not recognized
        """
        file_extension = file_path.suffix.lower()
        
        for file_type, extensions in self.ALLOWED_EXTENSIONS.items():
            if file_extension in extensions:
                return file_type
        
        return None
    
    def organize_files_by_type(self, file_paths: List[Path]) -> dict[str, List[Path]]:
        """
        Organize files by their type categories.
        
        Args:
            file_paths: List of file paths to organize
            
        Returns:
            Dictionary mapping file types to lists of file paths
        """
        organized = {file_type: [] for file_type in self.allowed_file_types}
        organized['unknown'] = []
        
        for file_path in file_paths:
            file_type = self.get_file_type(file_path)
            if file_type and file_type in self.allowed_file_types:
                organized[file_type].append(file_path)
            else:
                organized['unknown'].append(file_path)
        
        # Remove empty categories
        organized = {k: v for k, v in organized.items() if v}
        
        logger.debug(f"Organized {len(file_paths)} files by type: "
                    f"{[(k, len(v)) for k, v in organized.items()]}")
        
        return organized
    
    @classmethod
    def create_from_settings(cls, settings) -> 'FileValidator':
        """
        Create FileValidator instance from application settings.
        
        Args:
            settings: Application settings object
            
        Returns:
            Configured FileValidator instance
        """
        return cls(
            max_file_size=settings.max_file_size,
            allowed_file_types=settings.allowed_file_types
        )