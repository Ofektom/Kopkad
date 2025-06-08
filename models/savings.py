from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Enum,
)
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
    CASH = "cash"  # New payment method


class SavingsAccount(AuditMixin, Base):
    __tablename__ = "savings_accounts"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    tracking_number = Column(String(10), unique=True, nullable=False)
    savings_type = Column(
        Enum(SavingsType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SavingsType.DAILY.value,
    )
    daily_amount = Column(Numeric(10, 2), nullable=False)
    duration_months = Column(Integer, nullable=False)
    start_date = Column(Date, nullable=False)
    target_amount = Column(Numeric(10, 2))
    end_date = Column(Date)
    commission_days = Column(Integer, default=30)


class SavingsMarking(AuditMixin, Base):
    __tablename__ = "savings_markings"
    
    id = Column(Integer, primary_key=True)
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id"), nullable=False)
    marked_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    marked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_reference = Column(String(50), nullable=True)
    status = Column(
        Enum(SavingsStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SavingsStatus.PENDING.value,
    )
    payment_method = Column(
        Enum(PaymentMethod, values_callable=lambda obj: [e.value for e in obj]),
        nullable=True  # Allow null for existing records
    )

    __table_args__ = (
        UniqueConstraint("savings_account_id", "marked_date", name="unique_marking"),
    )