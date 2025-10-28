from sqlalchemy import Column, Integer, String, Enum, Numeric, ForeignKey, DateTime, Date, Boolean
from sqlalchemy.orm import relationship
from database.postgres_optimized import Base
from models.audit import AuditMixin
import enum

class IncomeType(enum.Enum):
    SALARY = "SALARY"
    SAVINGS = "SAVINGS"
    BORROWED = "BORROWED"
    BUSINESS = "BUSINESS"
    OTHER = "OTHER"
    PLANNER = "PLANNER"  # For budget planning/draft cards

class CardStatus(enum.Enum):
    DRAFT = "DRAFT"       # Planning mode (not yet activated)
    ACTIVE = "ACTIVE"     # Normal expense tracking
    ARCHIVED = "ARCHIVED" # Completed/closed

class ExpenseCategory(enum.Enum):
    FOOD = "FOOD"
    TRANSPORT = "TRANSPORT"
    ENTERTAINMENT = "ENTERTAINMENT"
    UTILITIES = "UTILITIES"
    RENT = "RENT"
    MISC = "MISC"

class ExpenseCard(AuditMixin, Base):
    __tablename__ = "expense_cards"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    name = Column(String(100), nullable=False)
    income_type = Column(Enum(IncomeType, name="income_type"), nullable=False)
    income_amount = Column(Numeric(10, 2), nullable=False, default=0.00)
    balance = Column(Numeric(10, 2), nullable=False, default=0.00)
    savings_id = Column(Integer, ForeignKey("savings_accounts.id", ondelete="SET NULL"), nullable=True)
    income_details = Column(String(255), nullable=True)
    status = Column(Enum(CardStatus, name="card_status"), nullable=False, default=CardStatus.ACTIVE)
    is_plan = Column(Boolean, default=False)  # Quick check if this is a planner card
    expenses = relationship("Expense", back_populates="expense_card", cascade="all, delete")
    savings_account = relationship("SavingsAccount", back_populates="expense_cards")

class Expense(AuditMixin, Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    expense_card_id = Column(Integer, ForeignKey("expense_cards.id", ondelete="CASCADE"), nullable=False)
    category = Column(Enum(ExpenseCategory, name="expensecategory"), nullable=True)
    description = Column(String(255), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)  # Actual amount spent (or planned if is_planned=True)
    date = Column(Date, nullable=False)
    is_planned = Column(Boolean, default=False)  # True if this is a planned expense (not yet spent)
    is_completed = Column(Boolean, default=False)  # True if user checked off this item
    planned_amount = Column(Numeric(10, 2), nullable=True)  # Original planned amount (for comparison)
    purpose = Column(String(255), nullable=True)  # Purpose/reason for this expense
    expense_card = relationship("ExpenseCard", back_populates="expenses")