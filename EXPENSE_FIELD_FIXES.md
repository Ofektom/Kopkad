# Expense Field Name Fixes

## Summary
Fixed critical field name errors in expense queries that were causing `AttributeError` exceptions.

## Issues Fixed

### 1. Wrong Field Name: `actual_amount` → `amount`
The `Expense` model uses `amount` field, not `actual_amount`.

### 2. Wrong Join Field: `card_id` → `expense_card_id`
The `Expense` model uses `expense_card_id` field for the foreign key relationship.

## Files Modified

### `/service/expenses.py` - `get_expense_metrics` function
**Lines 994-995**: Fixed all-time expenses query
```python
# BEFORE:
expenses_all_time_query = db.query(func.coalesce(func.sum(Expense.actual_amount), 0))\
    .join(ExpenseCard, Expense.card_id == ExpenseCard.id)\

# AFTER:
expenses_all_time_query = db.query(func.coalesce(func.sum(Expense.amount), 0))\
    .join(ExpenseCard, Expense.expense_card_id == ExpenseCard.id)\
```

**Lines 1004-1005**: Fixed this month expenses query
```python
# BEFORE:
expenses_this_month_query = db.query(func.coalesce(func.sum(Expense.actual_amount), 0))\
    .join(ExpenseCard, Expense.card_id == ExpenseCard.id)\

# AFTER:
expenses_this_month_query = db.query(func.coalesce(func.sum(Expense.amount), 0))\
    .join(ExpenseCard, Expense.expense_card_id == ExpenseCard.id)\
```

### `/service/savings.py` - `get_monthly_summary` function
**Lines 1553-1555**: Fixed current month expenses query
```python
# BEFORE:
total_expenses_current_month = db.query(
    func.coalesce(func.sum(Expense.actual_amount), 0)
).join(
    ExpenseCard, Expense.card_id == ExpenseCard.id
)

# AFTER:
total_expenses_current_month = db.query(
    func.coalesce(func.sum(Expense.amount), 0)
).join(
    ExpenseCard, Expense.expense_card_id == ExpenseCard.id
)
```

**Lines 1574-1576**: Fixed all-time expenses query
```python
# BEFORE:
total_expenses_all_time = db.query(
    func.coalesce(func.sum(Expense.actual_amount), 0)
).join(
    ExpenseCard, Expense.card_id == ExpenseCard.id
)

# AFTER:
total_expenses_all_time = db.query(
    func.coalesce(func.sum(Expense.amount), 0)
).join(
    ExpenseCard, Expense.expense_card_id == ExpenseCard.id
)
```

## Error Log References
These fixes resolve the following errors:
- `AttributeError: type object 'Expense' has no attribute 'actual_amount'`
- Wrong join causing query failures

## Additional Notes
- All Pydantic response schemas already have `from_attributes = True` set correctly
- Server needs to restart/redeploy to pick up these changes
- No frontend changes required for these backend fixes

## Date
November 3, 2025

