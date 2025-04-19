from models.business import Business
from models.savings import SavingsAccount, SavingsMarking
from models.audit import AuditMixin
from models.settings import Settings

db_models = [Business, SavingsAccount, SavingsMarking, AuditMixin, Settings]
