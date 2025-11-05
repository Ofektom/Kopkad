# ✅ Showroom360-Style Refactoring - Complete Guide

**Date:** 2025-11-05  
**Status:** Foundation Complete + User Module Example Done  
**Pattern:** Exact Showroom360 Architecture

---

## 🎯 What's Been Implemented

### ✅ Correct Architecture (Showroom360 Pattern)

```
savings-system/
├── api/
│   ├── controller/           ✅ SINGULAR (not controllers)
│   │   ├── __init__.py       ✅ EMPTY
│   │   └── user.py           ✅ COMPLETE EXAMPLE
│   ├── router/               ✅ SINGULAR (not routers)
│   │   ├── __init__.py       ✅ EMPTY
│   │   └── user.py           ✅ COMPLETE EXAMPLE
│   └── [old files]           📝 To be deprecated
├── store/
│   ├── enums/
│   │   └── enums.py          ✅ ALL ENUMS
│   └── repositories/
│       ├── base.py           ✅ Base CRUD
│       ├── user.py           ✅ User repo
│       └── business.py       ✅ Business repo
└── utils/
    └── auth_context.py       ✅ UserContext pattern
```

---

## 📋 Key Differences from Showroom360

| Aspect | Showroom360 | Our System |
|--------|-------------|------------|
| **Database** | MongoDB (Beanie) | PostgreSQL (SQLAlchemy) |
| **Repositories** | Beanie ODM | Custom BaseRepository pattern |
| **Context Loader** | `get_user_context(business_id: str)` | `get_user_context(business_id: int)` |
| **RBAC** | Casbin framework | Enhanced Native + business_permissions table |
| **Permissions** | `require_user_permission(Resource, Action)` | Same pattern, different implementation |
| **Logging** | loguru | Standard Python logging |

---

## 📝 Controller Pattern (Showroom360 Style)

### ✅ Correct Pattern (api/controller/user.py)

```python
"""Controllers contain business logic with dependency injection."""
from fastapi import Depends
from utils.auth_context import UserContext, require_super_admin
import logging

logger = logging.getLogger(__name__)

# Async functions (NOT classes)
async def signup_controller(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    """User signup (unauthenticated)"""
    return await signup_unauthenticated(request, db)

# With UserContext for permission-protected endpoints
async def assign_admin_controller(
    business_id: int,
    person_user_id: int,
    user_context: UserContext = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Assign admin to business (super_admin only)"""
    return await assign_admin_to_business(
        business_id, 
        person_user_id, 
        user_context.user.__dict__, 
        db
    )
```

### ❌ Wrong Pattern (What We Had Before)

```python
# DON'T DO THIS
class UserController:  # ❌ No classes
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db
```

---

## 📝 Router Pattern (Showroom360 Style)

### ✅ Correct Pattern (api/router/user.py)

```python
"""Routers only register routes using add_api_route()."""
from fastapi import APIRouter
from api.controller.user import signup_controller, login_controller

user_router = APIRouter(prefix="/auth", tags=["Authentication"])

# Use add_api_route() - NOT decorators
user_router.add_api_route(
    "/signup",
    endpoint=signup_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="User signup",
)

user_router.add_api_route(
    "/login",
    endpoint=login_controller,
    methods=["POST"],
    response_model=UserResponse,
    summary="User login",
)
```

### ❌ Wrong Pattern (What We Had Before)

```python
# DON'T DO THIS
@user_router.post("/signup")  # ❌ No decorators
async def signup(...):
    pass
```

---

## 🔄 Migration Checklist

### For Each API Module (business.py, savings.py, expenses.py, payments.py, etc.):

#### Step 1: Create Controller File

Create `api/controller/[module].py`:

```python
"""
[Module] controller - following Showroom360 pattern.
"""
from fastapi import Depends, Query
from sqlalchemy.orm import Session
from utils.auth_context import UserContext, require_business_access
from database.postgres_optimized import get_db

# Import existing service functions
from service.[module] import (
    existing_function_1,
    existing_function_2,
    # ... all functions from service layer
)

# Create controller functions (async functions, NOT classes)
async def function_1_controller(
    param1: str,
    param2: int = Query(...),
    user_context: UserContext = Depends(require_business_access),
    db: Session = Depends(get_db),
):
    """Description"""
    # Business validation if needed
    if user_context.current_business_id != param1:
        return error_response(403, "Access denied")
    
    # Call service function
    return await existing_function_1(param1, param2, user_context.user, db)
```

#### Step 2: Create Router File

Create `api/router/[module].py`:

```python
"""
[Module] router - following Showroom360 pattern.
"""
from fastapi import APIRouter
from api.controller.[module] import (
    function_1_controller,
    function_2_controller,
    # ... all controller functions
)

[module]_router = APIRouter(prefix="/[module]", tags=["[Module] Management"])

# Register routes using add_api_route()
[module]_router.add_api_route(
    "/endpoint",
    endpoint=function_1_controller,
    methods=["GET"],  # or ["POST"], ["PUT"], ["DELETE"]
    response_model=SomeSchema,
    summary="Short description",
)
```

#### Step 3: Update main.py

```python
# Remove old import
# from api.business import business_router  # OLD

# Add new import
from api.router.business import business_router  # NEW

# Router registration stays the same
app.include_router(business_router, prefix="/api/v1")
```

#### Step 4: Test

```bash
# Start server
uvicorn main:app --reload

# Test endpoints
curl http://localhost:8000/api/v1/auth/users
```

---

## 📚 Complete User Module Example

### ✅ api/controller/user.py (REFERENCE)

See `/Users/decagon/Documents/Ofektom/savings-system/api/controller/user.py`

**Key Points:**
- Async functions (not classes)
- Dependency injection with `Depends()`
- Uses `UserContext` for permission-protected endpoints
- Delegates to existing service layer functions
- Minimal business logic (mostly validation)

### ✅ api/router/user.py (REFERENCE)

See `/Users/decagon/Documents/Ofektom/savings-system/api/router/user.py`

**Key Points:**
- Uses `add_api_route()` method
- No `@router.get()` decorators
- Imports controller functions
- Defines routes, response models, summaries
- Pure routing logic only

---

## 🗂️ Modules to Migrate

### Priority Order:

1. ✅ **user.py** - COMPLETE (reference example)
2. 📝 **business.py** - Next (similar complexity)
3. 📝 **savings.py** - Core feature
4. 📝 **expenses.py** - Core feature
5. 📝 **payments.py** - Core feature
6. 📝 **financial_advisor.py** - Analytics
7. 📝 **settings.py** - User settings
8. 📝 **notifications.py** - Notifications
9. 📝 **whatsapp.py** - External integration
10. 📝 **analytics.py** - Reports
11. 📝 **deposits.py** - If used

---

## 🎨 Pattern Template

### Controller Template

```python
"""
[MODULE] controller - following Showroom360 pattern.
Controllers contain business logic with dependency injection.
"""
from fastapi import Depends, Query
from sqlalchemy.orm import Session
from utils.auth_context import UserContext, require_business_access
from database.postgres_optimized import get_db
from service.[module] import service_function
from store.enums import Resource, Action

async def [operation]_controller(
    # Path parameters
    item_id: int,
    # Query parameters
    filter_param: str = Query(None),
    # Dependency injection
    user_context: UserContext = Depends(require_business_access),
    db: Session = Depends(get_db),
):
    """[Operation] description"""
    # Business validation
    if user_context.current_business_id != business_id:
        return error_response(403, "Access denied")
    
    # Call service
    return await service_function(item_id, filter_param, user_context.user, db)
```

### Router Template

```python
"""
[MODULE] router - following Showroom360 pattern.
Routers only register routes using add_api_route().
"""
from fastapi import APIRouter
from api.controller.[module] import [operation]_controller

[module]_router = APIRouter(prefix="/[module]", tags=["[Module] Management"])

[module]_router.add_api_route(
    "/{item_id}",
    endpoint=[operation]_controller,
    methods=["GET"],
    response_model=SomeSchema,
    summary="[Operation] item",
)
```

---

## 🚀 Quick Start Migration Guide

### For business.py:

1. **Read current api/business.py**
   - Note all endpoint functions
   - Note all imports

2. **Create api/controller/business.py**
   ```python
   from service.business import (
       create_business,
       get_business,
       # ... all functions
   )
   
   async def create_business_controller(...):
       return await create_business(...)
   
   async def get_business_controller(...):
       return await get_business(...)
   ```

3. **Create api/router/business.py**
   ```python
   from api.controller.business import (
       create_business_controller,
       get_business_controller,
   )
   
   business_router = APIRouter(prefix="/business", tags=["Business"])
   
   business_router.add_api_route("/", endpoint=create_business_controller, methods=["POST"])
   business_router.add_api_route("/{id}", endpoint=get_business_controller, methods=["GET"])
   ```

4. **Update main.py**
   ```python
   from api.router.business import business_router
   app.include_router(business_router, prefix="/api/v1")
   ```

5. **Test**
   ```bash
   uvicorn main:app --reload
   curl http://localhost:8000/docs
   ```

---

## 🎯 Key Takeaways

1. **Folders are SINGULAR**: `controller/` and `router/` (not controllers/routers)
2. **__init__.py is EMPTY**: No exports needed
3. **Controllers use ASYNC FUNCTIONS**: Not classes
4. **Routers use add_api_route()**: Not decorators
5. **One file per module**: Match existing api/ files
6. **UserContext for permissions**: Use `Depends(require_user_permission())` pattern
7. **Keep service layer**: Controllers delegate to services
8. **Import from api.controller**: `from api.controller.user import func`

---

## 📊 Progress Tracking

```
✅ Foundation Complete
  ✅ store/enums/enums.py
  ✅ store/repositories/
  ✅ utils/auth_context.py
  ✅ api/controller/ (structure)
  ✅ api/router/ (structure)

✅ User Module Complete
  ✅ api/controller/user.py
  ✅ api/router/user.py

📝 Remaining Modules
  [ ] business.py
  [ ] savings.py
  [ ] expenses.py
  [ ] payments.py
  [ ] financial_advisor.py
  [ ] settings.py
  [ ] notifications.py
  [ ] whatsapp.py
  [ ] analytics.py
```

---

## 🔧 Testing After Migration

```bash
# 1. Start server
uvicorn main:app --reload

# 2. Check Swagger docs
open http://localhost:8000/docs

# 3. Test endpoints
curl -X GET http://localhost:8000/api/v1/auth/users \
  -H "Authorization: Bearer YOUR_TOKEN"

# 4. Run tests
pytest tests/
```

---

## 📞 Need Help?

Reference files:
- `api/controller/user.py` - Complete controller example
- `api/router/user.py` - Complete router example
- Showroom360's `app/api/controller/sales.py` - Original pattern
- Showroom360's `app/api/router/sales.py` - Original pattern

---

**Last Updated:** 2025-11-05  
**Status:** User module complete, ready for systematic migration of remaining modules

