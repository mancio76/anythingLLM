"""Document processing service with ZIP file extraction and validation."""

import asyncio
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.anythingllm_client import AnythingLLMClient, DocumentUploadError
from app.integrations.file_validator import FileValidator, FileValidationError
from app.integrations.storage_client import StorageClient
from app.models.pydantic_models import (
    Job,
    JobCreate,
    JobResponse,
    JobStatus,
    JobType,
)
from app.repositories.job_repository import JobRepository

logger = get_logger(__name__)


class DocumentProcessingError(Exception):
    """Document processing error."""
    pass


class ZipExtractionError(DocumentProcessingError):
    """ZIP file extraction error."""
    pass


class ProcessingResult:
    """Result of document processing operation."""
    
    def __init__(
        self,
        success: bool,
        message: str,
        processed_files: Optional[List[Path]] = None,
        failed_files: Optional[List[Tuple[Path, str]]] = None,
        organized_files: Optional[Dict[str, List[Path]]] = None,
        upload_result: Optional[Dict[str, Any]] = None
    ):
        self.success = success
        self.message = message
        self.processed_files = processed_files or []
        self.failed_files = failed_files or []
        self.organized_files = organized_files or {}
        self.upload_result = upload_result or {}


class DocumentService:
    """Service for document processing operations."""
    
    def __init__(
        self,
        settings: Settings,
        job_repository: JobRepository,
        anythingllm_client: AnythingLLMClient,
        storage_client: StorageClient,
        file_validator: Optional[FileValidator] = None
    ):
        """
        Initialize document service.
        
        Args:
            settings: Application settings
            job_repository: Job repository for tracking operations
            anythingllm_client: AnythingLLM integration client
            storage_client: File storage client
            file_validator: File validator (created from settings if not provided)
        """
        self.settings = settings
        self.job_repository = job_repository
        self.anythingllm_client = anythingllm_client
        self.storage_client = storage_client
        self.file_validator = file_validator or FileValidator.create_from_settings(settings)
        
        # Processing limits
        self.max_zip_size = settings.max_file_size
        self.max_files_per_zip = 100  # Reasonable limit
        self.max_extraction_depth = 3  # Prevent zip bombs
        
        logger.info("Initialized DocumentService")
    
    async def upload_documents(
        self,
        zip_file: UploadFile,
        workspace_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> JobResponse:
        """
        Upload and process ZIP file containing documents.
        
        Args:
            zip_file: Uploaded ZIP file
            workspace_id: Target workspace ID
            metadata: Additional metadata for the job
            
        Returns:
            Job response with processing status
            
        Raises:
            DocumentProcessingError: If upload initiation fails
        """
        logger.info(f"Starting document upload for workspace {workspace_id}")
        
        try:
            # Validate ZIP file size
            if zip_file.size and zip_file.size > self.max_zip_size:
                raise DocumentProcessingError(
                    f"ZIP file size {zip_file.size} bytes exceeds maximum allowed size "
                    f"{self.max_zip_size} bytes"
                )
            
            # Create job for tracking
            job_metadata = {
                "workspace_id": workspace_id,
                "filename": zip_file.filename,
                "file_size": zip_file.size,
                "content_type": zip_file.content_type,
                **(metadata or {})
            }
            
            job = await self.job_repository.create_job(
                job_type=JobType.DOCUMENT_UPLOAD,
                workspace_id=workspace_id,
                metadata=job_metadata
            )
            
            # Start background processing
            asyncio.create_task(self._process_zip_file_async(job.id, zip_file, workspace_id))
            
            logger.info(f"Created document upload job {job.id} for workspace {workspace_id}")
            
            return JobResponse(
                job=job,
                links={
                    "status": f"/api/v1/documents/jobs/{job.id}",
                    "cancel": f"/api/v1/documents/jobs/{job.id}"
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to initiate document upload: {e}")
            raise DocumentProcessingError(f"Failed to initiate upload: {e}")
    
    async def _process_zip_file_async(
        self,
        job_id: str,
        zip_file: UploadFile,
        workspace_id: str
    ) -> None:
        """
        Process ZIP file asynchronously in background.
        
        Args:
            job_id: Job ID for tracking
            zip_file: ZIP file to process
            workspace_id: Target workspace ID
        """
        try:
            # Update job status to processing
            await self.job_repository.update_job_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                progress=0.0
            )
            
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory(prefix="anythingllm_docs_") as temp_dir:
                temp_path = Path(temp_dir)
                
                # Save uploaded file
                zip_path = temp_path / f"{uuid4()}.zip"
                await self._save_uploaded_file(zip_file, zip_path)
                
                # Update progress
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    progress=10.0
                )
                
                # Process the ZIP file
                result = await self.process_zip_file(zip_path, job_id, workspace_id)
                
                # Update job with final result
                if result.success:
                    await self.job_repository.update_job_status(
                        job_id=job_id,
                        status=JobStatus.COMPLETED,
                        progress=100.0,
                        result={
                            "message": result.message,
                            "processed_files": len(result.processed_files),
                            "failed_files": len(result.failed_files),
                            "organized_files": {k: len(v) for k, v in result.organized_files.items()},
                            "upload_result": result.upload_result
                        }
                    )
                    logger.info(f"Successfully completed document processing job {job_id}")
                else:
                    await self.job_repository.update_job_status(
                        job_id=job_id,
                        status=JobStatus.FAILED,
                        progress=0.0,
                        error=result.message
                    )
                    logger.error(f"Document processing job {job_id} failed: {result.message}")
                    
        except Exception as e:
            logger.error(f"Error in background document processing for job {job_id}: {e}")
            try:
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    progress=0.0,
                    error=f"Processing error: {str(e)}"
                )
            except Exception as update_error:
                logger.error(f"Failed to update job status after error: {update_error}")
    
    async def _save_uploaded_file(self, upload_file: UploadFile, destination: Path) -> None:
        """
        Save uploaded file to destination.
        
        Args:
            upload_file: Uploaded file
            destination: Destination path
        """
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            with open(destination, 'wb') as f:
                while chunk := await upload_file.read(8192):
                    f.write(chunk)
            
            logger.debug(f"Saved uploaded file to {destination}")
            
        except Exception as e:
            logger.error(f"Failed to save uploaded file: {e}")
            raise DocumentProcessingError(f"Failed to save uploaded file: {e}")
    
    async def process_zip_file(
        self,
        zip_path: Path,
        job_id: str,
        workspace_id: str
    ) -> ProcessingResult:
        """
        Process ZIP file with extraction, validation, and upload.
        
        Args:
            zip_path: Path to ZIP file
            job_id: Job ID for progress tracking
            workspace_id: Target workspace ID
            
        Returns:
            Processing result with details
        """
        logger.info(f"Processing ZIP file {zip_path} for job {job_id}")
        
        try:
            # Validate ZIP file
            if not zip_path.exists():
                raise DocumentProcessingError(f"ZIP file not found: {zip_path}")
            
            # Create extraction directory
            extract_dir = zip_path.parent / f"extracted_{uuid4()}"
            extract_dir.mkdir(exist_ok=True)
            
            try:
                # Extract ZIP file securely
                extracted_files = await self.extract_zip_safely(zip_path, extract_dir)
                
                # Update progress
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    progress=30.0
                )
                
                # Validate extracted files
                valid_files, invalid_files = self.file_validator.validate_multiple_files(extracted_files)
                
                if not valid_files:
                    error_msg = f"No valid files found in ZIP. Invalid files: {len(invalid_files)}"
                    logger.warning(error_msg)
                    return ProcessingResult(
                        success=False,
                        message=error_msg,
                        failed_files=invalid_files
                    )
                
                # Update progress
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    progress=50.0
                )
                
                # Organize files by type
                organized_files = self.organize_documents_by_type(valid_files)
                
                # Update progress
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    progress=70.0
                )
                
                # Upload to AnythingLLM
                upload_result = await self.upload_to_anythingllm(valid_files, workspace_id)
                
                # Update progress
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.PROCESSING,
                    progress=90.0
                )
                
                success_msg = (
                    f"Successfully processed {len(valid_files)} files "
                    f"({len(invalid_files)} invalid files skipped)"
                )
                
                return ProcessingResult(
                    success=True,
                    message=success_msg,
                    processed_files=valid_files,
                    failed_files=invalid_files,
                    organized_files=organized_files,
                    upload_result=upload_result
                )
                
            finally:
                # Clean up extraction directory
                try:
                    import shutil
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    logger.debug(f"Cleaned up extraction directory {extract_dir}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup extraction directory: {cleanup_error}")
                    
        except Exception as e:
            logger.error(f"Error processing ZIP file {zip_path}: {e}")
            return ProcessingResult(
                success=False,
                message=f"Processing failed: {str(e)}"
            )
    
    async def extract_zip_safely(self, zip_path: Path, extract_to: Path) -> List[Path]:
        """
        Extract ZIP file with security protections.
        
        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract to
            
        Returns:
            List of extracted file paths
            
        Raises:
            ZipExtractionError: If extraction fails or security issues detected
        """
        logger.debug(f"Extracting ZIP file {zip_path} to {extract_to}")
        
        extracted_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Check ZIP file integrity
                bad_file = zip_ref.testzip()
                if bad_file:
                    raise ZipExtractionError(f"Corrupted file in ZIP: {bad_file}")
                
                # Get file list and validate
                file_list = zip_ref.infolist()
                
                if len(file_list) > self.max_files_per_zip:
                    raise ZipExtractionError(
                        f"ZIP contains too many files: {len(file_list)} "
                        f"(max: {self.max_files_per_zip})"
                    )
                
                # Check for zip bombs and path traversal
                total_size = 0
                for file_info in file_list:
                    # Check for path traversal
                    if self._is_path_traversal(file_info.filename):
                        raise ZipExtractionError(
                            f"Path traversal detected in file: {file_info.filename}"
                        )
                    
                    # Check for excessive compression ratio (zip bomb)
                    if file_info.file_size > 0:
                        compression_ratio = file_info.compress_size / file_info.file_size
                        if compression_ratio < 0.01:  # Less than 1% - suspicious
                            logger.warning(
                                f"High compression ratio detected for {file_info.filename}: "
                                f"{compression_ratio:.4f}"
                            )
                    
                    total_size += file_info.file_size
                    
                    # Check total uncompressed size
                    if total_size > self.max_zip_size * 10:  # 10x the ZIP size limit
                        raise ZipExtractionError(
                            f"Total uncompressed size too large: {total_size} bytes"
                        )
                
                # Extract files safely
                for file_info in file_list:
                    if file_info.is_dir():
                        continue
                    
                    # Normalize path and create safe filename
                    safe_filename = self._sanitize_filename(file_info.filename)
                    if not safe_filename:
                        logger.warning(f"Skipping file with invalid name: {file_info.filename}")
                        continue
                    
                    # Extract file
                    try:
                        # Use extract with path parameter to prevent path traversal
                        extracted_path = extract_to / safe_filename
                        extracted_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        with zip_ref.open(file_info) as source:
                            with open(extracted_path, 'wb') as target:
                                # Read in chunks to prevent memory exhaustion
                                while chunk := source.read(8192):
                                    target.write(chunk)
                        
                        extracted_files.append(extracted_path)
                        logger.debug(f"Extracted file: {safe_filename}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to extract file {file_info.filename}: {e}")
                        continue
                
                logger.info(f"Successfully extracted {len(extracted_files)} files from ZIP")
                return extracted_files
                
        except zipfile.BadZipFile as e:
            raise ZipExtractionError(f"Invalid ZIP file: {e}")
        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            raise ZipExtractionError(f"Extraction failed: {e}")
    
    def _is_path_traversal(self, filename: str) -> bool:
        """
        Check if filename contains path traversal attempts.
        
        Args:
            filename: Filename to check
            
        Returns:
            True if path traversal detected
        """
        # Normalize path separators
        normalized = filename.replace('\\', '/')
        
        # Check for directory traversal patterns
        dangerous_patterns = [
            '../',
            '..\\',
            '/..',
            '\\..',
            '//',
            '\\\\',
        ]
        
        for pattern in dangerous_patterns:
            if pattern in normalized:
                return True
        
        # Check for absolute paths
        if normalized.startswith('/') or (len(normalized) > 1 and normalized[1] == ':'):
            return True
        
        return False
    
    def _sanitize_filename(self, filename: str) -> Optional[str]:
        """
        Sanitize filename for safe extraction.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename or None if invalid
        """
        if not filename or filename.strip() == '':
            return None
        
        # Remove directory components and use only the filename
        safe_name = os.path.basename(filename)
        
        if not safe_name or safe_name in ['.', '..']:
            return None
        
        # Remove or replace dangerous characters
        dangerous_chars = '<>:"|?*'
        for char in dangerous_chars:
            safe_name = safe_name.replace(char, '_')
        
        # Limit filename length
        if len(safe_name) > 255:
            name_part, ext_part = os.path.splitext(safe_name)
            safe_name = name_part[:255-len(ext_part)] + ext_part
        
        return safe_name
    
    def validate_file_types(self, files: List[Path]) -> Tuple[List[Path], List[Tuple[Path, str]]]:
        """
        Validate file types for allowed formats.
        
        Args:
            files: List of file paths to validate
            
        Returns:
            Tuple of (valid_files, invalid_files_with_errors)
        """
        logger.debug(f"Validating file types for {len(files)} files")
        
        return self.file_validator.validate_multiple_files(files)
    
    def validate_file_size(self, file_path: Path) -> bool:
        """
        Validate individual file size.
        
        Args:
            file_path: Path to file to validate
            
        Returns:
            True if file size is valid
            
        Raises:
            FileValidationError: If file is too large
        """
        return self.file_validator.validate_file_size(file_path)
    
    def organize_documents_by_type(self, files: List[Path]) -> Dict[str, List[Path]]:
        """
        Organize documents by their type categories.
        
        Args:
            files: List of file paths to organize
            
        Returns:
            Dictionary mapping file types to lists of file paths
        """
        logger.debug(f"Organizing {len(files)} files by type")
        
        return self.file_validator.organize_files_by_type(files)
    
    async def upload_to_anythingllm(
        self,
        files: List[Path],
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Upload files to AnythingLLM workspace.
        
        Args:
            files: List of file paths to upload
            workspace_id: Target workspace ID
            
        Returns:
            Upload result dictionary
            
        Raises:
            DocumentUploadError: If upload fails
        """
        logger.info(f"Uploading {len(files)} files to AnythingLLM workspace {workspace_id}")
        
        if not files:
            return {"success": True, "message": "No files to upload", "files": []}
        
        try:
            # Upload files to AnythingLLM
            upload_response = await self.anythingllm_client.upload_documents(
                workspace_id=workspace_id,
                files=files
            )
            
            result = {
                "success": upload_response.success,
                "message": upload_response.message,
                "files": upload_response.files,
                "uploaded_count": len(files)
            }
            
            logger.info(f"Successfully uploaded {len(files)} files to workspace {workspace_id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to upload files to AnythingLLM: {e}")
            raise DocumentUploadError(f"Upload to AnythingLLM failed: {e}")
    
    async def get_processing_status(self, job_id: str) -> Optional[Job]:
        """
        Get processing status for a document upload job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job details or None if not found
        """
        try:
            job = await self.job_repository.get_by_id(job_id)
            if job and job.type == JobType.DOCUMENT_UPLOAD:
                return job
            return None
            
        except Exception as e:
            logger.error(f"Error getting processing status for job {job_id}: {e}")
            return None
    
    async def cancel_processing(self, job_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancel a document processing job.
        
        Args:
            job_id: Job ID to cancel
            reason: Optional cancellation reason
            
        Returns:
            True if cancellation successful
        """
        try:
            job = await self.job_repository.get_by_id(job_id)
            if not job or job.type != JobType.DOCUMENT_UPLOAD:
                return False
            
            await self.job_repository.cancel_job(job_id, reason)
            logger.info(f"Cancelled document processing job {job_id}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling job {job_id}: {e}")
            return False


# Factory function for dependency injection
def create_document_service(
    settings: Settings,
    job_repository: JobRepository,
    anythingllm_client: AnythingLLMClient,
    storage_client: StorageClient
) -> DocumentService:
    """
    Create DocumentService instance with dependencies.
    
    Args:
        settings: Application settings
        job_repository: Job repository
        anythingllm_client: AnythingLLM client
        storage_client: Storage client
        
    Returns:
        Configured DocumentService instance
    """
    return DocumentService(
        settings=settings,
        job_repository=job_repository,
        anythingllm_client=anythingllm_client,
        storage_client=storage_client
    )