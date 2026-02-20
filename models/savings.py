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
    DateTime,
)
from sqlalchemy.orm import relationship
from database.postgres_optimized import Base
from models.audit import AuditMixin
from enum import Enum as PyEnum
from datetime import datetime

class SavingsType(PyEnum):
    DAILY = "daily"
    TARGET = "target"
    COOPERATIVE = "cooperative"

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

class PaymentInitiationStatus(str, PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

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
    commission_amount = Column(Numeric(10, 2), nullable=False)
    marking_status = Column(
        Enum(MarkingStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=MarkingStatus.NOT_STARTED,
    )

    markings = relationship("SavingsMarking", back_populates="savings_account", cascade="all, delete")
    commissions = relationship("Commission", back_populates="savings_account", cascade="all, delete")
    expense_cards = relationship("ExpenseCard", back_populates="savings_account", cascade="all, delete")


    # Cooperative Group Link
    group_id = Column(Integer, ForeignKey("savings_groups.id"), nullable=True)
    group = relationship("SavingsGroup", back_populates="savings_accounts")
    payment_initiations = relationship("PaymentInitiation", back_populates="savings_account")

class SavingsMarking(AuditMixin, Base):
    __tablename__ = "savings_markings"
    
    id = Column(Integer, primary_key=True)
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id", ondelete="CASCADE"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=True)
    marked_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    marked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_reference = Column(String(100), nullable=True)
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

    payment_initiations = relationship("PaymentInitiation", back_populates="savings_marking")

    __table_args__ = (
        UniqueConstraint("savings_account_id", "marked_date", name="unique_marking"),
    )


class PaymentInitiation(Base):
    __tablename__ = "payment_initiations"

    id = Column(Integer, primary_key=True, index=True)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    reference = Column(String(100), nullable=False, index=True)
    status = Column(Enum(PaymentInitiationStatus), default=PaymentInitiationStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Foreign keys for traceability
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Assuming your User table is "users"
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id"), nullable=True)  # Optional for bulk/multi-account
    payment_method = Column(String(50), nullable=True)  # e.g., "card", "bank_transfer"
    
    # Store additional context (important for verify step)
    metadata = Column(JSONB, nullable=True)

    # Relationships (optional but useful)
    user = relationship("User", back_populates="payment_initiations")  # If User has backref
    savings_account = relationship("SavingsAccount", back_populates="payment_initiations")  # If SavingsAccount has backref

    savings_marking_id = Column(Integer, ForeignKey("savings_markings.id"), nullable=True)
    savings_marking = relationship("SavingsMarking", back_populates="payment_initiations")

    def __repr__(self):
        return f"<PaymentInitiation(id={self.id}, key={self.idempotency_key}, ref={self.reference}, status={self.status})>"