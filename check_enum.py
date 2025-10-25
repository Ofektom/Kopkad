import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv('POSTGRES_URI')
conn = psycopg2.connect(db_url)
cursor = conn.cursor()

print("Checking SavingsStatus enum values:")
cursor.execute("""
    SELECT e.enumlabel 
    FROM pg_enum e
    JOIN pg_type t ON e.enumtypid = t.oid
    WHERE t.typname = 'savingsstatus'
    ORDER BY e.enumsortorder
""")

values = cursor.fetchall()
for val in values:
    print(f"  - '{val[0]}'")

print("\nChecking actual status values in savings_markings table:")
cursor.execute("""
    SELECT DISTINCT status 
    FROM savings_markings 
    ORDER BY status
""")

statuses = cursor.fetchall()
for status in statuses:
    print(f"  - '{status[0]}'")

print("\nChecking markings with status = 'paid' (lowercase):")
cursor.execute("""
    SELECT COUNT(*), COALESCE(SUM(amount), 0)
    FROM savings_markings
    WHERE status = 'paid'
""")
count, total = cursor.fetchone()
print(f"Count: {count}, Total: ₦{total}")

cursor.close()
conn.close()
