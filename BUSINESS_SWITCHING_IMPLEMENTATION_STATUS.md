# Business Switching Implementation Status

## ✅ COMPLETED

### 1. Documentation

- ✅ Created `BUSINESS_SWITCHING_API.md` with complete API documentation
- ✅ Created SQL migration files (`add_active_business_id.sql` and `rollback_active_business_id.sql`)

### 2. Database Layer

- ✅ Created migration scripts for `active_business_id` column
- ✅ Updated `User` model with `active_business_id` field and `active_business` relationship

### 3. Schema Layer

- ✅ Updated `UserResponse` schema to include `active_business_id`

### 4. Authentication Layer

- ✅ Updated `create_access_token()` to include `active_business_id` in JWT
- ✅ Updated `get_current_user()` to extract and validate `active_business_id` from JWT

### 5. User Service & API

- ✅ Updated `login()` service to set default `active_business_id`
- ✅ Created `switch_business()` service function
- ✅ Added `/api/v1/auth/switch-business` endpoint

---

## ⚠️ PENDING - Requires Implementation

### 6. Apply Database Migration

**Run the SQL migration:**

```bash
psql -U your_username -d your_database -f add_active_business_id.sql
```

Or if using an ORM migration tool, create an alembic migration.

### 7. Update Service Layer - Add Flexible Business Filtering

The following services need to be updated to support the `business_id` parameter with fallback to `active_business_id`:

#### Pattern to Follow:

```python
async def get_some_data(
    business_id: int | None = None,  # Add this parameter
    # ... other params ...
    current_user: dict,
    db: Session
):
    """
    Business selection logic:
    1. If business_id provided → use it (with validation)
    2. Else use active_business_id from current_user
    3. Super admin with no business_id → show all
    """
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()

    query = db.query(SomeModel)

    # Determine target business
    target_business_id = None

    if current_user["role"] == "customer":
        # Customers: use explicit business_id or active_business_id
        if business_id:
            user_business_ids = [b.id for b in current_user_obj.businesses]
            if business_id not in user_business_ids:
                return error_response(status_code=403, message="Access denied")
            target_business_id = business_id
        elif current_user.get("active_business_id"):
            target_business_id = current_user["active_business_id"]
        # else: show all their businesses

    elif current_user["role"] in ["agent", "sub_agent"]:
        user_business_ids = [b.id for b in current_user_obj.businesses]
        if business_id:
            if business_id not in user_business_ids:
                return error_response(status_code=403, message="Access denied")
            target_business_id = business_id
        elif current_user.get("active_business_id"):
            target_business_id = current_user["active_business_id"]
        else:
            return error_response(status_code=400, message="Please specify business_id")

        query = query.filter(SomeModel.business_id == target_business_id)

    elif current_user["role"] == "admin":
        target_business_id = business_id or current_user.get("active_business_id")
        if not target_business_id:
            return error_response(status_code=400, message="Please specify business_id")
        query = query.filter(SomeModel.business_id == target_business_id)

    elif current_user["role"] == "super_admin":
        if business_id:
            query = query.filter(SomeModel.business_id == business_id)
            target_business_id = business_id
        elif current_user.get("active_business_id"):
            query = query.filter(SomeModel.business_id == current_user["active_business_id"])
            target_business_id = current_user["active_business_id"]
        # else: no filter - show all businesses

    # ... rest of function ...

    return success_response(
        status_code=200,
        message="Data retrieved",
        data={
            "items": [...],
            "filtered_by_business_id": target_business_id  # Include in response
        }
    )
```

#### Files to Update:

1. **`service/savings.py`**

   - ✅ `get_all_savings()` - Add business_id parameter with fallback logic
   - ✅ `get_savings_by_id()` - Verify business access
   - ✅ `get_markings()` - Add business_id parameter

2. **`service/payments.py`**

   - ✅ `get_customer_payments()` - Add business_id parameter
   - ✅ `get_payment_accounts()` - Add business_id parameter
   - ✅ `get_payment_requests()` - Add business_id parameter

3. **`service/expenses.py`**

   - ✅ `get_expense_cards()` - Add business_id parameter
   - ✅ `get_expenses()` - Add business_id parameter
   - ✅ `get_expense_stats()` - Add business_id parameter

4. **`service/business.py`**

   - ✅ `get_business_users()` - Add business_id parameter

5. **`service/financial_advisor.py`**

   - ✅ `get_savings_goals()` - Add business_id parameter
   - ✅ `get_financial_health()` - Add business_id parameter
   - ✅ `get_spending_patterns()` - Add business_id parameter

6. **`service/analytics.py`** (if exists)
   - ✅ All analytics functions - Add business_id parameter

### 8. Update API Layer - Add business_id Query Parameters

Add `business_id` as optional query parameter to all relevant GET endpoints:

1. **`api/savings.py`**

   ```python
   @savings_router.get("")
   async def get_all_savings_endpoint(
       business_id: Optional[int] = Query(None, description="Filter by business ID"),
       customer_id: Optional[int] = Query(None),
       # ... other params ...
   ):
       return await get_all_savings(
           business_id=business_id,
           customer_id=customer_id,
           # ...
       )
   ```

2. **`api/payments.py`**

   - Add `business_id` parameter to GET endpoints

3. **`api/expenses.py`**

   - Add `business_id` parameter to GET endpoints

4. **`api/business.py`**

   - Add `business_id` parameter to GET endpoints

5. **`api/financial_advisor.py`**
   - Add `business_id` parameter to GET endpoints

---

## 📋 Implementation Checklist

### Immediate Tasks (Required)

- [ ] **RUN DATABASE MIGRATION** - Apply `add_active_business_id.sql`
- [ ] Update `service/savings.py` with flexible business filtering
- [ ] Update `service/payments.py` with flexible business filtering
- [ ] Update `service/expenses.py` with flexible business filtering
- [ ] Update `service/business.py` with flexible business filtering
- [ ] Add `business_id` parameter to `api/savings.py` endpoints
- [ ] Add `business_id` parameter to `api/payments.py` endpoints
- [ ] Add `business_id` parameter to `api/expenses.py` endpoints
- [ ] Add `business_id` parameter to `api/business.py` endpoints

### Testing Tasks

- [ ] Test login - verify `active_business_id` in response
- [ ] Test switch-business endpoint
- [ ] Test GET endpoints without `business_id` (uses active_business_id)
- [ ] Test GET endpoints with explicit `business_id` (override)
- [ ] Test as customer role
- [ ] Test as agent role
- [ ] Test as admin role
- [ ] Test as super_admin role
- [ ] Test access validation (user trying to access business they don't belong to)

### Documentation Tasks

- [ ] Update API documentation if auto-generated
- [ ] Add examples to team wiki/docs
- [ ] Create migration runbook
- [ ] Document rollback procedure

---

## 🔧 Quick Start for Developers

### 1. Run Migration

```bash
psql -U postgres -d savings_system -f add_active_business_id.sql
```

### 2. Test Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "08000000002", "pin": "12345"}'
```

Expected response should include:

```json
{
  "data": {
    "active_business_id": 100,
    "access_token": "eyJ..."
  }
}
```

### 3. Test Business Switch

```bash
curl -X POST http://localhost:8000/api/v1/auth/switch-business \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"business_id": 200}'
```

### 4. Test Data Filtering

```bash
# Uses active_business_id from token
curl -X GET http://localhost:8000/api/v1/savings \
  -H "Authorization: Bearer YOUR_NEW_TOKEN"

# Explicitly override business
curl -X GET http://localhost:8000/api/v1/savings?business_id=100 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📞 Support

For questions or issues during implementation:

1. Check `BUSINESS_SWITCHING_API.md` for API specifications
2. Review this file for implementation status
3. Follow the pattern examples provided above
4. Test incrementally after each service update

---

## 🎯 Success Criteria

✅ **Implementation is complete when:**

1. Database migration applied successfully
2. All GET endpoints accept optional `business_id` parameter
3. All services implement flexible business filtering
4. Login returns `active_business_id`
5. Switch-business endpoint works correctly
6. Data automatically filters by active business
7. Explicit `business_id` parameter overrides active business
8. All role-based access rules enforced
9. Tests pass for all scenarios
10. Frontend can successfully switch businesses and see filtered data

---

**Status:** 50% Complete (Core infrastructure done, service layer updates pending)  
**Last Updated:** 2025-01-29  
**Next Step:** Run database migration and update service layer
