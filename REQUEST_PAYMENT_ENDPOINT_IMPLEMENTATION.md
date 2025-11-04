# Request Payment - New Dedicated Endpoint

## 🎯 Issue
Previously, I mistakenly modified the `get_eligible_savings` function (used for expense cards) instead of creating a dedicated endpoint for payment requests.

## ✅ Solution

### Created New Dedicated Endpoint for Payment Requests

#### 1. **New Service Function** (`service/get_unpaid_savings.py`)

```python
async def get_unpaid_completed_savings(current_user: dict, db: Session):
    """
    Get list of completed savings accounts that haven't been paid out yet.
    
    Criteria:
    - savings_account.marking_status == COMPLETED
    - No savings_markings with status == PAID
    """
    
    completed_savings = db.query(SavingsAccount).filter(
        SavingsAccount.customer_id == current_user["user_id"],
        SavingsAccount.marking_status == MarkingStatus.COMPLETED
    ).all()
    
    results = []
    for savings in completed_savings:
        # Check if any marking has PAID status - exclude if so
        has_paid_marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.status == SavingsStatus.PAID
        ).first()
        
        # Skip if already paid out
        if has_paid_marking:
            continue
        
        # Calculate payout and include in results
        ...
```

#### 2. **New API Endpoint** (`api/unpaid_savings.py`)

```python
@unpaid_savings_router.get("/unpaid-completed", response_model=dict)
async def get_unpaid_completed_savings_endpoint(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get list of completed savings that haven't been paid out yet.
    
    Returns savings where:
    - marking_status == COMPLETED
    - No markings with status == PAID
    """
    return await get_unpaid_completed_savings(current_user, db)
```

#### 3. **Updated Frontend** (`RequestPayment.jsx`)

```javascript
// BEFORE (wrong endpoint):
apiClient.get(`${API_BASE_URL}/api/v1/expenses/eligible-savings`)

// AFTER (correct endpoint):
apiClient.get(`${API_BASE_URL}/api/v1/savings/unpaid-completed`)
```

#### 4. **Reverted Expense Function**

Restored `get_eligible_savings` in `service/expenses.py` to original logic (for expense cards, not payment requests).

## 🔄 Endpoints Comparison

### Old (Incorrect) Approach:
- Modified `/api/v1/expenses/eligible-savings` ❌
- **Purpose:** For creating expense cards from completed savings
- **Problem:** Interfered with expense card creation logic

### New (Correct) Approach:
- Created `/api/v1/savings/unpaid-completed` ✅
- **Purpose:** For payment requests only
- **Benefit:** Separate concerns, no interference

## 📊 How It Works

### Backend Filter:
1. Get all completed savings (`MarkingStatus.COMPLETED`)
2. For each savings:
   - Check if any marking has `SavingsStatus.PAID`
   - If yes → **Exclude** (already paid out)
   - If no → **Include** (eligible for payment request)
3. Calculate payout, commission, net amount
4. Check payment request status
5. Return results

### Frontend Filter:
```javascript
// Backend already filters out PAID markings
const allSavings = savingsResponse.data?.data?.savings || [];

// Additional filter for approved payment requests
const unpaidSavings = allSavings.filter(s => s.payment_request_status !== 'approved');
```

## 🎯 Filtering Criteria

### Excluded Savings:
- ✅ `SavingsAccount.marking_status != COMPLETED`
- ✅ Any `SavingsMarking.status == PAID`
- ✅ `payment_request_status == 'approved'` (frontend filter)

### Included Savings:
- ✅ `SavingsAccount.marking_status == COMPLETED`
- ✅ No `SavingsMarking.status == PAID`
- ✅ `payment_request_status` is `null`, `pending`, `rejected`, or `cancelled`

## 📝 API Response Format

```json
{
  "status": "success",
  "message": "Unpaid completed savings retrieved successfully",
  "data": {
    "savings": [
      {
        "id": 123,
        "tracking_number": "KD-SAV-20231103-001",
        "savings_type": "DAILY",
        "total_amount": 50000.00,
        "commission": 2500.00,
        "net_payout": 47500.00,
        "start_date": "2023-10-01",
        "completion_date": "2023-11-03",
        "payment_request_status": null
      }
    ],
    "count": 1
  }
}
```

## 🚀 Registration Required

**To activate this endpoint, add to `main.py`:**

```python
from api.unpaid_savings import unpaid_savings_router

# Register router
app.include_router(unpaid_savings_router, prefix="/api/v1")
```

## ✅ Benefits

1. **Separation of Concerns:**
   - Expense cards: `/api/v1/expenses/eligible-savings`
   - Payment requests: `/api/v1/savings/unpaid-completed`

2. **Clear Purpose:**
   - Each endpoint serves its specific use case
   - No conflicting logic

3. **Backend Filtering:**
   - Backend does the heavy lifting
   - Frontend just does additional filtering for approved requests

4. **Maintainability:**
   - Easy to modify payment request logic without affecting expense cards
   - Clear, dedicated service function

## 🧪 Testing

```bash
# Test the new endpoint
curl -X GET "http://localhost:8001/api/v1/savings/unpaid-completed" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected: List of completed savings without PAID markings
```

---

**Created:** November 3, 2025  
**Type:** New Endpoint + Service Function  
**Status:** ⚠️ Requires router registration in main.py  
**Purpose:** Dedicated endpoint for Request Payment feature

