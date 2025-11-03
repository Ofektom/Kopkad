# Expense Creation Endpoint Testing Guide

This directory contains comprehensive test scripts and data for testing all expense creation endpoints.

## 📁 Test Files

1. **`test_expense_creation.py`** - Python script with full test suite
2. **`test_expense_creation.sh`** - Bash script with curl commands
3. **`expense_test_data.json`** - Sample test data and payloads
4. **`EXPENSE_TESTING_README.md`** - This file

## 🚀 Quick Start

### Prerequisites

- Python 3.8+ (for Python tests)
- `requests` library: `pip install requests`
- `curl` and `jq` (for bash tests)
- Valid user account credentials
- Active business associated with user

### Option 1: Python Test Script

```bash
# 1. Install dependencies
pip install requests

# 2. Update credentials in test_expense_creation.py
#    - TEST_USER_EMAIL
#    - TEST_USER_PASSWORD
#    - BASE_URL (if testing locally)

# 3. Run tests
cd /path/to/savings-system
python tests/test_expense_creation.py
```

### Option 2: Bash/Curl Test Script

```bash
# 1. Make script executable
chmod +x tests/test_expense_creation.sh

# 2. Update credentials in test_expense_creation.sh
#    - TEST_EMAIL
#    - TEST_PASSWORD
#    - BASE_URL (if testing locally)

# 3. Run tests
./tests/test_expense_creation.sh
```

## 🧪 Test Scenarios

### 1. Create SALARY Expense Card
```json
POST /api/v1/expenses/card
{
  "name": "November Salary Card",
  "income_type": "SALARY",
  "initial_income": 150000.00
}
```

### 2. Create BUSINESS Expense Card
```json
POST /api/v1/expenses/card
{
  "name": "Business Revenue - November",
  "income_type": "BUSINESS",
  "initial_income": 500000.00
}
```

### 3. Create BORROWED Expense Card
```json
POST /api/v1/expenses/card
{
  "name": "Loan for Business Expansion",
  "income_type": "BORROWED",
  "initial_income": 200000.00
}
```

### 4. Create OTHER Income Type Card
```json
POST /api/v1/expenses/card
{
  "name": "Freelance Project Income",
  "income_type": "OTHER",
  "initial_income": 75000.00,
  "income_details": "Web development project for Client XYZ"
}
```
**Note:** `income_details` is REQUIRED when `income_type` is "OTHER"

### 5. Create SAVINGS-Based Expense Card

First, get eligible savings:
```bash
GET /api/v1/expenses/eligible-savings
```

Then create card:
```json
POST /api/v1/expenses/card
{
  "name": "Expense Card from Savings Payout",
  "income_type": "SAVINGS",
  "savings_id": 123
}
```

### 6. Create PLANNER Card with Budget
```json
POST /api/v1/expenses/planner/create
{
  "name": "December Budget Plan",
  "capital": 250000.00,
  "planned_expenses": [
    {
      "category": "RENT",
      "amount": 80000.00,
      "purpose": "Monthly apartment rent"
    },
    {
      "category": "FOOD",
      "amount": 50000.00,
      "purpose": "Groceries and meal prep"
    },
    {
      "category": "TRANSPORT",
      "amount": 30000.00,
      "purpose": "Fuel and transportation"
    }
  ]
}
```
**Note:** Use `purpose` NOT `description` in planned_expenses

### 7. Record Expense on Card
```json
POST /api/v1/expenses/card/{card_id}/expense
{
  "category": "FOOD",
  "description": "Lunch at restaurant",
  "amount": 5500.00,
  "date": "2025-11-03"
}
```

## 📊 Valid Enum Values

### Income Types
- `SALARY` - Regular salary income
- `BUSINESS` - Business revenue
- `BORROWED` - Borrowed funds/loans
- `OTHER` - Other income sources (requires `income_details`)
- `SAVINGS` - From completed savings account (requires `savings_id`)
- `PLANNER` - Budget planning (system-generated)

### Expense Categories
- `FOOD` - Food and groceries
- `TRANSPORT` - Transportation costs
- `ENTERTAINMENT` - Entertainment and recreation
- `UTILITIES` - Utilities (electricity, water, internet)
- `RENT` - Rent payments
- `MISC` - Miscellaneous expenses

### Card Statuses
- `DRAFT` - Planning mode (not yet activated)
- `ACTIVE` - Normal expense tracking
- `ARCHIVED` - Completed/closed

## ✅ Validation Rules

### ExpenseCardCreate Schema
- `name`: **Required** string
- `income_type`: **Required** enum (IncomeType)
- `business_id`: **Optional** integer (defaults to user's active_business_id)
- `savings_id`: **Optional** integer (**required** if income_type is SAVINGS)
- `initial_income`: **Optional** decimal (**required** for non-SAVINGS types)
- `income_details`: **Optional** string (**required** if income_type is OTHER)

### PlannedExpense Schema
- `category`: **Required** enum (ExpenseCategory)
- `amount`: **Required** decimal
- `purpose`: **Required** string ⚠️ **NOT** `description`

### ExpenseCreate Schema
- `category`: **Required** enum (ExpenseCategory)
- `description`: **Optional** string
- `amount`: **Required** decimal
- `date`: **Required** date (YYYY-MM-DD format)

## 🔍 Troubleshooting

### Common Errors

#### 401 Unauthorized
- **Cause:** Invalid or missing access token
- **Solution:** Ensure you're logged in and passing valid Bearer token

#### 422 Validation Error
- **Causes:**
  - Missing `income_details` when `income_type` is OTHER
  - Missing `savings_id` when `income_type` is SAVINGS
  - Missing required fields
  - Invalid enum values (case-sensitive!)
  - Using `description` instead of `purpose` in planned_expenses
- **Solution:** Verify payload against schema requirements

#### 500 Internal Server Error
- **Causes:**
  - Invalid `business_id` (doesn't exist or not owned by user)
  - Invalid `savings_id` (doesn't exist or already linked)
  - Database constraint violations
  - Backend field name mismatches (should be fixed now!)
- **Solution:** Check backend logs for specific error

### Recent Fixes Applied
✅ Fixed `Expense.actual_amount` → `Expense.amount`  
✅ Fixed `Expense.card_id` → `Expense.expense_card_id`  
✅ Added `from_attributes = True` to all response schemas  
✅ Fixed planner `description` → `purpose` field

## 📝 Manual Testing with curl

### Get Access Token
```bash
curl -X POST 'https://kopkad.onrender.com/api/v1/users/login' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "your@email.com",
    "password": "your_password"
  }'
```

### Create Expense Card
```bash
curl -X POST 'https://kopkad.onrender.com/api/v1/expenses/card' \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Test Card",
    "income_type": "SALARY",
    "initial_income": 100000
  }'
```

### Get All Expense Cards
```bash
curl -X GET 'https://kopkad.onrender.com/api/v1/expenses/cards?limit=20&offset=0' \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

### Get Expense Metrics
```bash
curl -X GET 'https://kopkad.onrender.com/api/v1/expenses/metrics' \
  -H 'Authorization: Bearer YOUR_ACCESS_TOKEN'
```

## 🎯 Expected Responses

### Successful Card Creation (200)
```json
{
  "id": 5,
  "customer_id": 4,
  "business_id": 1,
  "name": "November Salary Card",
  "income_type": "SALARY",
  "income_amount": 150000.00,
  "balance": 150000.00,
  "savings_id": null,
  "income_details": null,
  "status": "ACTIVE",
  "is_plan": false,
  "created_at": "2025-11-03T10:30:00",
  "updated_at": null
}
```

### Successful Planner Creation (200)
```json
{
  "card": {
    "id": 6,
    "name": "December Budget Plan",
    "income_type": "PLANNER",
    "status": "DRAFT",
    ...
  },
  "total_planned": 220000.00,
  "remaining_balance": 30000.00,
  "is_sufficient": true,
  "ai_advice": "Your budget looks healthy with ₦30,000 remaining...",
  "category_breakdown": {
    "RENT": 80000.00,
    "FOOD": 50000.00,
    ...
  },
  "recommendations": [
    "Consider setting aside 10% for emergency savings",
    ...
  ]
}
```

## 🔄 Test Workflow

1. **Login** → Get access token
2. **Create various expense cards** (SALARY, BUSINESS, BORROWED, OTHER)
3. **Check eligible savings** → Create SAVINGS-based card
4. **Create planner card** → Get AI budget analysis
5. **Record expenses** on active cards
6. **Retrieve cards** → Verify all created correctly
7. **Check metrics** → Verify aggregated data is correct

## 📌 Notes

- All tests use the user's `active_business_id` by default
- You can override by passing `business_id` in the payload
- Planner cards start in DRAFT status
- Regular cards start in ACTIVE status
- Deleted cards are soft-deleted (archived)
- All amounts are in Naira (₦)

## 🆘 Support

If tests fail after following this guide:
1. Check backend logs for detailed error messages
2. Verify database migrations have been run
3. Ensure user has an active business assigned
4. Confirm all recent backend fixes have been deployed

---

**Last Updated:** November 3, 2025  
**Related Files:** `service/expenses.py`, `api/expenses.py`, `schemas/expenses.py`, `models/expenses.py`

