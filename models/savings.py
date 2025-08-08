from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Enum,
    JSON,
)
from sqlalchemy.orm import relationship
from database.postgres import Base
from models.audit import AuditMixin
from enum import Enum as PyEnum

class SavingsType(PyEnum):
    DAILY = "daily"
    TARGET = "target"

class SavingsStatus(PyEnum):
    PENDING = "pending"
    PAID = "paid"

class PaymentMethod(PyEnum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"

class MarkingStatus(PyEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class SavingsAccount(AuditMixin, Base):
    __tablename__ = "savings_accounts"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    tracking_number = Column(String(10), unique=True, nullable=False)
    savings_type = Column(
        Enum(SavingsType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SavingsType.DAILY,
    )
    daily_amount = Column(Numeric(10, 2), nullable=False)
    duration_months = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    target_amount = Column(Numeric(10, 2))
    end_date = Column(Date)
    commission_days = Column(Integer, default=30)
    marking_status = Column(
        Enum(MarkingStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=MarkingStatus.NOT_STARTED,
    )

    markings = relationship("SavingsMarking", back_populates="savings_account", cascade="all, delete")

class SavingsMarking(AuditMixin, Base):
    __tablename__ = "savings_markings"
    
    id = Column(Integer, primary_key=True)
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id", ondelete="CASCADE"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    marked_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    marked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_reference = Column(String(50), nullable=True)
    status = Column(
        Enum(SavingsStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SavingsStatus.PENDING,
    )
    payment_method = Column(
        Enum(PaymentMethod, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True
    )
    virtual_account_details = Column(JSON, nullable=True)

    savings_account = relationship("SavingsAccount", back_populates="markings")

    __table_args__ = (
        UniqueConstraint("savings_account_id", "marked_date", name="unique_marking"),
    )