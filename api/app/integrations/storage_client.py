"""File storage abstraction layer with local and S3 implementations."""

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import urlparse

import aiofiles
import aiofiles.os
from aioboto3 import Session
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic import BaseModel

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class FileNotFoundError(StorageError):
    """File not found in storage."""
    pass


class StorageConfigError(StorageError):
    """Storage configuration error."""
    pass


class FileValidationError(StorageError):
    """File validation error."""
    pass


class FileInfo(BaseModel):
    """File information model."""
    key: str
    size: int
    last_modified: Optional[str] = None
    content_type: Optional[str] = None


class StorageClient(ABC):
    """Abstract base class for file storage clients."""
    
    @abstractmethod
    async def upload_file(self, file_path: Path, key: str) -> str:
        """
        Upload a file to storage.
        
        Args:
            file_path: Local path to the file to upload
            key: Storage key/path for the file
            
        Returns:
            Storage URL or identifier for the uploaded file
            
        Raises:
            StorageError: If upload fails
        """
        pass
    
    @abstractmethod
    async def download_file(self, key: str, destination: Path) -> bool:
        """
        Download a file from storage.
        
        Args:
            key: Storage key/path of the file
            destination: Local path where to save the file
            
        Returns:
            True if download successful, False otherwise
            
        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If download fails
        """
        pass
    
    @abstractmethod
    async def delete_file(self, key: str) -> bool:
        """
        Delete a file from storage.
        
        Args:
            key: Storage key/path of the file to delete
            
        Returns:
            True if deletion successful, False otherwise
            
        Raises:
            StorageError: If deletion fails
        """
        pass
    
    @abstractmethod
    async def list_files(self, prefix: str = "") -> List[FileInfo]:
        """
        List files in storage with optional prefix filter.
        
        Args:
            prefix: Optional prefix to filter files
            
        Returns:
            List of file information objects
            
        Raises:
            StorageError: If listing fails
        """
        pass
    
    @abstractmethod
    async def file_exists(self, key: str) -> bool:
        """
        Check if a file exists in storage.
        
        Args:
            key: Storage key/path of the file
            
        Returns:
            True if file exists, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_file_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Get a URL for accessing the file.
        
        Args:
            key: Storage key/path of the file
            expires_in: URL expiration time in seconds
            
        Returns:
            URL for accessing the file
            
        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If URL generation fails
        """
        pass


class LocalStorageClient(StorageClient):
    """Local filesystem storage implementation."""
    
    def __init__(self, base_path: Union[str, Path]):
        """
        Initialize local storage client.
        
        Args:
            base_path: Base directory for file storage
        """
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized local storage at {self.base_path}")
    
    def _get_full_path(self, key: str) -> Path:
        """Get full local path for a storage key."""
        # Normalize the key to prevent path traversal
        key = key.strip("/")
        key_parts = [part for part in key.split("/") if part and part != "." and part != ".."]
        return self.base_path / Path(*key_parts)
    
    async def upload_file(self, file_path: Path, key: str) -> str:
        """Upload a file to local storage."""
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Source file not found: {file_path}")
            
            destination = self._get_full_path(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Use aiofiles for async file operations
            async with aiofiles.open(file_path, 'rb') as src:
                async with aiofiles.open(destination, 'wb') as dst:
                    while chunk := await src.read(8192):
                        await dst.write(chunk)
            
            logger.info(f"Uploaded file {file_path} to local storage as {key}")
            return str(destination)
            
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} to local storage: {e}")
            raise StorageError(f"Upload failed: {e}") from e
    
    async def download_file(self, key: str, destination: Path) -> bool:
        """Download a file from local storage."""
        try:
            source = self._get_full_path(key)
            
            if not source.exists():
                raise FileNotFoundError(f"File not found: {key}")
            
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(source, 'rb') as src:
                async with aiofiles.open(destination, 'wb') as dst:
                    while chunk := await src.read(8192):
                        await dst.write(chunk)
            
            logger.info(f"Downloaded file {key} from local storage to {destination}")
            return True
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to download file {key} from local storage: {e}")
            raise StorageError(f"Download failed: {e}") from e
    
    async def delete_file(self, key: str) -> bool:
        """Delete a file from local storage."""
        try:
            file_path = self._get_full_path(key)
            
            if not file_path.exists():
                logger.warning(f"File not found for deletion: {key}")
                return False
            
            await aiofiles.os.remove(file_path)
            
            # Clean up empty directories
            try:
                parent = file_path.parent
                while parent != self.base_path and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            except OSError:
                pass  # Directory not empty or other issues
            
            logger.info(f"Deleted file {key} from local storage")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {key} from local storage: {e}")
            raise StorageError(f"Deletion failed: {e}") from e
    
    async def list_files(self, prefix: str = "") -> List[FileInfo]:
        """List files in local storage."""
        try:
            files = []
            search_path = self._get_full_path(prefix) if prefix else self.base_path
            
            if search_path.is_file():
                # If prefix points to a specific file
                stat = search_path.stat()
                relative_path = search_path.relative_to(self.base_path)
                files.append(FileInfo(
                    key=str(relative_path).replace("\\", "/"),
                    size=stat.st_size,
                    last_modified=str(stat.st_mtime)
                ))
            elif search_path.is_dir():
                # If prefix points to a directory
                for file_path in search_path.rglob("*"):
                    if file_path.is_file():
                        stat = file_path.stat()
                        relative_path = file_path.relative_to(self.base_path)
                        files.append(FileInfo(
                            key=str(relative_path).replace("\\", "/"),
                            size=stat.st_size,
                            last_modified=str(stat.st_mtime)
                        ))
            
            logger.debug(f"Listed {len(files)} files with prefix '{prefix}'")
            return files
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix '{prefix}': {e}")
            raise StorageError(f"Listing failed: {e}") from e
    
    async def file_exists(self, key: str) -> bool:
        """Check if a file exists in local storage."""
        try:
            file_path = self._get_full_path(key)
            return file_path.exists() and file_path.is_file()
        except Exception as e:
            logger.error(f"Failed to check file existence for {key}: {e}")
            return False
    
    async def get_file_url(self, key: str, expires_in: int = 3600) -> str:
        """Get a file URL for local storage (file:// URL)."""
        try:
            file_path = self._get_full_path(key)
            
            if not await self.file_exists(key):
                raise FileNotFoundError(f"File not found: {key}")
            
            # Return file:// URL for local files
            return file_path.as_uri()
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate URL for file {key}: {e}")
            raise StorageError(f"URL generation failed: {e}") from e


class S3StorageClient(StorageClient):
    """AWS S3 storage implementation."""
    
    def __init__(self, bucket: str, region: str, aws_access_key_id: Optional[str] = None,
                 aws_secret_access_key: Optional[str] = None):
        """
        Initialize S3 storage client.
        
        Args:
            bucket: S3 bucket name
            region: AWS region
            aws_access_key_id: AWS access key ID (optional, can use IAM roles)
            aws_secret_access_key: AWS secret access key (optional, can use IAM roles)
        """
        self.bucket = bucket
        self.region = region
        
        # Create session with credentials if provided
        session_kwargs = {"region_name": region}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs.update({
                "aws_access_key_id": aws_access_key_id,
                "aws_secret_access_key": aws_secret_access_key
            })
        
        self.session = Session(**session_kwargs)
        logger.info(f"Initialized S3 storage for bucket {bucket} in region {region}")
    
    def _normalize_key(self, key: str) -> str:
        """Normalize S3 key to prevent issues."""
        return key.strip("/")
    
    async def upload_file(self, file_path: Path, key: str) -> str:
        """Upload a file to S3."""
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Source file not found: {file_path}")
            
            key = self._normalize_key(key)
            
            async with self.session.client('s3') as s3:
                await s3.upload_file(str(file_path), self.bucket, key)
            
            s3_url = f"s3://{self.bucket}/{key}"
            logger.info(f"Uploaded file {file_path} to S3 as {s3_url}")
            return s3_url
            
        except NoCredentialsError as e:
            logger.error("AWS credentials not found")
            raise StorageConfigError("AWS credentials not configured") from e
        except ClientError as e:
            logger.error(f"S3 client error during upload: {e}")
            raise StorageError(f"S3 upload failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} to S3: {e}")
            raise StorageError(f"Upload failed: {e}") from e
    
    async def download_file(self, key: str, destination: Path) -> bool:
        """Download a file from S3."""
        try:
            key = self._normalize_key(key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            async with self.session.client('s3') as s3:
                await s3.download_file(self.bucket, key, str(destination))
            
            logger.info(f"Downloaded file {key} from S3 to {destination}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise FileNotFoundError(f"File not found in S3: {key}") from e
            logger.error(f"S3 client error during download: {e}")
            raise StorageError(f"S3 download failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to download file {key} from S3: {e}")
            raise StorageError(f"Download failed: {e}") from e
    
    async def delete_file(self, key: str) -> bool:
        """Delete a file from S3."""
        try:
            key = self._normalize_key(key)
            
            async with self.session.client('s3') as s3:
                await s3.delete_object(Bucket=self.bucket, Key=key)
            
            logger.info(f"Deleted file {key} from S3")
            return True
            
        except ClientError as e:
            logger.error(f"S3 client error during deletion: {e}")
            raise StorageError(f"S3 deletion failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to delete file {key} from S3: {e}")
            raise StorageError(f"Deletion failed: {e}") from e
    
    async def list_files(self, prefix: str = "") -> List[FileInfo]:
        """List files in S3."""
        try:
            prefix = self._normalize_key(prefix)
            files = []
            
            async with self.session.client('s3') as s3:
                paginator = s3.get_paginator('list_objects_v2')
                
                async for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            files.append(FileInfo(
                                key=obj['Key'],
                                size=obj['Size'],
                                last_modified=obj['LastModified'].isoformat(),
                                content_type=obj.get('ContentType')
                            ))
            
            logger.debug(f"Listed {len(files)} files in S3 with prefix '{prefix}'")
            return files
            
        except ClientError as e:
            logger.error(f"S3 client error during listing: {e}")
            raise StorageError(f"S3 listing failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to list files in S3 with prefix '{prefix}': {e}")
            raise StorageError(f"Listing failed: {e}") from e
    
    async def file_exists(self, key: str) -> bool:
        """Check if a file exists in S3."""
        try:
            key = self._normalize_key(key)
            
            async with self.session.client('s3') as s3:
                await s3.head_object(Bucket=self.bucket, Key=key)
            
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"S3 client error checking file existence: {e}")
            raise StorageError(f"S3 existence check failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to check file existence in S3 for {key}: {e}")
            return False
    
    async def get_file_url(self, key: str, expires_in: int = 3600) -> str:
        """Get a presigned URL for S3 file access."""
        try:
            key = self._normalize_key(key)
            
            if not await self.file_exists(key):
                raise FileNotFoundError(f"File not found in S3: {key}")
            
            async with self.session.client('s3') as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket, 'Key': key},
                    ExpiresIn=expires_in
                )
            
            logger.debug(f"Generated presigned URL for S3 file {key}")
            return url
            
        except FileNotFoundError:
            raise
        except ClientError as e:
            logger.error(f"S3 client error generating presigned URL: {e}")
            raise StorageError(f"S3 URL generation failed: {e}") from e
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for S3 file {key}: {e}")
            raise StorageError(f"URL generation failed: {e}") from e