"""
Repository package for database operations.
Following Repository Pattern for clean separation of data access logic.
"""
from .base import BaseRepository
from .user import UserRepository
from .business import BusinessRepository, UnitRepository
from .permissions import PermissionRepository
from .settings import SettingsRepository

# Specialized repositories
from .user_business import UserBusinessRepository
from .savings import SavingsRepository
from .payments import PaymentsRepository

__all__ = [
    "BaseRepository",
    "UserRepository",
    "BusinessRepository",
    "UnitRepository",
    "PermissionRepository",
    "SettingsRepository",
    "UserBusinessRepository",
    "SavingsRepository",
    "PaymentsRepository",
]

