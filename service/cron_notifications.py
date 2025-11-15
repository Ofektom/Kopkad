import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.savings import (
    SavingsAccount,
    SavingsMarking,
    MarkingStatus,
    SavingsStatus,
)
from models.payments import PaymentRequest, PaymentRequestStatus, Commission
from models.user import User, Role
from models.business import Business
from models.expenses import ExpenseCard, CardStatus
from models.financial_advisor import NotificationType, NotificationPriority

from service.notifications import (
    notify_user,
    notify_business_admin,
    notify_super_admins,
)
from store.repositories import UserNotificationRepository, UserRepository

logger = logging.getLogger(__name__)


async def send_savings_nearing_completion_notifications(db: Session) -> int:
    """Notify customers 7 days before their savings account completion date."""
    target_date = date.today() + timedelta(days=7)
    accounts = (
        db.query(SavingsAccount)
        .filter(
            SavingsAccount.end_date == target_date,
            SavingsAccount.marking_status != MarkingStatus.COMPLETED,
        )
        .all()
    )

    if not accounts:
        return 0

    notification_repo = UserNotificationRepository(db)
    sent = 0

    for account in accounts:
        await notify_user(
            user_id=account.customer_id,
            notification_type=NotificationType.SAVINGS_NEARING_COMPLETION,
            title="Savings Account Almost Complete",
            message=(
                f"Your savings account {account.tracking_number} "
                f"will complete in 7 days."
            ),
            priority=NotificationPriority.MEDIUM,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=account.id,
            related_entity_type="savings_account",
        )
        sent += 1

    logger.info("Sent %s savings nearing completion notifications", sent)
    return sent


async def send_savings_completion_reminders(db: Session) -> int:
    """Notify customers 3 days before their savings account completion date."""
    target_date = date.today() + timedelta(days=3)
    accounts = (
        db.query(SavingsAccount)
        .filter(
            SavingsAccount.end_date == target_date,
            SavingsAccount.marking_status != MarkingStatus.COMPLETED,
        )
        .all()
    )

    if not accounts:
        return 0

    notification_repo = UserNotificationRepository(db)
    sent = 0

    for account in accounts:
        await notify_user(
            user_id=account.customer_id,
            notification_type=NotificationType.SAVINGS_COMPLETION_REMINDER,
            title="Savings Completion Reminder",
            message=(
                f"Your savings account {account.tracking_number} "
                f"completes in 3 days. Keep up the great work!"
            ),
            priority=NotificationPriority.MEDIUM,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=account.id,
            related_entity_type="savings_account",
        )
        sent += 1

    logger.info("Sent %s savings completion reminders", sent)
    return sent


async def send_payment_request_reminders(db: Session) -> int:
    """Notify business admins about pending payment requests older than 24 hours."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    pending_requests = (
        db.query(PaymentRequest)
        .filter(
            PaymentRequest.status == PaymentRequestStatus.PENDING,
            PaymentRequest.request_date <= threshold,
        )
        .all()
    )

    if not pending_requests:
        return 0

    notification_repo = UserNotificationRepository(db)
    sent = 0

    for request in pending_requests:
        if request.savings_account and request.savings_account.business_id:
            await notify_business_admin(
                business_id=request.savings_account.business_id,
                notification_type=NotificationType.PAYMENT_REQUEST_REMINDER,
                title="Pending Payment Requests",
                message=(
                    f"You have a pending payment request ({request.reference}) "
                    f"for {request.amount:.2f} awaiting review."
                ),
                priority=NotificationPriority.MEDIUM,
                db=db,
                notification_repo=notification_repo,
            )
            sent += 1

    logger.info("Sent %s payment request reminders", sent)
    return sent


async def send_savings_payment_overdue_notifications(db: Session) -> int:
    """Notify customers and agents about overdue savings markings."""
    overdue_markings = (
        db.query(SavingsMarking)
        .filter(
            SavingsMarking.status == SavingsStatus.PENDING,
            SavingsMarking.marked_date < date.today(),
        )
        .all()
    )

    if not overdue_markings:
        return 0

    notification_repo = UserNotificationRepository(db)
    sent = 0
    processed_accounts: set[int] = set()

    for marking in overdue_markings:
        account = marking.savings_account
        if not account or account.id in processed_accounts:
            continue

        processed_accounts.add(account.id)

        # Notify customer
        await notify_user(
            user_id=account.customer_id,
            notification_type=NotificationType.SAVINGS_PAYMENT_OVERDUE,
            title="Savings Payment Overdue",
            message=(
                f"You have overdue payments for savings account "
                f"{account.tracking_number}."
            ),
            priority=NotificationPriority.HIGH,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=account.id,
            related_entity_type="savings_account",
        )
        sent += 1

        # Notify agent / business owner
        business = db.query(Business).filter(Business.id == account.business_id).first()
        if business and business.agent_id:
            await notify_user(
                user_id=business.agent_id,
                notification_type=NotificationType.SAVINGS_PAYMENT_OVERDUE,
                title="Customer Payment Overdue",
                message=(
                    f"Savings account {account.tracking_number} has overdue payments."
                ),
                priority=NotificationPriority.HIGH,
                db=db,
                notification_repo=notification_repo,
                related_entity_id=account.id,
                related_entity_type="savings_account",
            )

    logger.info("Sent %s savings payment overdue notifications", sent)
    return sent


async def send_inactive_user_reminders(db: Session) -> int:
    """Notify users who have been inactive for 30 days."""
    threshold = datetime.now(timezone.utc) - timedelta(days=30)
    inactive_users = (
        db.query(User)
        .filter(
            User.role == Role.CUSTOMER,
            User.is_active.is_(True),
            User.updated_at != None,  # noqa: E711
            User.updated_at <= threshold,
        )
        .all()
    )

    if not inactive_users:
        return 0

    notification_repo = UserNotificationRepository(db)
    sent = 0

    for user in inactive_users:
        await notify_user(
            user_id=user.id,
            notification_type=NotificationType.INACTIVE_USER_REMINDER,
            title="We Miss You",
            message=(
                "We haven't seen you in a while. Come back and continue your "
                "savings journey!"
            ),
            priority=NotificationPriority.LOW,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=user.id,
            related_entity_type="user",
        )
        sent += 1

    logger.info("Sent %s inactive user reminders", sent)
    return sent


async def send_business_without_admin_alerts(db: Session) -> int:
    """Alert when businesses lack admins for more than 7 days."""
    threshold = datetime.now(timezone.utc) - timedelta(days=7)
    businesses = (
        db.query(Business)
        .filter(
            Business.admin_id.is_(None),
            Business.created_at <= threshold,
        )
        .all()
    )

    if not businesses:
        return 0

    notification_repo = UserNotificationRepository(db)
    user_repo = UserRepository(db)
    sent = 0

    for business in businesses:
        message = (
            f"Business '{business.name}' has been without an admin for 7+ days."
        )
        # Notify super admins
        await notify_super_admins(
            notification_type=NotificationType.BUSINESS_WITHOUT_ADMIN,
            title="Business Without Admin",
            message=message,
            priority=NotificationPriority.HIGH,
            db=db,
            user_repo=user_repo,
            notification_repo=notification_repo,
            related_entity_id=business.id,
            related_entity_type="business",
        )
        # Notify agent
        if business.agent_id:
            await notify_user(
                user_id=business.agent_id,
                notification_type=NotificationType.BUSINESS_WITHOUT_ADMIN,
                title="Assign Business Admin",
                message=message,
                priority=NotificationPriority.HIGH,
                db=db,
                notification_repo=notification_repo,
                related_entity_id=business.id,
                related_entity_type="business",
            )
        sent += 1

    logger.info("Sent %s business without admin alerts", sent)
    return sent


async def send_low_balance_alerts(db: Session) -> int:
    """Notify admins when expense card balances fall below threshold."""
    cards = (
        db.query(ExpenseCard)
        .filter(
            ExpenseCard.status == CardStatus.ACTIVE,
            ExpenseCard.balance <= (ExpenseCard.income_amount * Decimal("0.1")),
        )
        .all()
    )

    if not cards:
        return 0

    notification_repo = UserNotificationRepository(db)
    sent = 0

    for card in cards:
        if not card.business_id:
            continue
        await notify_business_admin(
            business_id=card.business_id,
            notification_type=NotificationType.LOW_BALANCE_ALERT,
            title="Low Balance Alert",
            message=(
                f"Expense card '{card.name}' has a low balance of {card.balance:.2f}."
            ),
            priority=NotificationPriority.HIGH,
            db=db,
            notification_repo=notification_repo,
            related_entity_id=card.id,
            related_entity_type="expense_card",
        )
        sent += 1

    logger.info("Sent %s low balance alerts", sent)
    return sent


async def send_daily_system_summary(db: Session) -> int:
    """Send a daily system summary to super admins."""
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_savings = (
        db.query(func.count(SavingsAccount.id))
        .filter(SavingsAccount.marking_status != MarkingStatus.COMPLETED)
        .scalar()
        or 0
    )
    pending_payments = (
        db.query(func.count(PaymentRequest.id))
        .filter(PaymentRequest.status == PaymentRequestStatus.PENDING)
        .scalar()
        or 0
    )

    message = (
        f"Users: {total_users}\n"
        f"Active savings accounts: {active_savings}\n"
        f"Pending payment requests: {pending_payments}"
    )

    notification_repo = UserNotificationRepository(db)
    user_repo = UserRepository(db)

    await notify_super_admins(
        notification_type=NotificationType.SYSTEM_SUMMARY,
        title="Daily System Summary",
        message=message,
        priority=NotificationPriority.LOW,
        db=db,
        user_repo=user_repo,
        notification_repo=notification_repo,
    )

    logger.info("Sent daily system summary")
    return 1


async def send_weekly_analytics_report(db: Session) -> int:
    """Send a weekly analytics snapshot to super admins."""
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    new_users = (
        db.query(func.count(User.id))
        .filter(User.created_at >= seven_days_ago)
        .scalar()
        or 0
    )
    new_savings = (
        db.query(func.count(SavingsAccount.id))
        .filter(SavingsAccount.created_at >= seven_days_ago)
        .scalar()
        or 0
    )
    payments_processed = (
        db.query(func.count(PaymentRequest.id))
        .filter(PaymentRequest.approval_date != None)  # noqa: E711
        .filter(PaymentRequest.approval_date >= seven_days_ago)
        .scalar()
        or 0
    )

    message = (
        f"Weekly recap:\n"
        f"- New users: {new_users}\n"
        f"- New savings accounts: {new_savings}\n"
        f"- Payments processed: {payments_processed}"
    )

    notification_repo = UserNotificationRepository(db)
    user_repo = UserRepository(db)

    await notify_super_admins(
        notification_type=NotificationType.WEEKLY_ANALYTICS,
        title="Weekly Analytics Report",
        message=message,
        priority=NotificationPriority.LOW,
        db=db,
        user_repo=user_repo,
        notification_repo=notification_repo,
    )

    logger.info("Sent weekly analytics report")
    return 1

