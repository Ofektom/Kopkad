"""
Base repository with common database operations.
Provides reusable CRUD operations for all repositories.
"""
from typing import TypeVar, Generic, List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.postgres_optimized import Base

T = TypeVar('T', bound=Base)


class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations"""
    
    def __init__(self, model: type[T], db: Session):
        self.model = model
        self.db = db
    
    def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID"""
        return self.db.query(self.model).filter(self.model.id == id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all entities with pagination"""
        return self.db.query(self.model).offset(skip).limit(limit).all()
    
    def create(self, obj_in: Dict[str, Any]) -> T:
        """Create new entity"""
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        self.db.flush()
        return db_obj
    
    def update(self, id: int, obj_in: Dict[str, Any]) -> Optional[T]:
        """Update entity by ID"""
        db_obj = self.get_by_id(id)
        if not db_obj:
            return None
        
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        
        self.db.flush()
        return db_obj
    
    def delete(self, id: int) -> bool:
        """Delete entity by ID"""
        db_obj = self.get_by_id(id)
        if not db_obj:
            return False
        
        self.db.delete(db_obj)
        self.db.flush()
        return True
    
    def find_by(self, **filters) -> List[T]:
        """Find entities by filters"""
        query = self.db.query(self.model)
        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.filter(getattr(self.model, field) == value)
        return query.all()
    
    def find_one_by(self, **filters) -> Optional[T]:
        """Find one entity by filters"""
        query = self.db.query(self.model)
        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.filter(getattr(self.model, field) == value)
        return query.first()
    
    def count(self, **filters) -> int:
        """Count entities matching filters"""
        query = self.db.query(self.model)
        for field, value in filters.items():
            if hasattr(self.model, field):
                query = query.filter(getattr(self.model, field) == value)
        return query.count()
    
    def exists(self, **filters) -> bool:
        """Check if entity exists"""
        return self.count(**filters) > 0

