"""Test script to verify savings totals calculation"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv('POSTGRES_URI')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

print("=" * 80)
print("TESTING SAVINGS TOTALS CALCULATION")
print("=" * 80)

# Get customer Fonfon Tommy
cursor.execute("""
    SELECT u.id, u.full_name, u.email
    FROM users u
    WHERE u.full_name ILIKE '%fonfon%tommy%'
    OR u.full_name ILIKE '%tommy%fonfon%'
    LIMIT 1
""")

customer = cursor.fetchone()
if not customer:
    print("\n❌ Customer 'Fonfon Tommy' not found!")
    print("   Searching for similar names...")
    cursor.execute("""
        SELECT id, full_name, email
        FROM users
        WHERE role = 'customer'
        AND (full_name ILIKE '%fonfon%' OR full_name ILIKE '%tommy%')
        LIMIT 5
    """)
    similar = cursor.fetchall()
    if similar:
        print("\n   Found similar customers:")
        for uid, name, email in similar:
            print(f"      - {name} ({email}) [ID: {uid}]")
    cursor.close()
    conn.close()
    exit(1)

customer_id, customer_name, customer_email = customer
print(f"\n✅ Testing with customer: {customer_name} ({customer_email})")
print(f"   Customer ID: {customer_id}")

# Test the exact query from get_monthly_summary (all-time)
cursor.execute("""
    SELECT COALESCE(SUM(sm.amount), 0) as total_savings_all_time
    FROM savings_markings sm
    JOIN savings_accounts sa ON sm.savings_account_id = sa.id
    WHERE sa.customer_id = %s
    AND sm.status = 'paid'
""", (customer_id,))

total_all_time = cursor.fetchone()[0]
print(f"\n📊 ALL-TIME TOTAL (what backend returns):")
print(f"   Total Savings (All Paid Markings): ₦{float(total_all_time):,.2f}")

# Show breakdown by savings account
cursor.execute("""
    SELECT 
        sa.tracking_number,
        sa.savings_type,
        sa.daily_amount,
        COUNT(sm.id) as marking_count,
        COALESCE(SUM(CASE WHEN sm.status = 'paid' THEN sm.amount ELSE 0 END), 0) as amount_paid,
        COALESCE(SUM(CASE WHEN sm.status = 'pending' THEN sm.amount ELSE 0 END), 0) as amount_pending
    FROM savings_accounts sa
    LEFT JOIN savings_markings sm ON sm.savings_account_id = sa.id
    WHERE sa.customer_id = %s
    GROUP BY sa.id, sa.tracking_number, sa.savings_type, sa.daily_amount
    ORDER BY sa.created_at DESC
""", (customer_id,))

accounts = cursor.fetchall()
print(f"\n📋 BREAKDOWN BY SAVINGS ACCOUNT:")
print(f"   Total Accounts: {len(accounts)}")
print()

total_check = 0
for tracking, sav_type, daily_amt, count, paid, pending in accounts:
    print(f"   Account: {tracking}")
    print(f"      Type: {sav_type} | Daily Amount: ₦{float(daily_amt):,.2f}")
    print(f"      Markings: {count}")
    print(f"      Amount Paid: ₦{float(paid):,.2f}")
    print(f"      Amount Pending: ₦{float(pending):,.2f}")
    print()
    total_check += float(paid)

print(f"   ✅ Total (Sum of all accounts): ₦{total_check:,.2f}")
print(f"   ✅ Backend Query Result: ₦{float(total_all_time):,.2f}")
print(f"   {'✅ MATCH!' if abs(total_check - float(total_all_time)) < 0.01 else '❌ MISMATCH!'}")

# Test current month
from datetime import datetime
now = datetime.now()
month_start = datetime(now.year, now.month, 1).date()
if now.month == 12:
    month_end = datetime(now.year + 1, 1, 1).date()
else:
    month_end = datetime(now.year, now.month + 1, 1).date()

cursor.execute("""
    SELECT COALESCE(SUM(sm.amount), 0) as total_savings_month
    FROM savings_markings sm
    JOIN savings_accounts sa ON sm.savings_account_id = sa.id
    WHERE sa.customer_id = %s
    AND sm.status = 'paid'
    AND sm.marked_date >= %s
    AND sm.marked_date < %s
""", (customer_id, month_start, month_end))

total_this_month = cursor.fetchone()[0]
print(f"\n📅 THIS MONTH ({now.strftime('%B %Y')}):")
print(f"   Total Savings: ₦{float(total_this_month):,.2f}")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✅ TEST COMPLETE")
print("=" * 80)
print("\nIf 'All-Time Total' shows a value > 0, the backend is working correctly!")
print("If it shows 0, there may be no PAID markings in the database.")
print("=" * 80)

