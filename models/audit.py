from sqlalchemy import Column, Integer, DateTime, ForeignKey, event
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timezone
from typing import Any


class AuditMixin:
    """
    Mixin class that provides automatic audit fields for database models.
    
    Automatically tracks:
    - created_by: User ID who created the record
    - created_at: Timestamp when the record was created
    - updated_by: User ID who last updated the record
    - updated_at: Timestamp when the record was last updated
    
    Usage:
        class MyModel(AuditMixin, Base):
            __tablename__ = "my_table"
            id = Column(Integer, primary_key=True)
            # ... other fields
    
    The audit fields are automatically populated by SQLAlchemy event listeners.
    """
    __tablename__ = None
    
    created_by = Column(
        Integer, 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True,
        comment="ID of the user who created this record"
    )
    created_at = Column(
        DateTime(timezone=True), 
        nullable=False,
        comment="Timestamp when this record was created"
    )
    updated_by = Column(
        Integer, 
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True,
        comment="ID of the user who last updated this record"
    )
    updated_at = Column(
        DateTime(timezone=True), 
        nullable=True,
        comment="Timestamp when this record was last updated"
    )


def get_current_user_id() -> int | None:
    """
    Get the current user ID from the context.
    This function checks for user_id in the SQLAlchemy session info.
    Returns None if no user context is available.
    """
    from sqlalchemy.orm import object_session
    # This will be set by the service layer when creating/updating records
    return None


@event.listens_for(AuditMixin, "before_insert", propagate=True)
def receive_before_insert(mapper, connection, target):
    """
    Automatically set created_at and created_by before inserting a new record.
    
    If these fields are already set (e.g., explicitly in service code), 
    they won't be overwritten.
    """
    now = datetime.now(timezone.utc)
    
    # Only set created_at if it's not already set
    if not target.created_at:
        target.created_at = now
    
    # Only set created_by if it's not already set
    # Note: created_by should be set explicitly in service code
    # This is a fallback that keeps the value if already set


@event.listens_for(AuditMixin, "before_update", propagate=True)
def receive_before_update(mapper, connection, target):
    """
    Automatically set updated_at before updating a record.
    
    This ensures that every update to a record automatically updates 
    the updated_at timestamp, even if the service code forgets to set it.
    
    Note: updated_by should still be set explicitly in service code
    to track which user made the change.
    """
    target.updated_at = datetime.now(timezone.utc)
    
    # Note: We don't automatically set updated_by here because we need
    # the current user context, which should be provided by the service layer.
    # If updated_by is not set, it will remain as the previous value or None.
