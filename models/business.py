from sqlalchemy import Column, Integer, String, Table, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.schema import UniqueConstraint
from database.postgres import Base
from models.audit import AuditMixin

user_units = Table(
    "user_units",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("unit_id", Integer, ForeignKey("units.id"), primary_key=True),
)

class Business(AuditMixin, Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    address = Column(String(255), nullable=True)
    unique_code = Column(String(10), unique=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=True)
    users = relationship("User", secondary="user_business", back_populates="businesses")
    units = relationship("Unit", back_populates="business")
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