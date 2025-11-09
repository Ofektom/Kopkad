from typing import Dict, List

from pydantic import BaseModel


class DashboardTotals(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    total_businesses: int
    total_units: int
    total_savings_accounts: int
    total_admins: int
    total_agents: int
    total_sub_agents: int
    total_customers: int
    total_payment_requests: int
    successful_payment_requests: int
    successful_transfers: int


class SavingsVolumeBreakdown(BaseModel):
    total_volume: float
    paid_volume: float
    pending_volume: float


class SavingsOverview(BaseModel):
    totals: SavingsVolumeBreakdown
    accounts_by_type: Dict[str, int]


class BusinessPerformanceMetrics(BaseModel):
    business_id: int
    name: str
    unique_code: str
    total_users: int
    total_units: int
    total_savings_accounts: int
    total_volume: float
    paid_volume: float
    pending_volume: float


class UnitCount(BaseModel):
    business_id: int
    name: str
    unique_code: str
    unit_count: int


class UnitSummary(BaseModel):
    total_units: int
    units_by_business: List[UnitCount]


class PaymentStatusMetric(BaseModel):
    status: str
    count: int
    amount: float


class PaymentSummary(BaseModel):
    total_requests: int
    status_metrics: List[PaymentStatusMetric]
    successful_payment_requests: int
    successful_payment_amount: float
    successful_transfers: int
    successful_transfer_amount: float


class ChartPoint(BaseModel):
    label: str
    value: float


class ChartSeries(BaseModel):
    id: str
    points: List[ChartPoint]


class DashboardCharts(BaseModel):
    user_growth: List[ChartSeries]
    payment_volume: List[ChartSeries]
    business_units: List[ChartSeries]
    transfer_volume: List[ChartSeries]


class DashboardAnalyticsResponse(BaseModel):
    totals: DashboardTotals
    role_breakdown: Dict[str, int]
    savings_overview: SavingsOverview
    business_performance: List[BusinessPerformanceMetrics]
    unit_summary: UnitSummary
    payment_summary: PaymentSummary
    charts: DashboardCharts


