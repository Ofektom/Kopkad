from sqlalchemy.orm import Session
from sqlalchemy import func
from models.expenses import ExpenseCard, Expense, IncomeType, ExpenseCategory
from models.savings import SavingsAccount, SavingsMarking, SavingsStatus, MarkingStatus
from schemas.expenses import (
    ExpenseCardCreate,
    ExpenseCardResponse,
    ExpenseCreate,
    ExpenseResponse,
    TopUpRequest,
    ExpenseStatsResponse,
    FinancialAdviceResponse,
    FinancialAnalyticsResponse,
)
from utils.response import success_response, error_response
from models.user import User
from datetime import datetime, timezone, date
from decimal import Decimal
import logging
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from sklearn.linear_model import LinearRegression
import numpy as np

logging.basicConfig(
    filename="expenses.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

async def create_expense_card(request: ExpenseCardCreate, current_user: dict, db: Session):
    current_user_obj = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not current_user_obj:
        return error_response(status_code=404, message="User not found")

    income_amount = Decimal(0)
    balance = Decimal(0)

    if request.income_type == IncomeType.SAVINGS:
        if not request.savings_id:
            return error_response(status_code=400, message="savings_id required for SAVINGS type")
        if request.income_details:
            return error_response(status_code=400, message="income_details should only be provided for OTHER income type")
        savings = db.query(SavingsAccount).filter(SavingsAccount.id == request.savings_id).first()
        if not savings:
            return error_response(status_code=404, message="Savings account not found")
        if savings.customer_id != current_user["user_id"]:
            return error_response(status_code=403, message="Not your savings account")
        if savings.marking_status != MarkingStatus.COMPLETED:
            return error_response(status_code=400, message="Savings account must be marked as COMPLETED")
        
        paid_markings = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.status == SavingsStatus.PAID
        ).order_by(SavingsMarking.marked_date).all()
        if not paid_markings:
            return error_response(status_code=400, message="No paid savings markings found")
        total_amount = sum(marking.amount for marking in paid_markings)
        earliest_date = paid_markings[0].marked_date
        latest_date = paid_markings[-1].marked_date
        total_savings_days = (latest_date - earliest_date).days + 1
        if savings.commission_days == 0:
            total_commission = Decimal(0)
        else:
            total_commission = savings.commission_amount * Decimal(total_savings_days / savings.commission_days)
            total_commission = total_commission.quantize(Decimal("0.01"))
        income_amount = total_amount - total_commission
        balance = income_amount
        if income_amount <= 0:
            return error_response(status_code=400, message="No positive payout available from savings")
    elif request.income_type in [IncomeType.SALARY, IncomeType.BORROWED, IncomeType.BUSINESS, IncomeType.OTHER]:
        if request.income_type == IncomeType.OTHER and not request.income_details:
            return error_response(status_code=400, message="income_details is required for OTHER income type")
        if request.income_type != IncomeType.OTHER and request.income_details:
            return error_response(status_code=400, message="income_details should only be provided for OTHER income type")
        if request.initial_income is not None:
            if request.initial_income < 0:
                return error_response(status_code=400, message="Initial income cannot be negative")
            income_amount = request.initial_income
            balance = request.initial_income

    expense_card = ExpenseCard(
        customer_id=current_user["user_id"],
        name=request.name,
        income_type=request.income_type,
        income_amount=income_amount,
        balance=balance,
        savings_id=request.savings_id if request.income_type == IncomeType.SAVINGS else None,
        income_details=request.income_details if request.income_type == IncomeType.OTHER else None,
        created_by=current_user["user_id"],
        created_at=datetime.now(timezone.utc)
    )
    db.add(expense_card)
    db.commit()
    db.refresh(expense_card)

    logger.info(f"Created expense card {expense_card.id} for user {current_user['user_id']}")
    return ExpenseCardResponse.from_orm(expense_card)

async def get_expense_cards(limit: int, offset: int, current_user: dict, db: Session):
    query = db.query(ExpenseCard).filter(ExpenseCard.customer_id == current_user["user_id"])
    total_count = query.count()
    cards = query.order_by(ExpenseCard.created_at.desc()).offset(offset).limit(limit).all()
    response_data = [ExpenseCardResponse.from_orm(card) for card in cards]
    return success_response(
        status_code=200,
        message="Expense cards retrieved successfully",
        data={"cards": response_data, "total_count": total_count, "limit": limit, "offset": offset}
    )

async def record_expense(card_id: int, request: ExpenseCreate, current_user: dict, db: Session):
    card = db.query(ExpenseCard).filter(ExpenseCard.id == card_id).first()
    if not card:
        return error_response(status_code=404, message="Expense card not found")
    if card.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your expense card")
    if request.amount <= 0:
        return error_response(status_code=400, message="Amount must be positive")
    if request.amount > card.balance:
        return error_response(status_code=400, message="Insufficient balance")

    expense = Expense(
        expense_card_id=card_id,
        category=request.category,
        description=request.description,
        amount=request.amount,
        date=request.date,
        created_by=current_user["user_id"],
        created_at=datetime.now(timezone.utc)
    )
    card.balance -= request.amount
    card.updated_at = datetime.now(timezone.utc)
    card.updated_by = current_user["user_id"]
    db.add(expense)
    db.commit()
    db.refresh(expense)

    logger.info(f"Recorded expense {expense.id} for card {card_id} by user {current_user['user_id']}")
    return ExpenseResponse.from_orm(expense)

async def top_up_expense_card(card_id: int, request: TopUpRequest, current_user: dict, db: Session):
    card = db.query(ExpenseCard).filter(ExpenseCard.id == card_id).first()
    if not card:
        return error_response(status_code=404, message="Expense card not found")
    if card.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your expense card")
    if request.amount <= 0:
        return error_response(status_code=400, message="Top-up amount must be positive")
    if card.income_type == IncomeType.SAVINGS:
        return error_response(status_code=400, message="Cannot top up savings-linked expense card")

    card.income_amount += request.amount
    card.balance += request.amount
    card.updated_at = datetime.now(timezone.utc)
    card.updated_by = current_user["user_id"]
    db.commit()
    db.refresh(card)

    logger.info(f"Topped up expense card {card_id} by {request.amount} for user {current_user['user_id']}")
    return ExpenseCardResponse.from_orm(card)

async def get_expenses_by_card(card_id: int, limit: int, offset: int, current_user: dict, db: Session):
    card = db.query(ExpenseCard).filter(ExpenseCard.id == card_id).first()
    if not card:
        return error_response(status_code=404, message="Expense card not found")
    if card.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your expense card")

    query = db.query(Expense).filter(Expense.expense_card_id == card_id)
    total_count = query.count()
    expenses = query.order_by(Expense.date.desc()).offset(offset).limit(limit).all()
    response_data = [ExpenseResponse.from_orm(exp) for exp in expenses]
    return success_response(
        status_code=200,
        message="Expenses retrieved successfully",
        data={"expenses": response_data, "total_count": total_count, "limit": limit, "offset": offset}
    )

async def update_expense_card(card_id: int, request: ExpenseCardCreate, current_user: dict, db: Session):
    card = db.query(ExpenseCard).filter(ExpenseCard.id == card_id).first()
    if not card:
        return error_response(status_code=404, message="Expense card not found")
    if card.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your expense card")

    if db.query(Expense).filter(Expense.expense_card_id == card_id).first():
        if request.income_type != card.income_type:
            return error_response(status_code=400, message="Cannot change income type after expenses are recorded")

    if request.income_type == IncomeType.SAVINGS:
        if not request.savings_id:
            return error_response(status_code=400, message="savings_id required for SAVINGS type")
        if request.income_details:
            return error_response(status_code=400, message="income_details should only be provided for OTHER income type")
        savings = db.query(SavingsAccount).filter(SavingsAccount.id == request.savings_id).first()
        if not savings or savings.customer_id != current_user["user_id"]:
            return error_response(status_code=400, message="Invalid or not owned savings account")
        if savings.marking_status != MarkingStatus.COMPLETED:
            return error_response(status_code=400, message="Savings account must be marked as COMPLETED")
        paid_markings = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == savings.id,
            SavingsMarking.status == SavingsStatus.PAID
        ).order_by(SavingsMarking.marked_date).all()
        if not paid_markings:
            return error_response(status_code=400, message="No paid savings markings found")
        total_amount = sum(marking.amount for marking in paid_markings)
        earliest_date = paid_markings[0].marked_date
        latest_date = paid_markings[-1].marked_date
        total_savings_days = (latest_date - earliest_date).days + 1
        if savings.commission_days == 0:
            total_commission = Decimal(0)
        else:
            total_commission = savings.commission_amount * Decimal(total_savings_days / savings.commission_days)
            total_commission = total_commission.quantize(Decimal("0.01"))
        new_income = total_amount - total_commission
        card.income_amount = new_income
        card.balance = new_income - sum(exp.amount for exp in card.expenses)
        card.savings_id = request.savings_id
        card.income_details = None
    elif request.income_type in [IncomeType.SALARY, IncomeType.BORROWED, IncomeType.BUSINESS, IncomeType.OTHER]:
        if request.income_type == IncomeType.OTHER and not request.income_details:
            return error_response(status_code=400, message="income_details is required for OTHER income type")
        if request.income_type != IncomeType.OTHER and request.income_details:
            return error_response(status_code=400, message="income_details should only be provided for OTHER income type")
        card.savings_id = None
        if request.initial_income is not None:
            diff = request.initial_income - card.income_amount
            card.income_amount = request.initial_income
            card.balance += diff
        card.income_details = request.income_details if request.income_type == IncomeType.OTHER else None
    card.name = request.name
    card.income_type = request.income_type
    card.updated_at = datetime.now(timezone.utc)
    card.updated_by = current_user["user_id"]
    db.commit()
    db.refresh(card)

    logger.info(f"Updated expense card {card_id} for user {current_user['user_id']}")
    return ExpenseCardResponse.from_orm(card)

async def delete_expense_card(card_id: int, current_user: dict, db: Session):
    card = db.query(ExpenseCard).filter(ExpenseCard.id == card_id).first()
    if not card:
        return error_response(status_code=404, message="Expense card not found")
    if card.customer_id != current_user["user_id"]:
        return error_response(status_code=403, message="Not your expense card")

    db.delete(card)
    db.commit()

    logger.info(f"Deleted expense card {card_id} for user {current_user['user_id']}")
    return success_response(status_code=200, message="Expense card deleted successfully", data={"card_id": card_id})

async def get_expense_stats(from_date: date | None, to_date: date | None, current_user: dict, db: Session):
    cards = db.query(ExpenseCard).filter(ExpenseCard.customer_id == current_user["user_id"]).all()
    savings_markings = db.query(SavingsMarking).join(SavingsAccount).filter(
        SavingsAccount.customer_id == current_user["user_id"],
        SavingsMarking.status == SavingsStatus.PAID
    )
    if from_date:
        savings_markings = savings_markings.filter(SavingsMarking.marked_date >= from_date)
    if to_date:
        savings_markings = savings_markings.filter(SavingsMarking.marked_date <= to_date)
    savings_markings = savings_markings.all()

    savings_accounts = db.query(SavingsAccount).filter(
        SavingsAccount.customer_id == current_user["user_id"],
        SavingsAccount.marking_status == MarkingStatus.COMPLETED
    ).all()
    savings_payout = sum(
        sum(marking.amount for marking in db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == account.id,
            SavingsMarking.status == SavingsStatus.PAID
        ).all()) - (account.commission_amount * Decimal(
            ((max(m.marked_date for m in db.query(SavingsMarking).filter(
                SavingsMarking.savings_account_id == account.id,
                SavingsMarking.status == SavingsStatus.PAID
            ).all()) - min(m.marked_date for m in db.query(SavingsMarking).filter(
                SavingsMarking.savings_account_id == account.id,
                SavingsMarking.status == SavingsStatus.PAID
            ).all())).days + 1) / account.commission_days
        ) if account.commission_days > 0 else 0)
        for account in savings_accounts
    )

    if not cards:
        return ExpenseStatsResponse(
            total_income=Decimal(0),
            total_expenses=Decimal(0),
            net_balance=Decimal(0),
            expenses_by_category={},
            savings_contribution=sum(marking.amount for marking in savings_markings),
            savings_payout=savings_payout
        )

    total_income = sum(card.income_amount for card in cards)

    expenses_query = db.query(Expense).join(ExpenseCard).filter(ExpenseCard.customer_id == current_user["user_id"])
    if from_date:
        expenses_query = expenses_query.filter(Expense.date >= from_date)
    if to_date:
        expenses_query = expenses_query.filter(Expense.date <= to_date)

    total_expenses = expenses_query.with_entities(func.sum(Expense.amount)).scalar() or Decimal(0)

    expenses_by_category_query = expenses_query.with_entities(
        Expense.category, func.sum(Expense.amount)
    ).group_by(Expense.category).all()

    expenses_by_category = {cat.value if cat else "Uncategorized": amt for cat, amt in expenses_by_category_query}
    savings_contribution = sum(marking.amount for marking in savings_markings)

    net_balance = total_income - total_expenses

    return ExpenseStatsResponse(
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=net_balance,
        expenses_by_category=expenses_by_category,
        savings_contribution=savings_contribution,
        savings_payout=savings_payout
    )

async def get_financial_advice(from_date: date | None, to_date: date | None, current_user: dict, db: Session):
    stats = await get_expense_stats(from_date, to_date, current_user, db)

    expenses_query = db.query(Expense).join(ExpenseCard).filter(ExpenseCard.customer_id == current_user["user_id"])
    if from_date:
        expenses_query = expenses_query.filter(Expense.date >= from_date)
    if to_date:
        expenses_query = expenses_query.filter(Expense.date <= to_date)
    expenses = expenses_query.all()

    projected_expenses = Decimal(0)
    if len(expenses) >= 3:
        try:
            data = [{'date': exp.date, 'amount': float(exp.amount)} for exp in expenses]
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df = df.resample('M').sum().fillna(0)
            if len(df) >= 3:
                model = ARIMA(df['amount'], order=(1, 0, 0))
                model_fit = model.fit()
                forecast = model_fit.forecast(steps=1)
                projected_expenses = Decimal(forecast.iloc[0]).quantize(Decimal("0.01"))
            else:
                projected_expenses = stats.total_expenses * Decimal("1.05")
        except Exception as e:
            logger.warning(f"ARIMA forecasting failed: {str(e)}")
            projected_expenses = stats.total_expenses * Decimal("1.05")
    else:
        projected_expenses = stats.total_expenses * Decimal("1.05")

    spending_trend_slope = 0.0
    spending_trend = "stable"
    if len(expenses) >= 2:
        try:
            base_date = min(exp.date for exp in expenses)
            dates = [(exp.date - base_date).days for exp in expenses]
            amounts = [float(exp.amount) for exp in expenses]
            X = np.array(dates).reshape(-1, 1)
            y = np.array(amounts)
            model = LinearRegression()
            model.fit(X, y)
            spending_trend_slope = float(model.coef_[0])
            if spending_trend_slope > 0.1:
                spending_trend = "increasing"
            elif spending_trend_slope < -0.1:
                spending_trend = "decreasing"
        except Exception as e:
            logger.warning(f"Linear regression failed: {str(e)}")

    savings_ratio = float((stats.savings_contribution / stats.total_income * 100) if stats.total_income > 0 else 0)

    advice = []
    expense_ratio = (stats.total_expenses / stats.total_income * 100) if stats.total_income > 0 else 0

    if expense_ratio > 80:
        advice.append(f"Your expenses are high ({expense_ratio:.1f}% of income). Focus on reducing spending in high-cost categories.")
    elif expense_ratio > 50:
        advice.append(f"Your expenses are moderate ({expense_ratio:.1f}% of income). Review categories like {max(stats.expenses_by_category, key=stats.expenses_by_category.get, default='NONE')} for savings opportunities.")

    if stats.net_balance < 0:
        advice.append("Your net balance is negative. Prioritize reducing expenses or increasing income to avoid debt.")
    elif stats.net_balance > stats.total_income * Decimal("0.2"):
        advice.append("You have a healthy net balance. Consider allocating excess funds to investments or emergency savings.")

    if savings_ratio < 10:
        advice.append("Your savings rate is low (below 10%). Aim to save 10-20% of your income for financial security.")
    elif savings_ratio > 50:
        advice.append("Great job saving aggressively! Ensure you're balancing savings with necessary expenses.")

    if stats.expenses_by_category:
        max_category = max(stats.expenses_by_category, key=stats.expenses_by_category.get, default="NONE")
        if stats.total_expenses > 0 and stats.expenses_by_category[max_category] / stats.total_expenses > 0.4:
            advice.append(f"Your spending in '{max_category}' accounts for over 40% of expenses. Evaluate if you can optimize this category.")

    if spending_trend == "increasing":
        advice.append("Your spending is trending upward. Review discretionary expenses to stay within budget.")
    elif spending_trend == "decreasing":
        advice.append("Your spending is decreasing, which is positive. Maintain this to optimize your budget.")

    if projected_expenses > stats.net_balance:
        advice.append(f"Projected expenses ({projected_expenses}) may exceed your current balance. Plan a budget to cover this gap.")

    if not advice:
        advice.append(f"Your financial behavior is {spending_trend}. Continue tracking expenses and savings to maintain discipline.")

    advice_str = " ".join(advice)

    response_data = FinancialAdviceResponse(
        total_income=stats.total_income,
        total_expenses=stats.total_expenses,
        net_balance=stats.net_balance,
        expenses_by_category=stats.expenses_by_category,
        savings_contribution=stats.savings_contribution,
        savings_payout=stats.savings_payout,
        projected_expenses=projected_expenses,
        spending_trend_slope=spending_trend_slope,
        savings_ratio=savings_ratio,
        advice=advice_str
    )

    logger.info(f"Generated financial advice for user {current_user['user_id']}")
    return response_data

async def get_financial_analytics(from_date: date | None, to_date: date | None, current_user: dict, db: Session):
    stats = await get_expense_stats(from_date, to_date, current_user, db)

    expenses_query = db.query(Expense).join(ExpenseCard).filter(ExpenseCard.customer_id == current_user["user_id"])
    if from_date:
        expenses_query = expenses_query.filter(Expense.date >= from_date)
    if to_date:
        expenses_query = expenses_query.filter(Expense.date <= to_date)
    expenses = expenses_query.all()

    expense_distribution = {}
    for expense in expenses:
        category = expense.category.value if expense.category else "Uncategorized"
        expense_distribution[category] = expense_distribution.get(category, Decimal(0)) + expense.amount
    expense_distribution = {
        k: float((v / stats.total_expenses * 100) if stats.total_expenses > 0 else 0)
        for k, v in expense_distribution.items()
    }

    transaction_counts = {}
    for expense in expenses:
        category = expense.category.value if expense.category else "Uncategorized"
        transaction_counts[category] = transaction_counts.get(category, 0) + 1

    income_count = db.query(ExpenseCard).filter(
        ExpenseCard.customer_id == current_user["user_id"],
        ExpenseCard.income_amount > 0
    ).count()
    expense_count = len(expenses)
    avg_income = Decimal(stats.total_income / income_count if income_count > 0 else 0).quantize(Decimal("0.01"))
    avg_expense = Decimal(stats.total_expenses / expense_count if expense_count > 0 else 0).quantize(Decimal("0.01"))

    spending_trend_slope = 0.0
    if len(expenses) >= 2:
        try:
            base_date = min(exp.date for exp in expenses)
            dates = [(exp.date - base_date).days for exp in expenses]
            amounts = [float(exp.amount) for exp in expenses]
            X = np.array(dates).reshape(-1, 1)
            y = np.array(amounts)
            model = LinearRegression()
            model.fit(X, y)
            spending_trend_slope = float(model.coef_[0])
        except Exception as e:
            logger.warning(f"Linear regression failed: {str(e)}")

    amounts = [float(exp.amount) for exp in expenses]
    expense_volatility = float(np.std(amounts)) if amounts else 0.0

    top_expense_category = None
    top_expense_percentage = 0.0
    if expense_distribution:
        top_expense_category = max(expense_distribution, key=expense_distribution.get, default=None)
        top_expense_percentage = expense_distribution.get(top_expense_category, 0.0)

    response_data = FinancialAnalyticsResponse(
        total_income=stats.total_income,
        total_expenses=stats.total_expenses,
        net_balance=stats.net_balance,
        savings_contribution=stats.savings_contribution,
        savings_payout=stats.savings_payout,
        savings_ratio=float((stats.savings_contribution / stats.total_income * 100) if stats.total_income > 0 else 0),
        expense_distribution=expense_distribution,
        transaction_counts=transaction_counts,
        avg_income=avg_income,
        avg_expense=avg_expense,
        spending_trend_slope=spending_trend_slope,
        expense_volatility=expense_volatility,
        top_expense_category=top_expense_category,
        top_expense_percentage=top_expense_percentage
    )

    logger.info(f"Generated financial analytics for user {current_user['user_id']}")
    return response_data