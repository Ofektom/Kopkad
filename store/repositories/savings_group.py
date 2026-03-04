from typing import List, Optional, Tuple
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from models.savings_group import SavingsGroup, GroupFrequency
from models.savings import SavingsAccount, SavingsType, SavingsMarking, SavingsStatus
from models.business import Unit
from store.repositories.base import BaseRepository
from datetime import date
from decimal import Decimal
from dateutil.relativedelta import relativedelta


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
        unit_id: Optional[int] = None,
    ) -> SavingsAccount:
        duration_months = 12
        if group.end_date:
            delta = group.end_date - group.start_date
            duration_months = max(1, delta.days // 30)

        # Ensure unit_id is set (Cooperative is not unit-based, but DB requires it)
        if unit_id is None:
            # Try to get first unit for business as default
            unit = self.db.query(Unit).filter(Unit.business_id == group.business_id).first()
            if unit:
                unit_id = unit.id

        account = SavingsAccount(
            customer_id=user_id,
            business_id=group.business_id,
            unit_id=unit_id,
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

        current_date = start_date
        # If no end date, default to duration months
        end_date = group.end_date
        if not end_date:
             end_date = start_date + relativedelta(months=duration_months)

        markings = []
        
        while current_date <= end_date:
            marking = SavingsMarking(
                savings_account_id=account.id,
                unit_id=unit_id, 
                marked_date=current_date,
                amount=group.contribution_amount,
                status=SavingsStatus.PENDING,
            )
            markings.append(marking)

            if group.frequency == GroupFrequency.WEEKLY:
                current_date += relativedelta(weeks=1)
            elif group.frequency == GroupFrequency.BI_WEEKLY:
                current_date += relativedelta(weeks=2)
            elif group.frequency == GroupFrequency.MONTHLY:
                current_date += relativedelta(months=1)
            elif group.frequency == GroupFrequency.QUARTERLY:
                current_date += relativedelta(months=3)
            else:
                current_date += relativedelta(months=1)
        
        if markings:
            self.db.add_all(markings)
            self.db.commit()

        return account

    def delete_group(self, group_id: int) -> bool:
        group = self.get_active_group(group_id)
        if not group:
            return False

        # Check for any PAID markings in any account associated with this group
        from models.savings import SavingsMarking, SavingsStatus
        
        has_paid_markings = (
            self.db.query(SavingsMarking)
            .join(SavingsAccount)
            .filter(
                SavingsAccount.group_id == group_id,
                SavingsMarking.status == SavingsStatus.PAID
            )
            .first()
        )

        if has_paid_markings:
            raise ValueError("Cannot delete group with active (PAID) contributions.")

        accounts = self.db.query(SavingsAccount).filter(SavingsAccount.group_id == group_id).all()
        for account in accounts:
            self.db.delete(account) 
            
        self.db.delete(group)
        self.db.commit()
        return True
    
    def get_member_count(self, group_id: int) -> int:
        return (
            self.db.query(func.count(SavingsAccount.id.distinct()))
            .filter(SavingsAccount.group_id == group_id)
            .scalar() or 0
        )

    def get_groups_for_member(self, member_id: int, skip: int = 0, limit: int = 100) -> Tuple[List[SavingsGroup], int]:
        query = self.db.query(SavingsGroup).join(SavingsAccount).filter(
            SavingsAccount.customer_id == member_id,
            SavingsGroup.is_active == 1
        )

        total = query.count()
        groups = query.order_by(SavingsGroup.created_at.desc()).offset(skip).limit(limit).all()
        return groups, total
    
    def get_member_account_for_user(self, group_id: int, user_id: int) -> Optional[SavingsAccount]:
        return self.db.query(SavingsAccount).filter(
            SavingsAccount.group_id == group_id,
            SavingsAccount.customer_id == user_id
        ).first()
    
    def member_exists_in_group(self, group_id: int, user_id: int) -> bool:
        return (
            self.db.query(func.exists().where(
                SavingsAccount.group_id == group_id,
                SavingsAccount.customer_id == user_id
            )).scalar() or False
        )

    def get_all_group_accounts(self, group_id: int) -> List[SavingsAccount]:
        return self.db.query(SavingsAccount).filter(SavingsAccount.group_id == group_id).all()

    def get_business_cooperative_summary(self, business_id: int) -> dict:
        """Aggregate cooperative stats for a business: groups, members, collected amounts."""
        from models.savings import SavingsStatus

        total_active_groups = (
            self.db.query(func.count(SavingsGroup.id))
            .filter(SavingsGroup.business_id == business_id, SavingsGroup.is_active == 1)
            .scalar() or 0
        )

        total_inactive_groups = (
            self.db.query(func.count(SavingsGroup.id))
            .filter(SavingsGroup.business_id == business_id, SavingsGroup.is_active == 0)
            .scalar() or 0
        )

        # Unique members across all groups in this business
        total_members = (
            self.db.query(func.count(func.distinct(SavingsAccount.customer_id)))
            .join(SavingsGroup, SavingsGroup.id == SavingsAccount.group_id)
            .filter(SavingsGroup.business_id == business_id)
            .scalar() or 0
        )

        # Total paid (collected) across all markings for all groups in this business
        total_collected = (
            self.db.query(func.coalesce(func.sum(SavingsMarking.amount), Decimal("0")))
            .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
            .join(SavingsGroup, SavingsGroup.id == SavingsAccount.group_id)
            .filter(
                SavingsGroup.business_id == business_id,
                SavingsMarking.status == SavingsStatus.PAID,
            )
            .scalar() or Decimal("0")
        )

        # Total expected (all markings regardless of status) — pre-seeded when member joins
        total_target = (
            self.db.query(func.coalesce(func.sum(SavingsMarking.amount), Decimal("0")))
            .join(SavingsAccount, SavingsAccount.id == SavingsMarking.savings_account_id)
            .join(SavingsGroup, SavingsGroup.id == SavingsAccount.group_id)
            .filter(SavingsGroup.business_id == business_id)
            .scalar() or Decimal("0")
        )

        progress_pct = (
            float(total_collected) / float(total_target) * 100
            if total_target > 0 else 0.0
        )

        return {
            "total_active_groups": total_active_groups,
            "total_inactive_groups": total_inactive_groups,
            "total_groups": total_active_groups + total_inactive_groups,
            "total_members": total_members,
            "total_collected": float(total_collected),
            "total_target": float(total_target),
            "overall_progress_percentage": round(progress_pct, 1),
        }