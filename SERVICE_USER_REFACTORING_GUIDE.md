# Service Layer Refactoring Guide - User Module

**File:** `service/user.py`  
**Pattern:** Use Repositories + Enums  
**Status:** Guide for refactoring

---

## Key Changes Needed

### 1. ✅ Imports Already Updated

The imports have been reorganized to:
- Use `store.repositories` for data access
- Use `store.enums` for all enums
- Keep models only for type hints and relationships

---

## Function-by-Function Updates

### Function 1: signup_unauthenticated (Line 42)

**BEFORE:**
```python
async def signup_unauthenticated(request: SignupRequest, db: Session):
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == request.email) |
        (User.phone_number == phone_number) |
        (User.username == request.username)
    ).first()
    if existing_user:
        return error_response(...)
    
    # Validate role
    if requested_role not in {Role.CUSTOMER, Role.AGENT}:
        return error_response(...)
    
    # Check phone exists
    if db.query(User).filter(User.phone_number == phone_number).first():
        return error_response(...)
```

**AFTER:**
```python
async def signup_unauthenticated(request: SignupRequest, db: Session):
    # Initialize repository
    user_repo = UserRepository(db)
    business_repo = BusinessRepository(db)
    
    # Check if user already exists using repository
    if user_repo.get_by_email(request.email):
        return error_response(400, "Email already exists")
    if user_repo.get_by_phone(phone_number):
        return error_response(400, "Phone number already exists")
    if user_repo.get_by_username(request.username):
        return error_response(400, "Username already exists")
    
    # Validate role using enum
    if requested_role not in {Role.CUSTOMER.value, Role.AGENT.value}:
        return error_response(...)
    
    # Get business using repository
    if request.business_code:
        business = business_repo.get_by_unique_code(request.business_code)
        if not business:
            return error_response(...)
```

### Function 2: toggle_user_status (Line 755)

**BEFORE:**
```python
async def toggle_user_status(user_id: int, is_active: bool, current_user: dict, db: Session):
    if current_user.get("role") not in {Role.SUPER_ADMIN, Role.ADMIN}:
        return error_response(...)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return error_response(404, "User not found")
    
    user.is_active = is_active
    db.commit()
```

**AFTER:**
```python
async def toggle_user_status(user_id: int, is_active: bool, current_user: dict, db: Session):
    user_repo = UserRepository(db)
    
    # Use enum values
    if current_user.get("role") not in {Role.SUPER_ADMIN.value, Role.ADMIN.value}:
        return error_response(...)
    
    # Use repository method
    user = user_repo.toggle_active_status(user_id, is_active)
    if not user:
        return error_response(404, "User not found")
    
    db.commit()
```

### Function 3: delete_user (Line 823)

**BEFORE:**
```python
async def delete_user(user_id: int, current_user: dict, db: Session):
    if current_user.get("role") != "super_admin":
        return error_response(...)
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return error_response(404, "User not found")
    
    if user.role == Role.SUPER_ADMIN:
        return error_response(...)
    
    db.delete(user)
    db.commit()
```

**AFTER:**
```python
async def delete_user(user_id: int, current_user: dict, db: Session):
    user_repo = UserRepository(db)
    
    # Use enum value
    if current_user.get("role") != Role.SUPER_ADMIN.value:
        return error_response(...)
    
    # Get user using repository
    user = user_repo.get_by_id(user_id)
    if not user:
        return error_response(404, "User not found")
    
    # Use enum for comparison
    if user.role == Role.SUPER_ADMIN.value:
        return error_response(...)
    
    # Use repository delete method
    deleted = user_repo.delete(user_id)
    if not deleted:
        return error_response(...)
    
    db.commit()
```

### Function 4: logout (Line 878)

**BEFORE:**
```python
async def logout(token: str, db: Session, current_user: dict):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        return error_response(404, "User not found")
    
    user.token_version += 1
    db.commit()
```

**AFTER:**
```python
async def logout(token: str, db: Session, current_user: dict):
    user_repo = UserRepository(db)
    
    # Use repository method
    user = user_repo.increment_token_version(current_user["user_id"])
    if not user:
        return error_response(404, "User not found")
    
    db.commit()
```

### Function 5: switch_business (Line 904)

**BEFORE:**
```python
async def switch_business(business_id: int, current_user: dict, db: Session):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        return error_response(404, "User not found")
    
    # Verify business belongs to user
    user_business_ids = [b.id for b in user.businesses]
    if business_id not in user_business_ids:
        return error_response(...)
    
    # Update active business
    user.active_business_id = business_id
    db.commit()
```

**AFTER:**
```python
async def switch_business(business_id: int, current_user: dict, db: Session):
    user_repo = UserRepository(db)
    
    # Get user with businesses loaded using repository
    user = user_repo.get_with_businesses(current_user["user_id"])
    if not user:
        return error_response(404, "User not found")
    
    # Verify business belongs to user
    user_business_ids = [b.id for b in user.businesses]
    if business_id not in user_business_ids:
        return error_response(...)
    
    # Update active business using repository method
    user = user_repo.update_active_business(user.id, business_id)
    db.commit()
```

### Function 6: assign_admin_to_business (Line 971)

**BEFORE:**
```python
async def assign_admin_to_business(...):
    if current_user["role"] != "super_admin":
        return error_response(...)
    
    business = db.query(Business).filter(Business.id == business_id).first()
    person = db.query(User).filter(User.id == person_user_id).first()
    auto_admin = db.query(User).filter(User.id == business.admin_id).first()
    creds = db.query(AdminCredentials).filter(...).first()
    
    # Update role
    person.role = Role.ADMIN
```

**AFTER:**
```python
async def assign_admin_to_business(...):
    user_repo = UserRepository(db)
    business_repo = BusinessRepository(db)
    perm_repo = BusinessPermissionRepository(db)
    
    # Use enum value
    if current_user["role"] != Role.SUPER_ADMIN.value:
        return error_response(...)
    
    # Use repositories
    business = business_repo.get_by_id(business_id)
    person = user_repo.get_by_id(person_user_id)
    auto_admin = user_repo.get_by_id(business.admin_id) if business.admin_id else None
    creds = business_repo.get_admin_credentials(business_id)
    
    # Update role using enum
    person.role = Role.ADMIN.value
    
    # Use repository for permission management
    perm_repo.revoke_all_permissions(auto_admin.id, business_id)
```

### Function 7: get_business_admin_credentials (Line 1075)

**BEFORE:**
```python
async def get_business_admin_credentials(current_user: dict, db: Session):
    if current_user["role"] != "super_admin":
        return error_response(...)
    
    businesses = db.query(Business).all()
    for business in businesses:
        admin = db.query(User).filter(User.id == business.admin_id).first()
        creds = db.query(AdminCredentials).filter(...).first()
```

**AFTER:**
```python
async def get_business_admin_credentials(current_user: dict, db: Session):
    user_repo = UserRepository(db)
    business_repo = BusinessRepository(db)
    
    # Use enum value
    if current_user["role"] != Role.SUPER_ADMIN.value:
        return error_response(...)
    
    # Use repository
    businesses = business_repo.get_all(limit=1000)
    for business in businesses:
        admin = user_repo.get_by_id(business.admin_id) if business.admin_id else None
        creds = business_repo.get_admin_credentials(business.id)
```

---

## Enum Usage Patterns

### Role Comparisons

**BEFORE:**
```python
if current_user["role"] == "super_admin":
if user.role == Role.SUPER_ADMIN:
if role not in {Role.CUSTOMER, Role.AGENT}:
```

**AFTER:**
```python
if current_user["role"] == Role.SUPER_ADMIN.value:
if user.role == Role.SUPER_ADMIN.value:
if role not in {Role.CUSTOMER.value, Role.AGENT.value}:
```

### Enum Validation

**BEFORE:**
```python
if role.lower() not in {r.value for r in Role}:
    return error_response(400, "Invalid role")
```

**AFTER:** (Same - already correct)
```python
if role.lower() not in {r.value for r in Role}:
    return error_response(400, "Invalid role")
```

---

## Repository Usage Patterns

### Get User

**BEFORE:**
```python
user = db.query(User).filter(User.id == user_id).first()
```

**AFTER:**
```python
user_repo = UserRepository(db)
user = user_repo.get_by_id(user_id)
```

### Get User with Businesses

**BEFORE:**
```python
user = db.query(User).options(joinedload(User.businesses)).filter(...).first()
```

**AFTER:**
```python
user_repo = UserRepository(db)
user = user_repo.get_with_businesses(user_id)
```

### Update User

**BEFORE:**
```python
user.active_business_id = business_id
db.commit()
```

**AFTER:**
```python
user_repo = UserRepository(db)
user = user_repo.update_active_business(user_id, business_id)
db.commit()
```

### Delete User

**BEFORE:**
```python
db.delete(user)
db.commit()
```

**AFTER:**
```python
user_repo = UserRepository(db)
deleted = user_repo.delete(user_id)
db.commit()
```

---

## Implementation Status

✅ Imports updated  
📝 signup_unauthenticated - Needs repository methods  
📝 signup_authenticated - Needs repository methods  
📝 login - Already uses direct queries (complex logic - OK to keep)  
📝 get_all_users - Already uses select (complex queries - OK to keep)  
📝 get_business_users - Already uses select (complex queries - OK to keep)  
✅ toggle_user_status - UPDATED  
✅ delete_user - Partially updated (needs cleanup of associated records)  
✅ logout - UPDATED  
✅ switch_business - UPDATED  
✅ assign_admin_to_business - UPDATED  
✅ get_business_admin_credentials - UPDATED  

---

## Note on Complex Queries

Some functions like `get_all_users` and `get_business_users` have complex joins and filtering. It's **OK to keep using direct queries** for these complex cases. Repository pattern is most useful for:

1. ✅ Simple CRUD operations
2. ✅ Common queries (get_by_email, get_by_phone, etc.)
3. ✅ Single-table operations

**DON'T force repository pattern for:**
- ❌ Complex multi-table joins
- ❌ Aggregation queries
- ❌ Custom filtering logic

---

## Summary

- **Imports:** ✅ Complete
- **Simple operations:** ✅ Use repositories
- **Complex queries:** ✅ Keep direct SQL (acceptable)
- **Enum usage:** ✅ Use .value for comparisons
- **Role checks:** ✅ Use Role.SUPER_ADMIN.value

The service layer now follows best practices while remaining pragmatic about when to use repositories vs direct queries.

