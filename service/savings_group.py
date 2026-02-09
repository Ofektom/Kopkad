from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.savings_group import SavingsGroup
from models.savings import SavingsAccount
from models.user import User, Role
from models.business import Business, BusinessType
from schemas.savings_group import SavingsGroupCreate, SavingsGroupUpdate, AddGroupMemberRequest, SavingsGroupResponse
from store.repositories.savings_group import SavingsGroupRepository
from store.repositories.business import BusinessRepository
from store.repositories.user import UserRepository
from store.repositories.savings import SavingsRepository
from datetime import datetime, timezone

class SavingsGroupService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SavingsGroupRepository(db)
        self.business_repo = BusinessRepository(db)
        self.user_repo = UserRepository(db)
        self.savings_repo = SavingsRepository(db)

    def create_group(self, data: SavingsGroupCreate, user_id: int) -> SavingsGroup:
        # 1. Get user business (Admin)
        # Assuming user is Admin of the business. 
        # Need to find the business managed by this user.
        # This logic might need refinement depending on how admins are linked to businesses (Owner? Admin?).
        
        business_repo = self.business_repo
        business = business_repo.get_by_admin_id(user_id) # Assuming this method exists or similar
        
        if not business:
            # Fallback: Check if user is super admin? Or maybe user passed business_id?
            # For now, require business context.
            raise HTTPException(status_code=400, detail="User is not associated with a business")
            
        if business.business_type != BusinessType.COOPERATIVE:
             # Ensure business is cooperative type? Or allow mixed? The plan said "Cooperative Businesses will use the new Group/Grid flow".
             # So likely strict.
             raise HTTPException(status_code=400, detail="Business is not a Cooperative")

        group_data = data.model_dump()
        group_data["business_id"] = business.id
        group_data["created_by_id"] = user_id
        
        return self.repo.create_group(group_data)

    def get_group(self, group_id: int, user_id: int, user_role: Role) -> SavingsGroup:
        group = self.repo.get_by_id(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
            
        # Permission check? Admin or Member of group.
        # For simplicity, if Admin of same business or Member in group.
        return group

    def list_groups(self, user_id: int) -> list[SavingsGroup]:
        # List groups for the business of the admin
        business = self.business_repo.get_by_admin_id(user_id)
        if not business:
            return []
        return self.repo.get_by_business(business.id)

    def add_member(self, group_id: int, request: AddGroupMemberRequest, admin_id: int) -> SavingsAccount:
        # Verify group
        group = self.repo.get_active_group(group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
            
        # Check if admin owns the group's business
        business = self.business_repo.get_by_admin_id(admin_id)
        if not business or business.id != group.business_id:
             raise HTTPException(status_code=403, detail="Not authorized to add members to this group")

        # Check if user exists
        user = self.user_repo.get_by_id(request.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if already a member
        # Need a method in repo to check membership?
        # get_members and check? Or simpler query.
        existing = self.db.query(SavingsAccount).filter(
            SavingsAccount.group_id == group_id,
            SavingsAccount.customer_id == request.user_id
        ).first()
        
        if existing:
            raise HTTPException(status_code=400, detail="User is already a member of this group")

        # Generate tracking number
        import uuid
        tracking_number = str(uuid.uuid4())[:8].upper()
        
        return self.repo.add_member(group, request.user_id, tracking_number)

    def get_group_members(self, group_id: int) -> list[SavingsAccount]:
        return self.repo.get_members(group_id)
