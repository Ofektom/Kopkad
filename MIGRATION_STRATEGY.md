# Migration Strategy

## Current Approach: Direct SQL Scripts

We use **direct SQL scripts** instead of Alembic migrations due to recurring issues with PostgreSQL enum handling in Alembic.

### Why SQL Scripts?

**Problems with Alembic:**
- ❌ Enum already exists errors even on first run
- ❌ Database shows enum doesn't exist but Alembic thinks it does
- ❌ Difficult to debug and resolve conflicts
- ❌ Migration failures break deployment pipeline

**Benefits of SQL Scripts:**
- ✅ Full control over SQL execution
- ✅ No enum handling issues
- ✅ Clear, readable migration files
- ✅ Easy to debug and verify
- ✅ Simple rollback process
- ✅ Works consistently across environments

## Migration Process

### 1. Create Migration

```bash
# Create forward migration
touch migrations/XXX_description.sql

# Create rollback script
touch migrations/XXX_rollback_description.sql
```

### 2. Write SQL

Use transactions and verification:
```sql
BEGIN;
-- Your DDL changes
ALTER TABLE ...
CREATE TABLE ...
COMMIT;

-- Verification
SELECT COUNT(*) FROM new_table;
```

### 3. Run Migration

```bash
psql "postgresql://avnadmin:AVNS_ULX1pSU0CWNrdDvjkZq@kopkad-db-kopkad.l.aivencloud.com:26296/defaultdb?sslmode=require" < migrations/XXX_description.sql
```

### 4. Update Python Models

After SQL migration succeeds:
- Update SQLAlchemy models in `models/`
- Restart FastAPI server
- Test endpoints

### 5. Document

Update `migrations/README.md` with:
- Migration number and date
- Purpose and changes
- Status (pending/applied)

## Alembic Status

**Status:** FROZEN - Reference Only

### What We Keep:
- `alembic/` directory - Historical reference
- `alembic.ini` - Configuration (unused)
- `alembic/versions/` - Past migrations (documentation)

### What We Don't Use:
- ❌ `alembic upgrade head`
- ❌ `alembic revision --autogenerate`
- ❌ `alembic downgrade`

### Checking Alembic State (Reference Only):

```bash
alembic current    # Shows current revision (may be outdated)
alembic history    # Shows migration history (pre-SQL strategy)
```

**Note:** Alembic revision state may not match actual database schema. Use SQL scripts going forward.

## Migration History

### SQL-Based Migrations (Current Strategy)

#### 001 - Business Admin RBAC System (2025-11-04)
- **Status:** ⏳ Ready to apply
- **Script:** `migrations/001_add_business_admin_rbac.sql`
- **Rollback:** `migrations/001_rollback_business_admin_rbac.sql`

#### Previous SQL Migrations (Root Directory)
These were created before organizing into `migrations/` folder:
- `add_business_id_to_expense_cards.sql`
- `add_active_business_id.sql`
- `migrate_expense_planner_fields.sql`
- `add_cancel_payment_request.sql`
- `add_rejection_reason_column.sql`
- `add_performance_indexes.sql`
- `migrate_financial_advisor.sql`
- `migrate_payment_requests.sql`
- `update_created_at.sql`
- `migrate_expenses.sql`

### Alembic Migrations (Historical - Reference Only)

Last Alembic revision before SQL strategy: Check `alembic/versions/` for latest file

Notable Alembic migrations (reference):
- Initial schema setup
- User and business models
- Savings accounts and markings
- Payment system
- Financial advisor features
- Expenses system

## Best Practices

1. ✅ **Always use transactions** (BEGIN/COMMIT)
2. ✅ **Include rollback scripts** for every migration
3. ✅ **Add verification queries** at the end
4. ✅ **Use IF NOT EXISTS** for idempotency
5. ✅ **Add comments** to explain complex changes
6. ✅ **Test on development first** before production
7. ✅ **Backup database** before migrations
8. ✅ **Document in README** after applying

## Troubleshooting

### Migration Fails

```bash
# Check error details
psql "$DB_URL" -c "\dt"  # See what tables exist
psql "$DB_URL" -c "\d table_name"  # Check table structure

# Rollback if needed
psql "$DB_URL" < migrations/XXX_rollback_script.sql
```

### Model Not Updating

1. Restart FastAPI server
2. Clear any Python cache: `find . -type d -name __pycache__ -exec rm -r {} +`
3. Check model imports in `main.py`

---

**Last Updated:** 2025-11-04  
**Migration Strategy:** SQL Scripts Only  
**Alembic Status:** Frozen (Reference Only)

