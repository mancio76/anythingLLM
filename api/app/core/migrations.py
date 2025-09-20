"""Database migration management."""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings

logger = logging.getLogger(__name__)


class MigrationManager:
    """Database migration manager."""
    
    def __init__(self, settings: Settings):
        """Initialize migration manager.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.alembic_cfg_path = Path(__file__).parent.parent.parent / "alembic.ini"
        
    def get_alembic_config(self) -> Config:
        """Get Alembic configuration.
        
        Returns:
            Alembic configuration object
        """
        alembic_cfg = Config(str(self.alembic_cfg_path))
        alembic_cfg.set_main_option("sqlalchemy.url", self.settings.database_url)
        return alembic_cfg
    
    async def check_migration_status(self, engine: AsyncEngine) -> dict:
        """Check current migration status.
        
        Args:
            engine: Database engine
            
        Returns:
            Migration status information
        """
        try:
            async with engine.connect() as conn:
                # Check if alembic_version table exists
                result = await conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'alembic_version'
                    );
                """))
                table_exists = result.scalar()
                
                if not table_exists:
                    return {
                        "status": "uninitialized",
                        "current_revision": None,
                        "head_revision": None,
                        "pending_migrations": True
                    }
                
                # Get current revision
                result = await conn.execute(text("SELECT version_num FROM alembic_version;"))
                current_revision = result.scalar()
                
                # Get head revision from Alembic
                alembic_cfg = self.get_alembic_config()
                script_dir = ScriptDirectory.from_config(alembic_cfg)
                head_revision = script_dir.get_current_head()
                
                return {
                    "status": "initialized",
                    "current_revision": current_revision,
                    "head_revision": head_revision,
                    "pending_migrations": current_revision != head_revision
                }
                
        except Exception as e:
            logger.error(f"Failed to check migration status: {e}")
            return {
                "status": "error",
                "error": str(e),
                "current_revision": None,
                "head_revision": None,
                "pending_migrations": True
            }
    
    async def run_migrations(self, engine: AsyncEngine) -> bool:
        """Run database migrations.
        
        Args:
            engine: Database engine
            
        Returns:
            True if migrations ran successfully, False otherwise
        """
        try:
            logger.info("Checking migration status...")
            status = await self.check_migration_status(engine)
            
            if status["status"] == "error":
                logger.error(f"Migration status check failed: {status.get('error')}")
                return False
            
            if not status["pending_migrations"]:
                logger.info("Database is up to date, no migrations needed")
                return True
            
            logger.info(f"Running migrations from {status['current_revision']} to {status['head_revision']}")
            
            # Run migrations in a separate process to avoid async issues with Alembic
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._run_alembic_upgrade
            )
            
            if result:
                logger.info("Database migrations completed successfully")
                return True
            else:
                logger.error("Database migrations failed")
                return False
                
        except Exception as e:
            logger.error(f"Failed to run migrations: {e}")
            return False
    
    def _run_alembic_upgrade(self) -> bool:
        """Run Alembic upgrade command.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            alembic_cfg = self.get_alembic_config()
            command.upgrade(alembic_cfg, "head")
            return True
        except Exception as e:
            logger.error(f"Alembic upgrade failed: {e}")
            return False
    
    async def create_migration(self, message: str, auto_generate: bool = True) -> bool:
        """Create a new migration.
        
        Args:
            message: Migration message
            auto_generate: Whether to auto-generate migration from model changes
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Creating migration: {message}")
            
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._run_alembic_revision, message, auto_generate
            )
            
            if result:
                logger.info(f"Migration created successfully: {message}")
                return True
            else:
                logger.error(f"Failed to create migration: {message}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create migration: {e}")
            return False
    
    def _run_alembic_revision(self, message: str, auto_generate: bool) -> bool:
        """Run Alembic revision command.
        
        Args:
            message: Migration message
            auto_generate: Whether to auto-generate
            
        Returns:
            True if successful, False otherwise
        """
        try:
            alembic_cfg = self.get_alembic_config()
            if auto_generate:
                command.revision(alembic_cfg, message=message, autogenerate=True)
            else:
                command.revision(alembic_cfg, message=message)
            return True
        except Exception as e:
            logger.error(f"Alembic revision failed: {e}")
            return False
    
    async def rollback_migration(self, revision: str = "-1") -> bool:
        """Rollback to a specific migration.
        
        Args:
            revision: Target revision (default: previous migration)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Rolling back to revision: {revision}")
            
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._run_alembic_downgrade, revision
            )
            
            if result:
                logger.info(f"Rollback completed successfully to: {revision}")
                return True
            else:
                logger.error(f"Rollback failed to: {revision}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to rollback migration: {e}")
            return False
    
    def _run_alembic_downgrade(self, revision: str) -> bool:
        """Run Alembic downgrade command.
        
        Args:
            revision: Target revision
            
        Returns:
            True if successful, False otherwise
        """
        try:
            alembic_cfg = self.get_alembic_config()
            command.downgrade(alembic_cfg, revision)
            return True
        except Exception as e:
            logger.error(f"Alembic downgrade failed: {e}")
            return False


def get_migration_manager(settings: Optional[Settings] = None) -> MigrationManager:
    """Get migration manager instance.
    
    Args:
        settings: Application settings
        
    Returns:
        MigrationManager instance
    """
    from app.core.config import get_settings
    return MigrationManager(settings or get_settings())