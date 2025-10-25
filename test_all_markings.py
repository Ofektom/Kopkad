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

print(f"Checking ALL markings in October 2025")
print(f"Date Range: {month_start.date()} to {month_end.date()}")
print("="*60)

db_url = os.getenv('POSTGRES_URI')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

# Check all markings this month regardless of status
cursor.execute("""
    SELECT u.id, u.full_name, u.email,
           COUNT(sm.id) as marking_count,
           COALESCE(SUM(sm.amount), 0) as total_amount,
           STRING_AGG(DISTINCT sm.status, ', ') as statuses
    FROM users u
    JOIN savings_accounts sa ON sa.customer_id = u.id
    JOIN savings_markings sm ON sm.savings_account_id = sa.id
    WHERE u.role = 'customer'
    AND sm.marked_date >= %s
    AND sm.marked_date <= %s
    GROUP BY u.id, u.full_name, u.email
    ORDER BY marking_count DESC
""", (month_start.date(), month_end.date()))

results = cursor.fetchall()

if results:
    print(f"\nFound {len(results)} customers with markings this month:\n")
    for customer_id, name, email, count, total, statuses in results:
        print(f"Customer: {name} ({email})")
        print(f"  ID: {customer_id}")
        print(f"  Total Markings: {count}")
        print(f"  Total Amount: ₦{float(total):,.2f}")
        print(f"  Statuses: {statuses}")
        
        # Show recent markings
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
        print(f"  Recent Markings:")
        for date, amount, status in markings:
            print(f"    {date}: ₦{float(amount):,.2f} ({status})")
        print()
else:
    print("\nNo markings found for October 2025!")
    print("\nLet's check the most recent markings:")
    cursor.execute("""
        SELECT u.full_name, sm.marked_date, sm.amount, sm.status
        FROM savings_markings sm
        JOIN savings_accounts sa ON sm.savings_account_id = sa.id
        JOIN users u ON sa.customer_id = u.id
        WHERE u.role = 'customer'
        ORDER BY sm.marked_date DESC
        LIMIT 10
    """)
    
    recent = cursor.fetchall()
    if recent:
        print("\nMost recent markings in the system:")
        for name, date, amount, status in recent:
            print(f"  {name}: {date} - ₦{float(amount):,.2f} ({status})")
    else:
        print("  No markings found in the entire system!")

cursor.close()
conn.close()
print("\n" + "="*60)
