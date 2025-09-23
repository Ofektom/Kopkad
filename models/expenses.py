from sqlalchemy import Column, Integer, String, Enum, Numeric, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship
from database.postgres import Base
from models.audit import AuditMixin
import enum

class IncomeType(enum.Enum):
    SALARY = "SALARY"
    SAVINGS = "SAVINGS"
    BORROWED = "BORROWED"
    BUSINESS = "BUSINESS"
    OTHER = "OTHER"

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
    expenses = relationship("Expense", back_populates="expense_card", cascade="all, delete")
    savings_account = relationship("SavingsAccount", back_populates="expense_cards")

class Expense(AuditMixin, Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    expense_card_id = Column(Integer, ForeignKey("expense_cards.id", ondelete="CASCADE"), nullable=False)
    category = Column(Enum(ExpenseCategory, name="expensecategory"), nullable=True)
    description = Column(String(255), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    date = Column(Date, nullable=False)
    expense_card = relationship("ExpenseCard", back_populates="expenses")