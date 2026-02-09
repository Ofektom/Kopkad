from typing import List, Optional
from sqlalchemy.orm import Session
from models.savings_group import SavingsGroup
from models.savings import SavingsAccount, SavingsType
from store.repositories.base import BaseRepository
from datetime import datetime, timezone

class SavingsGroupRepository(BaseRepository[SavingsGroup]):
    def __init__(self, db: Session):
        super().__init__(db, SavingsGroup)

    def create_group(self, group_data: dict) -> SavingsGroup:
        group = SavingsGroup(**group_data)
        # created_at and is_active defaults are handled by model columns/AuditMixin
        # But wait, create_group in BaseRepository handles add/commit usually.
        # Let's check BaseRepository. Assuming standard implementation.
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group
    
    def get_by_business(self, business_id: int, skip: int = 0, limit: int = 100) -> List[SavingsGroup]:
        return self.db.query(SavingsGroup).filter(
            SavingsGroup.business_id == business_id,
            SavingsGroup.is_active == 1
        ).offset(skip).limit(limit).all()

    def get_active_group(self, group_id: int) -> Optional[SavingsGroup]:
        return self.db.query(SavingsGroup).filter(
            SavingsGroup.id == group_id,
            SavingsGroup.is_active == 1
        ).first()

    def get_members(self, group_id: int, skip: int = 0, limit: int = 100) -> List[SavingsAccount]:
        return self.db.query(SavingsAccount).filter(
            SavingsAccount.group_id == group_id
        ).offset(skip).limit(limit).all()
        
    def add_member(self, group: SavingsGroup, user_id: int, tracking_number: str) -> SavingsAccount:
        # Create SavingsAccount linked to group
        # Defaults: duration matches group? Or open-ended?
        # Usually cooperative is indefinite until user leaves or group dissolves?
        # Or fixed duration?
        # Let's assume duration is 12 months default or group end_date - start_date
        
        duration_months = 12
        if group.end_date:
            delta = group.end_date - group.start_date
            duration_months = delta.days // 30
            
        account = SavingsAccount(
            customer_id=user_id,
            business_id=group.business_id,
            group_id=group.id,
            tracking_number=tracking_number,
            savings_type=SavingsType.COOPERATIVE,
            daily_amount=group.contribution_amount, # Reused as contribution amount
            duration_months=duration_months,
            start_date=group.start_date, # Or today? Usually align with group cycle
            # Maybe use today if joining late? But let's stick to group specs
            # Actually, `start_date` in SavingsAccount usually means when savings starts.
            target_amount=0, # Cooperative builds up, no fixed target usually? Or target = contribution * duration
            commission_amount=0,
            # created_by etc handled by AuditMixin if context is right, or passed explicitly?
            # AuditMixin needs context or manual set. `service` layer usually handles user context.
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account
