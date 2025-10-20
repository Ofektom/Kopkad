"""
Optimized PostgreSQL Database Configuration
Includes connection pooling, query optimization, and performance tuning
"""

from sqlalchemy import create_engine, event, pool
from sqlalchemy.orm import sessionmaker, registry
from sqlalchemy.ext.declarative import declarative_base
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = settings.POSTGRES_URI
logger.info(f"Application connecting to database: {DATABASE_URL}")

# Optimized engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    # Connection Pool Settings
    poolclass=pool.QueuePool,  # Use QueuePool for better performance
    pool_size=20,  # Number of connections to keep in pool
    max_overflow=30,  # Additional connections allowed beyond pool_size
    pool_timeout=30,  # Seconds to wait for connection from pool
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_pre_ping=True,  # Test connections before using them
    
    # Query Execution Settings
    echo=False,  # Disable SQL logging in production for performance
    echo_pool=False,  # Disable connection pool logging
    
    # Performance Settings
    connect_args={
        'connect_timeout': 10,  # Connection timeout in seconds
        'keepalives': 1,  # Enable TCP keepalives
        'keepalives_idle': 30,  # Seconds before starting keepalives
        'keepalives_interval': 10,  # Seconds between keepalive probes
        'keepalives_count': 5,  # Number of keepalives before closing
    },
    
    # Execution options for better query performance
    execution_options={
        'isolation_level': 'READ COMMITTED',  # Faster than SERIALIZABLE
        'postgresql_readonly': False,
        'postgresql_deferrable': False,
    }
)

# Configure session maker with optimized settings
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,  # Manual flush for better control
    bind=engine,
    expire_on_commit=False,  # Don't expire objects after commit
)

mapper_registry = registry()
Base = mapper_registry.generate_base()


# Event listeners for connection optimization
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """
    Optimize connection settings when connection is established
    """
    try:
        # Set PostgreSQL-specific performance parameters
        cursor = dbapi_conn.cursor()
        
        # Increase work memory for complex queries
        cursor.execute("SET work_mem = '16MB'")
        
        # Optimize planner settings
        cursor.execute("SET random_page_cost = 1.1")  # For SSD drives
        cursor.execute("SET effective_cache_size = '4GB'")
        
        # Enable parallel query execution
        cursor.execute("SET max_parallel_workers_per_gather = 2")
        
        cursor.close()
        logger.debug("Connection optimized with performance parameters")
    except Exception as e:
        logger.warning(f"Failed to set connection parameters: {e}")


@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_conn, connection_record):
    """
    Clean up connection when returned to pool
    """
    try:
        dbapi_conn.rollback()  # Rollback any uncommitted transactions
    except Exception as e:
        logger.error(f"Error during connection checkin: {e}")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """
    Verify connection health when checked out from pool
    """
    try:
        # Quick ping to ensure connection is alive
        cursor = dbapi_conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
    except Exception as e:
        logger.error(f"Connection health check failed: {e}")
        raise


def configure_mappers():
    """Configure SQLAlchemy mappers dynamically to avoid circular imports."""
    from models.user import User
    from models.business import Business, Unit, PendingBusinessRequest
    from models.savings import SavingsAccount, SavingsMarking
    from models.audit import AuditMixin
    from models.settings import Settings
    from models.payments import PaymentAccount, AccountDetails, PaymentRequest, Commission
    from models.expenses import ExpenseCard, Expense

    mapper_registry.configure()
    logger.info("Mappers configured successfully.")


def get_db():
    """
    Dependency for getting database sessions with automatic cleanup
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Initialize database with tables"""
    configure_mappers()
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized with tables")


def get_connection_pool_status():
    """
    Get current connection pool status for monitoring
    
    Returns:
        dict: Pool statistics
    """
    try:
        pool_obj = engine.pool
        return {
            'size': pool_obj.size(),
            'checked_in': pool_obj.checkedin(),
            'checked_out': pool_obj.checkedout(),
            'overflow': pool_obj.overflow(),
            'total_connections': pool_obj.size() + pool_obj.overflow(),
        }
    except Exception as e:
        logger.error(f"Error getting pool status: {e}")
        return {}


def close_all_connections():
    """Close all database connections (for shutdown)"""
    try:
        engine.dispose()
        logger.info("All database connections closed")
    except Exception as e:
        logger.error(f"Error closing connections: {e}")


# Health check function
def check_database_health() -> dict:
    """
    Check database health and return status
    
    Returns:
        dict: Database health status
    """
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # Test query
            result = conn.execute(text("SELECT current_database(), version()"))
            db_name, version = result.fetchone()
            
            # Get connection pool stats
            pool_status = get_connection_pool_status()
            
            return {
                'status': 'healthy',
                'database': db_name,
                'version': version.split()[0:2],  # PostgreSQL version
                'pool': pool_status,
            }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e)
        }

