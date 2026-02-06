"""
Centralized enumerations for the savings system.
Following Showroom360 pattern for enum organization.
"""
from enum import Enum


# ============================================================================
# USER & ROLE ENUMS
# ============================================================================

class Role(str, Enum):
    """User role definitions"""
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    AGENT = "agent"
    SUB_AGENT = "sub_agent"
    CUSTOMER = "customer"
    COOPERATIVE_MEMBER = "cooperative_member"


class Permission(str, Enum):
    """Permission definitions for RBAC"""
    # Super Admin Permissions (User Management Only)
    MANAGE_USERS = "manage_users"
    CREATE_ADMIN = "create_admin"
    DEACTIVATE_USERS = "deactivate_users"
    DELETE_USERS = "delete_users"
    VIEW_ADMIN_CREDENTIALS = "view_admin_credentials"
    ASSIGN_ADMIN = "assign_admin"
    
    # Admin Permissions (Business-scoped)
    APPROVE_PAYMENTS = "approve_payments"
    REJECT_PAYMENTS = "reject_payments"
    MANAGE_BUSINESS = "manage_business"
    VIEW_BUSINESS_ANALYTICS = "view_business_analytics"
    
    # Agent Permissions
    CREATE_AGENT = "create_agent"
    CREATE_SUB_AGENT = "create_sub_agent"
    CREATE_BUSINESS = "create_business"
    ASSIGN_BUSINESS = "assign_business"
    CREATE_CUSTOMER = "create_customer"
    
    # Operational Permissions
    CREATE_SAVINGS = "create_savings"
    REINITIATE_SAVINGS = "reinitiate_savings"
    UPDATE_SAVINGS = "update_savings"
    MARK_SAVINGS = "mark_savings"
    MARK_SAVINGS_BULK = "mark_savings_bulk"
    
    # User Permissions
    VIEW_OWN_CONTRIBUTIONS = "view_own_contributions"
    
    # Wildcard
    ALL = "*"


class Resource(str, Enum):
    """Resource types for permission system"""
    USERS = "users"
    BUSINESSES = "businesses"
    SAVINGS = "savings"
    EXPENSES = "expenses"
    PAYMENTS = "payments"
    COMMISSIONS = "commissions"
    UNITS = "units"
    REPORTS = "reports"
    SETTINGS = "settings"
    NOTIFICATIONS = "notifications"
    ALL = "*"


class Action(str, Enum):
    """Action types for permission system"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    REJECT = "reject"
    MARK = "mark"
    EXPORT = "export"
    INVITE = "invite"
    ASSIGN = "assign"
    ALL = "*"


# ============================================================================
# SAVINGS ENUMS
# ============================================================================

class SavingsType(str, Enum):
    """Types of savings accounts"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TARGET = "target"


class SavingsStatus(str, Enum):
    """Status of savings accounts"""
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    PAID = "paid"


class MarkingStatus(str, Enum):
    """Status of individual savings markings"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    PAID = "paid"


class PaymentMethod(str, Enum):
    """Methods of payment/deposit"""
    CASH = "cash"
    TRANSFER = "transfer"
    CARD = "card"
    MOBILE_MONEY = "mobile_money"


# ============================================================================
# EXPENSE ENUMS
# ============================================================================

class IncomeType(str, Enum):
    """Types of income sources for expense cards"""
    SALARY = "salary"
    BUSINESS = "business"
    SAVINGS = "savings"
    PLANNER = "planner"
    OTHER = "other"


class CardStatus(str, Enum):
    """Status of expense cards"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMPLETED = "completed"
    DRAFT = "draft"


class ExpenseCategory(str, Enum):
    """Categories for expenses"""
    FOOD = "food"
    TRANSPORT = "transport"
    UTILITIES = "utilities"
    ENTERTAINMENT = "entertainment"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    SHOPPING = "shopping"
    HOUSING = "housing"
    DEBT = "debt"
    SAVINGS = "savings"
    OTHER = "other"


# ============================================================================
# PAYMENT ENUMS
# ============================================================================

class PaymentRequestStatus(str, Enum):
    """Status of payment requests"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ============================================================================
# NOTIFICATION ENUMS
# ============================================================================

class NotificationMethod(str, Enum):
    """Notification delivery methods"""
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    BOTH = "both"
    ALL = "all"

