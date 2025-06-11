from sqlalchemy import Column, Integer, String, Boolean, Enum, Table, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import select
from database.postgres import Base
from models.audit import AuditMixin
from models.user_business import user_business

class Role:
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    AGENT = "agent"
    SUB_AGENT = "sub_agent"
    CUSTOMER = "customer"

class Permission:
    CREATE_ADMIN = "create_admin"
    CREATE_AGENT = "create_agent"
    CREATE_SUB_AGENT = "create_sub_agent"
    CREATE_BUSINESS = "create_business"
    ASSIGN_BUSINESS = "assign_business"
    CREATE_CUSTOMER = "create_customer"
    CREATE_SAVINGS = "create_savings"
    REINITIATE_SAVINGS = "reinitiate_savings"
    UPDATE_SAVINGS = "update_savings"
    MARK_SAVINGS = "mark_savings"
    MARK_SAVINGS_BULK = "mark_savings_bulk"

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
    role = Column(
        Enum(
            Role.SUPER_ADMIN,
            Role.ADMIN,
            Role.AGENT,
            Role.SUB_AGENT,
            Role.CUSTOMER,
            name="role",
        ),
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=True)
    businesses = relationship(
        "Business", secondary=user_business, back_populates="users"
    )
    settings = relationship(
        "Settings",
        uselist=False,
        back_populates="user",
        foreign_keys="Settings.user_id",
    )

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