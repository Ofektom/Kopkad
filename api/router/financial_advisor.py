from fastapi import APIRouter

from api.controller.financial_advisor import (
    allocate_to_goal_controller,
    create_savings_goal_controller,
    delete_savings_goal_controller,
    get_ai_recommended_goals_controller,
    get_category_recommendations_controller,
    get_current_health_score_controller,
    get_health_score_history_controller,
    get_improvement_roadmap_controller,
    get_notifications_controller,
    get_personalized_advice_controller,
    get_recurring_expenses_controller,
    get_savings_capacity_controller,
    get_savings_goal_controller,
    get_savings_opportunities_controller,
    get_spending_anomalies_controller,
    get_spending_patterns_controller,
    list_savings_goals_controller,
    mark_notification_as_read_controller,
    update_savings_goal_controller,
    get_unread_notification_count_controller,
)
from schemas.financial_advisor import (
    AnomalyResponse,
    FinancialHealthScoreResponse,
    HealthScoreHistory,
    ImprovementRoadmapResponse,
    NotificationMarkReadRequest,
    NotificationResponse,
    PersonalizedAdviceResponse,
    RecommendationResponse,
    RecurringExpenseResponse,
    SavingsGoalCreate,
    SavingsGoalResponse,
    SavingsGoalUpdate,
    SavingsOpportunitiesResponse,
    SpendingPatternResponse,
)

financial_advisor_router = APIRouter(prefix="/advisor", tags=["Financial Advisor"])

financial_advisor_router.add_api_route(
    "/goals",
    endpoint=create_savings_goal_controller,
    methods=["POST"],
    response_model=SavingsGoalResponse,
    summary="Create a savings goal",
)

financial_advisor_router.add_api_route(
    "/goals",
    endpoint=list_savings_goals_controller,
    methods=["GET"],
    response_model=dict,
    summary="List savings goals",
)

financial_advisor_router.add_api_route(
    "/goals/{goal_id}",
    endpoint=get_savings_goal_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get details for a savings goal",
)

financial_advisor_router.add_api_route(
    "/goals/{goal_id}",
    endpoint=update_savings_goal_controller,
    methods=["PUT"],
    response_model=SavingsGoalResponse,
    summary="Update a savings goal",
)

financial_advisor_router.add_api_route(
    "/goals/{goal_id}",
    endpoint=delete_savings_goal_controller,
    methods=["DELETE"],
    response_model=dict,
    summary="Delete a savings goal",
)

financial_advisor_router.add_api_route(
    "/goals/recommendations/ai",
    endpoint=get_ai_recommended_goals_controller,
    methods=["GET"],
    response_model=list[SavingsGoalResponse],
    summary="Get AI-recommended goals",
)

financial_advisor_router.add_api_route(
    "/goals/{goal_id}/allocate",
    endpoint=allocate_to_goal_controller,
    methods=["POST"],
    response_model=SavingsGoalResponse,
    summary="Allocate funds to a goal",
)

financial_advisor_router.add_api_route(
    "/health-score",
    endpoint=get_current_health_score_controller,
    methods=["GET"],
    response_model=FinancialHealthScoreResponse,
    summary="Get current financial health score",
)

financial_advisor_router.add_api_route(
    "/health-score/history",
    endpoint=get_health_score_history_controller,
    methods=["GET"],
    response_model=HealthScoreHistory,
    summary="Get financial health score history",
)

financial_advisor_router.add_api_route(
    "/roadmap",
    endpoint=get_improvement_roadmap_controller,
    methods=["GET"],
    response_model=ImprovementRoadmapResponse,
    summary="Get improvement roadmap",
)

financial_advisor_router.add_api_route(
    "/patterns",
    endpoint=get_spending_patterns_controller,
    methods=["GET"],
    response_model=list[SpendingPatternResponse],
    summary="Get spending patterns",
)

financial_advisor_router.add_api_route(
    "/patterns/recurring",
    endpoint=get_recurring_expenses_controller,
    methods=["GET"],
    response_model=list[RecurringExpenseResponse],
    summary="Get recurring expenses",
)

financial_advisor_router.add_api_route(
    "/patterns/anomalies",
    endpoint=get_spending_anomalies_controller,
    methods=["GET"],
    response_model=list[AnomalyResponse],
    summary="Get spending anomalies",
)

financial_advisor_router.add_api_route(
    "/advice",
    endpoint=get_personalized_advice_controller,
    methods=["GET"],
    response_model=PersonalizedAdviceResponse,
    summary="Get personalized advice",
)

financial_advisor_router.add_api_route(
    "/recommendations",
    endpoint=get_category_recommendations_controller,
    methods=["GET"],
    response_model=list[RecommendationResponse],
    summary="Get category recommendations",
)

financial_advisor_router.add_api_route(
    "/opportunities",
    endpoint=get_savings_opportunities_controller,
    methods=["GET"],
    response_model=SavingsOpportunitiesResponse,
    summary="Get savings opportunities",
)

financial_advisor_router.add_api_route(
    "/notifications",
    endpoint=get_notifications_controller,
    methods=["GET"],
    response_model=dict,
    summary="List notifications",
)

financial_advisor_router.add_api_route(
    "/notifications/{notification_id}/read",
    endpoint=mark_notification_as_read_controller,
    methods=["PATCH"],
    response_model=NotificationResponse,
    summary="Mark notification as read",
)

financial_advisor_router.add_api_route(
    "/notifications/unread-count",
    endpoint=get_unread_notification_count_controller,
    methods=["GET"],
    response_model=dict,
    summary="Get unread notification count",
)

financial_advisor_router.add_api_route(
    "/capacity",
    endpoint=get_savings_capacity_controller,
    methods=["GET"],
    response_model=dict,
    summary="Analyze savings capacity",
)

