# Audit System Guide

## Overview

The audit system automatically tracks who created and modified database records, along with timestamps. This is essential for compliance, debugging, and maintaining data integrity.

## Features

### Automatic Fields

All models that inherit from `AuditMixin` get these fields:

- **`created_by`**: User ID who created the record
- **`created_at`**: Timestamp when created (UTC)
- **`updated_by`**: User ID who last updated the record
- **`updated_at`**: Timestamp when last updated (UTC)

### Automatic Behavior

1. **`created_at`** - Automatically set when a record is inserted (if not already set)
2. **`updated_at`** - Automatically set EVERY time a record is updated
3. **`created_by`** and **`updated_by`** - Should be set explicitly in service code

## How to Use

### 1. Add AuditMixin to Your Model

```python
from models.audit import AuditMixin
from database.postgres import Base

class MyModel(AuditMixin, Base):
    __tablename__ = "my_table"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    # AuditMixin automatically adds: created_by, created_at, updated_by, updated_at
```

### 2. Creating Records

When creating a new record, **always set `created_by`** and optionally set `created_at`:

```python
from datetime import datetime, timezone

async def create_item(request: ItemCreate, current_user: dict, db: Session):
    item = MyModel(
        name=request.name,
        created_by=current_user["user_id"],
        created_at=datetime.now(timezone.utc)  # Optional - will be auto-set if omitted
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
```

**Best Practice**: Always set `created_by` explicitly. The `created_at` will be auto-set if you don't provide it.

### 3. Updating Records

When updating a record, **always set `updated_by`**. The `updated_at` will be automatically set:

```python
async def update_item(item_id: int, request: ItemUpdate, current_user: dict, db: Session):
    item = db.query(MyModel).filter(MyModel.id == item_id).first()

    if not item:
        return error_response(status_code=404, message="Item not found")

    # Update fields
    item.name = request.name

    # Set who updated it (REQUIRED)
    item.updated_by = current_user["user_id"]

    # updated_at is automatically set by the event listener - no need to set manually

    db.commit()
    db.refresh(item)
    return item
```

**Best Practice**: Always set `updated_by`. Do NOT set `updated_at` manually - it's handled automatically.

### 4. What Happens Automatically

#### On Insert (CREATE)

```python
# If you do this:
item = MyModel(name="Test", created_by=1)
db.add(item)
db.commit()

# The system automatically ensures:
# - created_at is set to current UTC time (if not already set)
# - created_by remains as you set it (1)
# - updated_by is None
# - updated_at is None
```

#### On Update

```python
# If you do this:
item.name = "Updated"
item.updated_by = 2
db.commit()

# The system automatically:
# - Sets updated_at to current UTC time (ALWAYS, even if you forget)
# - Keeps updated_by as you set it (2)
# - created_at and created_by remain unchanged
```

## Migration from Old Code

### Current Code Pattern (Manual)

```python
# OLD WAY (still works, but redundant)
item = MyModel(
    name="Test",
    created_by=current_user["user_id"],
    created_at=datetime.now(timezone.utc)  # Redundant
)

# On update:
item.name = "Updated"
item.updated_by = current_user["user_id"]
item.updated_at = datetime.now(timezone.utc)  # Redundant - will be overwritten
```

### Recommended Pattern (With Auto-Audit)

```python
# NEW WAY (recommended)
item = MyModel(
    name="Test",
    created_by=current_user["user_id"]
    # created_at is automatic
)

# On update:
item.name = "Updated"
item.updated_by = current_user["user_id"]
# updated_at is automatic
```

## Important Notes

### ✅ DO

- Always set `created_by` when creating records
- Always set `updated_by` when updating records
- Use `datetime.now(timezone.utc)` if you need to manually set timestamps
- Let the system handle `updated_at` automatically

### ❌ DON'T

- Don't forget to set `created_by` and `updated_by`
- Don't manually set `updated_at` - it's redundant and will be overwritten
- Don't use `func.now()` for audit fields - use `datetime.now(timezone.utc)`
- Don't rely on database defaults for consistency

## Troubleshooting

### Issue: created_at is None

**Cause**: You explicitly set it to None, or there's a database constraint issue.
**Solution**: Don't set `created_at` explicitly, or set it to `datetime.now(timezone.utc)`.

### Issue: updated_at is not updating

**Cause**: The record wasn't actually modified, or the event listener isn't firing.
**Solution**: Ensure you're calling `db.commit()` after making changes.

### Issue: updated_by is None after update

**Cause**: You forgot to set it in the service code.
**Solution**: Always explicitly set `updated_by = current_user["user_id"]` before committing.

## Technical Details

### Event Listeners

The audit system uses SQLAlchemy event listeners:

- **`before_insert`**: Fires before a new record is inserted

  - Sets `created_at` if not already set
  - Preserves `created_by` if already set

- **`before_update`**: Fires before a record is updated
  - Always sets `updated_at` to current time
  - Preserves `updated_by` (must be set in service code)

### Timezone Handling

All timestamps use **UTC timezone** (`datetime.timezone.utc`) for consistency:

- Eliminates timezone confusion
- Makes it easy to convert to user's local timezone in the frontend
- Consistent with PostgreSQL `TIMESTAMP WITH TIME ZONE`

## Testing Audit Fields

```python
# Test creation
item = MyModel(name="Test", created_by=1)
db.add(item)
db.commit()
assert item.created_at is not None
assert item.created_by == 1
assert item.updated_at is None
assert item.updated_by is None

# Test update
item.name = "Updated"
item.updated_by = 2
db.commit()
assert item.updated_at is not None
assert item.updated_by == 2
assert item.updated_at > item.created_at
```

## Summary

The improved audit system:

- ✅ Automatically handles `created_at` (if not set)
- ✅ Automatically handles `updated_at` (always)
- ✅ Requires explicit setting of `created_by` and `updated_by`
- ✅ Uses UTC timezone consistently
- ✅ Reduces code duplication
- ✅ Prevents forgotten audit field updates
- ✅ Works seamlessly with existing code
