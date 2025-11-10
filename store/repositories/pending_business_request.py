"""
Repository for PendingBusinessRequest model.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.business import PendingBusinessRequest
from store.repositories.base import BaseRepository


class PendingBusinessRequestRepository(BaseRepository[PendingBusinessRequest]):
    """Repository for managing pending business invitations."""

    def __init__(self, db: Session):
        super().__init__(PendingBusinessRequest, db)

    def get_by_token(self, token: str) -> Optional[PendingBusinessRequest]:
        """Fetch a pending request by invitation token."""
        return self.find_one_by(token=token)

    def create_request(
        self,
        *,
        customer_id: int,
        business_id: int,
        unit_id: Optional[int],
        token: str,
        expires_at: datetime,
    ) -> PendingBusinessRequest:
        """Create a new pending business request invitation."""
        request = PendingBusinessRequest(
            customer_id=customer_id,
            business_id=business_id,
            unit_id=unit_id,
            token=token,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(request)
        self.db.flush()
        return request

    def delete_request(self, pending_request: PendingBusinessRequest) -> None:
        """Remove a pending business invitation."""
        self.db.delete(pending_request)
        self.db.flush()

