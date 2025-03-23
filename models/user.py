from sqlalchemy import Column, Integer, String, Boolean, Enum, Table, ForeignKey
from sqlalchemy.orm import relationship
from database.postgres import Base
from models.audit import AuditMixin

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
    ASSIGN_BUSINESS = "assign_business"
    CREATE_CUSTOMER = "create_customer"  # New permission

# Define the user_permissions table with the updated Enum
user_permissions = Table(
    "user_permissions",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("permission", Enum(
        Permission.CREATE_ADMIN,
        Permission.CREATE_AGENT,
        Permission.CREATE_SUB_AGENT,
        Permission.ASSIGN_BUSINESS,
        Permission.CREATE_CUSTOMER,  # Add new permission here
        name="permission"
    ), nullable=False, primary_key=True)
)

class User(Base, AuditMixin):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    full_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    email = Column(String, unique=True, nullable=True)
    username = Column(String(50), unique=True, nullable=False)
    location = Column(String, nullable=True)
    pin = Column(String, nullable=False)
    role = Column(Enum(Role.SUPER_ADMIN, Role.ADMIN, Role.AGENT, Role.SUB_AGENT, Role.CUSTOMER, name="role"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=True)
    businesses = relationship("Business", secondary="user_business", back_populates="users")
    settings = relationship("Settings", uselist=False, back_populates="user", foreign_keys="Settings.user_id")
    
    @property
    def permissions(self):
        from sqlalchemy import select
        stmt = select(user_permissions.c.permission).where(user_permissions.c.user_id == self.id)
        return [row[0] for row in self._sa_instance_state.session.execute(stmt).fetchall()] if self.id else []
