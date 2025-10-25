"""Test script to check monthly summary data"""
import sys
sys.path.insert(0, '/Users/decagon/Documents/Ofektom/savings-system')

from database.postgres import SessionLocal, engine
# Import all models to resolve SQLAlchemy relationships
from models.savings import SavingsAccount, SavingsMarking, SavingsStatus
from models.user import User
from models.business import Business
from models.payments import Commission
from models.user_business import user_business
from models.expenses import ExpenseCard, Expense
from models.settings import Settings
from models.notifications import Notification
from models.financial_advisor import FinancialAdvisorNotification
from sqlalchemy import func
from datetime import datetime, timedelta
from decimal import Decimal

db = SessionLocal()

# Get current month dates
now = datetime.now()
month_start = datetime(now.year, now.month, 1)
if now.month == 12:
    month_end = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
else:
    month_end = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)

print(f"Testing Monthly Summary")
print(f"Current Date: {now}")
print(f"Month Start: {month_start}")
print(f"Month End: {month_end}")
print("="*60)

# Get all customers
customers = db.query(User).filter(User.role == 'customer').all()
print(f"\nFound {len(customers)} customers")

for customer in customers[:5]:  # Test first 5
    print(f"\n{'='*60}")
    print(f"Customer: {customer.full_name} (ID: {customer.id})")
    
    # Check all savings accounts for this customer
    savings_accounts = db.query(SavingsAccount).filter(
        SavingsAccount.customer_id == customer.id
    ).all()
    print(f"Total Savings Accounts: {len(savings_accounts)}")
    
    # Check markings for this month
    markings_this_month = db.query(SavingsMarking).join(
        SavingsAccount, SavingsMarking.savings_account_id == SavingsAccount.id
    ).filter(
        SavingsAccount.customer_id == customer.id,
        SavingsMarking.marked_date >= month_start.date(),
        SavingsMarking.marked_date <= month_end.date()
    ).all()
    
    print(f"Markings This Month: {len(markings_this_month)}")
    
    if markings_this_month:
        for marking in markings_this_month[:5]:  # Show first 5
            print(f"  - Date: {marking.marked_date}, Amount: {marking.amount}, Status: {marking.status}")
    
    # Check PAID markings
    paid_markings = db.query(SavingsMarking).join(
        SavingsAccount, SavingsMarking.savings_account_id == SavingsAccount.id
    ).filter(
        SavingsAccount.customer_id == customer.id,
        SavingsMarking.status == SavingsStatus.PAID,
        SavingsMarking.marked_date >= month_start.date(),
        SavingsMarking.marked_date <= month_end.date()
    ).all()
    
    print(f"PAID Markings This Month: {len(paid_markings)}")
    
    # Calculate total using the same query as the endpoint
    total_savings = db.query(
        func.coalesce(func.sum(SavingsMarking.amount), 0)
    ).join(
        SavingsAccount, SavingsMarking.savings_account_id == SavingsAccount.id
    ).filter(
        SavingsAccount.customer_id == customer.id,
        SavingsMarking.status == SavingsStatus.PAID,
        SavingsMarking.marked_date >= month_start.date(),
        SavingsMarking.marked_date <= month_end.date()
    ).scalar() or Decimal('0')
    
    print(f"Total Savings (PAID only): ₦{total_savings}")

db.close()
print("\n" + "="*60)
print("Test Complete")
