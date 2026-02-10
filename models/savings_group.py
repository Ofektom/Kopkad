from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Numeric,
    ForeignKey,
    Enum,
    DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.postgres_optimized import Base
from models.audit import AuditMixin
from enum import Enum as PyEnum

class GroupFrequency(PyEnum):
    WEEKLY = "weekly"
    BI_WEEKLY = "bi-weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"

class SavingsGroup(AuditMixin, Base):
    __tablename__ = "savings_groups"

    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String, nullable=True)
    contribution_amount = Column(Numeric(10, 2), nullable=False)
    frequency = Column(
        Enum(GroupFrequency, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=GroupFrequency.MONTHLY
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Integer, default=1)  # 1 for active, 0 for inactive/archived
    
    # Relationships
    savings_accounts = relationship("SavingsAccount", back_populates="group")
    business = relationship("Business", foreign_keys=[business_id])
    creator = relationship("User", foreign_keys=[created_by_id])
