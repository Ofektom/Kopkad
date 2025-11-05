# Database Migrations

## Migration Strategy

We use **direct SQL scripts** instead of Alembic due to PostgreSQL enum handling issues. Alembic is kept for historical reference but is not actively used.

## How to Run a Migration

```bash
# Run migration
psql "postgresql://avnadmin:AVNS_ULX1pSU0CWNrdDvjkZq@kopkad-db-kopkad.l.aivencloud.com:26296/defaultdb?sslmode=require" < migrations/XXX_migration_name.sql

# Verify migration
psql "postgresql://avnadmin:AVNS_ULX1pSU0CWNrdDvjkZq@kopkad-db-kopkad.l.aivencloud.com:26296/defaultdb?sslmode=require" -c "\dt"  # List tables
psql "postgresql://avnadmin:AVNS_ULX1pSU0CWNrdDvjkZq@kopkad-db-kopkad.l.aivencloud.com:26296/defaultdb?sslmode=require" -c "\d table_name"  # Describe table
```

## Rollback a Migration

```bash
psql "postgresql://avnadmin:AVNS_ULX1pSU0CWNrdDvjkZq@kopkad-db-kopkad.l.aivencloud.com:26296/defaultdb?sslmode=require" < migrations/XXX_rollback_migration_name.sql
```

## Migration History

### 001 - Business Admin RBAC System (2025-11-04)
- **File:** `001_add_business_admin_rbac.sql`
- **Rollback:** `001_rollback_business_admin_rbac.sql`
- **Purpose:** Implement auto-admin creation for businesses with business-scoped permissions
- **Tables Added:** 
  - `admin_credentials` - Stores temporary credentials for auto-created admins
  - `business_permissions` - Business-scoped permissions (e.g., admin can approve payments only for their business)
- **Columns Added:** 
  - `businesses.admin_id` - Links business to its auto-created admin
- **Status:** ✅ Applied (2025-11-04)

**Changes:**
- Each business gets an auto-created admin account on creation
- Super admin can view temporary credentials and assign real people to admin roles
- Admin permissions are scoped to their specific business
- Super admin role restricted to user management only (no operational tasks)

### Previous Migrations (Pre-SQL Strategy)

See root directory for earlier SQL scripts:
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

### Alembic Migrations (Historical Reference Only)

**Status:** FROZEN - Alembic is kept for reference but not actively used.

**Last Alembic Revision:** See `alembic/versions/` for complete history

**Do NOT use:**
- `alembic upgrade head`
- `alembic revision --autogenerate`

**Reference only:**
```bash
# View alembic history (reference only)
cd /path/to/savings-system
alembic current
alembic history
```

---

## Migration Naming Convention

Format: `{number}_{descriptive_name}.sql`

Examples:
- `001_add_business_admin_rbac.sql`
- `002_add_user_notifications.sql`
- `003_update_savings_status.sql`

Rollback: `{number}_rollback_{descriptive_name}.sql`

---

## Best Practices

1. **Always create rollback scripts** for each migration
2. **Test on local database first** before production
3. **Backup database** before running migrations
4. **Document changes** in this README
5. **Use transactions** (BEGIN/COMMIT) for atomic operations
6. **Add verification queries** at the end of each script
7. **Update Python models** after running SQL migrations
8. **Restart application** to pick up new schema changes

---

## Quick Reference: Database Connection

```bash
# Connection string
export DB_URL="postgresql://avnadmin:AVNS_ULX1pSU0CWNrdDvjkZq@kopkad-db-kopkad.l.aivencloud.com:26296/defaultdb?sslmode=require"

# Run migration
psql "$DB_URL" < migrations/001_add_business_admin_rbac.sql

# Connect to database
psql "$DB_URL"

# List tables
psql "$DB_URL" -c "\dt"

# Describe table
psql "$DB_URL" -c "\d table_name"

# Count rows
psql "$DB_URL" -c "SELECT COUNT(*) FROM table_name;"
```

---

Last Updated: 2025-11-04

