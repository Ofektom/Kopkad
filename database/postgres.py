from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, registry
from sqlalchemy.ext.declarative import declarative_base
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = settings.POSTGRES_URI
logger.info(f"Application connecting to database: {DATABASE_URL}")

# Create engine with optimized settings
engine = create_engine(
    DATABASE_URL, 
    echo=True,
    # Prevent set_session errors by disabling automatic connection characteristics
    connect_args={
        "options": "-c default_transaction_read_only=off"
    }
    # Note: Don't set isolation_level here as it causes "set_session cannot be used inside a transaction" errors
)

SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False  # Prevent detached instance issues
)

mapper_registry = registry()
Base = mapper_registry.generate_base()

def configure_mappers():
    """Configure SQLAlchemy mappers dynamically to avoid circular imports."""
    from models.user import User
    from models.business import Business, Unit, PendingBusinessRequest
    from models.savings import SavingsAccount, SavingsMarking
    from models.audit import AuditMixin
    from models.settings import Settings

    mapper_registry.configure()
    logger.info("Mappers configured successfully.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    configure_mappers()
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized with tables")