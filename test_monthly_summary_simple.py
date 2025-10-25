"""Simple test script to check monthly summary SQL query"""
import sys
sys.path.insert(0, '/Users/decagon/Documents/Ofektom/savings-system')

import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

# Get current month dates
now = datetime.now()
month_start = datetime(now.year, now.month, 1)
if now.month == 12:
    month_end = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
else:
    month_end = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)

print(f"Testing Monthly Summary SQL Query")
print(f"Current Date: {now}")
print(f"Month Start: {month_start.date()}")
print(f"Month End: {month_end.date()}")
print("="*60)

# Connect to database
db_url = os.getenv('POSTGRES_URI')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

# Get all customers
cursor.execute("SELECT id, full_name, email FROM users WHERE role = 'customer' LIMIT 5")
customers = cursor.fetchall()

print(f"\nFound {len(customers)} customers (showing first 5)")

for customer_id, name, email in customers:
    print(f"\n{'='*60}")
    print(f"Customer: {name} ({email})")
    print(f"Customer ID: {customer_id}")
    
    # Check savings accounts
    cursor.execute("""
        SELECT COUNT(*) FROM savings_accounts 
        WHERE customer_id = %s
    """, (customer_id,))
    account_count = cursor.fetchone()[0]
    print(f"Savings Accounts: {account_count}")
    
    # Check all markings this month
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(sm.amount), 0)
        FROM savings_markings sm
        JOIN savings_accounts sa ON sm.savings_account_id = sa.id
        WHERE sa.customer_id = %s
        AND sm.marked_date >= %s
        AND sm.marked_date <= %s
    """, (customer_id, month_start.date(), month_end.date()))
    
    all_markings_count, all_markings_sum = cursor.fetchone()
    print(f"All Markings This Month: {all_markings_count}, Total: ₦{all_markings_sum}")
    
    # Check PAID markings this month
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(sm.amount), 0)
        FROM savings_markings sm
        JOIN savings_accounts sa ON sm.savings_account_id = sa.id
        WHERE sa.customer_id = %s
        AND sm.status = 'PAID'
        AND sm.marked_date >= %s
        AND sm.marked_date <= %s
    """, (customer_id, month_start.date(), month_end.date()))
    
    paid_count, paid_sum = cursor.fetchone()
    print(f"PAID Markings This Month: {paid_count}, Total: ₦{paid_sum}")
    
    # Show recent markings
    if all_markings_count > 0:
        cursor.execute("""
            SELECT sm.marked_date, sm.amount, sm.status
            FROM savings_markings sm
            JOIN savings_accounts sa ON sm.savings_account_id = sa.id
            WHERE sa.customer_id = %s
            AND sm.marked_date >= %s
            AND sm.marked_date <= %s
            ORDER BY sm.marked_date DESC
            LIMIT 5
        """, (customer_id, month_start.date(), month_end.date()))
        
        markings = cursor.fetchall()
        print(f"\nRecent Markings:")
        for date, amount, status in markings:
            print(f"  - {date}: ₦{amount} ({status})")
    
    # Check expenses this month
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(e.actual_amount), 0)
        FROM expenses e
        JOIN expense_cards ec ON e.card_id = ec.id
        WHERE ec.customer_id = %s
        AND e.created_at >= %s
        AND e.created_at <= %s
    """, (customer_id, month_start, month_end))
    
    expense_count, expense_sum = cursor.fetchone()
    print(f"\nExpenses This Month: {expense_count}, Total: ₦{expense_sum}")

cursor.close()
conn.close()

print("\n" + "="*60)
print("Test Complete - Check if PAID markings exist for your test user")
