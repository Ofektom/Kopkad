from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Enum
from sqlalchemy.orm import relationship
from database.postgres import Base
from models.audit import AuditMixin
from enum import Enum as PyEnum

class PaymentStatus(PyEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class AccountDetails(AuditMixin, Base):
    __tablename__ = "account_details"

    id = Column(Integer, primary_key=True)
    payment_account_id = Column(Integer, ForeignKey("payment_accounts.id", ondelete="CASCADE"), nullable=False)
    account_name = Column(String(100), nullable=False)
    account_number = Column(String(20), nullable=False)
    bank_name = Column(String(100), nullable=False)
    bank_code = Column(String(10), nullable=True)  # Optional bank code for payment processing
    account_type = Column(String(50), nullable=True)  # e.g., "savings", "current"

    payment_account = relationship("PaymentAccount", back_populates="account_details")

class PaymentAccount(AuditMixin, Base):
    __tablename__ = "payment_accounts"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(
        Enum(PaymentStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    payment_reference = Column(String(50), nullable=True)

    account_details = relationship("AccountDetails", back_populates="payment_account", cascade="all, delete")