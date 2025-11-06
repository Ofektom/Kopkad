"""
Dependency injection utilities for FastAPI.
Following Showroom360 pattern for repository injection.
"""
from typing import Callable, Type, TypeVar
from sqlalchemy.orm import Session
from fastapi import Depends

from store.repositories.base import BaseRepository
from database.postgres_optimized import get_db

T = TypeVar("T", bound=BaseRepository)


def get_repository(repository_class: Type[T]) -> Callable[[Session], T]:
    """
    Generic dependency function that creates and returns repository instances.
    Works with SQLAlchemy repositories that require a db session.

    Usage:
        @app.get("/users")
        async def get_users(
            db: Session = Depends(get_db),
            user_repo: UserRepository = Depends(get_repository(UserRepository))
        ):
            return await user_repo.get_all()

    Args:
        repository_class: The repository class to instantiate

    Returns:
        A callable dependency function that returns the repository instance
    """
    def _get_repository(db: Session = Depends(get_db)) -> T:
        return repository_class(db)

    return _get_repository

