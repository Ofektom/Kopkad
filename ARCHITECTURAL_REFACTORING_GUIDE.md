# Architectural Refactoring Guide

**Date:** 2025-11-05  
**Status:** 🔄 IN PROGRESS  
**Pattern:** Showroom360-inspired 3-Layer Architecture + Enhanced Native RBAC

---

## Overview

This guide documents the migration from a 2-layer (API + Service) architecture to a 3-layer (Router + Controller + Repository) architecture, inspired by Showroom360 while maintaining our enhanced native RBAC strengths.

---

## What We've Implemented

### ✅ Phase 1: Foundation (COMPLETED)

1. **New Directory Structure**
   ```
   savings-system/
   ├── api/
   │   ├── controllers/      # NEW: Business logic coordination
   │   ├── routers/          # NEW: Thin HTTP routing
   │   └── [old files]       # TO BE MIGRATED
   ├── store/                # NEW: Data layer
   │   ├── enums/
   │   │   └── enums.py      # ✅ All system enums centralized
   │   └── repositories/
   │       ├── base.py       # ✅ Base repository with CRUD
   │       ├── user.py       # ✅ User repository
   │       ├── business.py   # ✅ Business, Unit, BusinessPermission repos
   │       └── permissions.py
   ├── utils/
   │   └── auth_context.py   # ✅ UserContext pattern + PermissionChecker
   └── [existing structure]
   ```

2. **Centralized Enums** (`store/enums/enums.py`)
   - ✅ Role, Permission, Resource, Action
   - ✅ SavingsType, SavingsStatus, MarkingStatus
   - ✅ IncomeType, CardStatus, ExpenseCategory
   - ✅ PaymentRequestStatus, NotificationMethod, PaymentMethod

3. **Repository Layer** (Data Access)
   - ✅ `BaseRepository` - Generic CRUD operations
   - ✅ `UserRepository` - User-specific queries
   - ✅ `BusinessRepository` - Business, admin credentials
   - ✅ `UnitRepository` - Unit management
   - ✅ `BusinessPermissionRepository` - Permission management

4. **UserContext Pattern** (`utils/auth_context.py`)
   - ✅ `UserContext` - Bundles user + business + permissions
   - ✅ `PermissionChecker` - Static permission validation
   - ✅ `get_user_context()` - Context loader dependency
   - ✅ `require_business_access()` - Business validation
   - ✅ `require_user_permission()` - Permission dependency factory

---

## New Architecture Pattern

### Before (2-Layer)
```
┌─────────────────────┐
│   API/Router        │  - FastAPI routes
│   (api/user.py)     │  - @router.get/post decorators
│                     │  - Direct service calls
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   Service Layer     │  - Business logic
│   (service/user.py) │  - Database queries
│                     │  - Response formatting
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│   Database          │  - SQLAlchemy models
│   (models/)         │  - Direct SQL
└─────────────────────┘
```

### After (3-Layer + Repository)
```
┌─────────────────────────────────┐
│   Router Layer                  │  - HTTP routing ONLY
│   (api/routers/user_router.py) │  - @router.get/post decorators
│                                 │  - Minimal validation
│                                 │  - Delegates to controller
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│   Controller Layer              │  - Business logic coordination
│   (api/controllers/            │  - Calls services/repos
│    user_controller.py)          │  - Response formatting
│                                 │  - Transaction management
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│   Repository Layer              │  - Data access ONLY
│   (store/repositories/)         │  - CRUD operations
│                                 │  - Query methods
│                                 │  - No business logic
└────────────┬────────────────────┘
             │
┌────────────▼────────────────────┐
│   Database + Models             │  - SQLAlchemy models
│   (models/)                     │  - Database schema
└─────────────────────────────────┘
```

---

## Migration Pattern

### Example: User Module Refactoring

#### OLD Structure (`api/user.py` - 217 lines)
```python
@user_router.post("/signup")
async def signup(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    # Business logic mixed with routing
    # Direct database queries
    # Response formatting
    return await signup_unauthenticated(request, db)
```

#### NEW Structure

**1. Router** (`api/routers/user_router.py` - Thin)
```python
from fastapi import APIRouter, Depends
from api.controllers import UserController
from utils.auth_context import UserContext, require_super_admin

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup")
async def signup(
    request: SignupRequest,
    controller: UserController = Depends()
):
    """User signup endpoint"""
    return await controller.signup(request)

@router.get("/admin-credentials")
async def get_admin_credentials(
    context: UserContext = Depends(require_super_admin),
    controller: UserController = Depends()
):
    """Get admin credentials (super_admin only)"""
    return await controller.get_admin_credentials(context)
```

**2. Controller** (`api/controllers/user_controller.py` - Business Logic)
```python
from fastapi import Depends
from sqlalchemy.orm import Session
from store.repositories import UserRepository, BusinessRepository
from utils.auth_context import UserContext
from utils.response import success_response, error_response

class UserController:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db
        self.user_repo = UserRepository(db)
        self.business_repo = BusinessRepository(db)
    
    async def signup(self, request: SignupRequest):
        """Handle user signup"""
        # Check if user exists
        if self.user_repo.get_by_email(request.email):
            return error_response(400, "Email already registered")
        
        # Create user
        user = self.user_repo.create({
            "email": request.email,
            "full_name": request.full_name,
            # ... other fields
        })
        
        self.db.commit()
        return success_response(201, "User created", user_response)
    
    async def get_admin_credentials(self, context: UserContext):
        """Get all admin credentials"""
        credentials = self.business_repo.get_all_admin_credentials()
        # Format and return
        return success_response(200, "Credentials retrieved", data)
```

**3. Repository** (`store/repositories/user.py` - Data Access)
```python
class UserRepository(BaseRepository[User]):
    def get_by_email(self, email: str) -> Optional[User]:
        return self.find_one_by(email=email)
    
    def get_by_phone(self, phone_number: str) -> Optional[User]:
        return self.find_one_by(phone_number=phone_number)
    
    def get_with_businesses(self, user_id: int) -> Optional[User]:
        return (
            self.db.query(User)
            .options(joinedload(User.businesses))
            .filter(User.id == user_id)
            .first()
        )
```

---

## Key Benefits

### 1. **Separation of Concerns**
- Router: HTTP only
- Controller: Business logic
- Repository: Data access

### 2. **Testability**
- Mock repositories easily
- Test business logic independently
- Integration tests cleaner

### 3. **Reusability**
- Repositories shared across controllers
- Services can use multiple repositories
- Cleaner dependency injection

### 4. **Maintainability**
- Smaller, focused files
- Clear responsibility boundaries
- Easier to locate code

### 5. **Consistency**
- Standardized patterns
- Similar to industry standards (Showroom360)
- Easier onboarding for new developers

---

## UserContext Pattern Benefits

### Before
```python
@router.post("/approve-payment")
async def approve_payment(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Manual permission checking
    if current_user["role"] != "admin":
        raise HTTPException(403)
    
    # Manual business validation
    business_id = get_business_somehow()
    if not can_approve(current_user, business_id, db):
        raise HTTPException(403)
```

### After
```python
@router.post("/approve-payment")
async def approve_payment(
    request_id: int,
    context: UserContext = Depends(require_user_permission("payments", "approve")),
    controller: PaymentController = Depends()
):
    # Permission already validated by dependency
    # Business context loaded
    # Clean, declarative
    return await controller.approve_payment(request_id, context)
```

---

## Migration Checklist (Per Module)

### For Each API Module:

- [ ] **1. Create Enum Values** (if needed)
  - Add to `store/enums/enums.py`

- [ ] **2. Create Repository**
  - Extend `BaseRepository`
  - Add model-specific query methods
  - Pure data access, no business logic

- [ ] **3. Create Controller**
  - Business logic coordination
  - Use repositories for data access
  - Format responses
  - Handle transactions

- [ ] **4. Create Router**
  - Thin HTTP layer
  - Route definitions only
  - Delegate to controller
  - Use UserContext dependencies

- [ ] **5. Update main.py**
  - Import new router
  - Replace old router registration

- [ ] **6. Test**
  - Verify all endpoints work
  - Check permission enforcement
  - Test error cases

---

## Modules to Migrate

### Priority 1 (Core)
- [x] User (Example - TO BE COMPLETED)
- [ ] Business
- [ ] Auth

### Priority 2 (Operations)
- [ ] Savings
- [ ] Expenses
- [ ] Payments

### Priority 3 (Supporting)
- [ ] Commissions
- [ ] Units
- [ ] Settings

---

## Best Practices from Showroom360

### 1. **Dependency Injection Pattern**
```python
# Good: Inject dependencies
class UserController:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db
        self.user_repo = UserRepository(db)

# Bad: Create dependencies inside
class UserController:
    def get_user(self, user_id):
        db = create_session()  # Don't do this
```

### 2. **Permission Dependencies**
```python
# Good: Declarative
@router.get("/inventory")
async def get_inventory(
    context: UserContext = Depends(require_user_permission("inventory", "read"))
):
    return data

# Bad: Imperative
@router.get("/inventory")
async def get_inventory(current_user: dict = Depends(get_current_user)):
    if not has_permission(current_user, "inventory", "read"):
        raise HTTPException(403)
```

### 3. **Context-Aware Operations**
```python
# Good: Use context
async def approve_payment(context: UserContext):
    if not context.is_business_owner:
        raise HTTPException(403)
    
    payment = get_payment(context.current_business_id)

# Bad: Pass individual params
async def approve_payment(user_id, business_id, role, permissions):
    # Too many parameters
```

---

## What We Keep from Current System

### ✅ Keep These Strengths:

1. **Auto-Admin Creation**
   - Unique workflow
   - Encrypted credentials
   - Admin assignment process

2. **Business-Scoped Permissions**
   - `business_permissions` table
   - Works well with PostgreSQL
   - Good for auditing

3. **Custom Permission Logic**
   - Super admin view-only restrictions
   - Complex business rules
   - Fine-grained control

4. **PostgreSQL Integration**
   - Foreign keys
   - Transactions
   - Relational integrity

---

## Future Enhancements

### Phase 2: CLI Tools (Pending)
- [ ] Create `manage_permissions.py`
- [ ] Add `--list-roles`
- [ ] Add `--grant-permission`
- [ ] Add `--validate-role`

### Phase 3: Declarative Seeding (Pending)
- [ ] Create permission seed file
- [ ] Auto-seed on startup
- [ ] Validation scripts

### Phase 4: Casbin Integration (Optional)
- [ ] Add Casbin for standard permissions
- [ ] Keep custom logic for special cases
- [ ] Use `casbin-sqlalchemy-adapter`

---

## Example File Structure (After Migration)

```
savings-system/
├── api/
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── user_controller.py          ✅ NEW
│   │   ├── business_controller.py      📝 TODO
│   │   ├── savings_controller.py       📝 TODO
│   │   ├── expense_controller.py       📝 TODO
│   │   └── payment_controller.py       📝 TODO
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── user_router.py              ✅ NEW
│   │   ├── business_router.py          📝 TODO
│   │   ├── savings_router.py           📝 TODO
│   │   ├── expense_router.py           📝 TODO
│   │   └── payment_router.py           📝 TODO
│   └── [old files to be deprecated]
├── store/
│   ├── enums/
│   │   ├── __init__.py                 ✅
│   │   └── enums.py                    ✅
│   └── repositories/
│       ├── __init__.py                 ✅
│       ├── base.py                     ✅
│       ├── user.py                     ✅
│       ├── business.py                 ✅
│       ├── savings.py                  📝 TODO
│       ├── expense.py                  📝 TODO
│       └── payment.py                  📝 TODO
├── utils/
│   ├── auth_context.py                 ✅ NEW
│   ├── permissions.py                  ✅ (keep)
│   └── password_utils.py               ✅ (keep)
└── main.py                             📝 TO UPDATE
```

---

## Implementation Status

### ✅ Completed
- Directory structure
- Enums consolidation
- Base repository pattern
- User/Business repositories
- UserContext pattern
- Permission checker utilities

### 🔄 In Progress
- User controller (example)
- User router (example)

### 📝 To Do
- Complete user module
- Migrate other modules
- CLI management tool
- Declarative seeding
- Update main.py
- Testing

---

## How to Continue

### For Each Module:

1. **Read this guide**
2. **Follow the migration pattern** (Router → Controller → Repository)
3. **Use UserContext** for permissions
4. **Test thoroughly**
5. **Update main.py** to use new router

### Example Command:
```bash
# Test new structure
python -m pytest tests/test_user_controller.py
python -m pytest tests/test_user_router.py

# Run application
uvicorn main:app --reload
```

---

**Last Updated:** 2025-11-05  
**Status:** Foundation Complete, Implementation In Progress  
**Next Step:** Complete User module as reference pattern

