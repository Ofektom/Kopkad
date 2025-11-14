from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import Dict, List, Optional, Tuple
from models.financial_advisor import (
    SavingsGoal, FinancialHealthScore, SpendingPattern, UserNotification,
    GoalPriority, GoalStatus, PatternType, NotificationType, NotificationPriority
)
from models.expenses import ExpenseCard, Expense, ExpenseCategory
from models.savings import SavingsAccount, SavingsMarking, SavingsStatus, MarkingStatus
from models.user import User
from schemas.financial_advisor import (
    SavingsGoalCreate, SavingsGoalUpdate, SavingsGoalResponse,
    FinancialHealthScoreResponse, HealthScoreHistory,
    SpendingPatternResponse, RecurringExpenseResponse, AnomalyResponse,
    RecommendationResponse, PersonalizedAdviceResponse,
    RoadmapStepResponse, ImprovementRoadmapResponse,
    SavingsOpportunityResponse, SavingsOpportunitiesResponse
)
from utils.response import success_response, error_response
from store.repositories import (
    ExpenseCardRepository,
    ExpenseRepository,
    SavingsRepository,
    SavingsGoalRepository,
    FinancialHealthScoreRepository,
    SpendingPatternRepository,
)
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta
import logging
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans, DBSCAN
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.seasonal import seasonal_decompose
from collections import Counter, defaultdict
import math

logging.basicConfig(
    filename="financial_advisor.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)

# ========================
# SAVINGS GOAL INTELLIGENCE
# ========================

async def analyze_savings_capacity(
    customer_id: int,
    db: Session,
    *,
    expense_card_repo: ExpenseCardRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    savings_repo: SavingsRepository | None = None,
) -> Dict:
    """Calculate optimal savings capacity based on income/expense patterns."""
    try:
        expense_card_repo = _resolve_repo(expense_card_repo, ExpenseCardRepository, db)
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
        savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
        session = expense_repo.db

        # Get expense cards and total income
        cards = expense_card_repo.get_all_for_user(customer_id)
        total_income = sum(card.income_amount for card in cards)
        
        # Get total expenses from last 3 months
        three_months_ago = date.today() - timedelta(days=90)
        expenses_query = session.query(Expense).join(ExpenseCard).filter(
            ExpenseCard.customer_id == customer_id,
            Expense.date >= three_months_ago
        )
        total_expenses = expenses_query.with_entities(func.sum(Expense.amount)).scalar() or Decimal(0)
        
        # Get current savings contribution
        savings_markings = savings_repo.db.query(SavingsMarking).join(SavingsAccount).filter(
            SavingsAccount.customer_id == customer_id,
            SavingsMarking.status == SavingsStatus.PAID,
            SavingsMarking.marked_date >= three_months_ago
        ).all()
        current_savings = sum(m.amount for m in savings_markings)
        
        # Calculate disposable income
        disposable_income = total_income - total_expenses
        
        # Calculate recommended savings (20-30% rule)
        recommended_minimum = total_income * Decimal("0.10")  # 10% minimum
        recommended_optimal = total_income * Decimal("0.20")  # 20% optimal
        recommended_aggressive = total_income * Decimal("0.30")  # 30% aggressive
        
        # Determine capacity level
        if disposable_income >= recommended_aggressive:
            capacity_level = "high"
            recommended_amount = recommended_aggressive
        elif disposable_income >= recommended_optimal:
            capacity_level = "moderate"
            recommended_amount = recommended_optimal
        elif disposable_income >= recommended_minimum:
            capacity_level = "low"
            recommended_amount = recommended_minimum
        else:
            capacity_level = "critical"
            recommended_amount = max(disposable_income * Decimal("0.5"), Decimal(0))
        
        return {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "disposable_income": disposable_income,
            "current_savings": current_savings,
            "capacity_level": capacity_level,
            "recommended_minimum_savings": recommended_minimum,
            "recommended_optimal_savings": recommended_optimal,
            "recommended_aggressive_savings": recommended_aggressive,
            "recommended_amount": recommended_amount,
            "savings_rate": float((current_savings / total_income * 100) if total_income > 0 else 0)
        }
    except Exception as e:
        logger.error(f"Error analyzing savings capacity for customer {customer_id}: {str(e)}")
        return {}


async def recommend_savings_goals(customer_id: int, db: Session) -> List[SavingsGoalResponse]:
    """Generate AI-recommended savings goals based on user's financial situation."""
    try:
        capacity = await analyze_savings_capacity(
            customer_id,
            db,
            expense_card_repo=expense_card_repo,
            expense_repo=expense_repo,
            savings_repo=savings_repo,
        )
        if not capacity:
            return []
        
        recommendations = []
        total_income = capacity["total_income"]
        recommended_amount = capacity["recommended_amount"]
        
        # Emergency Fund (3-6 months expenses)
        three_month_expenses = capacity["total_expenses"]
        if three_month_expenses > 0:
            emergency_goal = SavingsGoal(
                customer_id=customer_id,
                name="Emergency Fund",
                target_amount=three_month_expenses * 3,
                current_amount=Decimal(0),
                deadline=date.today() + relativedelta(months=12),
                priority=GoalPriority.HIGH,
                category="emergency_fund",
                status=GoalStatus.ACTIVE,
                is_ai_recommended=True,
                description="Build a safety net covering 3 months of expenses",
                created_by=customer_id,
                created_at=datetime.now(timezone.utc)
            )
            recommendations.append(emergency_goal)
        
        # Short-term savings (vacation/personal)
        if capacity["capacity_level"] in ["moderate", "high"]:
            short_term_goal = SavingsGoal(
                customer_id=customer_id,
                name="Short-term Savings Goal",
                target_amount=recommended_amount * 6,
                current_amount=Decimal(0),
                deadline=date.today() + relativedelta(months=6),
                priority=GoalPriority.MEDIUM,
                category="personal",
                status=GoalStatus.ACTIVE,
                is_ai_recommended=True,
                description="Save for a vacation, gadget, or personal project",
                created_by=customer_id,
                created_at=datetime.now(timezone.utc)
            )
            recommendations.append(short_term_goal)
        
        # Long-term investment goal
        if capacity["capacity_level"] == "high":
            long_term_goal = SavingsGoal(
                customer_id=customer_id,
                name="Long-term Investment Fund",
                target_amount=total_income * 2,
                current_amount=Decimal(0),
                deadline=date.today() + relativedelta(months=24),
                priority=GoalPriority.LOW,
                category="investment",
                status=GoalStatus.ACTIVE,
                is_ai_recommended=True,
                description="Build capital for future investments or major purchases",
                created_by=customer_id,
                created_at=datetime.now(timezone.utc)
            )
            recommendations.append(long_term_goal)
        
        return [SavingsGoalResponse.model_validate(goal) for goal in recommendations]
    except Exception as e:
        logger.error(f"Error recommending savings goals for customer {customer_id}: {str(e)}")
        return []


async def track_goal_progress(
    goal_id: int,
    customer_id: int,
    db: Session,
    *,
    savings_goal_repo: SavingsGoalRepository | None = None,
) -> Dict:
    """Monitor progress and suggest adjustments for a savings goal."""
    try:
        savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)

        goal = savings_goal_repo.get_by_id_for_customer(goal_id, customer_id)
        
        if not goal:
            return error_response(status_code=404, message="Goal not found")
        
        # Calculate progress
        progress_percentage = float((goal.current_amount / goal.target_amount * 100) if goal.target_amount > 0 else 0)
        remaining_amount = goal.target_amount - goal.current_amount
        
        # Calculate days remaining
        days_remaining = None
        on_track = None
        required_daily_savings = None
        
        if goal.deadline:
            days_remaining = (goal.deadline - date.today()).days
            
            if days_remaining > 0:
                required_daily_savings = remaining_amount / days_remaining
                
                # Check if on track (compare with actual savings rate)
                days_since_creation = (date.today() - goal.created_at.date()).days if goal.created_at else 1
                actual_daily_rate = goal.current_amount / max(days_since_creation, 1)
                on_track = actual_daily_rate >= required_daily_savings * Decimal("0.9")  # 90% threshold
        
        # Generate suggestions
        suggestions = []
        if goal.status == GoalStatus.ACTIVE:
            if progress_percentage < 25 and days_remaining and days_remaining < 30:
                suggestions.append("Consider extending the deadline or reducing the target amount")
            elif progress_percentage >= 100:
                suggestions.append("Congratulations! You've reached your goal. Consider marking it as achieved.")
            elif on_track is False:
                suggestions.append(f"You're behind schedule. Try to save {required_daily_savings:.2f} per day to reach your goal")
            elif on_track is True:
                suggestions.append("Great job! You're on track to reach your goal.")
        
        return {
            "goal": SavingsGoalResponse.model_validate(goal),
            "progress_percentage": progress_percentage,
            "remaining_amount": remaining_amount,
            "days_remaining": days_remaining,
            "required_daily_savings": required_daily_savings,
            "on_track": on_track,
            "suggestions": suggestions
        }
    except Exception as e:
        logger.error(f"Error tracking goal progress for goal {goal_id}: {str(e)}")
        return error_response(status_code=500, message="Error tracking goal progress")


# ========================
# SPENDING PATTERN ANALYSIS
# ========================

async def detect_spending_patterns(
    customer_id: int,
    db: Session,
    *,
    expense_repo: ExpenseRepository | None = None,
    spending_pattern_repo: SpendingPatternRepository | None = None,
) -> List[SpendingPatternResponse]:
    """Identify recurring, seasonal, and anomalous spending using ML."""
    try:
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
        spending_pattern_repo = _resolve_repo(spending_pattern_repo, SpendingPatternRepository, db)
        session = expense_repo.db

        # Get all expenses for the customer
        expenses = session.query(Expense).join(ExpenseCard).filter(
            ExpenseCard.customer_id == customer_id
        ).order_by(Expense.date).all()
        
        if len(expenses) < 10:  # Need minimum data
            return []
        
        patterns = []
        
        # Detect recurring expenses
        recurring = await _detect_recurring_expenses(
            expenses,
            customer_id,
            pattern_repo=spending_pattern_repo,
        )
        patterns.extend(recurring)
        
        # Detect anomalies
        anomalies = await _detect_anomalous_spending(
            expenses,
            customer_id,
            pattern_repo=spending_pattern_repo,
        )
        patterns.extend(anomalies)
        
        # Detect seasonal patterns (if enough data)
        if len(expenses) >= 30:
            seasonal = await _detect_seasonal_patterns(
                expenses,
                customer_id,
                pattern_repo=spending_pattern_repo,
            )
            patterns.extend(seasonal)
        
        return [SpendingPatternResponse.model_validate(p) for p in patterns]
    except Exception as e:
        logger.error(f"Error detecting spending patterns for customer {customer_id}: {str(e)}")
        return []


async def _detect_recurring_expenses(
    expenses: List[Expense],
    customer_id: int,
    *,
    pattern_repo: SpendingPatternRepository,
) -> List[SpendingPattern]:
    """Detect recurring expenses using frequency analysis."""
    try:
        # Group expenses by similar amounts and categories
        expense_groups = defaultdict(list)
        for exp in expenses:
            # Round amount to nearest 100 for grouping
            rounded_amount = round(float(exp.amount) / 100) * 100
            key = (exp.category.value if exp.category else "Uncategorized", rounded_amount)
            expense_groups[key].append(exp)
        
        patterns = []
        session = pattern_repo.db

        for (category, amount), exps in expense_groups.items():
            if len(exps) >= 3:  # At least 3 occurrences
                # Calculate average interval between expenses
                dates = sorted([e.date for e in exps])
                intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    std_interval = np.std(intervals) if len(intervals) > 1 else 0
                    
                    # If consistent interval (low std), it's recurring
                    if std_interval < avg_interval * 0.3:  # 30% variation tolerance
                        frequency = "weekly" if avg_interval <= 10 else "monthly" if avg_interval <= 35 else "quarterly"
                        
                        # Check if pattern already exists
                        existing = session.query(SpendingPattern).filter(
                            SpendingPattern.customer_id == customer_id,
                            SpendingPattern.pattern_type == PatternType.RECURRING,
                            SpendingPattern.description.like(f"%{category}%"),
                            SpendingPattern.amount.between(Decimal(amount * 0.9), Decimal(amount * 1.1))
                        ).first()
                        
                        if not existing:
                            pattern = SpendingPattern(
                                customer_id=customer_id,
                                pattern_type=PatternType.RECURRING,
                                description=f"Recurring {category} expense",
                                amount=Decimal(sum(float(e.amount) for e in exps) / len(exps)),
                                frequency=frequency,
                                detected_at=datetime.now(timezone.utc),
                                last_occurrence=max(dates),
                                pattern_metadata={"interval_days": avg_interval, "occurrences": len(exps)},
                                created_by=customer_id,
                                created_at=datetime.now(timezone.utc)
                            )
                            session.add(pattern)
                            patterns.append(pattern)
        
        if patterns:
            session.commit()
        
        return patterns
    except Exception as e:
        logger.error(f"Error detecting recurring expenses: {str(e)}")
        return []


async def _detect_anomalous_spending(
    expenses: List[Expense],
    customer_id: int,
    *,
    pattern_repo: SpendingPatternRepository,
) -> List[SpendingPattern]:
    """Detect unusual spending using Isolation Forest."""
    try:
        if len(expenses) < 20:  # Need enough data for anomaly detection
            return []
        
        # Prepare data for Isolation Forest
        amounts = np.array([float(exp.amount) for exp in expenses]).reshape(-1, 1)
        
        # Use Isolation Forest
        iso_forest = IsolationForest(contamination=0.1, random_state=42)
        predictions = iso_forest.fit_predict(amounts)
        
        session = pattern_repo.db

        patterns = []
        for i, pred in enumerate(predictions):
            if pred == -1:  # Anomaly detected
                exp = expenses[i]
                
                # Calculate how much it deviates from mean
                mean_amount = np.mean(amounts)
                deviation = abs(float(exp.amount) - mean_amount) / mean_amount * 100
                
                # Only flag significant anomalies (>50% deviation)
                if deviation > 50:
                    # Check if not already flagged recently
                    recent_anomaly = session.query(SpendingPattern).filter(
                        SpendingPattern.customer_id == customer_id,
                        SpendingPattern.pattern_type == PatternType.ANOMALY,
                        SpendingPattern.last_occurrence >= exp.date - timedelta(days=7)
                    ).first()
                    
                    if not recent_anomaly:
                        severity = "high" if deviation > 150 else "medium" if deviation > 100 else "low"
                        pattern = SpendingPattern(
                            customer_id=customer_id,
                            pattern_type=PatternType.ANOMALY,
                            description=f"Unusual {exp.category.value if exp.category else 'spending'} detected",
                            amount=exp.amount,
                            frequency=None,
                            detected_at=datetime.now(timezone.utc),
                            last_occurrence=exp.date,
                            pattern_metadata={"deviation_percentage": deviation, "severity": severity},
                            created_by=customer_id,
                            created_at=datetime.now(timezone.utc)
                        )
                        session.add(pattern)
                        patterns.append(pattern)
        
        if patterns:
            session.commit()
        
        return patterns
    except Exception as e:
        logger.error(f"Error detecting anomalous spending: {str(e)}")
        return []


async def _detect_seasonal_patterns(
    expenses: List[Expense],
    customer_id: int,
    *,
    pattern_repo: SpendingPatternRepository,
) -> List[SpendingPattern]:
    """Detect seasonal spending patterns using time series decomposition."""
    try:
        # Create time series data
        df = pd.DataFrame([
            {"date": exp.date, "amount": float(exp.amount)}
            for exp in expenses
        ])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        df = df.resample('W').sum()  # Weekly aggregation
        
        if len(df) < 52:  # Need at least a year of weekly data
            return []
        
        session = pattern_repo.db

        # Perform seasonal decomposition
        decomposition = seasonal_decompose(df['amount'], model='additive', period=4)  # Monthly cycle
        seasonal_component = decomposition.seasonal
        
        # Identify significant seasonal patterns
        seasonal_strength = np.std(seasonal_component) / np.std(df['amount'])
        
        patterns = []
        if seasonal_strength > 0.2:  # Significant seasonality
            pattern = SpendingPattern(
                customer_id=customer_id,
                pattern_type=PatternType.SEASONAL,
                description="Seasonal spending pattern detected",
                amount=None,
                frequency="cyclical",
                detected_at=datetime.now(timezone.utc),
                last_occurrence=df.index[-1].date(),
                pattern_metadata={"seasonal_strength": seasonal_strength, "period": "monthly"},
                created_by=customer_id,
                created_at=datetime.now(timezone.utc)
            )
            session.add(pattern)
            session.commit()
            patterns.append(pattern)
        
        return patterns
    except Exception as e:
        logger.error(f"Error detecting seasonal patterns: {str(e)}")
        return []


async def identify_wasteful_spending(
    customer_id: int,
    db: Session,
    *,
    spending_pattern_repo: SpendingPatternRepository | None = None,
) -> List[Dict]:
    """Flag unnecessary expenses based on patterns."""
    try:
        wasteful = []
        
        spending_pattern_repo = _resolve_repo(spending_pattern_repo, SpendingPatternRepository, db)

        # Get recurring expenses
        recurring_patterns = spending_pattern_repo.get_by_type(customer_id, PatternType.RECURRING)
        
        for pattern in recurring_patterns:
            if pattern.frequency == "monthly" and pattern.amount:
                yearly_cost = pattern.amount * 12
                if yearly_cost > 10000:  # Significant recurring cost
                    wasteful.append({
                        "description": pattern.description,
                        "amount": pattern.amount,
                        "frequency": pattern.frequency,
                        "yearly_cost": yearly_cost,
                        "recommendation": "Review if this subscription/expense is still necessary"
                    })
        
        return wasteful
    except Exception as e:
        logger.error(f"Error identifying wasteful spending: {str(e)}")
        return []


# ========================
# FINANCIAL HEALTH SCORING
# ========================

async def calculate_financial_health_score(
    customer_id: int,
    db: Session,
    *,
    financial_health_repo: FinancialHealthScoreRepository | None = None,
    savings_goal_repo: SavingsGoalRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    expense_card_repo: ExpenseCardRepository | None = None,
    savings_repo: SavingsRepository | None = None,
) -> FinancialHealthScoreResponse:
    """Calculate multi-factor financial health score (0-100)."""
    try:
        factors = {}
        
        financial_health_repo = _resolve_repo(financial_health_repo, FinancialHealthScoreRepository, db)
        savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
        expense_card_repo = _resolve_repo(expense_card_repo, ExpenseCardRepository, db)
        savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)

        session = financial_health_repo.db

        # Factor 1: Expense Ratio (30 points)
        capacity = await analyze_savings_capacity(customer_id, db)
        if capacity:
            expense_ratio = float(capacity["total_expenses"] / capacity["total_income"] * 100 if capacity["total_income"] > 0 else 100)
            if expense_ratio <= 50:
                factors["expense_ratio"] = 30
            elif expense_ratio <= 70:
                factors["expense_ratio"] = 20
            elif expense_ratio <= 80:
                factors["expense_ratio"] = 10
            else:
                factors["expense_ratio"] = 5
        
        # Factor 2: Savings Rate (25 points)
        savings_rate = capacity.get("savings_rate", 0) if capacity else 0
        if savings_rate >= 20:
            factors["savings_rate"] = 25
        elif savings_rate >= 15:
            factors["savings_rate"] = 20
        elif savings_rate >= 10:
            factors["savings_rate"] = 15
        elif savings_rate >= 5:
            factors["savings_rate"] = 10
        else:
            factors["savings_rate"] = 5
        
        # Factor 3: Goal Achievement (20 points)
        goals = savings_goal_repo.get_all_for_customer(customer_id)
        if goals:
            achieved_goals = [g for g in goals if g.status == GoalStatus.ACHIEVED]
            active_goals = [g for g in goals if g.status == GoalStatus.ACTIVE]
            
            achievement_rate = len(achieved_goals) / len(goals) * 100 if goals else 0
            if achievement_rate >= 75:
                factors["goal_achievement"] = 20
            elif achievement_rate >= 50:
                factors["goal_achievement"] = 15
            elif achievement_rate >= 25:
                factors["goal_achievement"] = 10
            else:
                factors["goal_achievement"] = 5
                
            # Check progress on active goals
            if active_goals:
                on_track_count = 0
                for goal in active_goals:
                    if goal.current_amount >= goal.target_amount * Decimal("0.25"):  # At least 25% progress
                        on_track_count += 1
                if on_track_count / len(active_goals) >= 0.5:
                    factors["goal_achievement"] = min(factors.get("goal_achievement", 0) + 5, 20)
        else:
            factors["goal_achievement"] = 10  # Neutral if no goals
        
        # Factor 4: Spending Consistency (15 points)
        expenses = (
            expense_repo.db.query(Expense)
            .join(ExpenseCard)
            .filter(ExpenseCard.customer_id == customer_id)
            .order_by(Expense.date.desc())
            .limit(90)
            .all()
        )
        
        if len(expenses) >= 30:
            daily_expenses = [float(e.amount) for e in expenses]
            std_dev = np.std(daily_expenses)
            mean_exp = np.mean(daily_expenses)
            coefficient_variation = (std_dev / mean_exp) if mean_exp > 0 else 1
            
            if coefficient_variation <= 0.3:
                factors["spending_consistency"] = 15
            elif coefficient_variation <= 0.5:
                factors["spending_consistency"] = 10
            else:
                factors["spending_consistency"] = 5
        else:
            factors["spending_consistency"] = 10
        
        # Factor 5: Savings Account Activity (10 points)
        savings_accounts = savings_repo.db.query(SavingsAccount).filter(
            SavingsAccount.customer_id == customer_id,
            SavingsAccount.marking_status == MarkingStatus.COMPLETED
        ).count()
        
        if savings_accounts >= 3:
            factors["savings_activity"] = 10
        elif savings_accounts >= 2:
            factors["savings_activity"] = 8
        elif savings_accounts >= 1:
            factors["savings_activity"] = 5
        else:
            factors["savings_activity"] = 0
        
        # Calculate total score
        total_score = sum(factors.values())
        
        # Generate recommendations
        recommendations = []
        if factors.get("expense_ratio", 0) < 15:
            recommendations.append({"area": "Expenses", "suggestion": "Reduce your expense ratio to below 70% of income"})
        if factors.get("savings_rate", 0) < 15:
            recommendations.append({"area": "Savings", "suggestion": "Increase your savings rate to at least 15% of income"})
        if factors.get("goal_achievement", 0) < 15:
            recommendations.append({"area": "Goals", "suggestion": "Set and work towards achievable savings goals"})
        
        # Save to database
        health_score = financial_health_repo.create(
            {
                "customer_id": customer_id,
                "score": total_score,
                "score_date": datetime.now(timezone.utc),
                "factors_breakdown": factors,
                "recommendations": recommendations,
                "created_by": customer_id,
                "created_at": datetime.now(timezone.utc),
            }
        )
        session.commit()
        session.refresh(health_score)

        return FinancialHealthScoreResponse.model_validate(health_score)
    except Exception as e:
        logger.error(f"Error calculating financial health score for customer {customer_id}: {str(e)}")
        raise


async def generate_improvement_roadmap(
    customer_id: int,
    db: Session,
    *,
    financial_health_repo: FinancialHealthScoreRepository | None = None,
    savings_goal_repo: SavingsGoalRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    expense_card_repo: ExpenseCardRepository | None = None,
    savings_repo: SavingsRepository | None = None,
) -> ImprovementRoadmapResponse:
    """Generate actionable steps to improve financial health score."""
    try:
        financial_health_repo = _resolve_repo(financial_health_repo, FinancialHealthScoreRepository, db)
        savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
        expense_card_repo = _resolve_repo(expense_card_repo, ExpenseCardRepository, db)
        savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)

        # Get current score
        current_record = (
            financial_health_repo.db.query(FinancialHealthScore)
            .filter(FinancialHealthScore.customer_id == customer_id)
            .order_by(FinancialHealthScore.score_date.desc())
            .first()
        )

        if current_record:
            current_score_response = FinancialHealthScoreResponse.model_validate(current_record)
        else:
            current_score_response = await calculate_financial_health_score(
                customer_id,
                db,
                financial_health_repo=financial_health_repo,
                savings_goal_repo=savings_goal_repo,
                expense_repo=expense_repo,
                expense_card_repo=expense_card_repo,
                savings_repo=savings_repo,
            )
        
        current_score = current_score_response.score
        target_score = min(current_score + 20, 100)
        
        steps = []
        step_num = 1
        
        factors = current_score_response.factors_breakdown
        
        # Step for expense ratio
        if factors.get("expense_ratio", 0) < 20:
            steps.append(RoadmapStepResponse(
                step_number=step_num,
                title="Reduce Monthly Expenses",
                description="Cut unnecessary spending and reduce your expense-to-income ratio to below 70%",
                estimated_impact="+5-10 points",
                timeframe="2-4 weeks",
                difficulty="medium"
            ))
            step_num += 1
        
        # Step for savings rate
        if factors.get("savings_rate", 0) < 20:
            steps.append(RoadmapStepResponse(
                step_number=step_num,
                title="Increase Savings Rate",
                description="Aim to save at least 15-20% of your monthly income",
                estimated_impact="+5-10 points",
                timeframe="1 month",
                difficulty="medium"
            ))
            step_num += 1
        
        # Step for goals
        if factors.get("goal_achievement", 0) < 15:
            steps.append(RoadmapStepResponse(
                step_number=step_num,
                title="Set and Track Savings Goals",
                description="Create 2-3 achievable savings goals and contribute to them regularly",
                estimated_impact="+5-10 points",
                timeframe="2-3 weeks",
                difficulty="easy"
            ))
            step_num += 1
        
        # Step for consistency
        if factors.get("spending_consistency", 0) < 10:
            steps.append(RoadmapStepResponse(
                step_number=step_num,
                title="Stabilize Your Spending",
                description="Create a monthly budget and stick to it to reduce spending variability",
                estimated_impact="+5 points",
                timeframe="1-2 months",
                difficulty="medium"
            ))
            step_num += 1
        
        key_focus_areas = []
        if factors.get("expense_ratio", 0) < 15:
            key_focus_areas.append("Expense Management")
        if factors.get("savings_rate", 0) < 15:
            key_focus_areas.append("Savings Discipline")
        if factors.get("goal_achievement", 0) < 15:
            key_focus_areas.append("Goal Setting")
        
        estimated_weeks = len(steps) * 2  # Average 2 weeks per step
        
        return ImprovementRoadmapResponse(
            current_score=current_score,
            target_score=target_score,
            estimated_weeks=estimated_weeks,
            steps=steps,
            key_focus_areas=key_focus_areas if key_focus_areas else ["Maintain Current Performance"]
        )
    except Exception as e:
        logger.error(f"Error generating improvement roadmap for customer {customer_id}: {str(e)}")
        raise


# ========================
# PERSONALIZED RECOMMENDATIONS
# ========================

async def generate_personalized_advice(
    customer_id: int,
    db: Session,
    *,
    financial_health_repo: FinancialHealthScoreRepository | None = None,
    savings_goal_repo: SavingsGoalRepository | None = None,
    expense_repo: ExpenseRepository | None = None,
    expense_card_repo: ExpenseCardRepository | None = None,
    savings_repo: SavingsRepository | None = None,
    spending_pattern_repo: SpendingPatternRepository | None = None,
) -> PersonalizedAdviceResponse:
    """Generate context-aware recommendations using user history."""
    try:
        financial_health_repo = _resolve_repo(financial_health_repo, FinancialHealthScoreRepository, db)
        savings_goal_repo = _resolve_repo(savings_goal_repo, SavingsGoalRepository, db)
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
        expense_card_repo = _resolve_repo(expense_card_repo, ExpenseCardRepository, db)
        savings_repo = _resolve_repo(savings_repo, SavingsRepository, db)
        spending_pattern_repo = _resolve_repo(spending_pattern_repo, SpendingPatternRepository, db)

        # Get financial health score
        health_score_record = await calculate_financial_health_score(
            customer_id,
            db,
            financial_health_repo=financial_health_repo,
            savings_goal_repo=savings_goal_repo,
            expense_repo=expense_repo,
            expense_card_repo=expense_card_repo,
            savings_repo=savings_repo,
        )
        
        # Get capacity analysis
        capacity = await analyze_savings_capacity(
            customer_id,
            db,
            expense_card_repo=expense_card_repo,
            expense_repo=expense_repo,
            savings_repo=savings_repo,
        )
        
        # Get spending patterns
        patterns = await detect_spending_patterns(
            customer_id,
            db,
            expense_repo=expense_repo,
            spending_pattern_repo=spending_pattern_repo,
        )
        
        # Generate recommendations
        recommendations = []
        
        # Recommendation 1: Based on recurring expenses
        wasteful = await identify_wasteful_spending(
            customer_id,
            db,
            spending_pattern_repo=spending_pattern_repo,
        )
        if wasteful:
            total_wasteful = sum(w["yearly_cost"] for w in wasteful)
            recommendations.append(RecommendationResponse(
                title="Reduce Recurring Expenses",
                description=f"You have {len(wasteful)} recurring expenses totaling {total_wasteful:.2f} per year",
                category="expense_reduction",
                potential_savings=Decimal(total_wasteful) / 12,
                priority="high",
                action_items=[
                    "Review each recurring expense and cancel unused subscriptions",
                    "Negotiate better rates for essential services",
                    "Consider cheaper alternatives"
                ]
            ))
        
        # Recommendation 2: Savings opportunities
        if capacity:
            if capacity["capacity_level"] in ["moderate", "high"]:
                potential = capacity["recommended_optimal_savings"] - capacity["current_savings"]
                if potential > 0:
                    recommendations.append(RecommendationResponse(
                        title="Increase Your Savings",
                        description=f"You have capacity to save an additional {potential:.2f} per month",
                        category="savings_increase",
                        potential_savings=potential,
                        priority="medium",
                        action_items=[
                            "Set up automatic savings transfers",
                            "Create specific savings goals",
                            f"Start with saving {potential/4:.2f} weekly"
                        ]
                    ))
        
        # Recommendation 3: Category-specific
        category_advice = await suggest_category_optimizations(
            customer_id,
            db,
            expense_repo=expense_repo,
        )
        for advice in category_advice[:2]:  # Top 2 categories
            recommendations.append(RecommendationResponse(
                title=f"Optimize {advice['category']} Spending",
                description=advice['description'],
                category="category_optimization",
                potential_savings=advice.get('potential_savings'),
                priority="medium",
                action_items=advice.get('action_items', [])
            ))
        
        # Generate spending insights
        insights = []
        anomaly_patterns = [p for p in patterns if p.pattern_type == PatternType.ANOMALY]
        if anomaly_patterns:
            insights.append(f"Detected {len(anomaly_patterns)} unusual spending event(s) recently")
        
        recurring_patterns = [p for p in patterns if p.pattern_type == PatternType.RECURRING]
        if recurring_patterns:
            total_recurring = sum(float(p.amount) for p in recurring_patterns if p.amount)
            insights.append(f"You have {len(recurring_patterns)} recurring expenses totaling {total_recurring:.2f}")
        
        if capacity:
            insights.append(f"Your savings rate is {capacity['savings_rate']:.1f}% (Target: 15-20%)")
        
        # Generate advice summary
        if health_score_record.score >= 80:
            advice_summary = "Excellent! Your financial health is strong. Keep up the good work and consider investing for the future."
        elif health_score_record.score >= 60:
            advice_summary = "Good progress! Focus on increasing your savings rate and reducing unnecessary expenses to reach excellent health."
        elif health_score_record.score >= 40:
            advice_summary = "You're on the right track, but there's room for improvement. Focus on building an emergency fund and reducing high-cost categories."
        else:
            advice_summary = "Your financial health needs attention. Start by tracking all expenses, creating a budget, and reducing unnecessary spending."
        
        return PersonalizedAdviceResponse(
            total_income=capacity.get("total_income", Decimal(0)) if capacity else Decimal(0),
            total_expenses=capacity.get("total_expenses", Decimal(0)) if capacity else Decimal(0),
            net_balance=capacity.get("disposable_income", Decimal(0)) if capacity else Decimal(0),
            savings_contribution=capacity.get("current_savings", Decimal(0)) if capacity else Decimal(0),
            financial_health_score=health_score_record.score,
            advice_summary=advice_summary,
            recommendations=recommendations,
            spending_insights=insights
        )
    except Exception as e:
        logger.error(f"Error generating personalized advice for customer {customer_id}: {str(e)}")
        raise


async def suggest_category_optimizations(
    customer_id: int,
    db: Session,
    *,
    expense_repo: ExpenseRepository | None = None,
) -> List[Dict]:
    """Suggest category-specific optimizations."""
    try:
        # Get expenses by category
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)

        session = expense_repo.db

        expenses_query = session.query(
            Expense.category,
            func.sum(Expense.amount).label('total')
        ).join(ExpenseCard).filter(
            ExpenseCard.customer_id == customer_id,
            Expense.date >= date.today() - timedelta(days=90)
        ).group_by(Expense.category).all()
        
        total_spending = sum(float(e.total) for e in expenses_query)
        suggestions = []
        
        # Define optimal ranges (percentage of total spending)
        optimal_ranges = {
            ExpenseCategory.FOOD: (25, 35),
            ExpenseCategory.TRANSPORT: (10, 20),
            ExpenseCategory.ENTERTAINMENT: (5, 15),
            ExpenseCategory.UTILITIES: (10, 20),
            ExpenseCategory.RENT: (25, 35),
            ExpenseCategory.MISC: (5, 15)
        }
        
        for exp in expenses_query:
            if exp.category and total_spending > 0:
                percentage = float(exp.total) / total_spending * 100
                category_name = exp.category.value
                optimal_range = optimal_ranges.get(exp.category, (10, 20))
                
                if percentage > optimal_range[1]:
                    overspending = Decimal(exp.total) * Decimal((percentage - optimal_range[1]) / 100)
                    suggestions.append({
                        "category": category_name,
                        "description": f"Your {category_name} spending ({percentage:.1f}%) is above the optimal range ({optimal_range[1]}%)",
                        "potential_savings": overspending,
                        "action_items": [
                            f"Review {category_name} expenses for reduction opportunities",
                            f"Set a monthly budget of {exp.total * Decimal(optimal_range[1]/100/percentage):.2f}",
                            "Track daily spending in this category"
                        ]
                    })
        
        return sorted(suggestions, key=lambda x: x['potential_savings'], reverse=True)
    except Exception as e:
        logger.error(f"Error suggesting category optimizations: {str(e)}")
        return []


async def recommend_savings_opportunities(
    customer_id: int,
    db: Session,
    *,
    expense_repo: ExpenseRepository | None = None,
    spending_pattern_repo: SpendingPatternRepository | None = None,
) -> SavingsOpportunitiesResponse:
    """Identify where to cut spending and save money."""
    try:
        opportunities = []
        
        expense_repo = _resolve_repo(expense_repo, ExpenseRepository, db)
        spending_pattern_repo = _resolve_repo(spending_pattern_repo, SpendingPatternRepository, db)

        # Get category spending
        category_suggestions = await suggest_category_optimizations(
            customer_id,
            db,
            expense_repo=expense_repo,
        )
        for suggestion in category_suggestions:
            opportunities.append(SavingsOpportunityResponse(
                category=suggestion['category'],
                current_spending=suggestion['potential_savings'] + Decimal(100),  # Approximate
                recommended_spending=Decimal(100),
                potential_savings=suggestion['potential_savings'],
                confidence=0.8,
                reasoning=suggestion['description']
            ))
        
        # Get recurring expenses analysis
        wasteful = await identify_wasteful_spending(
            customer_id,
            db,
            spending_pattern_repo=spending_pattern_repo,
        )
        for waste in wasteful:
            opportunities.append(SavingsOpportunityResponse(
                category="Subscriptions",
                current_spending=waste['amount'],
                recommended_spending=Decimal(0),
                potential_savings=waste['amount'],
                confidence=0.9,
                reasoning=f"Recurring {waste['frequency']} expense that can be reviewed"
            ))
        
        total_potential = sum(opp.potential_savings for opp in opportunities)
        monthly_goal = total_potential * Decimal("0.5")  # Conservative estimate
        
        return SavingsOpportunitiesResponse(
            total_potential_savings=total_potential,
            opportunities=opportunities,
            monthly_savings_goal_suggestion=monthly_goal
        )
    except Exception as e:
        logger.error(f"Error recommending savings opportunities: {str(e)}")
        raise

