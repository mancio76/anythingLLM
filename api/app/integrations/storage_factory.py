"""Storage factory for creating storage clients based on configuration."""

from typing import Optional

from app.core.config import Settings, StorageType
from app.core.logging import get_logger
from app.integrations.storage_client import (
    LocalStorageClient,
    S3StorageClient,
    StorageClient,
    StorageConfigError
)

logger = get_logger(__name__)


class StorageFactory:
    """Factory class for creating storage clients."""
    
    @staticmethod
    def create_storage_client(settings: Settings) -> StorageClient:
        """
        Create a storage client based on application settings.
        
        Args:
            settings: Application settings containing storage configuration
            
        Returns:
            Configured storage client instance
            
        Raises:
            StorageConfigError: If storage configuration is invalid
        """
        try:
            if settings.storage_type == StorageType.LOCAL:
                logger.info("Creating local storage client")
                return LocalStorageClient(base_path=settings.storage_path)
            
            elif settings.storage_type == StorageType.S3:
                logger.info("Creating S3 storage client")
                
                # Validate required S3 settings
                if not settings.s3_bucket:
                    raise StorageConfigError("S3 bucket name is required for S3 storage")
                if not settings.s3_region:
                    raise StorageConfigError("S3 region is required for S3 storage")
                
                return S3StorageClient(
                    bucket=settings.s3_bucket,
                    region=settings.s3_region,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key
                )
            
            else:
                raise StorageConfigError(f"Unsupported storage type: {settings.storage_type}")
                
        except StorageConfigError:
            raise
        except Exception as e:
            logger.error(f"Failed to create storage client: {e}")
            raise StorageConfigError(f"Storage client creation failed: {e}") from e
    
    @staticmethod
    def create_local_storage_client(base_path: str) -> LocalStorageClient:
        """
        Create a local storage client with specified base path.
        
        Args:
            base_path: Base directory for file storage
            
        Returns:
            Local storage client instance
        """
        logger.info(f"Creating local storage client with base path: {base_path}")
        return LocalStorageClient(base_path=base_path)
    
    @staticmethod
    def create_s3_storage_client(
        bucket: str,
        region: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None
    ) -> S3StorageClient:
        """
        Create an S3 storage client with specified configuration.
        
        Args:
            bucket: S3 bucket name
            region: AWS region
            aws_access_key_id: AWS access key ID (optional)
            aws_secret_access_key: AWS secret access key (optional)
            
        Returns:
            S3 storage client instance
            
        Raises:
            StorageConfigError: If required parameters are missing
        """
        if not bucket:
            raise StorageConfigError("S3 bucket name is required")
        if not region:
            raise StorageConfigError("S3 region is required")
        
        logger.info(f"Creating S3 storage client for bucket: {bucket}, region: {region}")
        return S3StorageClient(
            bucket=bucket,
            region=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )


# Convenience function for dependency injection
def get_storage_client(settings: Settings) -> StorageClient:
    """
    Get storage client instance for dependency injection.
    
    Args:
        settings: Application settings
        
    Returns:
        Storage client instance
    """
    return StorageFactory.create_storage_client(settings)