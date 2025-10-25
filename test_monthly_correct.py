import psycopg2
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

now = datetime.now()
month_start = datetime(now.year, now.month, 1)
if now.month == 12:
    month_end = datetime(now.year + 1, 1, 1) - timedelta(seconds=1)
else:
    month_end = datetime(now.year, now.month + 1, 1) - timedelta(seconds=1)

print(f"Testing Monthly Summary (October 2025)")
print(f"Date Range: {month_start.date()} to {month_end.date()}")
print("="*60)

db_url = os.getenv('POSTGRES_URI')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

# Get customers with savings this month
cursor.execute("""
    SELECT u.id, u.full_name, u.email
    FROM users u
    WHERE u.role = 'customer'
    AND EXISTS (
        SELECT 1 FROM savings_accounts sa
        WHERE sa.customer_id = u.id
    )
    LIMIT 10
""")

customers = cursor.fetchall()
print(f"Found {len(customers)} customers with savings accounts\n")

for customer_id, name, email in customers:
    # Check PAID markings this month (matching backend query)
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(sm.amount), 0)
        FROM savings_markings sm
        JOIN savings_accounts sa ON sm.savings_account_id = sa.id
        WHERE sa.customer_id = %s
        AND sm.status = 'paid'
        AND sm.marked_date >= %s
        AND sm.marked_date <= %s
    """, (customer_id, month_start.date(), month_end.date()))
    
    count, total = cursor.fetchone()
    
    if count > 0:
        print(f"Customer: {name} ({email})")
        print(f"  ID: {customer_id}")
        print(f"  PAID Markings This Month: {count}")
        print(f"  Total Amount: ₦{float(total):,.2f}")
        
        # Show recent markings
        cursor.execute("""
            SELECT sm.marked_date, sm.amount, sm.status
            FROM savings_markings sm
            JOIN savings_accounts sa ON sm.savings_account_id = sa.id
            WHERE sa.customer_id = %s
            AND sm.marked_date >= %s
            AND sm.marked_date <= %s
            ORDER BY sm.marked_date DESC
            LIMIT 3
        """, (customer_id, month_start.date(), month_end.date()))
        
        markings = cursor.fetchall()
        print(f"  Recent Markings:")
        for date, amount, status in markings:
            print(f"    {date}: ₦{float(amount):,.2f} ({status})")
        print()

cursor.close()
conn.close()

print("="*60)
print("If your user shows ₦0, they might not have PAID markings this month")
print("Check if markings are still in 'pending' status")
