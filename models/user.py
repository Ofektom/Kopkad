from sqlalchemy import Column, Integer, String, Boolean, Enum, Table, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import select, func
from database.postgres_optimized import Base
from models.audit import AuditMixin
from models.user_business import user_business
import datetime

class Role:
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    AGENT = "agent"
    SUB_AGENT = "sub_agent"
    CUSTOMER = "customer"
    COOPERATIVE_MEMBER = "cooperative_member"

class Permission:
    # Super Admin Permissions (User Management Only)
    MANAGE_USERS = "manage_users"
    CREATE_ADMIN = "create_admin"
    DEACTIVATE_USERS = "deactivate_users"
    DELETE_USERS = "delete_users"
    VIEW_ADMIN_CREDENTIALS = "view_admin_credentials"
    ASSIGN_ADMIN = "assign_admin"
    
    # Admin Permissions (Business-scoped via BusinessPermission table)
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
    
    # Cooperative and Member Permissions
    VIEW_OWN_CONTRIBUTIONS = "view_own_contributions"

user_permissions = Table(
    "user_permissions",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission",
        Enum(
            Permission.CREATE_ADMIN,
            Permission.CREATE_AGENT,
            Permission.CREATE_SUB_AGENT,
            Permission.CREATE_BUSINESS,
            Permission.ASSIGN_BUSINESS,
            Permission.CREATE_CUSTOMER,
            Permission.CREATE_SAVINGS,
            Permission.REINITIATE_SAVINGS,
            Permission.UPDATE_SAVINGS,
            Permission.MARK_SAVINGS,
            Permission.MARK_SAVINGS_BULK,
            Permission.VIEW_OWN_CONTRIBUTIONS,
            name="permission",
        ),
        nullable=False,
        primary_key=True,
    ),
)

class User(AuditMixin, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    email = Column(String, unique=True, nullable=True)
    username = Column(String(50), unique=True, nullable=False)
    pin = Column(String(255), nullable=False)
    payment_provider_customer_id = Column(String(255), nullable=True)
    role = Column(
        Enum(
            Role.SUPER_ADMIN,
            Role.ADMIN,
            Role.AGENT,
            Role.SUB_AGENT,
            Role.SUB_AGENT,
            Role.CUSTOMER,
            Role.COOPERATIVE_MEMBER,
            name="role",
        ),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=True)
    token_version = Column(Integer, nullable=False, default=1)
    active_business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    businesses = relationship(
        "Business", secondary=user_business, back_populates="users"
    )
    active_business = relationship("Business", foreign_keys=[active_business_id])
    payment_accounts = relationship(
        "PaymentAccount", 
        back_populates="customer",
        foreign_keys="PaymentAccount.customer_id"
    )
    settings = relationship(
        "Settings",
        uselist=False,
        back_populates="user",
        foreign_keys="Settings.user_id",
    )
    payment_initiations = relationship("PaymentInitiation", back_populates="user")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    @property
    def permissions(self):
        stmt = select(user_permissions.c.permission).where(
            user_permissions.c.user_id == self.id
        )
        return (
            [row[0] for row in self._sa_instance_state.session.execute(stmt).fetchall()]
            if self.id
            else []
        )

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="password_reset_tokens")



class PasswordResetOtp(Base):
    __tablename__ = "password_reset_otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    otp_hash = Column(String(255), nullable=False)           # hashed OTP
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def is_valid(self):
        return not self.is_used and self.expires_at > datetime.datetime.now(datetime.timezone.utc)