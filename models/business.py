from sqlalchemy import Column, Integer, String, Table, ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.schema import UniqueConstraint
from database.postgres_optimized import Base
from models.audit import AuditMixin
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import Enum

user_units = Table(
    "user_units",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("unit_id", Integer, ForeignKey("units.id"), primary_key=True),
)

class BusinessType(PyEnum):
    STANDARD = "standard"
    COOPERATIVE = "cooperative"

class Business(AuditMixin, Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    address = Column(String(255), nullable=True)
    unique_code = Column(String(10), unique=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=True)
    business_type = Column(
        Enum(BusinessType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=BusinessType.STANDARD,
        server_default=BusinessType.STANDARD.value
    )
    users = relationship("User", secondary="user_business", back_populates="businesses")
    units = relationship("Unit", back_populates="business")
    agent = relationship("User", foreign_keys=[agent_id], backref="owned_businesses")
    admin = relationship("User", foreign_keys=[admin_id], backref="managed_businesses")
    admin_credentials = relationship("AdminCredentials", back_populates="business", uselist=False, cascade="all, delete")
    __table_args__ = (UniqueConstraint("agent_id", name="unique_agent_id"),)

class Unit(Base):
    __tablename__ = "units"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    location = Column(String(255), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    business = relationship("Business", back_populates="units")
    members = relationship("User", secondary=user_units, backref="unit_memberships")

class PendingBusinessRequest(Base):
    __tablename__ = "pending_business_requests"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    token = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class AdminCredentials(Base):
    """Store temporary credentials for auto-created business admins."""
    __tablename__ = "admin_credentials"
    
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), unique=True, nullable=False)
    admin_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    temp_password = Column(String(255), nullable=False)
    is_password_changed = Column(Boolean, default=False, nullable=False)
    is_assigned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    business = relationship("Business", back_populates="admin_credentials")
    admin_user = relationship("User", foreign_keys=[admin_user_id])


class BusinessPermission(Base):
    """Business-scoped permissions for admins."""
    __tablename__ = "business_permissions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    permission = Column(String(50), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    business = relationship("Business")
    grantor = relationship("User", foreign_keys=[granted_by])