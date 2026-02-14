from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
from dateutil.relativedelta import relativedelta

from datetime import date, datetime
import uuid
import logging

from models.savings_group import SavingsGroup, GroupFrequency
from models.savings import SavingsAccount, SavingsMarking, SavingsStatus, PaymentMethod
from models.user import User


from models.business import BusinessType

from schemas.savings_group import (
    SavingsGroupCreate,
    AddGroupMemberRequest,
    SavingsGroupResponse,
    CreateSavingsGroupResponse,
    SavingsGroupMarkingPaystackInit,
)

from store.repositories.savings_group import SavingsGroupRepository
from store.repositories.savings import SavingsRepository
from store.repositories.business import BusinessRepository
from store.repositories.user import UserRepository
from utils.response import success_response, error_response
import requests

logger = logging.getLogger(__name__)

from paystackapi.transaction import Transaction
from paystackapi.paystack import Paystack
import os
from decimal import Decimal

from schemas.savings import SavingsMarkingResponse


paystack = Paystack(secret_key=os.getenv("PAYSTACK_SECRET_KEY"))


def _resolve_repo(repo, repo_cls, db: Session):
    return repo if repo is not None else repo_cls(db)


def _generate_group_grid_dates(
    start_date: date,
    frequency: GroupFrequency,
    limit: int,
    offset: int,
    end_date: Optional[date] = None
) -> List[date]:
    """
    Generate a list of dates based on frequency, handling pagination.
    """
    dates = []
    current_date = start_date
    
    # Skip to offset
    skipped = 0
    while skipped < offset:
        if end_date and current_date > end_date:
            break
            
        if frequency == GroupFrequency.WEEKLY:
            current_date += relativedelta(weeks=1)
        elif frequency == GroupFrequency.BI_WEEKLY:
            current_date += relativedelta(weeks=2)
        elif frequency == GroupFrequency.MONTHLY:
            current_date += relativedelta(months=1)
        elif frequency == GroupFrequency.QUARTERLY:
            current_date += relativedelta(months=3)
        skipped += 1

    # Collect dates up to limit
    collected = 0
    while collected < limit:
        if end_date and current_date > end_date:
            break
            
        dates.append(current_date)
        
        if frequency == GroupFrequency.WEEKLY:
            current_date += relativedelta(weeks=1)
        elif frequency == GroupFrequency.BI_WEEKLY:
            current_date += relativedelta(weeks=2)
        elif frequency == GroupFrequency.MONTHLY:
            current_date += relativedelta(months=1)
        elif frequency == GroupFrequency.QUARTERLY:
            current_date += relativedelta(months=3)
        collected += 1
        
    return dates


async def initiate_virtual_account_payment(amount: Decimal, email: str, customer_id: int, reference: str, db: Session):
    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json",
        }
        user = db.query(User).filter(User.id == customer_id).first()
        if not user:
            logger.error(f"User {customer_id} not found in database")
            return error_response(status_code=404, message="User not found")

        payment_provider_customer_id = getattr(user, 'payment_provider_customer_id', None)
        if not payment_provider_customer_id:
            customer_payload = {
                "email": email,
                "first_name": "Customer",
                "last_name": f"ID_{customer_id}",
            }
            customer_response = requests.post(
                "https://api.paystack.co/customer",
                headers=headers,
                json=customer_payload,
            )
            customer_data = customer_response.json()
            logger.info(f"Paystack customer creation response: {customer_data}")
            if customer_response.status_code != 200 or not customer_data.get("status"):
                logger.error(f"Failed to create Paystack customer: {customer_data}")
                return error_response(
                    status_code=customer_response.status_code,
                    message=f"Failed to create customer: {customer_data.get('message', 'Unknown error')}",
                )
            payment_provider_customer_id = customer_data["data"]["customer_code"]
            try:
                user.payment_provider_customer_id = payment_provider_customer_id
                db.commit()
            except AttributeError:
                logger.warning(f"User model lacks payment_provider_customer_id field; proceeding without storing")

        is_test_mode = "test" in os.getenv("PAYSTACK_SECRET_KEY", "").lower() or os.getenv("PAYSTACK_ENV", "production") == "test"
        if is_test_mode:
            logger.info(f"Running in test mode; generating mock virtual account for customer {payment_provider_customer_id}")
            virtual_account = {
                "bank": "Test Bank",
                "account_number": f"TEST{str(customer_id).zfill(10)}",
                "account_name": f"Test Account - ID_{customer_id}",
            }
            logger.info(f"Generated mock virtual account: {virtual_account}")
        else:
            dedicated_response = requests.get(
                f"https://api.paystack.co/dedicated_account?customer={payment_provider_customer_id}",
                headers=headers,
            )
            dedicated_data = dedicated_response.json()
            logger.info(f"Paystack dedicated account check response: {dedicated_data}")

            if dedicated_response.status_code == 200 and dedicated_data.get("status") and dedicated_data["data"]:
                account_data = dedicated_data["data"][0]
                virtual_account = {
                    "bank": account_data["bank"]["name"],
                    "account_number": account_data["account_number"],
                    "account_name": account_data["account_name"],
                }
                logger.info(f"Using existing dedicated account for customer {payment_provider_customer_id}: {virtual_account}")
            else:
                if dedicated_data.get("code") == "feature_unavailable":
                    logger.error(f"Dedicated NUBAN not available: {dedicated_data}")
                    return error_response(
                        status_code=400,
                        message="Virtual account payments are currently unavailable. Please contact support@paystack.com to enable this feature.",
                    )
                payload = {
                    "customer": payment_provider_customer_id,
                    "preferred_bank": "wema-bank",
                }
                response = requests.post(
                    "https://api.paystack.co/dedicated_account",
                    headers=headers,
                    json=payload,
                )
                response_data = response.json()
                logger.info(f"Paystack dedicated account creation response: {response_data}")
                if response.status_code == 200 and response_data.get("status"):
                    virtual_account = {
                        "bank": response_data["data"]["bank"]["name"],
                        "account_number": response_data["data"]["account_number"],
                        "account_name": response_data["data"]["account_name"],
                    }
                else:
                    if response_data.get("code") == "feature_unavailable":
                        logger.error(f"Dedicated NUBAN not available: {response_data}")
                        return error_response(
                            status_code=400,
                            message="Virtual account payments are currently unavailable. Please contact support@paystack.com to enable this feature.",
                        )
                    logger.error(f"Failed to create dedicated account: {response_data}")
                    return error_response(
                        status_code=response.status_code,
                        message=f"Failed to initiate virtual account: {response_data.get('message', 'Dedicated NUBAN creation failed')}",
                    )

        transaction = Transaction.initialize(
            reference=reference,
            amount=int(amount * 100),
            email=email,
            callback_url="https://kopkad-frontend.vercel.app/payment-confirmation",
        )
        logger.info(f"Paystack transaction initialize response: {transaction}")
        if not transaction["status"]:
            logger.error(f"Failed to initialize transaction: {transaction}")
            return error_response(
                status_code=500,
                message=f"Failed to initialize transaction: {transaction.get('message', 'Unknown error')}",
            )

        return virtual_account
    except Exception as e:
        logger.error(f"Error initiating virtual account: {str(e)}", exc_info=True)
        return error_response(status_code=500, message=f"Error initiating virtual account: {str(e)}")


async def create_group(
    request: SavingsGroupCreate,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
    user_repo: Optional[UserRepository] = None,
    savings_repo: Optional[SavingsRepository] = None,
) -> CreateSavingsGroupResponse:
    logger.info("[SERVICE] create_group called")
    logger.info(f"[SERVICE] Received request data: {request.model_dump_json(indent=2)}")
    logger.info(f"[SERVICE] Current user: role={current_user.get('role')}, id={current_user.get('user_id')}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent"]:
        logger.warning(f"[SERVICE] Unauthorized role attempt: {role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins, super admins or agents can create savings groups"
        )

    business = business_repo.get_by_admin_id(user_id) or business_repo.get_by_agent_id(user_id)
    if not business:
        logger.warning(f"[SERVICE] No business found for user {user_id}")
        raise HTTPException(status_code=400, detail="User is not associated with any business")

    if business.business_type != BusinessType.COOPERATIVE:
        logger.warning(f"[SERVICE] Business type is not COOPERATIVE: {business.business_type}")
        raise HTTPException(status_code=400, detail="Only cooperative businesses can create savings groups")

    member_ids = request.member_ids or []
    duration_months = request.duration_months

    group_data = request.model_dump(exclude={"member_ids", "duration_months"})
    group_data["business_id"] = business.id
    group_data["created_by_id"] = user_id

    if duration_months:
        group_data["end_date"] = group_data["start_date"] + relativedelta(months=duration_months)
    # If no duration_months, end_date remains null (open-ended)

    logger.info(f"[SERVICE] Creating group with data: {group_data}")

    group = group_repo.create_group(group_data)
    logger.info(f"[SERVICE] Group created - ID: {group.id}, frequency: {group.frequency.value}")

    created_accounts = []
    for member_id in member_ids:
        try:
            req = AddGroupMemberRequest(user_id=member_id, start_date=group.start_date)
            logger.info(f"[SERVICE] Attempting to add member {member_id} to group {group.id}")
            account = await add_member_to_group(
                group_id=group.id,
                request=req,
                current_user=current_user,
                db=db,
                group_repo=group_repo,
                business_repo=business_repo,
                user_repo=user_repo,
                savings_repo=savings_repo,
            )
            created_accounts.append(account)
            logger.info(f"[SERVICE] Successfully added member {member_id}")
        except Exception as e:
            logger.warning(f"[SERVICE] Failed to add member {member_id} to group {group.id}: {str(e)}")
            continue

    response = CreateSavingsGroupResponse(
        message="Savings group created successfully",
        group=SavingsGroupResponse.from_orm(group),
        created_members_count=len(created_accounts)
    )
    logger.info(f"[SERVICE] Returning response: {response.model_dump_json(indent=2)}")

    return response


async def list_groups(
    current_user: dict,
    db: Session,
    name: Optional[str] = None,
    frequency: Optional[str] = None,
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
) -> dict:
    logger.info(f"[SERVICE] list_groups called - params: limit={limit}, offset={offset}, frequency={frequency}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent", "customer"]:
        logger.warning(f"[SERVICE] Unauthorized list attempt - role: {role}")
        raise HTTPException(status_code=403, detail="Not authorized to list savings groups")

    if role == "customer":
        # Customers can only see groups they are members of
        groups, total_count = group_repo.get_groups_for_member(
            member_id=user_id,
            limit=limit,
            skip=offset
        )
    else:
        # Admins/Agents see all groups for the business
        business = business_repo.get_by_admin_id(user_id) or business_repo.get_by_agent_id(user_id)
        if not business:
            logger.info(f"[SERVICE] No business found for user {user_id}")
            return {
                "groups": [],
                "total_count": 0,
                "limit": limit,
                "offset": offset,
                "message": "No business associated with user"
            }

        logger.info(f"[SERVICE] Listing groups for business {business.id}")

        groups, total_count = group_repo.get_groups_by_business(
            business_id=business.id,
            name=name,
            frequency=frequency,
            is_active=is_active,
            search=search,
            skip=offset,
            limit=limit,
        )

    response_data = []
    
    for group in groups:
        group_resp = SavingsGroupResponse.from_orm(group)
        
        member_account = None
        member_account = db.query(SavingsAccount).filter(
            SavingsAccount.group_id == group.id,
            SavingsAccount.customer_id == user_id
        ).first()

        if member_account:
            group_resp.user_relationship = {
                "tracking_number": member_account.tracking_number,
                "savings_account_id": member_account.id,
                "status": "active" # or check account status
            }
            
        response_data.append(group_resp)

    result = {
        "groups": response_data,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "message": f"Retrieved {len(response_data)} of {total_count} savings groups"
    }
    logger.info(f"[SERVICE] Returning {len(response_data)} groups")
    return result


async def get_group(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
) -> SavingsGroupResponse:
    logger.info(f"[SERVICE] get_group - group_id: {group_id}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)

    group = group_repo.get_active_group(group_id)
    if not group:
        logger.warning(f"[SERVICE] Group {group_id} not found or inactive")
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    return SavingsGroupResponse.from_orm(group)


async def add_member_to_group(
    group_id: int,
    request: AddGroupMemberRequest,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
    user_repo: Optional[UserRepository] = None,
    savings_repo: Optional[SavingsRepository] = None,
) -> SavingsAccount:
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)
    user_repo = _resolve_repo(user_repo, UserRepository, db)

    user_id = current_user["user_id"]
    role = current_user["role"]

    if role not in ["admin", "super_admin", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to add members")

    group = group_repo.get_active_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    business = business_repo.get_by_agent_id(user_id) or business_repo.get_by_admin_id(user_id)
    if not business or business.id != group.business_id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this group")

    user = user_repo.get_by_id(request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Allow both CUSTOMER and AGENT roles to join savings groups
    allowed_roles = ["customer", "agent"]
    if user.role.lower() not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Only customers and agents can join savings groups (user role: {user.role})"
        )

    # Optional: ensure the user is associated with the same business (extra safety)
    # If your user_business table or business.agent_id already enforces this, skip
    user_businesses = business_repo.get_user_businesses_with_units(user.id)  # or your method
    if not any(b.id == group.business_id for b in user_businesses):
        raise HTTPException(status_code=403, detail="User does not belong to this cooperative")

    existing = db.query(SavingsAccount).filter(
        SavingsAccount.group_id == group_id,
        SavingsAccount.customer_id == request.user_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this group")

    tracking_number = str(uuid.uuid4())[:10].upper()

    start_date = request.start_date or group.start_date

    account = group_repo.add_member(
        group=group,
        user_id=request.user_id,
        tracking_number=tracking_number,
        start_date=start_date,
    )

    return account


async def get_group_members(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
) -> List[dict]:
    logger.info(f"[SERVICE] get_group_members - group_id: {group_id}")

    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)

    group = group_repo.get_active_group(group_id)
    if not group:
        logger.warning(f"[SERVICE] Group {group_id} not found or inactive")
        raise HTTPException(status_code=404, detail="Group not found or inactive")

    members = group_repo.get_members(group_id)

    result = [
        {
            "user_id": m.customer_id,
            "savings_account_id": m.id,
            "tracking_number": m.tracking_number,
            "joined_at": m.created_at,
            "status": "active"
        }
        for m in members
    ]

    logger.info(f"[SERVICE] Returning {len(result)} members for group {group_id}")
    return result


async def delete_group_service(
    group_id: int,
    current_user: dict,
    db: Session,
    *,
    group_repo: Optional[SavingsGroupRepository] = None,
    business_repo: Optional[BusinessRepository] = None,
) -> bool:
    logger.info(f"[SERVICE] delete_group_service called for group {group_id}")
    
    group_repo = _resolve_repo(group_repo, SavingsGroupRepository, db)
    business_repo = _resolve_repo(business_repo, BusinessRepository, db)

    # Check authorization
    if current_user["role"] not in ["admin", "super_admin", "agent"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete groups")

    group = group_repo.get_active_group(group_id)
    if not group:
         raise HTTPException(status_code=404, detail="Group not found")

    # Verify ownership/business association
    if current_user["role"] == "agent":
         business = business_repo.get_by_agent_id(current_user["user_id"])
         if not business or business.id != group.business_id:
              raise HTTPException(status_code=403, detail="Group does not belong to your business")

    try:
        group_repo.delete_group(group_id)
        logger.info(f"[SERVICE] Group {group_id} deleted successfully")
        return True
    except ValueError as e:
        logger.warning(f"[SERVICE] Cannot delete group {group_id}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SERVICE] Error deleting group {group_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during deletion")


async def get_group_grid_data(
    group_id: int,
    db: Session,
    date_page: int = 1,
    date_limit: int = 10
) -> Dict[str, Any]:
    """
    Fetch grid data: Members x Dates matrix.
    """
    group = db.query(SavingsGroup).filter(SavingsGroup.id == group_id).first()
    if not group:
        logger.warning(f"Group {group_id} not found")
        return None

    offset = (date_page - 1) * date_limit
    projection_end_date = group.end_date or (group.start_date + relativedelta(years=1))
    
    dates = _generate_group_grid_dates(
        start_date=group.start_date,
        frequency=group.frequency,
        limit=date_limit,
        offset=offset,
        end_date=projection_end_date
    )
    
    total_dates_approx = 0
    temp_date = group.start_date
    while temp_date <= projection_end_date:
        total_dates_approx += 1
        if group.frequency == GroupFrequency.WEEKLY:
            temp_date += relativedelta(weeks=1)
        elif group.frequency == GroupFrequency.BI_WEEKLY:
            temp_date += relativedelta(weeks=2)
        elif group.frequency == GroupFrequency.MONTHLY:
            temp_date += relativedelta(months=1)
        elif group.frequency == GroupFrequency.QUARTERLY:
            temp_date += relativedelta(months=3)
            
    has_next_page = (offset + len(dates)) < total_dates_approx

    savings_accounts = db.query(SavingsAccount).join(User, SavingsAccount.customer_id == User.id)\
        .filter(SavingsAccount.group_id == group_id)\
        .all()
        
    members_data = []
    markings_map = {}

    if dates:
        start_range = dates[0]
        end_range = dates[-1]

        account_ids = [acc.id for acc in savings_accounts]
        
        if account_ids:
            markings = db.query(SavingsMarking)\
                .filter(
                    SavingsMarking.savings_account_id.in_(account_ids),
                    SavingsMarking.marked_date >= start_range,
                    SavingsMarking.marked_date <= end_range
                ).all()
                
            for marking in markings:
                acc = next((a for a in savings_accounts if a.id == marking.savings_account_id), None)
                if acc:
                    if acc.tracking_number not in markings_map:
                        markings_map[acc.tracking_number] = {}
                    markings_map[acc.tracking_number][str(marking.marked_date)] = marking.status.value

    # SAFE full_name handling - adapt to your actual User model
    for acc in savings_accounts:
        user = db.query(User).filter(User.id == acc.customer_id).first()
        
        full_name = "Unknown User"
        if user:
            # Option 1: most common - use full_name
            if hasattr(user, 'full_name') and user.full_name and user.full_name.strip():
                full_name = user.full_name.strip()
            # Option 2: fallback to name if exists
            elif hasattr(user, 'name') and user.name and user.name.strip():
                full_name = user.name.strip()
            # Option 3: username/email/id
            else:
                full_name = (
                    user.username or
                    user.email or
                    f"User {user.id}"
                )

        members_data.append({
            "user_id": acc.customer_id,
            "full_name": full_name,
            "tracking_number": acc.tracking_number,
            "savings_account_id": acc.id
        })
        
        if acc.tracking_number not in markings_map:
            markings_map[acc.tracking_number] = {}

    return {
        "group_name": group.name,
        "contribution_amount": group.contribution_amount,
        "members": members_data,
        "dates": [d.isoformat() for d in dates],
        "markings": markings_map,
        "pagination": {
            "current_page": date_page,
            "limit": date_limit,
            "has_next": has_next_page,
            "total_dates_approx": total_dates_approx
        }
    }


async def initiate_group_marking_payment(
    group_id: int,
    request: SavingsGroupMarkingPaystackInit,
    current_user: dict,
    db: Session,
):
    """
    Initiate Paystack payment for group markings (replicates mark_savings_payment logic)
    """
    # 1. Authorization
    if current_user["role"] not in ["agent", "admin", "super_admin"]:
        raise HTTPException(403, "Only agents/admins can mark group contributions")

    # 2. Validate markings
    if not request.markings:
        raise HTTPException(400, "No markings provided")

    total_amount = Decimal("0")
    markings_to_update = []
    affected_accounts = {}

    for m in request.markings:
        account = db.query(SavingsAccount).filter(
            SavingsAccount.id == m.savings_account_id,
            SavingsAccount.group_id == group_id
        ).first()
        if not account:
            raise HTTPException(404, f"Savings account {m.savings_account_id} not in group")

        marking = db.query(SavingsMarking).filter(
            SavingsMarking.savings_account_id == account.id,
            SavingsMarking.marked_date == m.date
        ).first()
        if not marking or marking.status != SavingsStatus.PENDING:
            raise HTTPException(400, f"Date {m.date} invalid or already marked")

        total_amount += marking.amount
        affected_accounts[account.id] = account
        markings_to_update.append(marking)

    if total_amount <= 0:
        raise HTTPException(400, "No amount to pay")

    # 3. Payer info (agent/admin paying)
    payer = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not payer or not payer.email:
        raise HTTPException(400, "Payer email required for payment")

    reference = f"grp_{group_id}_{uuid.uuid4().hex[:8]}"

    # 4. Paystack initialization (exact same as savings.py)
    if request.payment_method == PaymentMethod.CARD:
        total_amount_kobo = int(total_amount * 100)
        resp = Transaction.initialize(
            reference=reference,
            amount=total_amount_kobo,
            email=payer.email,
            callback_url="https://kopkad-frontend.vercel.app/payment-confirmation"
        )
        if not resp["status"]:
            raise HTTPException(500, f"Paystack init failed: {resp.get('message')}")

        # Store reference
        for marking in markings_to_update:
            marking.payment_reference = resp["data"]["reference"]
            marking.payment_method = PaymentMethod.CARD
            marking.status = SavingsStatus.PENDING
        db.commit()

        return success_response(
            status_code=200,
            message="Proceed to payment",
            data=SavingsMarkingResponse(
                tracking_number="group_" + str(group_id),  # placeholder, can be improved
                unit_id=None,  # group-level, no unit
                savings_schedule={},  # not returning full schedule here
                total_amount=float(total_amount),
                authorization_url=resp["data"]["authorization_url"],
                payment_reference=resp["data"]["reference"],
                virtual_account=None
            ).model_dump()
        )

    elif request.payment_method == PaymentMethod.BANK_TRANSFER:
        virtual_account = await initiate_virtual_account_payment(
            amount=total_amount,
            email=payer.email,
            customer_id=payer.id,
            reference=reference,
            db=db
        )
        if isinstance(virtual_account, dict):
            for marking in markings_to_update:
                marking.payment_reference = reference
                marking.payment_method = PaymentMethod.BANK_TRANSFER
                marking.status = SavingsStatus.PENDING
                # Optionally store virtual_account details
            db.commit()

            return success_response(
                status_code=200,
                message="Pay to the virtual account",
                data=SavingsMarkingResponse(
                    tracking_number="group_" + str(group_id),
                    unit_id=None,
                    savings_schedule={},
                    total_amount=float(total_amount),
                    authorization_url=None,
                    payment_reference=reference,
                    virtual_account=virtual_account
                ).model_dump()
            )
        else:
            raise HTTPException(500, "Failed to generate virtual account")

    raise HTTPException(400, "Invalid payment method")


async def verify_group_marking_payment(reference: str, db: Session):
    """
    Verify Paystack payment for group markings (replicates verify_savings_payment)
    """
    markings = db.query(SavingsMarking).filter(
        SavingsMarking.payment_reference == reference
    ).all()
    if not markings:
        raise HTTPException(404, "Payment reference not found")

    # Assume all markings belong to same group
    group_id = markings[0].savings_account.group_id

    resp = Transaction.verify(reference=reference)
    if not resp["status"] or resp["data"]["status"] != "success":
        raise HTTPException(400, "Payment not successful")

    paid_amount = Decimal(resp["data"]["amount"]) / 100
    expected = sum(m.amount for m in markings)
    if paid_amount < expected:
        raise HTTPException(400, f"Underpayment: {paid_amount} < {expected}")

    # Mark all as paid
    for marking in markings:
        marking.status = SavingsStatus.PAID
        marking.marked_by_id = marking.updated_by
        marking.updated_at = datetime.utcnow()

    db.commit()

    return success_response(
        status_code=200,
        message=f"Marked {len(markings)} contributions as paid",
        data={
            "reference": reference,
            "status": "PAID",
            "paid_amount": float(paid_amount)
        }
    )