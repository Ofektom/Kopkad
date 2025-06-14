def get_db_models():
    """
    Dynamically import models to avoid circular imports.
    Returns list of SQLAlchemy models for registration or other purposes.
    """
    from models.user import User
    from models.business import Business, Unit, PendingBusinessRequest
    from models.savings import SavingsAccount, SavingsMarking
    from models.audit import AuditMixin
    from models.settings import Settings
    from models.user_business import user_business
    from models.token import TokenBlocklist


    return [
        User,
        Business,
        Unit,
        PendingBusinessRequest,
        SavingsAccount,
        SavingsMarking,
        AuditMixin,
        Settings,
        user_business,
        TokenBlocklist,
    ]