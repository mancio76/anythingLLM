"""Base repository class with common patterns."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union
from datetime import datetime

from sqlalchemy import and_, desc, func, or_, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError, NoResultFound

from app.core.database import Base
from app.models.pydantic_models import PaginationParams

logger = logging.getLogger(__name__)

# Type variables for generic repository
ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class RepositoryError(Exception):
    """Base repository error."""
    pass


class NotFoundError(RepositoryError):
    """Resource not found error."""
    pass


class ConflictError(RepositoryError):
    """Resource conflict error."""
    pass


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType], ABC):
    """Base repository class with common CRUD operations."""
    
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Initialize repository with model and session.
        
        Args:
            model: SQLAlchemy model class
            session: Database session
        """
        self.model = model
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def create(self, obj_in: CreateSchemaType, **kwargs) -> ModelType:
        """Create a new record.
        
        Args:
            obj_in: Creation schema object
            **kwargs: Additional fields to set
            
        Returns:
            Created model instance
            
        Raises:
            ConflictError: If record conflicts with existing data
            RepositoryError: If creation fails
        """
        try:
            # Convert Pydantic model to dict if needed
            if hasattr(obj_in, 'model_dump'):
                obj_data = obj_in.model_dump(exclude_unset=True)
            elif hasattr(obj_in, 'dict'):
                obj_data = obj_in.dict(exclude_unset=True)
            else:
                obj_data = obj_in
            
            # Add any additional kwargs
            obj_data.update(kwargs)
            
            # Create model instance
            db_obj = self.model(**obj_data)
            
            # Add to session and flush to get ID
            self.session.add(db_obj)
            await self.session.flush()
            await self.session.refresh(db_obj)
            
            self.logger.debug(f"Created {self.model.__name__} with ID: {db_obj.id}")
            return db_obj
            
        except IntegrityError as e:
            await self.session.rollback()
            self.logger.error(f"Integrity error creating {self.model.__name__}: {e}")
            raise ConflictError(f"Record conflicts with existing data: {str(e)}")
        except Exception as e:
            await self.session.rollback()
            self.logger.error(f"Error creating {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to create record: {str(e)}")
    
    async def get_by_id(self, id: Union[str, int], load_relationships: bool = False) -> Optional[ModelType]:
        """Get record by ID.
        
        Args:
            id: Record ID
            load_relationships: Whether to eagerly load relationships
            
        Returns:
            Model instance or None if not found
        """
        try:
            query = select(self.model).where(self.model.id == id)
            
            # Add relationship loading if requested
            if load_relationships:
                query = self._add_relationship_loading(query)
            
            result = await self.session.execute(query)
            record = result.scalar_one_or_none()
            
            if record:
                self.logger.debug(f"Found {self.model.__name__} with ID: {id}")
            else:
                self.logger.debug(f"No {self.model.__name__} found with ID: {id}")
            
            return record
            
        except Exception as e:
            self.logger.error(f"Error getting {self.model.__name__} by ID {id}: {e}")
            raise RepositoryError(f"Failed to get record: {str(e)}")
    
    async def get_by_id_or_raise(self, id: Union[str, int], load_relationships: bool = False) -> ModelType:
        """Get record by ID or raise NotFoundError.
        
        Args:
            id: Record ID
            load_relationships: Whether to eagerly load relationships
            
        Returns:
            Model instance
            
        Raises:
            NotFoundError: If record not found
        """
        record = await self.get_by_id(id, load_relationships)
        if not record:
            raise NotFoundError(f"{self.model.__name__} with ID {id} not found")
        return record
    
    async def update(
        self, 
        id: Union[str, int], 
        obj_in: Union[UpdateSchemaType, Dict[str, Any]], 
        **kwargs
    ) -> ModelType:
        """Update record by ID.
        
        Args:
            id: Record ID
            obj_in: Update schema object or dict
            **kwargs: Additional fields to update
            
        Returns:
            Updated model instance
            
        Raises:
            NotFoundError: If record not found
            ConflictError: If update conflicts with existing data
            RepositoryError: If update fails
        """
        try:
            # Get existing record
            db_obj = await self.get_by_id_or_raise(id)
            
            # Convert update data to dict
            if hasattr(obj_in, 'model_dump'):
                update_data = obj_in.model_dump(exclude_unset=True)
            elif hasattr(obj_in, 'dict'):
                update_data = obj_in.dict(exclude_unset=True)
            else:
                update_data = obj_in
            
            # Add any additional kwargs
            update_data.update(kwargs)
            
            # Update fields
            for field, value in update_data.items():
                if hasattr(db_obj, field):
                    setattr(db_obj, field, value)
            
            # Update timestamp if available
            if hasattr(db_obj, 'updated_at'):
                db_obj.updated_at = datetime.utcnow()
            
            await self.session.flush()
            await self.session.refresh(db_obj)
            
            self.logger.debug(f"Updated {self.model.__name__} with ID: {id}")
            return db_obj
            
        except NotFoundError:
            raise
        except IntegrityError as e:
            await self.session.rollback()
            self.logger.error(f"Integrity error updating {self.model.__name__} {id}: {e}")
            raise ConflictError(f"Update conflicts with existing data: {str(e)}")
        except Exception as e:
            await self.session.rollback()
            self.logger.error(f"Error updating {self.model.__name__} {id}: {e}")
            raise RepositoryError(f"Failed to update record: {str(e)}")
    
    async def delete(self, id: Union[str, int]) -> bool:
        """Delete record by ID.
        
        Args:
            id: Record ID
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            RepositoryError: If deletion fails
        """
        try:
            # Check if record exists
            db_obj = await self.get_by_id(id)
            if not db_obj:
                self.logger.debug(f"No {self.model.__name__} found with ID {id} to delete")
                return False
            
            # Delete the record
            await self.session.delete(db_obj)
            await self.session.flush()
            
            self.logger.debug(f"Deleted {self.model.__name__} with ID: {id}")
            return True
            
        except Exception as e:
            await self.session.rollback()
            self.logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            raise RepositoryError(f"Failed to delete record: {str(e)}")
    
    async def list_with_pagination(
        self,
        pagination: PaginationParams,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        load_relationships: bool = False
    ) -> tuple[List[ModelType], int]:
        """List records with pagination and filtering.
        
        Args:
            pagination: Pagination parameters
            filters: Filter conditions
            order_by: Field to order by (default: created_at desc)
            load_relationships: Whether to eagerly load relationships
            
        Returns:
            Tuple of (records, total_count)
        """
        try:
            # Build base query
            query = select(self.model)
            count_query = select(func.count(self.model.id))
            
            # Apply filters
            if filters:
                filter_conditions = self._build_filter_conditions(filters)
                if filter_conditions:
                    query = query.where(and_(*filter_conditions))
                    count_query = count_query.where(and_(*filter_conditions))
            
            # Add relationship loading if requested
            if load_relationships:
                query = self._add_relationship_loading(query)
            
            # Apply ordering
            if order_by:
                if order_by.startswith('-'):
                    # Descending order
                    field_name = order_by[1:]
                    if hasattr(self.model, field_name):
                        query = query.order_by(desc(getattr(self.model, field_name)))
                else:
                    # Ascending order
                    if hasattr(self.model, order_by):
                        query = query.order_by(getattr(self.model, order_by))
            else:
                # Default ordering by created_at desc if available
                if hasattr(self.model, 'created_at'):
                    query = query.order_by(desc(self.model.created_at))
            
            # Apply pagination
            query = query.offset(pagination.offset).limit(pagination.size)
            
            # Execute queries
            result = await self.session.execute(query)
            records = result.scalars().all()
            
            count_result = await self.session.execute(count_query)
            total_count = count_result.scalar()
            
            self.logger.debug(
                f"Listed {len(records)} {self.model.__name__} records "
                f"(page {pagination.page}, total {total_count})"
            )
            
            return list(records), total_count
            
        except Exception as e:
            self.logger.error(f"Error listing {self.model.__name__} records: {e}")
            raise RepositoryError(f"Failed to list records: {str(e)}")
    
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count records with optional filtering.
        
        Args:
            filters: Filter conditions
            
        Returns:
            Number of matching records
        """
        try:
            query = select(func.count(self.model.id))
            
            # Apply filters
            if filters:
                filter_conditions = self._build_filter_conditions(filters)
                if filter_conditions:
                    query = query.where(and_(*filter_conditions))
            
            result = await self.session.execute(query)
            count = result.scalar()
            
            self.logger.debug(f"Counted {count} {self.model.__name__} records")
            return count
            
        except Exception as e:
            self.logger.error(f"Error counting {self.model.__name__} records: {e}")
            raise RepositoryError(f"Failed to count records: {str(e)}")
    
    async def exists(self, id: Union[str, int]) -> bool:
        """Check if record exists by ID.
        
        Args:
            id: Record ID
            
        Returns:
            True if record exists, False otherwise
        """
        try:
            query = select(func.count(self.model.id)).where(self.model.id == id)
            result = await self.session.execute(query)
            count = result.scalar()
            
            exists = count > 0
            self.logger.debug(f"{self.model.__name__} with ID {id} exists: {exists}")
            return exists
            
        except Exception as e:
            self.logger.error(f"Error checking if {self.model.__name__} {id} exists: {e}")
            raise RepositoryError(f"Failed to check existence: {str(e)}")
    
    def _build_filter_conditions(self, filters: Dict[str, Any]) -> List[Any]:
        """Build SQLAlchemy filter conditions from filter dict.
        
        Args:
            filters: Filter conditions
            
        Returns:
            List of SQLAlchemy filter conditions
        """
        conditions = []
        
        for field, value in filters.items():
            if value is None:
                continue
                
            # Handle special filter operators
            if field.endswith('__in') and isinstance(value, (list, tuple)):
                # IN operator
                field_name = field[:-4]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name).in_(value))
            
            elif field.endswith('__not_in') and isinstance(value, (list, tuple)):
                # NOT IN operator
                field_name = field[:-8]
                if hasattr(self.model, field_name):
                    conditions.append(~getattr(self.model, field_name).in_(value))
            
            elif field.endswith('__like'):
                # LIKE operator
                field_name = field[:-6]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name).like(f"%{value}%"))
            
            elif field.endswith('__ilike'):
                # ILIKE operator (case-insensitive)
                field_name = field[:-7]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name).ilike(f"%{value}%"))
            
            elif field.endswith('__gt'):
                # Greater than
                field_name = field[:-4]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name) > value)
            
            elif field.endswith('__gte'):
                # Greater than or equal
                field_name = field[:-5]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name) >= value)
            
            elif field.endswith('__lt'):
                # Less than
                field_name = field[:-4]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name) < value)
            
            elif field.endswith('__lte'):
                # Less than or equal
                field_name = field[:-5]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name) <= value)
            
            elif field.endswith('__ne'):
                # Not equal
                field_name = field[:-4]
                if hasattr(self.model, field_name):
                    conditions.append(getattr(self.model, field_name) != value)
            
            else:
                # Exact match
                if hasattr(self.model, field):
                    conditions.append(getattr(self.model, field) == value)
        
        return conditions
    
    def _add_relationship_loading(self, query):
        """Add relationship loading to query.
        
        This method should be overridden by subclasses to specify
        which relationships to load.
        
        Args:
            query: SQLAlchemy query
            
        Returns:
            Query with relationship loading options
        """
        return query
    
    async def bulk_create(self, objects: List[CreateSchemaType], **kwargs) -> List[ModelType]:
        """Create multiple records in bulk.
        
        Args:
            objects: List of creation schema objects
            **kwargs: Additional fields to set on all objects
            
        Returns:
            List of created model instances
            
        Raises:
            ConflictError: If any record conflicts with existing data
            RepositoryError: If bulk creation fails
        """
        try:
            db_objects = []
            
            for obj_in in objects:
                # Convert Pydantic model to dict if needed
                if hasattr(obj_in, 'model_dump'):
                    obj_data = obj_in.model_dump(exclude_unset=True)
                elif hasattr(obj_in, 'dict'):
                    obj_data = obj_in.dict(exclude_unset=True)
                else:
                    obj_data = obj_in
                
                # Add any additional kwargs
                obj_data.update(kwargs)
                
                # Create model instance
                db_obj = self.model(**obj_data)
                db_objects.append(db_obj)
            
            # Add all objects to session
            self.session.add_all(db_objects)
            await self.session.flush()
            
            # Refresh all objects to get generated IDs
            for db_obj in db_objects:
                await self.session.refresh(db_obj)
            
            self.logger.debug(f"Bulk created {len(db_objects)} {self.model.__name__} records")
            return db_objects
            
        except IntegrityError as e:
            await self.session.rollback()
            self.logger.error(f"Integrity error in bulk create {self.model.__name__}: {e}")
            raise ConflictError(f"Bulk create conflicts with existing data: {str(e)}")
        except Exception as e:
            await self.session.rollback()
            self.logger.error(f"Error in bulk create {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to bulk create records: {str(e)}")
    
    async def bulk_update(
        self, 
        updates: List[Dict[str, Any]], 
        id_field: str = "id"
    ) -> int:
        """Update multiple records in bulk.
        
        Args:
            updates: List of update dictionaries, each must contain the ID field
            id_field: Name of the ID field (default: "id")
            
        Returns:
            Number of updated records
            
        Raises:
            RepositoryError: If bulk update fails
        """
        try:
            updated_count = 0
            
            for update_data in updates:
                if id_field not in update_data:
                    continue
                
                record_id = update_data.pop(id_field)
                
                # Add updated_at timestamp if available
                if hasattr(self.model, 'updated_at'):
                    update_data['updated_at'] = datetime.utcnow()
                
                # Execute update
                stmt = (
                    update(self.model)
                    .where(self.model.id == record_id)
                    .values(**update_data)
                )
                
                result = await self.session.execute(stmt)
                updated_count += result.rowcount
            
            await self.session.flush()
            
            self.logger.debug(f"Bulk updated {updated_count} {self.model.__name__} records")
            return updated_count
            
        except Exception as e:
            await self.session.rollback()
            self.logger.error(f"Error in bulk update {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to bulk update records: {str(e)}")
    
    async def bulk_delete(self, ids: List[Union[str, int]]) -> int:
        """Delete multiple records by IDs.
        
        Args:
            ids: List of record IDs
            
        Returns:
            Number of deleted records
            
        Raises:
            RepositoryError: If bulk deletion fails
        """
        try:
            if not ids:
                return 0
            
            stmt = delete(self.model).where(self.model.id.in_(ids))
            result = await self.session.execute(stmt)
            deleted_count = result.rowcount
            
            await self.session.flush()
            
            self.logger.debug(f"Bulk deleted {deleted_count} {self.model.__name__} records")
            return deleted_count
            
        except Exception as e:
            await self.session.rollback()
            self.logger.error(f"Error in bulk delete {self.model.__name__}: {e}")
            raise RepositoryError(f"Failed to bulk delete records: {str(e)}")