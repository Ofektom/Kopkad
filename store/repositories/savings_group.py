from typing import List, Optional, Tuple
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from models.savings_group import SavingsGroup
from models.savings import SavingsAccount, SavingsType
from store.repositories.base import BaseRepository
from datetime import date


class SavingsGroupRepository(BaseRepository[SavingsGroup]):
    def __init__(self, db: Session):
        super().__init__(SavingsGroup, db)

    def create_group(self, group_data: dict) -> SavingsGroup:
        group = SavingsGroup(**group_data)
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group

    def get_groups_by_business(
        self,
        business_id: int,
        name: Optional[str] = None,
        frequency: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[SavingsGroup], int]:
        query = self.db.query(SavingsGroup).filter(SavingsGroup.business_id == business_id)

        if is_active is not None:
            query = query.filter(SavingsGroup.is_active == (1 if is_active else 0))

        if frequency:
            query = query.filter(SavingsGroup.frequency == frequency)

        if name:
            query = query.filter(SavingsGroup.name.ilike(f"%{name}%"))

        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(SavingsGroup.name).like(pattern),
                    func.lower(SavingsGroup.description).like(pattern),
                )
            )

        total = query.count()

        groups = (
            query
            .order_by(SavingsGroup.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return groups, total

    def get_active_group(self, group_id: int) -> Optional[SavingsGroup]:
        return (
            self.db.query(SavingsGroup)
            .filter(SavingsGroup.id == group_id, SavingsGroup.is_active == 1)
            .first()
        )

    def get_members(self, group_id: int, skip: int = 0, limit: int = 100) -> List[SavingsAccount]:
        return (
            self.db.query(SavingsAccount)
            .filter(SavingsAccount.group_id == group_id)
            .offset(skip)
            .limit(limit)
            .all()
        )

    def add_member(
        self,
        group: SavingsGroup,
        user_id: int,
        tracking_number: str,
        start_date: date,
    ) -> SavingsAccount:
        duration_months = 12
        if group.end_date:
            delta = group.end_date - group.start_date
            duration_months = max(1, delta.days // 30)

        account = SavingsAccount(
            customer_id=user_id,
            business_id=group.business_id,
            unit_id=None,
            group_id=group.id,
            tracking_number=tracking_number,
            savings_type=SavingsType.COOPERATIVE,
            daily_amount=group.contribution_amount,
            duration_months=duration_months,
            start_date=start_date,
            target_amount=Decimal("0"),
            commission_amount=Decimal("0"),
            commission_days=0,
            marking_status="not_started",
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account