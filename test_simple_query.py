"""Simple direct database query to check savings markings"""
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

print("=" * 80)
print("SIMPLE SAVINGS MARKINGS CHECK")
print("=" * 80)
print(f"\nCurrent Month: {now.strftime('%B %Y')}")
print(f"Date Range: {month_start.date()} to {month_end.date()}")

db_url = os.getenv('POSTGRES_URI')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

# Check total markings across all time
cursor.execute("""
    SELECT 
        COUNT(*) as total_markings,
        COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_markings,
        COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) as total_paid_amount
    FROM savings_markings
""")
total_all = cursor.fetchone()
print(f"\n📊 ALL TIME STATISTICS:")
print(f"  Total Markings: {total_all[0]}")
print(f"  Paid Markings: {total_all[1]}")
print(f"  Total Paid Amount: ₦{float(total_all[2]):,.2f}")

# Check markings this month
cursor.execute("""
    SELECT 
        COUNT(*) as total_markings,
        COUNT(CASE WHEN status = 'paid' THEN 1 END) as paid_markings,
        COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) as total_paid_amount
    FROM savings_markings
    WHERE marked_date >= %s AND marked_date <= %s
""", (month_start.date(), month_end.date()))
total_month = cursor.fetchone()
print(f"\n📅 THIS MONTH (October 2025):")
print(f"  Total Markings: {total_month[0]}")
print(f"  Paid Markings: {total_month[1]}")
print(f"  Total Paid Amount: ₦{float(total_month[2]):,.2f}")

# Show recent paid markings
cursor.execute("""
    SELECT marked_date, amount, status
    FROM savings_markings
    WHERE status = 'paid'
    ORDER BY marked_date DESC
    LIMIT 10
""")
recent = cursor.fetchall()
print(f"\n📝 RECENT PAID MARKINGS (Last 10):")
for date, amount, status in recent:
    print(f"  {date} | ₦{float(amount):,.2f} | {status}")

cursor.close()
conn.close()

print("\n" + "=" * 80)
print("✅ DIAGNOSIS COMPLETE")
print("=" * 80)
print("\nCONCLUSION:")
print(f"- All-time paid savings: ₦{float(total_all[2]):,.2f}")
print(f"- This month paid savings: ₦{float(total_month[2]):,.2f}")
print("\nSOLUTION: Update dashboard to show all-time totals, not just current month!")
print("=" * 80)

