from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Enum, DateTime
from sqlalchemy.orm import relationship
from database.postgres_optimized import Base
from models.audit import AuditMixin
from enum import Enum as PyEnum
from datetime import datetime, timezone

class PaymentRequestStatus(PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class Commission(Base, AuditMixin):
    __tablename__ = "commissions"
    id = Column(Integer, primary_key=True)
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    commission_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    savings_account = relationship("SavingsAccount", back_populates="commissions")
    agent = relationship("User", foreign_keys=[agent_id])

class PaymentAccount(AuditMixin, Base):
    __tablename__ = "payment_accounts"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    account_details = relationship("AccountDetails", back_populates="payment_account", cascade="all, delete")
    payment_requests = relationship("PaymentRequest", back_populates="payment_account", cascade="all, delete")
    customer = relationship("User", foreign_keys=[customer_id], back_populates="payment_accounts")

class AccountDetails(AuditMixin, Base):
    __tablename__ = "account_details"
    id = Column(Integer, primary_key=True)
    payment_account_id = Column(Integer, ForeignKey("payment_accounts.id", ondelete="CASCADE"), nullable=False)
    account_name = Column(String(100), nullable=False)
    account_number = Column(String(20), nullable=False)
    bank_name = Column(String(100), nullable=False)
    bank_code = Column(String(10), nullable=True)
    account_type = Column(String(50), nullable=True)
    payment_account = relationship("PaymentAccount", back_populates="account_details")

class PaymentRequest(AuditMixin, Base):
    __tablename__ = "payment_requests"
    id = Column(Integer, primary_key=True)
    payment_account_id = Column(Integer, ForeignKey("payment_accounts.id", ondelete="CASCADE"), nullable=False)
    account_details_id = Column(Integer, ForeignKey("account_details.id", ondelete="CASCADE"), nullable=False)
    savings_account_id = Column(Integer, ForeignKey("savings_accounts.id", ondelete="SET NULL"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(
        Enum(PaymentRequestStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=PaymentRequestStatus.PENDING
    )
    request_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    approval_date = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String, nullable=True)
    reference = Column(String(50), nullable=False)
    payment_account = relationship("PaymentAccount", back_populates="payment_requests")
    account_details = relationship("AccountDetails")
    savings_account = relationship("SavingsAccount")